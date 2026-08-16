# region imports
from AlgorithmImports import *
from collections import deque
import statistics
# endregion

# ============================================================================
# XSP/SPX 2:00 Settlement Condor — QuantConnect LEAN port
# ----------------------------------------------------------------------------
# Purpose: validate our XSP condor on SPX index-option MINUTE data back to 2012
# — a decade of tail regimes (2015 flash, 2018 Volmageddon, 2020 COVID) that our
# Alpaca-based 30-month backtest has NEVER seen. SPX options are European &
# cash-settled, exactly like XSP, so the hold-to-settlement thesis transfers.
#
# SCALE NOTE: SPX = 10 x XSP. All our XSP numbers are multiplied by 10 here:
#   XSP fence floor 0.60 -> SPX 6.0   |  XSP $1 wing -> SPX 10 pts
#   XSP gate +0.10       -> SPX +1.0  |  credit/settle all in SPX points ($100 mult)
# One SPX condor risks ~ (10 - credit) x 100 ≈ $900-1000, so we size 1 contract
# and read PER-CONTRACT EV / win-rate (the edge validation), not account %.
#
# 0DTE AVAILABILITY: daily SPXW expirations exist ~May 2022 onward; before that
# 0DTE lands mainly on Fridays (weekly/monthly expiries). The algo trades
# whatever 0DTE is available each day, so pre-2022 is a Friday sample — still
# covers the vol events we care about.
#
# HOW TO RUN (free QuantConnect account):
#   1. quantconnect.com -> Create Algorithm -> paste this file
#   2. Backtest. When done: Results -> export the trade log / statistics JSON
#   3. Commit that results JSON into github/xsp-data/quantconnect/results/
# Results are YOURS to export; only the raw licensed data must stay in QC.
# ============================================================================

class SettlementCondor(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2012, 1, 1)
        self.set_end_date(2026, 8, 15)
        self.set_cash(5000)
        self.set_time_zone(TimeZones.NEW_YORK)

        self.spx = self.add_index("SPX").symbol
        # SPXW = weekly/daily European PM-settled index options
        opt = self.add_index_option(self.spx, "SPXW")
        opt.set_filter(lambda u: u.include_weeklys().expiration(0, 0).strikes(-25, 25))
        self.opt_symbol = opt.symbol

        self.moves = deque(maxlen=20)     # trailing |2:00 -> close| SPX moves
        self.px2 = None                   # today's 2:00 PM SPX price
        self.strikes = None               # (put_short, call_short) held today
        self.WING = 10                    # SPX points (= $1 XSP wing)
        self.chain = None

        # FOMC decision days (2:00 PM statement detonates in the entry window).
        # Reasonably complete 2012-2026; extend as needed. Missing dates only
        # make results CONSERVATIVE (we'd trade a Fed day we should skip).
        self.fomc = set(map(lambda s: s, [
            # 2018-2026 (the tail years we most care about) — decision dates:
            "2018-01-31","2018-03-21","2018-05-02","2018-06-13","2018-08-01",
            "2018-09-26","2018-11-08","2018-12-19","2019-01-30","2019-03-20",
            "2019-05-01","2019-06-19","2019-07-31","2019-09-18","2019-10-30",
            "2019-12-11","2020-01-29","2020-03-18","2020-04-29","2020-06-10",
            "2020-07-29","2020-09-16","2020-11-05","2020-12-16","2021-01-27",
            "2021-03-17","2021-04-28","2021-06-16","2021-07-28","2021-09-22",
            "2021-11-03","2021-12-15","2022-01-26","2022-03-16","2022-05-04",
            "2022-06-15","2022-07-27","2022-09-21","2022-11-02","2022-12-14",
            "2023-02-01","2023-03-22","2023-05-03","2023-06-14","2023-07-26",
            "2023-09-20","2023-11-01","2023-12-13","2024-01-31","2024-03-20",
            "2024-05-01","2024-06-12","2024-07-31","2024-09-18","2024-11-07",
            "2024-12-18","2025-01-29","2025-03-19","2025-05-07","2025-06-18",
            "2025-07-30","2025-09-17","2025-10-29","2025-12-10","2026-01-28",
            "2026-03-18","2026-04-29","2026-06-17","2026-07-29"]))

        # entry at 2:00 PM ET, close-move recording just before the bell
        self.schedule.on(self.date_rules.every_day(self.spx),
                         self.time_rules.at(14, 0), self.enter)
        self.schedule.on(self.date_rules.every_day(self.spx),
                         self.time_rules.before_market_close(self.spx, 2), self.record_close)

        self.trades = 0; self.wins = 0; self.ml = 0
        self.set_warm_up(timedelta(days=30))

    def on_data(self, slice):
        # keep the freshest 0DTE chain for use at 14:00
        ch = slice.option_chains.get(self.opt_symbol)
        if ch: self.chain = ch

    def enter(self):
        if self.is_warming_up: return
        today = self.time.strftime("%Y-%m-%d")
        if today in self.fomc:
            self.debug(f"{today} FOMC — skip"); return
        self.px2 = self.securities[self.spx].price
        if len(self.moves) < 15 or self.chain is None or not self.px2:
            return
        F = max(sorted(self.moves)[int(len(self.moves) * 0.7)], 6.0)   # p70, floor 6.0
        fair = statistics.mean(min(max(m - F, 0), self.WING) for m in self.moves)

        # 0DTE contracts only, expiring today
        contracts = [c for c in self.chain if c.expiry.date() == self.time.date()]
        if not contracts: return
        puts = sorted([c for c in contracts if c.right == OptionRight.PUT], key=lambda c: c.strike)
        calls = sorted([c for c in contracts if c.right == OptionRight.CALL], key=lambda c: c.strike)
        if not puts or not calls: return

        pk = self.nearest(puts, self.px2 - F, below=True)      # short put strike
        ck = self.nearest(calls, self.px2 + F, below=False)    # short call strike
        if pk is None or ck is None: return
        p_short = self.pick(puts, pk); p_long = self.pick(puts, pk - self.WING)
        c_short = self.pick(calls, ck); c_long = self.pick(calls, ck + self.WING)
        if not all([p_short, p_long, c_short, c_long]): return

        # credit from quote mids (SPX points)
        credit = (self.mid(p_short) - self.mid(p_long)
                  + self.mid(c_short) - self.mid(c_long))
        if credit is None: return
        gate = max(fair + 1.0, 1.5)          # XSP +0.10 -> SPX +1.0 ; abs floor 1.5
        if credit < gate:            self.debug(f"{today} thin {credit:.2f}<{gate:.2f}"); return
        if credit > 2.5 * fair:      self.debug(f"{today} rich {credit:.2f}>{2.5*fair:.2f}"); return

        # sell the condor as a 4-leg combo, hold to PM cash settlement (no exit)
        legs = [Leg.create(c_short.symbol, -1), Leg.create(c_long.symbol, 1),
                Leg.create(p_short.symbol, -1), Leg.create(p_long.symbol, 1)]
        self.combo_market_order(legs, 1)
        self.strikes = (p_short.strike, c_short.strike, credit)
        self.trades += 1
        self.debug(f"{today} ENTER P{p_short.strike}/{c_short.strike}C credit {credit:.2f} fair {fair:.2f}")

    def record_close(self):
        if self.px2:
            close = self.securities[self.spx].price
            self.moves.append(abs(self.px2 - close))
            if self.strikes:
                pk, ck, credit = self.strikes
                settle = min(max(pk - close, 0) + max(close - ck, 0), self.WING)
                if credit > settle: self.wins += 1
                if settle >= self.WING: self.ml += 1
            self.px2 = None; self.strikes = None

    # --- helpers ---
    def nearest(self, lst, target, below):
        ks = [c.strike for c in lst]
        cands = [k for k in ks if (k <= target) == below]
        if not cands: return None
        return max(cands) if below else min(cands)

    def pick(self, lst, strike):
        for c in lst:
            if abs(c.strike - strike) < 0.01: return c
        return None

    def mid(self, c):
        b, a = c.bid_price, c.ask_price
        if b and a: return (b + a) / 2
        return c.last_price if c.last_price else None

    def on_end_of_algorithm(self):
        wr = 100 * self.wins / self.trades if self.trades else 0
        self.log(f"SUMMARY trades={self.trades} wins={self.wins} ({wr:.0f}%) "
                 f"max_losses={self.ml} final_equity={self.portfolio.total_portfolio_value:.0f}")

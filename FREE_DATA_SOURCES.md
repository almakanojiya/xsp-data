# Free / cheap historical options data — research 2026-08-16

## The problem
Historical intraday option QUOTES (NBBO) on SPX/XSP are the single most
paywalled data type. Our own 24/7 backfill (backfill.py) solves the TRADES/BARS
side for free; quotes remain the gap. Options if we ever revisit budget:

## Best FREE
- **QuantConnect free cloud tier** — real minute SPX/SPXW trades+quotes back to
  2012, $0, but only usable inside their LEAN engine (no raw export). Strongest
  free path if we port the backtest there.
- **optionsDX free EOD** — downloadable SPX chains 2010-2023 with bid/ask+Greeks,
  $0, but EOD-only (daily-mark entries).
- **Alpaca historical option BARS/TRADES** — what our backfill uses; free; XSP;
  from Mar 2024. NO historical quotes (derived-quote real feed = $99/mo).
- **CBOE free delayed JSON** (_SPX/_XSP) — full chain+Greeks, 15-min delayed,
  snapshot only; value is cron-archiving forward (our harvest.py already does the
  XSP equivalent via Tradier+Alpaca).

## Best CHEAP-PAID (only if budget ever opens)
- **ThetaData Value $40/mo** — 1-min NBBO quotes+trades+Greeks on SPX/XSP/SPY
  back to Jan 2020. The one sub-$80 source of intraday index-option quotes.
- **Databento** — usage-based, $125 free credits; SPX+XSP cbbo-1m (1-min NBBO)
  back to 2013; run metadata.get_cost first — a targeted 1-yr XSP pull may be free.
- **CBOE DataShop** — one-time $550 for a year of ^SPX 1-min NBBO (no subscription).

## Dead / useless for us
IEX Cloud (shut down 2024), Tradier (no expired-option history), yfinance
(snapshot only, 429s), Finnhub/TwelveData/Marketstack/FMP (no or snapshot-only
options), DoltHub (SPX returns zero rows). Polygon = now "Massive"; historical
quotes still gated at $199/mo.

## Verdict for $0 budget
Our self-built archive (backfill.py trades/bars + harvest.py forward quotes) is
the right call. If we ever want a true historical-NBBO rebuild: ThetaData $40 for
one month, bulk-pull, cancel. Until then the archive grows for free.

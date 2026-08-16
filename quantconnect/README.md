# QuantConnect validation — SPX condor back to 2012

`condor_lean.py` ports the XSP 2:00 Settlement Condor to QuantConnect's LEAN
engine so we can validate it on **SPX index-option minute data back to 2012** —
a decade of tail regimes (2015 flash crash, Feb-2018 Volmageddon, Mar-2020 COVID)
that our Alpaca 30-month backtest has never seen. SPX options are European &
cash-settled exactly like XSP, so the hold-to-settlement edge transfers.

## Run it (free, ~10 min)
1. Sign up at quantconnect.com (free, no card).
2. Create Algorithm -> New -> paste `condor_lean.py`.
3. Click **Backtest**. It runs on QC's servers using their licensed data.
4. When done: open **Results**, export the **Orders** + **Statistics** (JSON/CSV).
5. Commit those exports into `quantconnect/results/` here. (Results are yours to
   export; only the raw licensed data must stay inside QC — which is why we send
   the strategy IN rather than pulling data OUT.)

## What it does (faithful to the live strategy)
- Fence = trailing-20-day p70 of |2:00->close| SPX move, floor 6.0 (=0.60 XSP x10)
- Short strikes just beyond the fence, 10-pt wings (=$1 XSP wing)
- Gate 5c: credit in [fair+1.0, 2.5x fair], FOMC decision days skipped
- Sells the 4-leg combo at 2:00 PM, **holds to PM cash settlement, never exits**
- 1 contract/trade -> read per-contract EV & win rate (SPX=10x XSP notional)

## Verify-points (things to confirm in QC, may need a tweak)
- SPXW 0DTE availability pre-2022 (daily expiries began ~May 2022; earlier =
  mostly Friday 0DTE — still covers the crash days).
- Exact combo-order API / OptionRight enums if LEAN version differs.
- QC's option fill model prices at quote — MORE realistic than our print-based
  fills, so a positive result here is strong independent evidence.

## Why this matters
If the condor is still positive through 2015/2018/2020 on real SPX quotes, that's
the tail-regime validation every council seat said we were missing. If it blows
up in those years, we learn the strategy's true worst-case before risking a dollar
— which is exactly the point.

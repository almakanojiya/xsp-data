# xsp-data — continuous free option-data harvester

Historical option **quotes** (bid/ask) are paywalled at every provider. This repo
solves that the only free way: it **accumulates its own history**. A GitHub Actions
job runs every ~10 minutes during US market hours and appends a full XSP option-chain
snapshot to `data/YYYY-MM-DD.jsonl` — every snapshot captured today is owned
historical data tomorrow.

## Each snapshot (`data/*.jsonl`, one JSON object per line)
- `ts_et` / `ts_utc` — capture time
- `spot` — SPY bid/ask/last/mid (Alpaca); XSP ≈ SPY × ~1.003
- `chains` — 0DTE and 1DTE XSP strikes within ±$10 of spot, each with:
  - **Source 1 (Tradier):** `t_bid t_ask t_last vol oi iv delta gamma`
  - **Source 2 (Alpaca):** `a_bid a_ask a_print`
  - two independent NBBO sources per contract = built-in cross-check + the
    print-vs-quote calibration the strategy needs.

## Cost
Stdlib only, no pip. ~54 short runs/weekday (many exit instantly off-hours) ≈
~1,100 Actions min/month — inside the free private-repo budget. Off-hours the
script idles (no quotes exist to capture). For unbounded density, flip the repo
public (unlimited Actions minutes; the data is public market quotes anyway).

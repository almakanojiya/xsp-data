#!/usr/bin/env python3
"""XSP historical backfill — the TRUE 24/7 job. Historical option bars are free
on Alpaca and don't change, so this runs round-the-clock (nights, weekends) and
methodically archives the full near-money XSP option chain (1-min bars) at our
entry and settlement windows for every 0DTE trading day from Feb 2024 to present.
Checkpointed: each run processes a batch, commits, exits; resumes next run;
idles once caught up to today. Stdlib only."""
import json, os, sys, time, math, datetime, urllib.request, urllib.parse
ALP_ID=os.environ.get("ALPACA_KEY_ID",""); ALP_SEC=os.environ.get("ALPACA_SECRET","")
AH={"APCA-API-KEY-ID":ALP_ID,"APCA-API-SECRET-KEY":ALP_SEC}
BUDGET_S=230        # stop and commit before the 5-min Actions timeout
def log(m): print(m, flush=True)
def get(u,tries=3):
    for a in range(tries):
        try: return json.loads(urllib.request.urlopen(
            urllib.request.Request(u,headers=AH),timeout=25).read())
        except Exception as e:
            if a==tries-1: log(f"GET fail: {e}"); return {}
            time.sleep(2*(a+1))
def edt(d):
    mth=int(d[5:7]); dy=int(d[8:10])
    return (3<mth<11) or (mth==3 and dy>=10) or (mth==11 and dy<=3)
def occ(e,cp,k): return f"XSP{e}{cp}{int(k*1000):08d}"

def calendar():
    """Trading days from SPY daily bars (holidays auto-excluded)."""
    days=[]; token=None
    while True:
        u=("https://data.alpaca.markets/v2/stocks/SPY/bars?"+urllib.parse.urlencode(
            {"timeframe":"1Day","start":"2024-02-01","limit":10000,"adjustment":"raw"})
           +((f"&page_token={token}") if token else ""))
        r=get(u); days+=[(b["t"][:10],float(b["c"])) for b in (r.get("bars") or [])]
        token=r.get("next_page_token")
        if not token: break
    return days

def spot_at(d,off):
    u=("https://data.alpaca.markets/v2/stocks/SPY/bars?"+urllib.parse.urlencode(
        {"timeframe":"5Min","start":d+f"T{13+off}:55:00Z","end":d+f"T{14+off}:05:00Z",
         "limit":3,"adjustment":"raw"}))
    b=(get(u).get("bars") or [])
    return float(b[0]["o"]) if b else None

def window_bars(d,off,syms,h1,m1,h2,m2):
    out={}
    for i in range(0,len(syms),25):
        u=("https://data.alpaca.markets/v1beta1/options/bars?"+urllib.parse.urlencode(
            {"symbols":",".join(syms[i:i+25]),"timeframe":"1Min",
             "start":d+f"T{h1+off:02d}:{m1:02d}:00Z","end":d+f"T{h2+off:02d}:{m2:02d}:00Z","limit":1000}))
        for s,bars in (get(u).get("bars") or {}).items():
            out[s]=[[b["t"][11:16],round(b["c"],2),b.get("v",0)] for b in bars]
    return out

def process(d,ratio):
    off=4 if edt(d) else 5
    s=spot_at(d,off)
    if not s: return None
    center=round(s*ratio)
    e=d.replace("-","")[2:]
    syms=[occ(e,cp,k) for k in range(center-8,center+9) for cp in ("P","C")]
    entry=window_bars(d,off,syms,13,45,14,25)     # 1:45-2:25pm ET (entry window)
    settle=window_bars(d,off,syms,15,25,16,10)     # 3:25-4:10pm ET (settle window)
    if not entry and not settle: return None
    return {"d":d,"center":center,"off":off,"entry":entry,"settle":settle}

def main():
    if not ALP_ID: log("no ALPACA_KEY_ID"); sys.exit(1)
    os.makedirs("history",exist_ok=True); os.makedirs("state",exist_ok=True)
    cal=calendar()
    if not cal: log("no calendar"); return
    dates=[d for d,_ in cal]
    ck=json.load(open("state/backfill.json")) if os.path.exists("state/backfill.json") else {"cursor":dates[0]}
    cursor=ck.get("cursor",dates[0])
    todo=[d for d in dates if d>=cursor and not os.path.exists(f"history/{d}.jsonl")]
    if not todo:
        log(f"caught up — archive complete through {dates[-1]} ({len([d for d in dates if os.path.exists(f'history/{d}.jsonl')])} days on disk)")
        return
    t0=time.monotonic(); done=0
    for d in todo:
        if time.monotonic()-t0>BUDGET_S: break
        rec=process(d,1.003)
        if rec:
            nb=sum(len(v) for v in rec["entry"].values())+sum(len(v) for v in rec["settle"].values())
            with open(f"history/{d}.jsonl","w") as fh: fh.write(json.dumps(rec)+"\n")
            log(f"archived {d}: {nb} bars, {len(rec['entry'])+len(rec['settle'])} contracts")
        else:
            with open(f"history/{d}.jsonl","w") as fh: fh.write(json.dumps({"d":d,"empty":True})+"\n")
            log(f"{d}: no data (holiday/early-close) — marked")
        done+=1
        json.dump({"cursor":d,"updated":datetime.datetime.now(datetime.timezone.utc).isoformat()},
                  open("state/backfill.json","w"))
    remaining=len([d for d in dates if d>cursor and not os.path.exists(f"history/{d}.jsonl")])
    log(f"batch done: {done} days this run, ~{remaining} remaining")

if __name__=="__main__": main()

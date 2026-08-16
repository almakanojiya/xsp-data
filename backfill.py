#!/usr/bin/env python3
"""XSP historical backfill — the TRUE 24/7 job. Historical option bars are free
on Alpaca and don't change, so this runs round-the-clock and archives AS MUCH AS
POSSIBLE: the full near-money XSP option chain (1-min bars, ±12 strikes) across
the WHOLE regular session (9:30-16:15 ET) plus the underlying SPY 1-min bars, for
every 0DTE trading day from the start of Alpaca's coverage to present. This lets
us backtest any entry time, any fence, and every alternative strategy on real
data. Checkpointed + schema-versioned; upgrades older thin files in place. Stdlib only."""
import json, os, sys, time, datetime, urllib.request, urllib.parse
ALP_ID=os.environ.get("ALPACA_KEY_ID",""); ALP_SEC=os.environ.get("ALPACA_SECRET","")
AH={"APCA-API-KEY-ID":ALP_ID,"APCA-API-SECRET-KEY":ALP_SEC}
VER=2               # schema version; files with v<VER get re-archived richer
STRIKES=12          # +/- strikes around 2:00 spot
BUDGET_S=250        # stop and commit before the 6-min Actions timeout
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
    days=[]; token=None
    while True:
        u=("https://data.alpaca.markets/v2/stocks/SPY/bars?"+urllib.parse.urlencode(
            {"timeframe":"1Day","start":"2024-02-01","limit":10000,"adjustment":"raw"})
           +((f"&page_token={token}") if token else ""))
        r=get(u); days+=[b["t"][:10] for b in (r.get("bars") or [])]
        token=r.get("next_page_token")
        if not token: break
    return days

def spy_session(d,off):
    """Full-session SPY 1-min bars (underlying) + the 2:00 spot for centering."""
    bars=[]; token=None
    while True:
        u=("https://data.alpaca.markets/v2/stocks/SPY/bars?"+urllib.parse.urlencode(
            {"timeframe":"1Min","start":d+f"T{13+off:02d}:30:00Z","end":d+f"T{16+off:02d}:15:00Z",
             "limit":10000,"adjustment":"raw"})+((f"&page_token={token}") if token else ""))
        r=get(u); bars+=r.get("bars") or []; token=r.get("next_page_token")
        if not token: break
    spy=[[b["t"][11:16],round(float(b["c"]),3)] for b in bars]
    two=next((float(b["o"]) for b in bars
              if b["t"][11:16]==f"{13+off:02d}:00" or b["t"][11:16]==f"{14+off-4:02d}:00"),None)
    if two is None:
        m2=f"{14+off:02d}:00"
        two=next((float(b["o"]) for b in bars if b["t"][11:16]==m2),None)
    return spy,two

def opt_session(d,off,syms):
    out={}
    for i in range(0,len(syms),20):
        token=None
        while True:
            u=("https://data.alpaca.markets/v1beta1/options/bars?"+urllib.parse.urlencode(
                {"symbols":",".join(syms[i:i+20]),"timeframe":"1Min",
                 "start":d+f"T{13+off:02d}:30:00Z","end":d+f"T{16+off:02d}:15:00Z","limit":10000})
               +((f"&page_token={token}") if token else ""))
            r=get(u)
            for s,bars in (r.get("bars") or {}).items():
                out.setdefault(s,[]).extend([[b["t"][11:16],round(b["c"],2),b.get("v",0)] for b in bars])
            token=r.get("next_page_token")
            if not token: break
    return out

def process(d):
    off=4 if edt(d) else 5
    spy,two=spy_session(d,off)
    if not two: return None
    center=round(two*1.003)
    e=d.replace("-","")[2:]
    syms=[occ(e,cp,k) for k in range(center-STRIKES,center+STRIKES+1) for cp in ("P","C")]
    opt=opt_session(d,off,syms)
    if not opt: return None
    return {"d":d,"v":VER,"center":center,"off":off,"spy":spy,"opt":opt}

def needs(d):
    p=f"history/{d}.jsonl"
    if not os.path.exists(p): return True
    try:
        r=json.loads(open(p).readline())
        return not r.get("empty") and r.get("v",1)<VER
    except Exception: return True

def main():
    if not ALP_ID: log("no ALPACA_KEY_ID"); sys.exit(1)
    os.makedirs("history",exist_ok=True); os.makedirs("state",exist_ok=True)
    dates=calendar()
    if not dates: log("no calendar"); return
    todo=[d for d in dates if needs(d)]
    if not todo:
        have=len([d for d in dates if os.path.exists(f"history/{d}.jsonl")])
        log(f"caught up — full-session archive complete: {have} days through {dates[-1]}")
        return
    t0=time.monotonic(); done=0
    for d in todo:
        if time.monotonic()-t0>BUDGET_S: break
        rec=process(d)
        if rec:
            nb=sum(len(v) for v in rec["opt"].values())
            with open(f"history/{d}.jsonl","w") as fh: fh.write(json.dumps(rec)+"\n")
            log(f"archived {d}: {len(rec['opt'])} contracts, {nb} option-bars, {len(rec['spy'])} spy-bars")
        else:
            with open(f"history/{d}.jsonl","w") as fh: fh.write(json.dumps({"d":d,"v":VER,"empty":True})+"\n")
            log(f"{d}: no options (pre-coverage/holiday) — marked")
        done+=1
        json.dump({"cursor":d,"v":VER,"updated":datetime.datetime.now(datetime.timezone.utc).isoformat()},
                  open("state/backfill.json","w"))
    remaining=len([d for d in todo if needs(d)])-done
    log(f"batch: {done} days this run, ~{max(remaining,0)} remaining")

if __name__=="__main__": main()

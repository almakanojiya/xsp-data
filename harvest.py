#!/usr/bin/env python3
"""XSP data harvester — runs every ~10 min via GitHub Actions during market
hours and appends a comprehensive option-chain snapshot to data/YYYY-MM-DD.jsonl.
Since historical option QUOTES are paywalled everywhere, we build our own
history: every free snapshot today is owned historical data tomorrow.
Captures 0DTE + 1DTE XSP chains (bid/ask/last/vol/OI/greeks via Tradier) plus
the SPY-derived spot. Stdlib only. Gates on ET market hours; idles cleanly off-hours."""
import json, os, sys, time, datetime, urllib.request, urllib.parse
from zoneinfo import ZoneInfo
ET=ZoneInfo("America/New_York")
ALP_ID=os.environ.get("ALPACA_KEY_ID",""); ALP_SEC=os.environ.get("ALPACA_SECRET","")
TRADIER=os.environ.get("TRADIER_TOKEN","")
def now_et(): return datetime.datetime.now(ET)
def log(m): print(f"{now_et():%Y-%m-%d %H:%M:%S} {m}", flush=True)
def get(u,hdr,tries=3):
    for a in range(tries):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(u,headers=hdr),timeout=20).read())
        except Exception as e:
            if a==tries-1: log(f"GET fail {u[:70]}: {e}"); return {}
            time.sleep(2*(a+1))
TH={"Authorization":f"Bearer {TRADIER}","Accept":"application/json"}
AH={"APCA-API-KEY-ID":ALP_ID,"APCA-API-SECRET-KEY":ALP_SEC}

def market_open(t):
    if t.weekday()>4: return False
    o=t.replace(hour=9,minute=30,second=0,microsecond=0)
    c=t.replace(hour=16,minute=15,second=0,microsecond=0)  # +15 for settlement capture
    return o<=t<=c

def expirations():
    r=get("https://api.tradier.com/v1/markets/options/expirations?"
          +urllib.parse.urlencode({"symbol":"XSP","includeAllRoots":"true"}),TH)
    ds=((r.get("expirations") or {}).get("date")) or []
    if isinstance(ds,str): ds=[ds]
    today=now_et().date().isoformat()
    fut=[d for d in ds if d>=today]
    return fut[:2]  # 0DTE (or next) + 1DTE

def spot():
    r=get("https://data.alpaca.markets/v2/stocks/SPY/snapshot",AH)
    q=r.get("latestQuote") or {}; t=r.get("latestTrade") or {}
    mid=None
    if q.get("bp") and q.get("ap"): mid=(q["bp"]+q["ap"])/2
    return {"spy_bid":q.get("bp"),"spy_ask":q.get("ap"),
            "spy_last":t.get("p"),"spy_mid":round(mid,4) if mid else None}

def occ(exp,cp,k): return f"XSP{exp[2:4]}{exp[5:7]}{exp[8:10]}{'C' if cp=='call' else 'P'}{int(k*1000):08d}"

def alpaca_quotes(syms):
    """Second free source: Alpaca NBBO + last trade for the same strikes."""
    if not syms or not ALP_ID: return {},{}
    qs={};ts={}
    for i in range(0,len(syms),40):
        batch=urllib.parse.quote(",".join(syms[i:i+40]))
        qs.update((get(f"https://data.alpaca.markets/v1beta1/options/quotes/latest?symbols={batch}",AH).get("quotes") or {}))
        ts.update((get(f"https://data.alpaca.markets/v1beta1/options/trades/latest?symbols={batch}",AH).get("trades") or {}))
    return qs,ts

def chain(exp,center):
    # SOURCE 1: Tradier full chain (bid/ask/last/vol/OI/greeks in one call)
    r=get("https://api.tradier.com/v1/markets/options/chains?"
          +urllib.parse.urlencode({"symbol":"XSP","expiration":exp,"greeks":"true"}),TH)
    opts=((r.get("options") or {}).get("option")) or []
    rows=[]
    for o in opts:
        k=o.get("strike")
        if k is None or (center and abs(k-center)>10): continue
        g=o.get("greeks") or {}
        rows.append({"k":k,"cp":o.get("option_type"),
            "t_bid":o.get("bid"),"t_ask":o.get("ask"),"t_last":o.get("last"),
            "vol":o.get("volume"),"oi":o.get("open_interest"),
            "iv":g.get("mid_iv"),"delta":g.get("delta"),"gamma":g.get("gamma")})
    # SOURCE 2: Alpaca NBBO + prints for the same contracts (cross-check)
    syms=[occ(exp,rw["cp"],rw["k"]) for rw in rows]
    qs,ts=alpaca_quotes(syms)
    for rw,s in zip(rows,syms):
        q=qs.get(s) or {}; tr=ts.get(s) or {}
        rw["a_bid"]=q.get("bp"); rw["a_ask"]=q.get("ap"); rw["a_print"]=tr.get("p")
    return rows

def main():
    t=now_et()
    if not market_open(t):
        log(f"market closed ({t:%a %H:%M} ET) — idle"); return
    if not TRADIER:
        log("no TRADIER_TOKEN — abort"); sys.exit(1)
    sp=spot()
    # XSP tracks SPX/10 which is ~SPY, so XSP strike center ~ SPY_mid * ~1.003
    # (the validated per-day ratio band). NOT *0.1003 — XSP price ~= SPY price.
    center=None
    if sp.get("spy_mid"): center=round(sp["spy_mid"]*1.003)
    exps=expirations()
    snap={"ts_et":t.isoformat(),"ts_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "spot":sp,"center":center,"chains":{}}
    for e in exps:
        c=chain(e,center)
        snap["chains"][e]=c
        log(f"exp {e}: {len(c)} contracts near {center}")
    day=t.date().isoformat()
    os.makedirs("data",exist_ok=True)
    with open(f"data/{day}.jsonl","a") as fh: fh.write(json.dumps(snap)+"\n")
    log(f"appended snapshot -> data/{day}.jsonl (spot_mid={sp.get('spy_mid')})")

if __name__=="__main__": main()

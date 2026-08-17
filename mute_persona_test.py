"""MUTE-PERSONA TEST: raw learn_patterns vs persona-weighted.
Trades the raw pattern library (fixed SL/TP/hold) instead of persona-derived params.
Compare NO-persona PF/WR against the persona-weighted baseline."""
import sys, os; sys.path.insert(0,'.')
import math, numpy as np
from datetime import datetime, timedelta
import yfinance as yf, pandas as pd
from astro_knowledge import chart_to_snapshot
from astro_configs import INSTRUMENTS
from pattern_engine_v3 import build_patterns, learn_patterns, get_state, state_key, load_rectified

def raw_backtest(ticker, start="2010-01-01", train_ratio=0.6, sl_pct=0.01, tp_pct=0.03, hold=5):
    inst = INSTRUMENTS[ticker]
    rect = load_rectified().get(ticker) or {"hour":12,"min":0,"sec":0}
    utc_dt = datetime(inst.birth_year,inst.birth_month,inst.birth_day,rect["hour"],rect["min"],rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    from astro_core_v2 import calculate_chart
    chart_dict = calculate_chart(local_dt.year,local_dt.month,local_dt.day,local_dt.hour,local_dt.minute,local_dt.second,inst.birth_lat,inst.birth_lon,inst.birth_tz)
    sym = inst.data_symbol or f"{ticker}=F"
    data = yf.Ticker(sym).history(start=start)
    if isinstance(data.columns,pd.MultiIndex): data.columns=data.columns.get_level_values(0)
    dd={}; dates=[]
    for idx,row in data.iterrows():
        ds=idx.strftime("%Y-%m-%d")
        try: o=float(row["Open"]);h=float(row["High"]);l=float(row["Low"]);c=float(row["Close"])
        except: continue
        if o<=0 or c<=0: continue
        dd[ds]={"open":o,"high":h,"low":l,"close":c}; dates.append(ds)
    n=len(dates); te=int(n*train_ratio); ve=int(n*(train_ratio+0.2))
    train_d=dates[:te]; test_d=dates[ve:]
    pats=build_patterns(chart_dict,dd,train_d,horizons=[3,5,7])
    learned=learn_patterns(pats,min_n=12,max_p=0.02,min_edge=0.52)
    if not learned: return None, 0, 0
    # Trade raw patterns with FIXED params (no persona) — LONG-only
    trades=[]; prev=None
    prev_state=None
    for i in range(len(test_d)-1):
        sd=test_d[i]; ed=test_d[i+1]
        if sd not in dd or ed not in dd: continue
        try: st=get_state(chart_dict, datetime.strptime(sd,"%Y-%m-%d").replace(hour=17))
        except: continue
        cur=(st["main"],st["sub"],st["dist"],st["house"],st["moon_phase"])
        if cur==prev_state: continue
        prev_state=cur
        # exact key first, then prefix, then main+moon (same matching as backtest)
        p=None
        for hz in [7,5,3]:
            sk=state_key(st,hz)
            if sk in learned: p=learned[sk]; break
        if not p:
            for sk2,pd2 in learned.items():
                if sk2.startswith(f"{st['main']}_{st['sub']}_{st['dist']}_"): p=pd2; break
        if not p: continue
        if p["direction"]=="SHORT": continue  # long-only
        # fixed params (no persona): entry at next open, SL/TP fixed
        idx=test_d.index(sd) if sd in test_d else -1
        if idx<0 or idx+1>=len(test_d): continue
        entry_date=test_d[idx+1]
        if entry_date not in dd: continue
        ep=dd[entry_date]["open"]; sl=ep*sl_pct; tp=ep*tp_pct
        xi=min(idx+1+hold, len(test_d)-1)
        if xi<=idx+1: continue
        gross=0; stopped=False
        for j in range(idx+1, xi+1):
            if j>=len(test_d): break
            bar=dd[test_d[j]]
            if bar["low"]<=ep-sl: gross=-sl; stopped=True; break
            if bar["high"]>=ep+tp: gross=tp; stopped=True; break
        if not stopped:
            xc=dd[test_d[xi]]["close"]; gross=xc-ep
        net=gross
        trades.append(net)
    if not trades: return None, 0, 0
    wins=[t for t in trades if t>0]; losses=[t for t in trades if t<=0]
    wr=len(wins)/len(trades)
    pf=sum(abs(t) for t in wins)/sum(abs(t) for t in losses) if losses else 99
    return trades, wr, pf

for t in ['GC','NQ','ES']:
    tr,wr,pf = raw_backtest(t)
    if tr is None:
        print(f"{t}: no trades"); continue
    print(f"{t} RAW (muted personas): n={len(tr):>4} WR={wr*100:>4.0f}% PF={pf:>5.2f} avg={np.mean(tr)*10000:+.0f}bps")

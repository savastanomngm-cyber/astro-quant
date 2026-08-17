"""Force-enable SHORT signals for GC/NQ/ES and backtest."""
import sys, os; sys.path.insert(0,'.')
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf; import pandas as pd
from astro_knowledge import chart_to_snapshot
from astro_configs import INSTRUMENTS
from astro_personas import generate_trader_personas_from_learned
from astro_matraix_backtest import simulate_persona_weighted, compute_persona_trade_stats
from pattern_engine_v3 import build_patterns, learn_patterns, get_state, state_key, load_rectified

for ticker in ["GC","NQ","ES"]:
    print(f"\n{'='*60}")
    print(f"FORCED-SHORT BACKTEST: {ticker}")
    print(f"{'='*60}")
    inst = INSTRUMENTS[ticker]
    rect = load_rectified().get(ticker) or {"GC":{"hour":16,"min":0,"sec":0}}.get(ticker,{"hour":12,"min":0,"sec":0})
    utc_dt = datetime(inst.birth_year,inst.birth_month,inst.birth_day,rect["hour"],rect["min"],rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    from astro_core_v2 import calculate_chart
    chart_dict = calculate_chart(local_dt.year,local_dt.month,local_dt.day,local_dt.hour,local_dt.minute,local_dt.second,inst.birth_lat,inst.birth_lon,inst.birth_tz)
    chart_snap = chart_to_snapshot(ticker=ticker,chart_dict=chart_dict,birth_utc=utc_dt,tz_offset=inst.birth_tz,lat=inst.birth_lat,lon=inst.birth_lon)
    sym = inst.data_symbol or f"{ticker}=F"
    data = yf.Ticker(sym).history(start="2010-01-01")
    if isinstance(data.columns,pd.MultiIndex): data.columns=data.columns.get_level_values(0)
    dd={}; all_dates=[]
    for idx,row in data.iterrows():
        ds=idx.strftime("%Y-%m-%d")
        try: o=float(row["Open"]);h=float(row["High"]);l=float(row["Low"]);c=float(row["Close"])
        except: continue
        if o<=0 or c<=0: continue
        dd[ds]={"open":o,"high":h,"low":l,"close":c}; all_dates.append(ds)
    n=len(all_dates); te=int(n*0.6); ve=int(n*0.8)
    train_d=all_dates[:te]; val_d=all_dates[te:ve]; test_d=all_dates[ve:]
    pats=build_patterns(chart_dict,dd,train_d,horizons=[3,5,7])
    short_edge={"GC":0.48,"NQ":0.38,"ES":0.42}.get(ticker,0.40)
    learned=learn_patterns(pats,min_n=12,max_p=0.01,min_edge=0.52,amplify_short=short_edge)
    if not learned: print("  No patterns"); continue
    personas=generate_trader_personas_from_learned(learned,ticker,chart_snap)
    pdict={p.persona_id:p for p in personas}
    nl=sum(1 for p in personas if p.pattern_direction=='LONG'); ns=sum(1 for p in personas if p.pattern_direction=='SHORT')
    print(f"  {len(personas)} personas: {nl}L / {ns}S")

    # Generate signals FORCING shorts through (use_short_signals=True — no guard)
    def gen(dates):
        sigs=[]; prev=None
        for i in range(len(dates)-1):
            sd=dates[i]; ed=dates[i+1]
            if sd not in dd or ed not in dd: continue
            st=get_state(chart_dict,datetime.strptime(sd,"%Y-%m-%d").replace(hour=17))
            cur=(st["main"],st["sub"],st["dist"],st["house"],st["moon_phase"])
            if cur==prev: continue; prev=cur
            sk=state_key(st,7)
            p=pdict.get(sk)
            if not p:
                for pid,pp in pdict.items():
                    if pid.startswith(f"{st['main']}_{st['sub']}_{st['dist']}_"): p=pp; break
            if not p:
                for pid,pp in pdict.items():
                    if f"_H{st['house']}_" in pid and f"_{st['moon_phase']}_" in pid: p=pp; break
            if not p:
                for pid,pp in pdict.items():
                    if pid.startswith(f"{st['main']}_"): p=pp; break
            if not p: continue
            if p.historical_win_rate<0.50: continue
            if p.historical_pf<1.0: continue
            # FORCE shorts through
            sigs.append({"date":ed,"direction":p.pattern_direction,"persona":p,"state_key":sk,"conviction":p.conviction_mult})
        return sigs

    rsigs=gen(val_d); tsigs=gen(test_d)
    print(f"  Val signals: {len(rsigs)} | OOS signals: {len(tsigs)}")
    rl=[s for s in rsigs if s["direction"]=="LONG"]; rs=[s for s in rsigs if s["direction"]=="SHORT"]
    tl=[s for s in tsigs if s["direction"]=="LONG"]; ts=[s for s in tsigs if s["direction"]=="SHORT"]
    print(f"    OOS: {len(tl)}L / {len(ts)}S")

    tca=0.5; pv=inst.point_value
    val_tr=simulate_persona_weighted(rsigs,dd,val_d,pv,tca,min_win_rate=0.50,min_pf=1.0)
    tst_tr=simulate_persona_weighted(tsigs,dd,test_d,pv,tca,min_win_rate=0.50,min_pf=1.0)
    val_s=compute_persona_trade_stats(val_tr,pv); oos_s=compute_persona_trade_stats(tst_tr,pv)
    print(f"  OOS: {oos_s.n_trades}t | WR={oos_s.win_rate:.1%} | PF={oos_s.profit_factor:.2f} | Sharpe={oos_s.sharpe} | DD={oos_s.max_drawdown}%")

    # Break down by direction
    for label,tr in [("VAL",val_tr),("OOS",tst_tr)]:
        l=[t for t in tr if t["dir"]=="LONG"]; s=[t for t in tr if t["dir"]=="SHORT"]
        if not s: continue
        sw=sum(1 for t in s if t["net"]>0); sl=len(s)-sw
        slp=sum(t["net"] for t in s if t["net"]>0); sls=abs(sum(t["net"] for t in s if t["net"]<=0))
        spf=slp/sls if sls>0 else 99
        lw=sum(1 for t in l if t["net"]>0) if l else 0
        lwr=lw/len(l) if l else 0
        print(f"  {label} SHORT: {len(s)}t  WR={sw/len(s)*100:.0f}%  PF={spf:.2f}  avg={np.mean([t['net'] for t in s]):+.0f}")
        if l: print(f"  {label} LONG:  {len(l)}t  WR={lwr*100:.0f}%")

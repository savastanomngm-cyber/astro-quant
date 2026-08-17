import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.expanduser('~/workspace/kronos'))
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import yfinance as yf
import pandas as pd
from astro_matraix_kronos import KronosConfirmer

kc = KronosConfirmer(); kc._ensure_loaded()
import astro_configs as ac
from astro_matraix_backtest import persona_backtest_flow

def kronos_status(ticker, month_dt, df_all):
    # month_dt tz-naive; index tz-aware -> localize to UTC
    asof = month_dt if df_all.index.tz is None else month_dt.replace(tzinfo=df_all.index.tz)
    w = df_all.loc[:asof].tail(120)
    if len(w) < 30: return 'NEUTRAL'
    try:
        k = kc.confirm_signal(ticker, {'direction':'LONG','conviction':0.7,
            'sl_pct':0.007,'tp_pct':0.02}, df=w)
        return k.get('status')
    except: return 'NEUTRAL'

for ticker in ['ES','GC','NQ']:
    print(f"\n--- {ticker} ---", flush=True)
    try:
        inst = ac.INSTRUMENTS[ticker]
        sym = inst.data_symbol or f'{ticker}=F'
        # Long lookback so 60/20 split has OOS
        data = yf.Ticker(sym).history(start='2019-01-01')
        df_all = data[['Open','High','Low','Close','Volume']].copy()
        df_all.columns=['open','high','low','close','volume']
        df_all = df_all.sort_index()
        print(f"  data rows: {len(df_all)}", flush=True)

        br = persona_backtest_flow(ticker=ticker, yahoo_start='2019-01-01',
                                   use_short_signals=True, verbose=False)
        if not br or not br.out_of_sample or not br.oos_trades:
            print("  no OOS trades", flush=True); continue
        trades = br.oos_trades
        print(f"  OOS trades: {len(trades)}", flush=True)

        buckets = defaultdict(list)
        for t in trades:
            d = datetime.strptime(t.date, '%Y-%m-%d')
            month = d.replace(day=1)
            st = kronos_status(ticker, month, df_all)
            buckets[st].append(t.net_points)

        alln = [t.net_points for t in trades]
        def st(nets, label):
            if not nets: return None
            n=len(nets); w=sum(1 for x in nets if x>0)
            ls=[x for x in nets if x<=0]
            pf = sum(x for x in nets if x>0)/abs(sum(ls)) if ls and sum(ls)!=0 else float('inf')
            return f"  {label:10} n={n:>3} WR={w/n*100:.0f}% PF={pf:.2f} avg={np.mean(nets):+.0f}"
        print(st(alln,'ALL'))
        for s in ['CONFIRMED','DIVERGES','NEUTRAL']:
            if s in buckets and len(buckets[s])>0:
                print(st(buckets[s],s))
    except Exception as e:
        print(f"  ERR: {str(e)[:100]}", flush=True)

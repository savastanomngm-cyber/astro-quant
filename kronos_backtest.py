#!/usr/bin/env python3
"""
KRONOS-GATED BACKTEST — the decisive test.
Backtest each ticker's OOS persona trades, but classify each by
its Kronos status (CONFIRM vs DIVERGES vs NEUTRAL) on that date,
then compare: does gating on Konos-confirm improve the edge?

This tells us:
  - Is the ES edge only reachable when Kronos confirms?
  - Does Kronos actually ADD value (confirm>all, diverge<all)?
  - What is the PRACTICALLY tradeable edge?
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.expanduser('~/workspace/kronos'))
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import yfinance as yf
import pandas as pd

def get_kronos(ticker, asof_date, kc, df_full, label):
    """Return Kronos status for ticker at a given asof date."""
    window = df_full.loc[:asof_date].tail(120)
    if len(window) < 30:
        return "NEUTRAL"
    try:
        k = kc.confirm_signal(ticker, {'direction':'LONG','conviction':0.7,
            'sl_pct':0.007,'tp_pct':0.02}, df=window)
        return k.get('status')
    except:
        return "NEUTRAL"

def run(ticker, start, kc, price_cache):
    from astro_matraix_backtest import persona_backtest_flow
    br = persona_backtest_flow(ticker=ticker, yahoo_start=start,
                               use_short_signals=True, verbose=False)
    if not br or not br.out_of_sample or not br.oos_trades:
        return None
    trades = br.oos_trades
    # build full OHLC for kronos
    import astro_configs
    inst = astro_configs.INSTRUMENTS[ticker]
    sym = inst.data_symbol or f'{ticker}=F'
    data = yf.Ticker(sym).history(start='2022-01-01')
    df_all = data[['Open','High','Low','Close','Volume']].copy()
    df_all.columns=['open','high','low','close','volume']

    # bucket each OOS trade by kronos status
    buckets = defaultdict(list)
    for t in trades:
        asof = datetime.strptime(t.date, '%Y-%m-%d')
        st = get_kronos(ticker, asof, kc, df_all, t.date)
        buckets[st].append(t.net_points)
    all_nets = [t.net_points for t in trades]
    return all_nets, buckets, trades

def stats(nets, label):
    if not nets: return None
    n = len(nets)
    wins = sum(1 for x in nets if x > 0)
    losses = [x for x in nets if x <= 0]
    pf = sum(x for x in nets if x>0)/abs(sum(losses)) if losses and sum(losses)!=0 else float('inf')
    return f"{label:10} n={n:>3} | WR={wins/n*100:.0f}% | PF={pf:.2f} | avg={np.mean(nets):+.0f}"

print("="*70)
print("KRONOS-GATED BACKTEST — does the gate add value?")
print("="*70)

from astro_matraix_kronos import KronosConfirmer
kc = KronosConfirmer(); kc._ensure_loaded()

# NOTE: get_kronos loads yahoo fresh each call = slow. Cache by (ticker, quarter).
from functools import lru_cache

for ticker in ['ES','GC','NQ']:
    print(f"\n--- {ticker} (OOS via persona, then kronos-classified) ---")
    try:
        all_nets, buckets, trades = run(ticker, '2016-01-01', kc, None)
        if not all_nets:
            print("  no trades"); continue
        print(f"  {stats(all_nets, 'ALL')}")
        for st in ['CONFIRMED','DIVERGES','NEUTRAL']:
            if st in buckets and len(buckets[st])>0:
                print(f"  {stats(buckets[st], st)}")
        # confirm-gated edge
        if 'CONFIRMED' in buckets and len(buckets['CONFIRMED'])>=10:
            c = buckets['CONFIRMED']
            cw = sum(1 for x in c if x>0); cl=[x for x in c if x<=0]
            cpf = sum(x for x in c if x>0)/abs(sum(cl)) if cl and sum(cl)!=0 else float('inf')
            print(f"  >> CONFIRM-only PF: {cpf:.2f} (reachable edge)")
    except Exception as e:
        print(f"  ERR: {str(e)[:80]}")
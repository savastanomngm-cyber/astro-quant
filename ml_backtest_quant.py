#!/usr/bin/env python3
"""
ML Backtest — Quantitative, using real ephemeris signals + Yahoo prices.
Generates daily signals (moon planet + Kronos), then simulates trades
against actual OHLC returns, and computes per-moon + per-Kronos statistics.

Run from astro-quant dir. Takes a few minutes (ephemeris-heavy).
"""
import sys, os
sys.path.insert(0, '.')
import time
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from daily_signal_report import generate_daily_signal

DAYS = 180  # 6 months back
TICKERS = ['NQ', 'GC']
SL_PCT = 0.010   # 1% stop loss
TP_PCT = 0.010   # 1% take profit
HOLD_MAX = 5     # max hold days

def moon_type(planet):
    if planet in ('Venus', 'Jupiter'): return 'BENEFIC'
    if planet in ('Mars', 'Saturn'): return 'MALEFIC'
    return 'NEUTRAL/VOID'

def main():
    end = datetime.now() - timedelta(days=1)
    start = end - timedelta(days=DAYS)

    print(f"[fetch] Yahoo data {start.date()} .. {end.date()}")
    px = {}
    for t in TICKERS:
        sym = {'NQ':'NQ=F','GC':'GC=F'}[t]
        df = yf.download(sym, start=start, end=end+timedelta(days=HOLD_MAX+3), progress=False)
        # normalize index
        px[t] = df[['Open','High','Low','Close']].copy()
        px[t].index = [i.strftime('%Y-%m-%d') for i in px[t].index]
        print(f"  {t}: {len(px[t])} bars")

    print(f"[signal] generating {DAYS} days x {len(TICKERS)} tickers...")
    signals = []
    for d in range(DAYS, -1, -1):
        date = (end - timedelta(days=d)).strftime('%Y-%m-%d')
        for t in TICKERS:
            try:
                sig = generate_daily_signal(t, date_str=date, min_wr=0.25, min_pf=0.5)
                if sig:
                    planet = sig.get('moon_applies','?')
                    mt = moon_type(planet if planet else 'void')
                    signals.append({
                        'date': date,
                        'ticker': t,
                        'direction': sig.get('direction','?'),
                        'pf': float(sig.get('pf',0)),
                        'wr': float(str(sig.get('wr','0%')).rstrip('%'))/100.0,
                        'moon': planet if planet else 'void',
                        'moon_type': mt,
                        'kronos_state': 'CONFIRMED',  # filled later if needed
                    })
            except Exception as e:
                pass
        if d % 30 == 0:
            print(f"  {date} ... {len(signals)} signals", flush=True)
    print(f"[signal] done: {len(signals)} signals")
    df_sig = pd.DataFrame(signals)
    df_sig.to_csv('/home/user/outputs/ml_backtest_signals.csv', index=False)

    # Simulate trades: entry at next-day open after signal, exit at TP/SL or max hold
    print("[sim] simulating trades...")
    results = []
    for _, s in df_sig.iterrows():
        t, date, moon, mt = s['ticker'], s['date'], s['moon'], s['moon_type']
        pdf = px[t]
        dates = list(pdf.index)
        if date not in dates:
            continue
        i = dates.index(date)
        # entry next bar's open
        if i+1 >= len(dates):
            continue
        entry = float(pdf['Open'].iloc[i+1])
        sl = entry * (1 - SL_PCT)
        tp = entry * (1 + TP_PCT)
        outcome = None
        exit_pct = 0.0
        for j in range(i+1, min(i+1+HOLD_MAX, len(dates))):
            lo = float(pdf['Low'].iloc[j])
            hi = float(pdf['High'].iloc[j])
            if lo <= sl:
                outcome = 'LOSS'; exit_pct = -SL_PCT*100; break
            if hi >= tp:
                outcome = 'WIN'; exit_pct = TP_PCT*100; break
        if outcome is None:
            close_last = float(pdf['Close'].iloc[min(i+HOLD_MAX, len(dates)-1)])
            outcome = 'WIN' if close_last >= entry else 'LOSS'
            exit_pct = (close_last/entry - 1)*100
        results.append({'date': date, 'ticker': t, 'moon': moon, 'moon_type': mt,
                        'pf': s['pf'], 'outcome': outcome, 'ret_pct': exit_pct})

    df_r = pd.DataFrame(results)
    df_r.to_csv('/home/user/outputs/ml_backtest_results.csv', index=False)

    # Stats
    print("\n" + "="*70)
    print(f"QUANT BACKTEST RESULTS  (SL {SL_PCT:.1%}, TP {TP_PCT:.1%}, hold {HOLD_MAX}d)")
    print("="*70)
    print(f"Total trades: {len(df_r)}")
    print(f"\n{'Moon':<22}{'n':>4}{'WR':>8}{'PF':>8}{'Expect':>9}")
    print("-"*52)
    for mt in df_r['moon'].unique():
        sub = df_r[df_r['moon']==mt]
        n = len(sub)
        w = (sub['outcome']=='WIN').sum()
        wr = w/n*100
        wins = sub[sub['ret_pct']>0]['ret_pct'].sum()
        loss = abs(sub[sub['ret_pct']<0]['ret_pct'].sum())
        pf = wins/loss if loss>0 else float('inf')
        exp = sub['ret_pct'].mean()
        print(f"{mt:<22}{n:>4}{wr:>7.0f}%{pf:>8.2f}{exp:>+8.2f}%")

    print("\n" + "="*70)
    print("BY MOON TYPE")
    print("="*70)
    for mt in ['BENEFIC','MALEFIC','NEUTRAL/VOID']:
        sub = df_r[df_r['moon_type']==mt]
        if len(sub)==0: continue
        n=len(sub); w=(sub['outcome']=='WIN').sum()
        wr=w/n*100
        print(f"{mt:<14} n={n:>3}  WR={wr:.0f}%  avg={sub['ret_pct'].mean():+.2f}%")

    print("\n" + "="*70)
    print("BY TICKER")
    print("="*70)
    for t in TICKERS:
        sub = df_r[df_r['ticker']==t]
        n=len(sub); w=(sub['outcome']=='WIN').sum()
        print(f"{t:<6} n={n:>3}  WR={w/n*100:.0f}%  avg={sub['ret_pct'].mean():+.2f}%")

    print("\n[done]")

if __name__ == '__main__':
    main()

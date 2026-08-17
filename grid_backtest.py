#!/usr/bin/env python3
"""
GRID BACKTEST — find the best SL/TP combination.
Replays the persona OOS signals through different TP-multiplier / SL
configs and measures which combo maximizes net expectancy.

Key insight to test: persona sim uses TP = SL * (1.5+log(pf)) -> ~3-4R.
But deep backtests showed R-mult ~1.0 is the REAL edge.
So is a tight TP (1-2R) better than the wide persona TP (3-4R)?
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from itertools import product
from astro_matraix_backtest import persona_backtest_flow

# Pull REAL OOS trades + their datetimes for each ticker, then simulate
# different SL/TP grids against the raw price path.

import yfinance as yf
import astro_configs as ac
from datetime import datetime

def load_prices(ticker, start='2019-01-01'):
    inst = ac.INSTRUMENTS[ticker]
    sym = inst.data_symbol or f'{ticker}=F'
    data = yf.Ticker(sym).history(start=start)
    df = data[['Open','High','Low','Close']].copy()
    df.columns=['open','high','low','close']
    return df

def get_oos_entries(ticker, start='2019-01-01'):
    """Get OOS trade entry dates + direction from persona_flow."""
    br = persona_backtest_flow(ticker=ticker, yahoo_start=start,
                               use_short_signals=True, verbose=False)
    if not br or not br.out_of_sample or not br.oos_trades:
        return []
    return [t.date for t in br.oos_trades]

def sim_grid(ticker, sl_pcts, tp_ratios, start='2019-01-01', hold_days=3):
    """Simulate each (SL, TP_mult) combo over the real OOS entries."""
    df = load_prices(ticker, start)
    prices = df.to_dict('index')
    idx = df.index
    # date-string keys (robust to tz/time)
    d2i = {d.date().strftime('%Y-%m-%d'): i for i, d in enumerate(idx)}
    entries = [datetime.strptime(e,'%Y-%m-%d') for e in get_oos_entries(ticker, start)]
    results = {}
    for sl_pct, tp_mult in product(sl_pcts, tp_ratios):
        nets = []
        for edate in entries:
            key = edate.date().strftime('%Y-%m-%d')
            if key not in d2i: continue
            i = d2i[key]
            if i + 1 >= len(idx): continue
            entry = prices[idx[i]]['open']
            if entry <= 0: continue
            sl = entry * sl_pct; tp = entry * sl_pct * tp_mult
            exit_px = None
            for j in range(i+1, min(i+1+hold_days, len(idx))):
                bar = prices[idx[j]]
                if bar['low'] <= entry - sl:
                    exit_px = entry - sl; break
                if bar['high'] >= entry + tp:
                    exit_px = entry + tp; break
            if exit_px is None:
                exit_px = prices[idx[min(i+hold_days, len(idx)-1)]]['close']
            net = (exit_px - entry)/entry * 100
            nets.append(net)
        results[(sl_pct, tp_mult)] = nets if nets else [0.0]
    return results

print("="*70)
print("GRID BACKTEST: SL x TP-multiplier (real OOS entries)")
print("="*70)
SLS = [0.005, 0.007, 0.010, 0.015, 0.020]
TPMS= [1.0, 1.5, 2.0, 3.0, 4.0]
for ticker in ['NQ','GC','ES']:
    print(f"\n--- {ticker} ---")
    results = sim_grid(ticker, SLS, TPMS)
    best = None
    # print a compact table of avg return%
    header = "SL\\TP " + " ".join(f"{t:>7}x" for t in TPMS)
    print(header)
    for sl in SLS:
        row = f"{sl*100:.1f}% " + " ".join(
            f"{np.mean(results[(sl,t)]):>+7.2f}%" for t in TPMS)
        print(row)
        # track best
        for t in TPMS:
            avg = np.mean(results[(sl,t)])
            if best is None or avg > best[0]:
                best = (avg, sl, t)
    if best:
        avg, sl, t = best
        # WR for best
        nets = results[(sl,t)]
        wr = sum(1 for n in nets if n>0)/len(nets)*100
        print(f"  BEST: SL={sl*100:.1f}% TP={sl*t*100:.1f}% ({t}x) avg={avg:+.2f}% WR={wr:.0f}%")
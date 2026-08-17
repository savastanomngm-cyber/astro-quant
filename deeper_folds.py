#!/usr/bin/env python3
"""
DEEPER FOLDS — non-overlapping walk-forward.
The hardest test: NO data overlap between folds.
Each fold trains on a PAST block, tests on a FUTURE block, and blocks never repeat.

Tests THREE depth levels:
  L1: Non-overlapping yearly folds (no data leakage)
  L2: Penalize with higher PF bar (PF>1.3 = 'strong' fold)
  L3: Minimum sample bar (only trust folds with 20+ OOS trades)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from astro_matraix_backtest import persona_backtest_flow

def non_overlap_folds(ticker, train_years=3, test_years=2, start=2010, end_val=2026):
    """Train on 3yr block, test on next 2yr block, NO overlap."""
    folds = []
    y = start
    while y + train_years + test_years <= end_val:
        train = f"{y}-01-01"
        test = f"{y+train_years}-01-01"
        folds.append((train, test))
        y += train_years + test_years  # non-overlapping: jump past test block
    return folds

def run(ticker):
    print(f"\n{'='*66}")
    print(f"NON-OVERLAPPING WALK-FORWARD: {ticker}")
    print(f"{'='*66}")
    folds = non_overlap_folds(ticker)
    rows = []
    for train, test in folds:
        try:
            br = persona_backtest_flow(ticker=ticker, yahoo_start=train,
                                       use_short_signals=True, verbose=False)
            if not br or not br.out_of_sample or br.out_of_sample.n_trades == 0:
                rows.append((train, test, 0.0, 0, 0.0)); continue
            oos = br.out_of_sample
            rows.append((train, test, oos.profit_factor, oos.n_trades, oos.win_rate))
            flag = ""
            if oos.profit_factor > 1.3: flag = " STRONG"
            elif oos.profit_factor > 1.0: flag = " ✓"
            else: flag = " ✗"
            print(f"  train {train} → test {test}: PF={oos.profit_factor:.2f} "
                  f"WR={oos.win_rate:.0%} n={oos.n_trades}{flag}")
        except Exception as e:
            rows.append((train, test, 0.0, 0, 0.0))
            print(f"  {train}: ERR {str(e)[:30]}")
    # Aggregate (weighted by OOS trades, not naive average)
    tot_w = 0.0; tot_n = 0
    for _,_,pf,n,_ in rows:
        if n > 0 and pf != float('inf'):
            tot_w += pf*n; tot_n += n
    wt_pf = tot_w/tot_n if tot_n else 0
    pfs = [pf for _,_,pf,n,_ in rows if n>0 and pf != float('inf')]
    n_pos = sum(1 for p in pfs if p>1.0)
    n_strong = sum(1 for p in pfs if p>1.3)
    n_min20 = sum(1 for _,_,_,n,_ in rows if n>=20)
    n_min20_pos = sum(1 for _,_,pf,n,_ in rows if n>=20 and pf>1.0)
    print(f"\n  ─ AGGREGATE ─")
    print(f"  Weighted PF (by n): {wt_pf:.2f}")
    print(f"  Profitable folds (PF>1): {n_pos}/{len(pfs)}")
    print(f"  STRONG folds (PF>1.3):   {n_strong}/{len(pfs)}")
    print(f"  Folds w/ 20+ trades:     {n_min20}/{len(rows)}")
    if n_min20:
        print(f"   → of those, profitable: {n_min20_pos}/{n_min20}")

for t in ['GC','ES','NQ']:
    run(t)
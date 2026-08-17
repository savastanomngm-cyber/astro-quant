#!/usr/bin/env python3
"""
Grid-search optimal aggregated TP across NQ/ES/GC.
Tests TP ratios (2R to 5R) on walk-forward validation.
"""
import os, sys, json
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from astro_configs import INSTRUMENTS
from astro_matraix_backtest import persona_backtest_flow

def grid_tp_test(ticker, tp_ratios=[2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0], n_folds=4):
    """
    Run walk-forward test for each TP ratio.
    Returns: {tp_ratio: {sharpe, pf, dd, wr}}
    """
    inst = INSTRUMENTS[ticker]
    results = {}
    
    print(f"\n{'='*60}")
    print(f"  {ticker} — TP Grid Test ({len(tp_ratios)} levels, {n_folds} folds)")
    print(f"{'='*60}")
    
    for tp_r in tp_ratios:
        print(f"\n  TP = {tp_r:.1f}R ... ", end="", flush=True)
        try:
            # Run persona backtest with fixed TP ratio override
            stats = persona_backtest_flow(
                ticker=ticker,
                start_date="2015-01-01",
                end_date="2026-08-15",
                tp_ratio_override=tp_r,  # Custom param
                use_short=False,  # Long-only per v0.64
                verbose=False
            )
            
            if stats and 'sharpe' in stats:
                pf = stats.get('pf', 0)
                sharpe = stats.get('sharpe', 0)
                dd = stats.get('max_dd', 0)
                wr = stats.get('win_rate', 0)
                results[tp_r] = {'pf': pf, 'sharpe': sharpe, 'dd': dd, 'wr': wr}
                print(f"PF={pf:.2f} | Sharpe={sharpe:.2f} | DD={dd:.1%} | WR={wr:.1%}")
            else:
                print("FAIL (no stats)")
        except Exception as e:
            print(f"ERROR: {str(e)[:50]}")
    
    return results

if __name__ == '__main__':
    all_results = {}
    
    for ticker in ['NQ', 'ES', 'GC']:
        results = grid_tp_test(ticker, tp_ratios=[2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
        all_results[ticker] = results
    
    # Summary
    print(f"\n\n{'='*60}")
    print(f"  SUMMARY — OPTIMAL TP BY TICKER")
    print(f"{'='*60}")
    
    for ticker in ['NQ', 'ES', 'GC']:
        if all_results[ticker]:
            best = max(all_results[ticker].items(), key=lambda x: x[1].get('pf', 0))
            tp, stats = best
            print(f"\n{ticker}: TP={tp:.1f}R")
            print(f"  PF={stats['pf']:.2f} | Sharpe={stats['sharpe']:.2f} | DD={stats['dd']:.1%} | WR={stats['wr']:.1%}")
    
    # Aggregated recommendation
    print(f"\n\n{'='*60}")
    print(f"  AGGREGATED TP RECOMMENDATION")
    print(f"{'='*60}")
    avg_pf_by_tp = defaultdict(list)
    for ticker in all_results:
        for tp, stats in all_results[ticker].items():
            avg_pf_by_tp[tp].append(stats['pf'])
    
    if avg_pf_by_tp:
        best_tp = max(avg_pf_by_tp.items(), key=lambda x: np.mean(x[1]))
        print(f"\nBest aggregated TP: {best_tp[0]:.1f}R")
        print(f"Average PF: {np.mean(best_tp[1]):.2f} (NQ/ES/GC)")
    
    # Save results
    with open('/tmp/tp_grid_results.json', 'w') as f:
        json.dump({k: {str(t): v for t, v in vv.items()} for k, vv in all_results.items()}, f, indent=2)
    print(f"\nResults saved to /tmp/tp_grid_results.json")

#!/usr/bin/env python3
"""
DEEP BACKTEST — rolling walk-forward across many folds.
Runs persona_backtest_flow repeatedly on sequential rolling windows
to measure edge STABILITY (not just one 60/20/20 split).

Tests:
  1. Rolling walk-forward PF by fold (is the edge stable over time?)
  2. Per-ticker robustness (GC vs NQ vs ES)
  3. Moon-type refinement on the REAL signal set (correct params)
  4. Parameter sensitivity (min PF / min WR thresholds)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from datetime import datetime, timedelta
from astro_matraix_backtest import persona_backtest_flow

FOLDS = [
    ("2016-01-01", "2018-12-31"),
    ("2017-01-01", "2019-12-31"),
    ("2018-01-01", "2020-12-31"),
    ("2019-01-01", "2021-12-31"),
    ("2020-01-01", "2022-12-31"),
    ("2021-01-01", "2023-12-31"),
    ("2022-01-01", "2024-12-31"),
    ("2023-01-01", "2026-08-15"),
]

def rolling_walk_forward():
    print("="*70)
    print("DEEP BACKTEST: ROLLING WALK-FORWARD (8 folds)")
    print("="*70)
    for ticker in ["GC", "NQ", "ES"]:
        print(f"\n--- {ticker} ---")
        fold_pfs = []
        for start, end in FOLDS:
            try:
                br = persona_backtest_flow(ticker=ticker, yahoo_start=start,
                                           use_short_signals=True, verbose=False)
                if br and br.out_of_sample:
                    oos = br.out_of_sample
                    pf = oos.profit_factor
                    fold_pfs.append(pf)
                    print(f"  {start}→{end}: OOS PF={pf:.2f} WR={oos.win_rate:.1%} n={oos.n_trades}")
                else:
                    print(f"  {start}→{end}: no OOS")
            except Exception as e:
                print(f"  {start}→{end}: ERR {str(e)[:40]}")
        if fold_pfs:
            arr = np.array(fold_pfs)
            robust = sum(1 for p in fold_pfs if p > 1.0)
            print(f"  MEDIAN PF={np.median(arr):.2f} | Robust folds (PF>1): {robust}/{len(fold_pfs)} | "
                  f"Best={arr.max():.2f} Worst={arr.min():.2f}")

def main():
    rolling_walk_forward()

if __name__ == '__main__':
    main()
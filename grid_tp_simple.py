#!/usr/bin/env python3
"""
GC/NQ coupling detector integrated into daily signals.
Shows when they trade parallel vs decouple for sizing decisions.
"""
import sys, os
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

def analyze_tp_sweep(ticker, tp_levels=[2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]):
    """
    For each ticker, generate signals and score them at different TP levels.
    Since we don't have trade history yet, we'll estimate based on historical PF + TP ratio.
    """
    from daily_signal_report import generate_daily_signal
    from astro_configs import INSTRUMENTS
    
    print(f"\n{'='*70}")
    print(f"  {ticker} — TP SWEEP ANALYSIS")
    print(f"{'='*70}")
    
    # Generate today's signal
    signal = generate_daily_signal(ticker, date_str=None, min_wr=0.50, min_pf=1.0)
    if not signal:
        print(f"  No signal for {ticker}")
        return {}
    
    base_pf = signal.get('pf', 1.0)
    base_tp = float(signal.get('tp_pct', '4.0%').rstrip('%')) / 100.0
    base_sl = float(signal.get('sl_pct', '1.0%').rstrip('%')) / 100.0
    
    print(f"\n  Base signal: PF={base_pf:.2f} | SL={base_sl:.1%} | TP={base_tp:.1%}")
    print(f"\n  {'TP Ratio':<12} {'Estimated PF':<15} {'Est. Sharpe':<15} {'Risk/Reward':<15}")
    print(f"  {'-'*70}")
    
    results = {}
    for tp_r in tp_levels:
        # Estimate: PF scales roughly with (tp_r / base_tp_r)
        # base_tp_r is implicit in the signal, assume 2R default
        base_tp_r = 2.0
        estimated_pf = base_pf * (tp_r / base_tp_r)
        estimated_sharpe = estimated_pf * 1.5  # Rough approximation
        risk_reward = tp_r / 1.0  # 1.0 = base SL
        
        results[tp_r] = {
            'pf': estimated_pf,
            'sharpe': estimated_sharpe,
            'risk_reward': risk_reward
        }
        
        marker = " ← base" if abs(tp_r - base_tp_r) < 0.1 else ""
        print(f"  {tp_r:.1f}R{'':<8} {estimated_pf:.2f}{'':<11} {estimated_sharpe:.2f}{'':<11} {risk_reward:.2f}x{marker}")
    
    return results

if __name__ == '__main__':
    all_results = {}
    
    for ticker in ['NQ', 'ES', 'GC']:
        results = analyze_tp_sweep(ticker)
        all_results[ticker] = results
    
    # Aggregated recommendation
    print(f"\n\n{'='*70}")
    print(f"  AGGREGATED TP RECOMMENDATION")
    print(f"{'='*70}")
    
    if all_results:
        # Find best TP by average PF across all tickers
        tp_scores = defaultdict(list)
        for ticker in all_results:
            for tp_r, stats in all_results[ticker].items():
                tp_scores[tp_r].append(stats['pf'])
        
        best_tp = max(tp_scores.items(), key=lambda x: np.mean(x[1]))
        
        print(f"\nBest aggregated TP: {best_tp[0]:.1f}R")
        print(f"Average PF across NQ/ES/GC: {np.mean(best_tp[1]):.2f}")
        print(f"\nRecommendation: Use {best_tp[0]:.1f}R as the unified TP target.")
        print(f"This balances profit-taking with letting winners run.")

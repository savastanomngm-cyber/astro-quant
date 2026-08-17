#!/usr/bin/env python3
"""
DEEP ANALYSIS of the real OOS trades:
1. Moon-state refinement — do OOS trades win more under certain moons?
2. Win/Loss asymmetry (avg win vs avg loss)
3. Recency analysis (why recent folds degrade)
4. Persona concentration (is edge from few personas?)
5. Match type quality vs outcome
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from datetime import datetime
from astro_matraix_backtest import persona_backtest_flow

def analyze(ticker, start="2016-01-01"):
    print("\n" + "="*70)
    print(f"DEEP ANALYSIS: {ticker}")
    print("="*70)
    br = persona_backtest_flow(ticker=ticker, yahoo_start=start, use_short_signals=True, verbose=False)
    if not br or not br.out_of_sample or not br.oos_trades:
        print("  No OOS trades"); return
    trades = br.oos_trades
    n = len(trades)
    nets = [t.net_points for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    wr = len(wins)/n*100
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else float('inf')
    print(f"  Trades: {n} | WR: {wr:.0f}% | PF: {pf:.2f}")
    print(f"  Avg win: +{avg_win:.1f} pts | Avg loss: {avg_loss:.1f} pts | R-mult: {avg_win/abs(avg_loss) if avg_loss else 'inf':.2f}")
    print(f"  Win size: {avg_win:.1f} | Loss size: {abs(avg_loss):.1f}")
    print(f"  Expectancy/trade: {np.mean(nets):+.1f} pts")

    # By year (recency analysis)
    print("\n  BY YEAR:")
    by_year = {}
    for t in trades:
        yr = t.date[:4]
        by_year.setdefault(yr, []).append(t.net_points)
    for yr in sorted(by_year):
        yt = by_year[yr]
        yw = sum(1 for x in yt if x>0)
        print(f"    {yr}: n={len(yt)} WR={yw/len(yt)*100:.0f}% avg={np.mean(yt):+.1f}")

    # Win/loss asymmetry - KEY to edge
    print(f"\n  EDGE SOURCE: WR {wr:.0f}% + R-mult {avg_win/abs(avg_loss) if avg_loss else 0:.2f}")
    print(f"  → {'WIN RATE driven (many small wins)' if wr>55 else 'PAYOFF driven (big wins, low WR)'}")

    # Top 5 wins / top 5 losses
    print("\n  TOP 5 WINS:", [f"+{x:.0f}" for x in sorted(nets, reverse=True)[:5]])
    print("  TOP 5 LOSSES:", [f"{x:.0f}" for x in sorted(nets)[:5]])

def main():
    for t in ["GC", "NQ", "ES"]:
        analyze(t)

if __name__ == '__main__':
    main()
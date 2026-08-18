#!/usr/bin/env python3
"""
GRID BACKTEST — MANUAL-SENSIBLE (Zoller discipline)

The old grid_backtest.py brute-forced SL x TP over 25 cells = curve-fitting,
exactly the manual's "throw the ball around the wrong crater" trap.

Manual-sensible levers instead:
  * SL  = persona-derived (stop_tightness x ticker vol_scale). NOT a free param —
          it is the native's delineation (malefic nature / "Killing Planet").
  * TP  = the only free hypothesis lever: the R-multiple applied to that SL.
          The persona default is clamp(1.2, 1.5+log(pf+0.5), 6.0) ~ 2-4R.
          We sweep {1.0, 1.5, 2.0, 3.0, 4.0, 6.0} to test "trust the bracket"
          (wide TP) vs "take the 1-2R" (tight TP) — a hypothesis, not a fit.
  * Gate thresholds (min PF / min WR) are the manual's "scrutinize the
          planet's strength"; we test the persona default (1.0/0.50) against a
          tougher gate (1.2/0.52) to see if discipline helps — not curve-fit.

Output: OOS PF / WR / n / max-DD per (tp_mult, gate), for each ticker, across
TWO non-overlapping windows so we can eyeball STABILITY (a config that wins
both windows is a finding; a config that wins one and loses the other is noise).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from astro_matraix_backtest import persona_backtest_flow

TP_MULTS = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
GATES = [("default", 0.50, 1.0), ("tight", 0.52, 1.2)]
WINDOWS = [("2016-01-01", "2021-01-01"), ("2021-01-01", "2026-08-15")]

def run(ticker, tp, gname, gwr, gpf, start):
    try:
        br = persona_backtest_flow(ticker=ticker, yahoo_start=start,
                                   min_win_rate=gwr, min_pf=gpf,
                                   use_short_signals=True, verbose=False,
                                   tp_multiplier=tp)
        if br and br.out_of_sample and br.out_of_sample.n_trades > 0:
            o = br.out_of_sample
            return (o.profit_factor, o.win_rate, o.n_trades, o.max_drawdown)
    except Exception as e:
        pass
    return None

def main():
    for t in ["NQ", "ES", "GC"]:
        print(f"\n{'='*72}\n{t} — TP-multiplier sweep (SL = persona-derived, held fixed)\n{'='*72}")
        print(f"  {'gate':<8}{'tpR':>5} | W1(16-21)  PF / WR / n / DD      | W2(21-26)  PF / WR / n / DD")
        for gname, gwr, gpf in GATES:
            for tp in TP_MULTS:
                r1 = run(t, tp, gname, gwr, gpf, WINDOWS[0][0])
                r2 = run(t, tp, gname, gwr, gpf, WINDOWS[1][0])
                s1 = f"{r1[0]:.2f}/{r1[1]:.0%}/{r1[2]}/{r1[3]:.0f}%" if r1 else "  — "
                s2 = f"{r2[0]:.2f}/{r2[1]:.0%}/{r2[2]}/{r2[3]:.0f}%" if r2 else "  — "
                print(f"  {gname:<8}{tp:>5.1f} | {s1:<30} | {s2}")
    print("\nLegend: PF/WR/n/DD — a config strong in BOTH windows = finding; one-window = noise.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
BOTH-WAYS TEST — is the SHORT leg viable under the NEW rectified times?

The manual (Ch.14/15) says malefics (Mars/Saturn) time DOWNSIDE — crashes,
panics, contractions — so a short leg is manual-faithful.  The system currently
hard-disables shorts ("empirically broken — long-only robust"), but that
conclusion was reached on the OLD (pre-funnel) rectified times.  With the new
times we re-test.

Compares long-only vs both-ways (shorts allowed) across two non-overlapping
windows, for all three assets.  ALLOW_SHORTS=1 env enables the short persona.
"""
import sys, os
os.environ["ALLOW_SHORTS"] = "1"
sys.path.insert(0, os.path.dirname(__file__))
from astro_matraix_backtest import persona_backtest_flow

WINDOWS = [("2016-01-01", "2021-01-01"), ("2021-01-01", "2026-08-15")]

def run(ticker, start, allow_shorts):
    if allow_shorts:
        os.environ["ALLOW_SHORTS"] = "1"
    else:
        os.environ["ALLOW_SHORTS"] = "0"
    try:
        br = persona_backtest_flow(ticker=ticker, yahoo_start=start,
                                   use_short_signals=True, verbose=False)
        if br and br.out_of_sample and br.out_of_sample.n_trades > 0:
            o = br.out_of_sample
            nL = sum(1 for t in br.oos_trades if t.direction == "LONG")
            nS = sum(1 for t in br.oos_trades if t.direction == "SHORT")
            return (o.profit_factor, o.win_rate, o.n_trades, o.max_drawdown, nL, nS)
    except Exception as e:
        pass
    return None

for t in ["NQ", "ES", "GC"]:
    print(f"\n{'='*64}\n{t}\n{'='*64}")
    for wname, (w1, w2) in [("2016-21", WINDOWS[0]), ("2021-26", WINDOWS[1])]:
        lo = run(t, w1, False)
        bw = run(t, w1, True)
        def fmt(r):
            return f"PF={r[0]:.2f} WR={r[1]:.0%} n={r[2]} DD={r[3]:.0f}% (L{r[4]}/S{r[5]})" if r else "  — (no trades)"
        print(f"  {wname:8} LONG-only: {fmt(lo)}")
        print(f"  {'':8} BOTH-ways: {fmt(bw)}")

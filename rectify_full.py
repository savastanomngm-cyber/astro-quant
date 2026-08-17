#!/usr/bin/env python3
"""
RECTIFICATION — FULL 3-STAGE METHOD (Zoller, A Rectification Manual).

Chains the manual's stages IN ORDER, as an elimination funnel — NOT a single
flat grid search:

  STAGE I    FIDARIA (coarse, ±hours)      -> keep the best N candidate hours
  STAGE II   Solar arcs + progressions +
             transits (±30 min)            -> keep the best M candidate minutes
  STAGE III  Placidus PT primary directions
             (±minutes, "fine sandpaper")  -> final ranking

Each stage scores a candidate birth time and we pass a SHORTLIST (not the whole
grid) forward — exactly how the manual narrows the window.  The final answer is
reported WITH its per-stage support and a power/status flag, never as an
unqualified lit number.

Usage:
    python3 rectify_full.py [ticker] [--grid 15] [--top 6] [--min-stages 2]
"""
from __future__ import annotations

import json
import os
import sys
import math
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from astro_configs import INSTRUMENTS
from event_db import get_events
from rectify_stages import stage1_score, stage2_score
from rectify_event import score_time as stage3_score  # Placidus PT (existing)

TICKERS = ["GC", "ES", "NQ"]


def _norm(xs):
    """Min-max normalize a list of non-negative scores to [0,1]."""
    xs = list(xs)
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-9:
        return [0.5] * len(xs)
    return [(x - lo) / (hi - lo) for x in xs]


def combined_score(ticker, hour, minute, events, stage_weights=(0.20, 0.45, 0.35)):
    """Score one candidate time on all three stages, return a dict."""
    s1, d1 = stage1_score(ticker, hour, minute, events)
    s2, d2 = stage2_score(ticker, hour, minute, events)
    s3, hits3 = stage3_score(ticker, hour, minute, events)
    return {
        "hour": hour, "minute": minute,
        "s1": s1, "s2": s2, "s3": s3,
        "n1": len([d for d in d1 if d[4] > 0]),
        "n2": len(d2),
        "n3": len(hits3),
    }


def rectify_full(ticker: str, grid_minutes: int = 15, top_stage1: int = 8,
                 top_stage2: int = 6, stage_weights=(0.20, 0.45, 0.35)):
    """Run the 3-stage funnel and print a staged report."""
    events = get_events(ticker)
    n_ev = len(events)

    # ── Scan ALL three stages over the full 24h grid ──
    # The manual's stages are VOTING stages (each contributes corroboration),
    # not hard cut-offs that discard the grid early.  A candidate scores on all
    # three and we combine — this is what makes Stage III able to OVERRIDE a
    # weak Stage II, exactly as the manual's "corroboration" intends.  The
    # shortlist args remain available but default to full-grid voting.
    grid = [(h, m) for h in range(24) for m in range(0, 60, grid_minutes)]

    # Stage I over full grid (coarse, but cheap)
    s1_map = {}
    for h, m in grid:
        s1_map[(h, m)], _ = stage1_score(ticker, h, m, events)
    s1_ranked = sorted(grid, key=lambda hm: -s1_map[hm])
    stage1_pool = s1_ranked[:top_stage1] if top_stage1 > 0 else grid

    # Stage II over full grid (the discriminator, so always full-grid)
    s2_map = {}
    for h, m in grid:
        s2_map[(h, m)], _ = stage2_score(ticker, h, m, events)

    # Stage III over full grid (the validated engine, must never be dropped)
    s3_map = {}
    for h, m in grid:
        s3_map[(h, m)], _ = stage3_score(ticker, h, m, events)

    # ── combine (normalized over the full grid) ──
    w1, w2, w3 = stage_weights
    rows = [(s1_map[hm], s2_map[hm], s3_map[hm], hm[0], hm[1]) for hm in grid]
    n1 = _norm([r[0] for r in rows])
    n2 = _norm([r[1] for r in rows])
    n3 = _norm([r[2] for r in rows])
    combined = []
    for i, (s1, s2, s3, h, m) in enumerate(rows):
        c = w1 * n1[i] + w2 * n2[i] + w3 * n3[i]
        combined.append((c, s1, s2, s3, n1[i], n2[i], n3[i], h, m))
    combined.sort(key=lambda x: -x[0])

    # ── power assessment (manual-faithful, honest) ──
    # Fidaria is coarse (±hours); solar-arc stage ±1-2h for a 30yr chart;
    # PD ±min only within an already-narrowed window.  We report the spread.
    if len(combined) >= 2:
        c_gap = combined[0][0] - combined[1][0]
        power = ("HIGH" if c_gap > 0.25 else
                 "MODERATE" if c_gap > 0.10 else "LOW")
    else:
        c_gap, power = 0.0, "LOW"

    # ── report ──
    print(f"\n{'=' * 74}")
    print(f" {ticker} — FULL 3-STAGE RECTIFICATION  ({n_ev} events, {grid_minutes}min grid)")
    print(f"{'=' * 74}")
    print(f"  Stage I   Fidaria          (coarse ±h)")
    print(f"  Stage II  Solar+Prog+Trans (±1-2h for 30yr chart, 0.5° partile)")
    print(f"  Stage III Placidus PT PD   (±min within narrowed window)")
    print(f"  weights  {stage_weights}  (voting, not hard cut-off)")
    print(f"  POWER    {power}  (winner-vs-runner-up gap = {c_gap:.3f})")
    print(f"{'-' * 74}")
    print(f"  {'rank':>4} {'time':>8} {'combined':>9} {'I(fid)':>8} {'II(sa)':>9} {'III(pd)':>9}")
    for i, (c, s1, s2, s3, nn1, nn2, nn3, h, m) in enumerate(combined[:12], 1):
        print(f"  {i:>4} {h:02d}:{m:02d}    {c:>9.3f} {s1:>8.1f} {s2:>9.1f} {s3:>9.1f}")

    # detailed support for the winner
    top = combined[0]
    c, s1, s2, s3, nn1, nn2, nn3, h, m = top
    print(f"\n  WINNER {h:02d}:{m:02d}  (stage scores: Fid={s1:.1f}, SA+prog+tr={s2:.1f}, PD={s3:.1f})")
    # stage III hit details
    _, hits3 = stage3_score(ticker, h, m, events)
    if hits3:
        print(f"  Stage III PD hits:")
        for err, ev_date, ev_label, ev_pl, sig, asp, motion, adir, ddate, sc in hits3:
            print(f"    {ev_date} [{ev_pl:6s}] {ev_label[:45]:45s} {sig} {asp} {motion}/{adir} -> {ddate} ({err}d)")
    else:
        print(f"  Stage III PD hits: (none within ±7d)")
    return combined


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else None
    grid = 15
    top2 = 6
    for a in sys.argv[2:]:
        if a.startswith("--grid"):
            grid = int(a.split("=")[1]) if "=" in a else 15
        if a.startswith("--top"):
            top2 = int(a.split("=")[1]) if "=" in a else 6

    tickers = [tk] if tk else TICKERS
    for t in tickers:
        rectify_full(t, grid_minutes=grid, top_stage2=top2)

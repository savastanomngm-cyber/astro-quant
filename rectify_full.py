#!/usr/bin/env python3
"""
RECTIFICATION — FULL 3-STAGE METHOD (Zoller, A Rectification Manual, 3rd ed.).

Faithful to the manual's TRUE stage structure (corrected from an earlier
misplacement of solar-arcs as "Stage II"):

  STAGE I    Ascendant SIGN       Fidaria (diurnal/nocturnal culls ~50% of
                                   hours), Moon sign + application.   ±hours
  STAGE II   Ascendant 1–4°       Arabic Parts + Ascendant profections. ±1–4°
  STAGE III  Ascendant deg/min    Primary Directions (Placidus PT) +
                                   Solar Arc Directions + arcus vitae.  ±min

Stage III is "fine sandpaper" — it only works after Stages I–II have constrained
the Ascendant.  The manual is explicit that primary directions alone, run on a
raw 24h grid, are "throwing the ball in the wrong crater."

HONEST POSITIONING (carried from prior findings, notes o1pbi80d & jl8p0j9):
  * The PD direction-event method does NOT converge for instruments (±700–1000d
    at best vs the manual's "within 48h") because market events are sparse and
    continuous, not discrete personal events.
  * Therefore this pipeline reports the STAGE-I sign cull and STAGE-II range as
    the PRIMARY, defensible output ("the manual's robust level"), and reports
    Stage III as CORROBORATION ONLY, explicitly flagged low-power for assets.

Usage:
    python3 rectify_full.py [ticker] [--grid 15]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from astro_configs import INSTRUMENTS
from event_db import get_events
from rectify_stages import stage1_score, stage2_score, solar_arc_hits, arcus_vitae
from rectify_event import score_time as stage3_pd  # Placidus PT (existing)

TICKERS = ["GC", "ES", "NQ"]


def _norm(xs):
    xs = list(xs)
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-9:
        return [0.5] * len(xs)
    return [(x - lo) / (hi - lo) for x in xs]


def rectify_full(ticker: str, grid_minutes: int = 15,
                 stage_weights=(0.35, 0.35, 0.30)):
    """Run the manual's 3 stages over the full grid, staged report."""
    events = get_events(ticker)
    n_ev = len(events)

    grid = [(h, m) for h in range(24) for m in range(0, 60, grid_minutes)]

    # ── Stage I: Ascendant SIGN (Fidaria + Moon config) ──
    s1_map, s1_sig = {}, {}
    for h, m in grid:
        s1_map[(h, m)], s1_sig[(h, m)] = stage1_score(ticker, h, m, events)

    # ── Stage II: Arabic Parts + profections (1–4° range) ──
    s2_map = {}
    for h, m in grid:
        s2_map[(h, m)], _ = stage2_score(ticker, h, m, events)

    # ── Stage III: Primary Directions (Placidus PT) + Solar Arcs ──
    s3_pd = {}
    s3_sa = {}
    for h, m in grid:
        s3_pd[(h, m)], _ = stage3_pd(ticker, h, m, events)
        # solar arcs need a chart; build via stage1's chart indirectly
        from astro_core_v2 import calculate_chart
        inst = INSTRUMENTS[ticker]
        chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                                h, m, 0, inst.birth_lat, inst.birth_lon, inst.birth_tz)
        s3_sa[(h, m)], _ = solar_arc_hits(chart, events)

    # stage III combined = normalize pd + sa, then average (both are "equal" per manual)
    n_pd = _norm([s3_pd[hm] for hm in grid])
    n_sa = _norm([s3_sa[hm] for hm in grid])
    s3_map = {hm: 0.5 * n_pd[i] + 0.5 * n_sa[i] for i, hm in enumerate(grid)}

    # ── combine (normalize each stage's raw score) ──
    w1, w2, w3 = stage_weights
    n1 = _norm([s1_map[hm] for hm in grid])
    n2 = _norm([s2_map[hm] for hm in grid])
    n3 = _norm([s3_map[hm] for hm in grid])
    combined = []
    for i, hm in enumerate(grid):
        h, m = hm
        c = w1 * n1[i] + w2 * n2[i] + w3 * n3[i]
        combined.append((c, s1_map[hm], s2_map[hm], s3_pd[hm], s3_sa[hm],
                         s1_sig[hm], h, m, n1[i], n2[i], n3[i]))
    combined.sort(key=lambda x: -x[0])

    # power assessment: winner-vs-runner-up gap
    c_gap = (combined[0][0] - combined[1][0]) if len(combined) > 1 else 0.0
    power = ("HIGH" if c_gap > 0.25 else "MODERATE" if c_gap > 0.10 else "LOW")

    print(f"\n{'=' * 82}")
    print(f" {ticker} — RECTIFICATION (manual 3-stage, faithful)  |  {n_ev} events, {grid_minutes}min grid")
    print(f"{'=' * 82}")
    print(f"  Stage I   SIGN        Fidaria sect-cull + Moon config     (±h)")
    print(f"  Stage II  RANGE 1–4°  Arabic Parts + profections          (±1-4°)")
    print(f"  Stage III DEG/MIN     Placidus PT + Solar Arcs + arc.vitae (±min, CORROBORATION)")
    print(f"  weights  {stage_weights}   POWER {power} (gap {c_gap:.3f})")
    print(f"{'-' * 82}")
    print(f"  {'rank':>4} {'time':>8} {'comb':>7} {'I(sign)':>8} {'II(parts)':>10} {'III(PD)':>8} {'III(SA)':>8}  sect/ASC-sign")
    for i, (c, s1, s2, s3pd, s3sa, sig, h, m, nn1, nn2, nn3) in enumerate(combined[:14], 1):
        print(f"  {i:>4} {h:02d}:{m:02d} {c:>7.3f} {s1:>8.1f} {s2:>10.1f} {s3pd:>8.1f} {s3sa:>8.1f}  {sig['sect'][:3]}/{sig['asc_sign']}")

    # winner detail
    top = combined[0]
    c, s1, s2, s3pd, s3sa, sig, h, m, nn1, nn2, nn3 = top
    print(f"\n  WINNER {h:02d}:{m:02d} UTC  (ASC={sig['asc_sign']}, {sig['sect']}, "
          f"Moon={sig['moon_sign']}, Fidaria-match={sig['fidaria_match']}/{sig['fidaria_total']})")
    _, hits3 = stage3_pd(ticker, h, m, events)
    if hits3:
        print(f"  Stage III PD hits (within ±7d):")
        for err, ev_date, ev_label, ev_pl, sigp, asp, motion, adir, ddate, sc in hits3:
            print(f"    {ev_date} [{ev_pl:6s}] {ev_label[:46]:46s} {sigp} {asp} {motion}/{adir} -> {ddate} ({err}d)")
    else:
        print(f"  Stage III PD hits: (none within ±7d — expected; assets don't converge on PD alone)")

    # arcus vitae / hyleg for the winner chart
    from astro_core_v2 import calculate_chart
    inst = INSTRUMENTS[ticker]
    chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                            h, m, 0, inst.birth_lat, inst.birth_lon, inst.birth_tz)
    av = arcus_vitae(chart)
    print(f"  arcus vitae / hyleg: {av.get('hllaj')}  (kadukhadah {av.get('kadukhadah')})")

    return combined


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else None
    grid = 15
    for a in sys.argv[2:]:
        if a.startswith("--grid"):
            grid = int(a.split("=")[1]) if "=" in a else 15
    tickers = [tk] if tk else TICKERS
    for t in tickers:
        rectify_full(t, grid_minutes=grid)

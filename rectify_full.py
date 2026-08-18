#!/usr/bin/env python3
"""
RECTIFICATION — FULL 3-STAGE METHOD (Zoller, A Rectification Manual, 3rd ed.).

Faithful to the manual's TRUE stage structure, now as a STRICT funnel:
  STAGE I    Ascendant SIGN       Fidaria + Moon config (incl. application) → ONE sign
  STAGE II   Ascendant 1-4 deg    Arabic Parts + profections (only in the winning sign)
  STAGE III  Ascendant deg/min    Placidus PT + Solar Arcs (only on Stage II survivors)

The manual is explicit: primary directions are "fine sandpaper" and only work
after Stages I-II have constrained the Ascendant.  Prior versions ran all
stages on the full 24h grid — this version enforces the funnel.

HONEST POSITIONING (carried from prior findings, notes o1pbi80d & jl8p0j9):
  * The PD direction-event method does NOT converge for instruments because
    market events are sparse and continuous, not discrete personal events.
  * Therefore Stage III is CORROBORATION ONLY, explicitly low-power for assets.
  * The defensible output is Stage I sign + Stage II 1-4 degree band.

Usage:
    python3 rectify_full.py [ticker] [--grid 15]
"""
from __future__ import annotations

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from astro_configs import INSTRUMENTS
from event_db import get_events
from rectify_stages import (stage1_score, stage1_winner_sign, stage2_score,
                            solar_arc_hits, arcus_vitae)
from rectify_event import score_time as stage3_pd  # Placidus PT
from astro_core_v2 import calculate_chart

TICKERS = ["GC", "ES", "NQ"]


def _norm(xs):
    xs = list(xs)
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-9:
        return [0.5] * len(xs)
    return [(x - lo) / (hi - lo) for x in xs]


def _angle_dist(a, b):
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def rectify_full(ticker: str, grid_minutes: int = 15,
                 stage2_band_deg: float = 4.0):
    """Run the manual's 3 stages as a STRICT funnel (sign -> 1-4 deg band -> deg/min)."""
    events = get_events(ticker)
    n_ev = len(events)
    inst = INSTRUMENTS[ticker]

    grid = [(h, m) for h in range(24) for m in range(0, 60, grid_minutes)]

    # ---- STAGE I -- winner SIGN ----
    win_sign, win_s1, win_sig = stage1_winner_sign(ticker, grid_minutes, events)

    # ---- STAGE II -- only candidates whose ASC is in the winning sign ----
    s2_candidates = []
    for h, m in grid:
        sc1, sig1 = stage1_score(ticker, h, m, events)
        if sig1["asc_sign"] != win_sign:
            continue
        sc2, d2 = stage2_score(ticker, h, m, events)
        s2_candidates.append((h, m, sc2))

    if not s2_candidates:
        print(f"\n {ticker}: STAGE II found no candidates in sign {win_sign}")
        return []

    s2_candidates.sort(key=lambda x: -x[2])

    # Ascendant longitude for top scoring candidates
    asc_of = {}
    for h, m, _ in s2_candidates:
        chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                                h, m, 0, inst.birth_lat, inst.birth_lon, inst.birth_tz)
        asc_of[(h, m)] = chart["ascendant"]["longitude"]

    top_asc = asc_of[(s2_candidates[0][0], s2_candidates[0][1])]
    band = [(h, m, sc2) for (h, m, sc2) in s2_candidates
            if _angle_dist(asc_of[(h, m)], top_asc) <= stage2_band_deg]

    # ---- STAGE III -- Primary Directions + Solar Arcs on the Stage-II band ----
    pd_map, sa_map = {}, {}
    for h, m, _ in band:
        pd_map[(h, m)], _ = stage3_pd(ticker, h, m, events)
        chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                                h, m, 0, inst.birth_lat, inst.birth_lon, inst.birth_tz)
        sa_map[(h, m)], _ = solar_arc_hits(chart, events)

    n_pd = _norm([pd_map[(h, m)] for h, m, _ in band])
    n_sa = _norm([sa_map[(h, m)] for h, m, _ in band])
    s3_map = {band[i][:2]: 0.5 * n_pd[i] + 0.5 * n_sa[i]
              for i in range(len(band))}

    # ---- report ----
    combined = []
    for i, (h, m, sc2) in enumerate(band):
        sc1, sig1 = stage1_score(ticker, h, m, events)
        s3n = s3_map[(h, m)]
        # simple combined = Stage I + Stage II (Stage III is corroboration only)
        c = sc1 + sc2
        combined.append((c, sc1, sc2, pd_map[(h, m)], sa_map[(h, m)],
                         sig1, h, m, s3n))
    combined.sort(key=lambda x: -x[0])

    print(f"\n{'=' * 82}")
    print(f" {ticker} -- RECTIFICATION (manual 3-stage funnel)  |  {n_ev} events, {grid_minutes}min grid")
    print(f"{'=' * 82}")
    print(f"  STAGE I   SIGN          -> {win_sign}  ({win_sig['sect']}, Moon {win_sig['moon_sign']} "
          f"{win_sig['moon_separates']}->{win_sig['moon_applies']}; Fidaria {win_sig['fidaria_match']}/{win_sig['fidaria_total']}; "
          f"Moon-nature sep {win_sig['moon_sep_match']}/{win_sig['event_total']} app {win_sig['moon_app_match']}/{win_sig['event_total']})")
    print(f"  STAGE II  RANGE 1-4deg   {len(s2_candidates)} candidates in {win_sign} -> "
          f"{len(band)} within +-{stage2_band_deg}deg of best ASC")
    print(f"  STAGE III DEG/MIN       Placidus PT + Solar Arcs (CORROBORATION ONLY for assets)")
    print(f"{'-' * 82}")
    print(f"  {'rank':>4} {'time':>8} {'comb':>7} {'I(sign)':>8} {'II(parts)':>10} {'III(PD)':>8} {'III(SA)':>8} {'III(norm)':>9}  sect/ASC-sign")
    for i, (c, s1, s2, s3pd, s3sa, sig, h, m, s3n) in enumerate(combined[:14], 1):
        print(f"  {i:>4} {h:02d}:{m:02d} {c:>7.3f} {s1:>8.3f} {s2:>10.1f} {s3pd:>8.1f} {s3sa:>8.1f} {s3n:>9.3f}  {sig['sect'][:3]}/{sig['asc_sign']}")

    if not combined:
        return []

    # winner detail
    top = combined[0]
    c, s1, s2, s3pd, s3sa, sig, h, m, s3n = top
    print(f"\n  WINNER {h:02d}:{m:02d} UTC  (ASC={sig['asc_sign']}, {sig['sect']}, "
          f"Moon={sig['moon_sign']}({sig['moon_separates']}->{sig['moon_applies']}), "
          f"Fidaria-match={sig['fidaria_match']}/{sig['fidaria_total']})")
    _, hits3 = stage3_pd(ticker, h, m, events)
    if hits3:
        print(f"  Stage III PD hits (within +-7d):")
        for err, ev_date, ev_label, ev_pl, sigp, asp, motion, adir, ddate, sc in hits3:
            print(f"    {ev_date} [{ev_pl:6s}] {ev_label[:46]:46s} {sigp} {asp} {motion}/{adir} -> {ddate} ({err}d)")
    else:
        print(f"  Stage III PD hits: (none within +-7d -- expected; assets don't converge on PD alone)")

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
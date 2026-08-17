#!/usr/bin/env python3
"""
EVENT-DRIVEN RECTIFICATION — Placidus (PT) primary directions.

Rebuild of action_rectify per *A Rectification Manual* (Zoller) Ch.14-15:

  * Events of Martian/Saturnian/Solar nature (crashes, panics, peaks, structural
    breaks) are matched to PRIMARY DIRECTIONS of Mars/Saturn/Sun to the ASC/MC.
  * Directions use the PTOLEMY / PLACIDUS (PT) engine in placidian_pd.py.
  * Score = how many known event dates are "hit" by a direction within a tight
    orb (±3 days).  Mars/Saturn hits are weighted higher (manual: "Mars always
    leaves his mark").

This deliberately replaces the old grid-search-maximizes-backtest approach with
event-matching (no overfitting to price data).

Usage:  python3 rectify_event.py [ticker]   (default: GC, ES, NQ)
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from astro_core_v2 import calculate_chart
from astro_configs import INSTRUMENTS
from event_db import get_events
from placidian_pd import direction, CONJ, SEXTILE, SQUARE, TRINE, OPPOSITION

PROMITTORS = ["Mars", "Saturn", "Sun"]
ASPECTS = [CONJ, SEXTILE, SQUARE, TRINE, OPPOSITION]
ASPECT_NAMES = {0: "conj", 60: "sextile", 90: "square", 120: "trine", 180: "opp"}
SIGNIFICATORS = ["ASC", "MC"]
MOTIONS = ["direct", "converse"]
ASPECT_DIRS = ["sinister", "dexter"]

# manual: Mars/Saturn are the rectification workhorses; Sun marks peaks
PROM_WEIGHT = {"Mars": 1.5, "Saturn": 1.5, "Sun": 1.0}

DAYS_TIGHT = 3
DAYS_GOOD = 7


def build_chart(ticker: str, hour: int, minute: int = 0) -> dict:
    inst = INSTRUMENTS[ticker]
    return calculate_chart(
        inst.birth_year, inst.birth_month, inst.birth_day,
        hour, minute, 0,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )


def chart_directions(chart: dict, max_arc_deg: float = 100.0) -> list:
    """All PT directions of Mars/Saturn/Sun to ASC/MC within max_arc years.

    Returns [(direction_date, promittor, significator, aspect, motion, aspect_dir)].
    """
    out = []
    for sig in SIGNIFICATORS:
        for prom in PROMITTORS:
            for asp in ASPECTS:
                for motion in MOTIONS:
                    for adir in ASPECT_DIRS:
                        d = direction(chart, prom, asp, sig,
                                      motion=motion, aspect_dir=adir,
                                      use_lat_prom=False, use_lat_sig=False)
                        if d is None or d["arc_deg"] > max_arc_deg:
                            continue
                        out.append((d["date"], prom, sig, asp, motion, adir))
    return out


def score_time(ticker: str, hour: int, minute: int, events: list) -> "tuple[float, list]":
    """Score one candidate birth time against the event database.

    Returns (score, hits) where hits are (error_days, event_date, event_label,
    promittor, significator, aspect, motion, aspect_dir, direction_date).
    """
    chart = build_chart(ticker, hour, minute)
    dirs = chart_directions(chart)
    hits = []
    total = 0.0

    if not dirs:
        return 0.0, []

    for ev_date, ev_planet, ev_label in events:
        try:
            ev_dt = datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue

        # find the closest direction to this event date
        nearest = None
        for d_date, prom, sig, asp, motion, adir in dirs:
            err = abs((d_date.date() - ev_dt.date()).days)
            if nearest is None or err < nearest[0]:
                nearest = (err, d_date, prom, sig, asp, motion, adir)

        if nearest is None:
            continue
        err, d_date, prom, sig, asp, motion, adir = nearest

        if err <= DAYS_TIGHT:
            w = PROM_WEIGHT.get(prom, 1.0)
            # solar events favour Sun as promittor; martian/saturnian favour malefics
            if ev_planet == "Sun" and prom == "Sun":
                w *= 1.2
            if ev_planet in ("Mars", "Saturn") and prom in ("Mars", "Saturn"):
                w *= 1.2
            score = w * 3.0
            total += score
            hits.append((err, ev_date, ev_label, prom, sig, ASPECT_NAMES[asp],
                         motion, adir, d_date.strftime("%Y-%m-%d"), score))
        elif err <= DAYS_GOOD:
            w = PROM_WEIGHT.get(prom, 1.0)
            score = w * 1.0
            total += score
            hits.append((err, ev_date, ev_label, prom, sig, ASPECT_NAMES[asp],
                         motion, adir, d_date.strftime("%Y-%m-%d"), score))

    return total, hits


def rectify(ticker: str, grid_minutes: int = 15, hour_range=(-6, 6)):
    """Grid-search birth hour/minute around the current rectified time.

    Returns sorted list of (score, hour, minute, n_hits, hits).
    """
    events = get_events(ticker)

    # seed from current rectified time
    seed_hour = 12
    try:
        with open(os.path.join(os.path.dirname(__file__), "rectified_times_v3.json")) as f:
            rt = json.load(f).get(ticker, {})
        seed_hour = rt.get("hour", 12)
    except Exception:
        pass

    results = []
    for dh in range(hour_range[0], hour_range[1] + 1):
        hour = (seed_hour + dh) % 24
        for minute in range(0, 60, grid_minutes):
            sc, hits = score_time(ticker, hour, minute, events)
            results.append((sc, hour, minute, hits))

    results.sort(key=lambda x: -x[0])
    top = results[:15]
    print(f"\n{ticker} — {len(events)} events | seed {seed_hour:02d}h | grid {grid_minutes}min")
    print(f"  {'score':>6} {'time':>6} {'hits':>4}")
    for sc, h, m, hits in top:
        print(f"  {sc:>6.2f} {h:02d}:{m:02d} {len(hits):>4}")
    return top


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else None
    tickers = [tk] if tk else ["GC", "ES", "NQ"]
    for t in tickers:
        rectify(t)

#!/usr/bin/env python3
"""
EVENT-DRIVEN RECTIFICATION — per A Rectification Manual Ch 14-15.

Rebuild of action_rectify: instead of grid-searching birth hour to maximize
backtest pattern score (overfitting), we match the contract's MAJOR EVENTS
(crashes/panics/peaks — Martian/Saturnian/Solar) to PRIMARY DIRECTIONS of
Mars/Saturn/Sun to the Asc/MC.

Stage III method (the "scalpel"): for each candidate birth time, compute
primary-direction arcs of the malefics+Sun to the angles; the arcs (in degrees ≈
years) give direction DATES. Score = how many event dates are "hit" by a
direction within a tight orb (±3 days for angles, the manual says directions to
angles are exact to a few days).

input seed times from INSTRUMENTS birth dates + current rectified hours;
grid-search minutes/hours around them.

Usage: python3 rectify_event.py [ticker]
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
from datetime import datetime, timedelta
from astro_core_v2 import calculate_chart, primary_direction_arc, direction_date, get_longitude, get_latitude
from event_db import get_events
from astro_configs import INSTRUMENTS

PROMITTORS = ["Mars", "Saturn", "Sun"]
ASPECTS = [0, 60, 90, 120, 180]  # conjunction, sextile, square, trine, opposition
SIGNIFICATORS = ["ASC", "MC"]

def build_chart(ticker, hour, minute=0):
    inst = INSTRUMENTS[ticker]
    local_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day, hour, minute, 0)
    return calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )

def chart_directions(chart):
    """Return list of (direction_date, promittor, significator, aspect) for all
    primary directions of Mars/Saturn/Sun to ASC/MC within a useful arc range."""
    out = []
    birth_utc = chart['utc_time']
    for sig in SIGNIFICATORS:
        for prom in PROMITTORS:
            for asp in ASPECTS:
                # Try both motions; take the SHORTEST arc (the actual direction date).
                best_arc = None
                for motion in ('direct', 'converse'):
                    try:
                        arc = primary_direction_arc(chart, sig, prom, asp, motion, False, False)
                    except Exception:
                        continue
                    if best_arc is None or arc < best_arc:
                        best_arc = arc
                if best_arc is None:
                    continue
                arc = best_arc
                # arc in degrees; 1 deg ~ 1 year. Keep 0-60 years (birth→lifetime).
                if arc > 60:
                    continue
                d = direction_date(birth_utc, arc)
                out.append((d, prom, sig, asp, arc))
    return out

def score_time(ticker, hour, minute, events, orb_days=5.0):
    """Score a candidate birth time by how well its directions hit events."""
    chart = build_chart(ticker, hour, minute)
    dirs = chart_directions(chart)
    if not dirs:
        return 0.0, []
    hits = []
    score = 0.0
    for ev_date, ev_planet, label in events:
        edt = datetime.strptime(ev_date, "%Y-%m-%d")
        best = None; best_delta = 1e9
        for d, prom, sig, asp, arc in dirs:
            delta = abs((d - edt).total_seconds()) / 86400.0
            if delta < best_delta:
                best_delta = delta; best = (d, prom, sig, asp, arc)
        if best and best_delta <= orb_days:
            # weight: closer = higher; malefic hit = stronger; score in [0,1] per hit
            w = 1.0 - (best_delta / orb_days)
            score += w
            hits.append((ev_date, ev_planet, round(best_delta,1), best[1], best[2], best[3], round(best[4],1), label))
    return score, hits

def rectify(ticker, grid_minutes=15, hour_range=(-6, +6)):
    events = get_events(ticker)
    inst = INSTRUMENTS[ticker]
    # seed from current rectified hour if present
    try:
        with open(os.path.join(os.path.dirname(__file__), "rectified_times_v3.json")) as f:
            rt = json.load(f).get(ticker, {})
        seed_hour = rt.get("hour", 12)
    except Exception:
        seed_hour = 12

    best = (-1, None, None, [])
    print(f"\n{ticker} — {len(events)} events, grid {grid_minutes}min, seed hour {seed_hour} ± {hour_range}")
    results = []
    for dh in range(hour_range[0], hour_range[1]+1):
        hour = (seed_hour + dh) % 24
        for minute in range(0, 60, grid_minutes):
            sc, hits = score_time(ticker, hour, minute, events)
            results.append((sc, hour, minute, len(hits), hits))
    results.sort(key=lambda x: -x[0])
    top = results[:10]
    print(f"  {'score':>6} {'time':>6} {'hits':>4}")
    for sc, h, m, nh, _ in top:
        print(f"  {sc:>6.2f} {h:02d}:{m:02d} {nh:>4}")
    return top

if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv)>1 else None
    tickers = [tk] if tk else ["GC","ES","NQ"]
    for t in tickers:
        rectify(t)

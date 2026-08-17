#!/usr/bin/env python3
"""
EVENT-DRIVEN RECTIFICATION — Placidus (PT) primary directions, full method.

Per *A Rectification Manual* (Zoller, 3rd ed.):

  * PRIMARY DIRECTION SEQUENCE: each direction produces a *date pair* (full-lat
    + zero-lat) for angle significators, or 4 dates for planet significators.
    An event is counted as "hit" if it falls within the date bookends.
  * PROMITTORS: Mars, Saturn, Sun, Jupiter, North Node (the manual's workhorses).
  * SIGNIFICATORS: ASC, MC, Moon, Sun (the fixed points receiving the direction).

Scoring matches known Martian/Saturnian/Solar events — crashes, panics, peaks,
structural breaks — against Placidus PT primary directions.  No backtest
overfitting; this is the manual's Stage III method.

Usage:  python3 rectify_event.py [ticker]   (default: GC, ES, NQ)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from astro_core_v2 import calculate_chart
from astro_configs import INSTRUMENTS
from placidian_pd import (
    direction, CONJ, SEXTILE, SQUARE, TRINE, OPPOSITION,
)

# ── Merged event database ────────────────────────────────────────────
# event_db.EVENTS (curated Mars/Saturn/Sun labels) + rectify_v3.ASSET_EVENTS
# (richer date coverage).  Preferences: event_db label where dates overlap;
# rectify_v3 adds unique dates.

_EV_db: dict  = None  # lazy import

def _load_event_db():
    global _EV_db
    from event_db import EVENTS as edb_ev
    from rectify_v3 import ASSET_EVENTS as rv3_ev
    _EV_db = {}
    for tk in ("GC","ES","NQ"):
        merged = {}  # date -> (planet, label)
        # event_db first (higher quality)
        for (_tk, ds, pl, lb) in edb_ev:
            if _tk == tk:
                merged[ds] = (pl, lb)
        # rectify_v3 adds unique dates
        for (ds, lb, pl, _, wt, comment) in rv3_ev.get(tk, []):
            if ds not in merged:
                # map planet hints to canonical keys
                canon = {"mars":"Mars","saturn":"Saturn","sun":"Sun",
                         "jupiter":"Jupiter","venus":"Venus","moon":"Moon","":""}
                pl2 = canon.get(pl, "").title() if pl else ""
                merged[ds] = (pl2, lb)
        # filter to only dated, labeled events with a planet
        _EV_db[tk] = [(d, p, l) for d,(p,l) in sorted(merged.items()) if p and l]
    return _EV_db

def get_events(ticker: str) -> list:
    db = _load_event_db()
    return db.get(ticker, [])


# ── Scoring ───────────────────────────────────────────────────────────

# The manual's Stage III discipline (ch.14): "Directions of Mars, Saturn, and
# the Sun to the Ascendant and Midheaven produce the most consistently timed
# events."  A Martian event is timed by a MARS direction; a Saturnian event by
# SATURN; a solar event by the SUN.  We do NOT brute-force every planet to
# every point — that manufactures spurious near-matches.
PROMITTORS = ["Mars", "Saturn", "Sun"]
SIGNIFICATORS = ["ASC", "MC"]
ASPECTS = [CONJ, SEXTILE, SQUARE, TRINE, OPPOSITION]
ASPECT_NAMES = {0:"cjn", 60:"sex", 90:"sq", 120:"tri", 180:"opp"}
MOTIONS = ["direct", "converse"]
ASPECT_DIRS = ["sinister", "dexter"]

PLANET_WEIGHT = {"Mars":1.5, "Saturn":1.5, "Sun":1.2}

DAYS_TIGHT = 3
DAYS_GOOD  = 7


def build_chart(ticker: str, hour: int, minute: int = 0) -> dict:
    inst = INSTRUMENTS[ticker]
    return calculate_chart(
        inst.birth_year, inst.birth_month, inst.birth_day,
        hour, minute, 0,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )


def score_time(ticker: str, hour: int, minute: int,
               events: list, max_arc: float = 100.0) -> "tuple[float,list]":
    """Score one candidate birth time.

    For each event we compute the directions of ITS OWN astro-planet (Mars,
    Saturn, or Sun) to the ASC/MC — with BOTH zero-latitude and full-latitude
    (Primary Direction Sequence).  An event is "hit" if either the zero-lat or
    full-lat date lands within a tight orb.  A hit where BOTH lat variants land
    close (a true sequence) scores higher.
    """
    chart = build_chart(ticker, hour, minute)

    # directions of each promittor -> each angle, zero & full lat, all aspects/motions/dirs
    dirs_by_prom = {}
    for prom in PROMITTORS:
        lst = []
        for sig in SIGNIFICATORS:
            for asp in ASPECTS:
                for motion in MOTIONS:
                    for adir in ASPECT_DIRS:
                        for lat_kind, lp, ls in (("zero", False, False), ("full", True, False)):
                            d = direction(chart, prom, asp, sig, motion, adir,
                                          use_lat_prom=lp, use_lat_sig=ls)
                            if d and d["arc_deg"] <= max_arc:
                                lst.append((d["date"], sig, asp, motion, adir, lat_kind))
        dirs_by_prom[prom] = lst

    total = 0.0
    hits  = []

    for ev_date, ev_planet, ev_label in events:
        try:
            ev_dt = datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue

        # the event is timed by ITS own planet's directions
        if ev_planet not in dirs_by_prom:
            continue
        cands = dirs_by_prom[ev_planet]

        # nearest zero-lat and full-lat direction date for this event
        best_zero = None   # (err, date, sig, asp, motion, adir)
        best_full = None
        for d_date, sig, asp, motion, adir, lat_kind in cands:
            err = abs((d_date - ev_dt).days)
            rec = (err, d_date, sig, asp, motion, adir)
            if err <= DAYS_GOOD:
                if lat_kind == "zero":
                    if best_zero is None or err < best_zero[0]:
                        best_zero = rec
                else:
                    if best_full is None or err < best_full[0]:
                        best_full = rec

        best = best_zero if best_zero else best_full
        if best is None:
            continue
        err, d_date, sig, asp, motion, adir = best

        # score
        w = PLANET_WEIGHT.get(ev_planet, 1.0)
        sequence_bonus = 0.0
        if best_zero is not None and best_full is not None:
            # both lat variants corroborate -> true Primary Direction Sequence
            sequence_bonus = 0.6 * w

        if err <= DAYS_TIGHT:
            score = w * 3.0 + sequence_bonus
        else:
            score = w * 1.5 + sequence_bonus

        total += score
        hits.append((
            err,
            ev_date,
            ev_label,
            ev_planet,
            sig,
            ASPECT_NAMES.get(asp, str(asp)),
            motion,
            adir,
            d_date.strftime("%Y-%m-%d"),
            score,
        ))

    return total, hits


def rectify(ticker: str, grid_minutes: int = 15):
    """Grid-search birth time around current rectified time.

    Returns sorted list of (score, hour, minute, hits).
    """
    events = get_events(ticker)

    seed_hour = 12
    try:
        with open(os.path.join(os.path.dirname(__file__), "rectified_times_v3.json")) as f:
            rt = json.load(f).get(ticker, {})
        seed_hour = rt.get("hour", 12)
    except Exception:
        pass

    # search all 24h at grid resolution
    results = []
    for h in range(24):
        for m in range(0, 60, grid_minutes):
            sc, hits = score_time(ticker, h, m, events)
            results.append((sc, h, m, hits))
    results.sort(key=lambda x: -x[0])

    top = results[:12]
    n_ev = len(events)
    print(f"\n{ticker} — {n_ev} events | seed {seed_hour:02d}h | grid {grid_minutes}min")
    print(f"  {'score':>6} {'time':>6} {'hits':>4}")
    for sc, h, m, hits in top:
        print(f"  {sc:>6.2f} {h:02d}:{m:02d}  {len(hits):>4}")
    return top


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else None
    tickers = [tk] if tk else ["GC", "ES", "NQ"]
    for t in tickers:
        rectify(t)
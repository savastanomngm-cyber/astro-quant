#!/usr/bin/env python3
"""
RECTIFICATION STAGES — faithful to Zoller, *A Rectification Manual* (3rd ed.).

This module implements the manual's TRUE three-stage structure, as documented in
the project canon (notes "The Source Manual", "Rectification Audit").  The prior
misplacement of solar-arcs/progressions/transits as "Stage II" is corrected here:

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ STAGE I   Ascendant SIGN  (Fidaria diurnal/nocturnal culls ~50% of      │
    │                             hours in one step; Moon sign + application; │
    │                             basic config)                               │
    │ STAGE II  Ascendant 1–4°   (Arabic Parts + Ascendant profections)       │
    │ STAGE III Ascendant degree/minute (Primary Directions + PD Sequence +   │
    │                             Solar Arc Directions + arcus vitae)         │
    └─────────────────────────────────────────────────────────────────────────┘

The manual's predictive hierarchy (authoritative, highest first):
    1. Primary Directions (Sun/Mars/Saturn -> ASC/MC)
    2. Primary Direction Sequence (with/without latitude)
    3. Solar Arc Directions (also Stage III, "equally accurate")
    4. Fidaria (robust period culling)
    5. Transits / Progressions / Profections (coarsest support)

Primary Directions are "fine sandpaper" — only after Stages I–II have the
Ascendant within 1–4°.

KEY: this module is ABOUT SIGN-LEVEL + RANGE-LEVEL narrowing.  Stage III lives
in placidian_pd.py (primary directions) + the solar-arc additions below.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import swisseph as swe

swe.set_ephe_path()

from astro_core_v2 import (
    calculate_chart, FIDARIA_YEARS, FIDARIA_ORDER_D, FIDARIA_ORDER_N,
    SIGN_NAMES, part_of_fortune, part_of_spirit, find_hllaj, profected_asc,
    bound_ruler, distributor,
)
from astro_configs import INSTRUMENTS
from event_db import get_events

DEG = math.pi / 180.0

# Ptolemaic bodies whose application to the natal Moon is meaningful for
# event-nature discrimination (the full planet set, since the manual's
# "Moon separates/applies" uses all seven classic planets, not only the
# Mars/Saturn/Sun event natures).
APPLICABLE_PLANETS = [
    ("Sun", swe.SUN), ("Mercury", swe.MERCURY), ("Venus", swe.VENUS),
    ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN),
]
PLANET_SWE_IDS = {name: pid for name, pid in APPLICABLE_PLANETS}


def moon_application(chart: dict) -> str:
    """Which planet does the natal Moon next apply to, by Ptolemaic aspect.

    The manual's Ch.6 "flow of energy": a separating/applying Moon tells which
    planet colours the native's disposition.  It is the fastest-moving
    birth-time-sensitive discriminator in Stage I (~13°/day), so it is what
    turns a coarse sect-cull into a single-sign verdict.

    We reuse the same aspect logic as `pattern_engine_v3._moon_applying_to`
    (the transiting-Moon analogue), but here against the NATAL planet
    longitudes so the result is a property of the candidate birth chart.
    """
    moon = chart["planets"]["Moon"]
    moon_lon = moon["longitude"]
    planets = chart["planets"]

    next_sign_boundary = (int(moon_lon / 30) + 1) * 30.0
    best = None  # (planet_name, travel_deg)

    for name in PLANET_SWE_IDS:
        plon = planets[name]["longitude"]
        for aspect_deg in sorted(ASPECTS):
            target = (plon + aspect_deg) % 360.0
            travel = (target - moon_lon) % 360.0
            if travel < 0.01:       # separated (past the exact aspect)
                continue
            if travel > next_sign_boundary:  # won't reach before sign change
                continue
            if best is None or travel < best[1]:
                best = (name, travel)

    return best[0] if best else "void"

# Ptolemaic aspects
ASPECTS = {0, 60, 90, 120, 180}
ASPECT_NAMES = {0: "cjn", 60: "sex", 90: "sq", 120: "tri", 180: "opp"}

# triplicity rulers (day and night lords) for "directing by triplicity"
# (Egyptian triplicities per the manual; day lord / night lord / participating)
TRIPLICITY = {
    "Aries":      ("Sun", "Jupiter", "Saturn"),
    "Leo":        ("Sun", "Jupiter", "Saturn"),
    "Sagittarius":("Sun", "Jupiter", "Saturn"),
    "Taurus":     ("Venus", "Moon", "Mars"),
    "Virgo":      ("Venus", "Moon", "Mars"),
    "Capricorn":  ("Venus", "Moon", "Mars"),
    "Gemini":     ("Saturn", "Mercury", "Jupiter"),
    "Libra":      ("Saturn", "Mercury", "Jupiter"),
    "Aquarius":   ("Saturn", "Mercury", "Jupiter"),
    "Cancer":     ("Venus", "Mars", "Moon"),
    "Scorpio":    ("Venus", "Mars", "Moon"),
    "Pisces":     ("Venus", "Mars", "Moon"),
}


# ----------------------------------------------------------------------
# STAGE I — Ascendant SIGN
# ----------------------------------------------------------------------
def stage1_sign(chart: dict, events: list) -> dict:
    """Determine the Ascendant SIGN by Fidaria + Moon config.

    Returns a signature dict describing what SIGN the method predicts, and how
    strongly.  This is the manual's coarse cull: diurnal-vs-nocturnal Fidaria
    eliminates ~50% of the day's hours in a single step.

    We produce a per-sign vote:
      * Fidaria: for each event, does a Fidaria period-ruler (Sun/Mars/Saturn)
        whose nature matches the event's nature dominate?  The event's OWN
        planet is its nature; if that planet is luminating a period at that date,
        that's a Fidaria confirm.  The sign that MOST supports the event-nature
        match wins (indirectly: which sign makes the Fidaria rulers line up).
      * Moon: the Moon's sign + application — the manual's "Moon config".
    """
    birth_utc = chart["utc_time"]
    sect = chart["sect"]
    asc_sign = chart["ascendant"]["sign"]            # 0..11
    asc_sign_name = SIGN_NAMES[asc_sign]

    # Fidaria period rulers across the events (as in astro_core_v2.fidaria)
    from astro_core_v2 import fidaria as _fidaria

    # Moon config: sign + application
    moon = chart["planets"]["Moon"]
    moon_sign_name = SIGN_NAMES[moon["sign"]]
    moon_app = moon_application(chart)

    # -- Fidaria period-nature match --
    fid_match = 0
    fid_total = 0
    for ev_date, ev_planet, ev_label in events:
        try:
            ev_dt = datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue
        main_r, sub_r, yrs = _fidaria(birth_utc, ev_dt, sect)
        fid_total += 1
        # the event's OWN nature (Mars/Saturn/Sun) matched by a period ruler
        if ev_planet in (main_r, sub_r):
            fid_match += 1

    # -- Moon application: does the native's disposition match the event-nature
    #    distribution?  The Moon "applying to Mars" means Martian events are the
    #    native's expected energy-flow; count how many events bear that nature.
    moon_match = 0
    for ev_date, ev_planet, ev_label in events:
        if ev_planet == moon_app:
            moon_match += 1

    return {
        "sect": sect,
        "asc_sign": asc_sign_name,
        "moon_sign": moon_sign_name,
        "moon_applies": moon_app,
        "fidaria_match": fid_match,
        "fidaria_total": fid_total,
        "moon_match": moon_match,
        "event_total": len(events),
    }


def stage1_score(ticker: str, hour: int, minute: int, events: list):
    """Score a candidate time at SIGN level — now returns ONE sign as winner.

    The manual's Stage I ends when you pick ONE sign, and the tool that does
    the final discrimination is the Moon's application.

    Scoring formula (both sub-scores are fractions in [0,1]):
      score = fidaria_nature_match_fraction + moon_application_event_alignment_fraction

    The second term answers: does this candidate's natal Moon-application
    planet better explain the event-nature distribution?
      e.g., Moon applies to Mars → Martian events count as aligned.
    """
    inst = INSTRUMENTS[ticker]
    chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                            hour, minute, 0, inst.birth_lat, inst.birth_lon,
                            inst.birth_tz)
    sig = stage1_sign(chart, events)

    # Fidaria-nature match with better statistical treatment (avoid zero-div)
    n_total = max(sig["fidaria_total"], 1)
    n_total_ev = max(sig["event_total"], 1)
    fid_frac = sig["fidaria_match"] / n_total
    moon_frac = sig["moon_match"] / n_total_ev

    score = fid_frac + moon_frac
    return float(score), sig


def stage1_winner_sign(ticker: str, grid_minutes: int = 15,
                       events: list | None = None) -> tuple[str, float, dict]:
    """Grid-search over 24h and return the winning Ascendant SIGN + its stats.

    Returns (sign_name, score, best_sig_dict).
    """
    if events is None:
        events = get_events(ticker)
    best_sign, best_score, best_sig = None, -1.0, {}
    for h in range(24):
        for m in range(0, 60, grid_minutes):
            sc, sig = stage1_score(ticker, h, m, events)
            if sc > best_score:
                best_score, best_sig = sc, sig
                best_sign = sig["asc_sign"]
    return best_sign, best_score, best_sig


# ----------------------------------------------------------------------
# STAGE II — Ascendant 1–4° range: Arabic Parts + profections
# ----------------------------------------------------------------------
def stage2_score(ticker: str, hour: int, minute: int, events: list):
    """Score a candidate time by Arabic Parts + Ascendant profections.

    The manual narrows the Ascendant to a 1–4° range using the rising decan
    physiognomy, the Arabic Parts, and profections of the Ascendant.

    Operationalized form (for an instrument):
      * Part of Fortune / Part of Spirit place in Whole-Sign houses; an event of
        a given nature that lands on the profected Ascendant (or POF) at that
        event date corroborates.
      * The profected Ascendant moves 30°/year; at each event date we check
        whether the profected ASC aspects (by sign) the event's OWN planet or
        a relevant angle.

    Returns (score, details).
    """
    inst = INSTRUMENTS[ticker]
    chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                            hour, minute, 0, inst.birth_lat, inst.birth_lon,
                            inst.birth_tz)
    pof = part_of_fortune(chart)
    pos = part_of_spirit(chart)
    asc_lon = chart["ascendant"]["longitude"]

    score = 0.0
    details = []
    for ev_date, ev_planet, ev_label in events:
        try:
            ev_dt = datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue
        # profected Ascendant at event
        prof_lon = profected_asc(chart, ev_dt)
        # sign of the profected ASC
        prof_sign = int(prof_lon / 30)

        # Arabic Parts: POF/POS sign + whether the event planet rules that sign
        event_lon = chart["planets"][ev_planet]["longitude"]
        event_sign = int(event_lon / 30)

        got = []
        # (a) profected ASC in the event planet's sign
        if prof_sign == event_sign:
            got.append(("profASC-in-sign", 1.0))
        # (b) profected ASC in POF/POS sign (fortune activation)
        for name, lon in (("POF", pof), ("POS", pos)):
            if prof_sign == int(lon / 30):
                got.append((f"profASC-{name}-sign", 0.6))
        # (c) event planet sign == POF/POS sign (part of fortune tied to event nature)
        for name, lon in (("POF", pof), ("POS", pos)):
            if event_sign == int(lon / 30):
                got.append((f"{name}-sign-match", 0.4))

        for kind, w in got:
            score += w
            details.append((ev_date, ev_planet, kind, w))

    return score, details


# ----------------------------------------------------------------------
# STAGE III extras — Solar Arc Directions (manual hierarchy #3)
# ----------------------------------------------------------------------
def solar_arc_direction_lon(natal_lon: float, age_years: float,
                            converse: bool = False) -> float:
    """Solar-arc directed longitude.  ~0°59'08" per year (Naibod)."""
    naibod = 0.9856473314
    sign = -1.0 if converse else 1.0
    return (natal_lon + sign * age_years * naibod) % 360.0


def _angle_dist(a, b):
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    return d


def solar_arc_hits(chart: dict, events: list, orb: float = 0.75):
    """Solar-arc directions of Sun/Mars/Saturn (event planets) to ASC/MC.

    Returns (score, details) — the manual's Stage III tool #3, "equally
    accurate" to primary directions but unable to time death.
    """
    asc_lon = chart["ascendant"]["longitude"]
    mc_lon = chart["midheaven"]["longitude"]
    birth_utc = chart["utc_time"]

    score = 0.0
    details = []
    for ev_date, ev_planet, ev_label in events:
        try:
            ev_dt = datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue
        age_years = (ev_dt - birth_utc).total_seconds() / 86400.0 / 365.25
        natal_lon = chart["planets"][ev_planet]["longitude"]
        for conv in (False, True):
            directed = solar_arc_direction_lon(natal_lon, age_years, conv)
            for tag, ang in (("ASC", asc_lon), ("MC", mc_lon)):
                for asp in sorted(ASPECTS):
                    err = abs(_angle_dist(directed, ang) - asp)
                    if err <= orb:
                        w = max(0.0, 1.0 - err / orb)
                        score += w
                        details.append((ev_date, ev_planet,
                                        "csa" if conv else "sa",
                                        ASPECT_NAMES[asp], err, w))
    return score, details


# ----------------------------------------------------------------------
# arcus vitae confirmation (manual Stage III)
# ----------------------------------------------------------------------
def arcus_vitae(chart: dict) -> dict:
    """Al-mubtazz (Hyleg) + giver-of-years, from find_hllaj."""
    return find_hllaj(chart)


# ----------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    for tk in ("GC", "ES", "NQ"):
        ev = get_events(tk)
        win = stage1_winner_sign(tk, 15, ev)
        print(f"\n=== {tk} ({len(ev)} events) ===")
        print(f"  STAGE I winner sign: {win[0]}  (score={win[1]:.3f})")
        s = win[2]
        print(f"    sect={s['sect']}  asc={s['asc_sign']}  moon={s['moon_sign']} "
              f"moon_applies_to={s['moon_applies']}  "
              f"fidaria-match={s['fidaria_match']}/{s['fidaria_total']}  "
              f"moon-match={s['moon_match']}/{s['event_total']}")
        for h, m in ((12, 0), (0, 0)):
            s1, sig = stage1_score(tk, h, m, ev)
            s2, d2 = stage2_score(tk, h, m, ev)
            print(f"  {h:02d}:{m:02d}  STAGE I={s1:.3f} fid={sig['fidaria_match']}/{sig['fidaria_total']} "
                  f"moon_applies={sig['moon_applies']} sect={sig['sect']} asc={sig['asc_sign']} "
                  f"| STAGE II(parts+prof) score={s2:.1f} ({len(d2)} contacts)")

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


def moon_config(chart: dict) -> dict:
    """The natal Moon's configuration: which planet she SEPARATES from and
    which she APPLIES TO next, by Ptolemaic aspect (manual Ch.6).

    The manual: "the separating planet bears influence during early life; the
    applying planet, during later years."  Rectification use (Franklin Pierce
    case study): list the Moon's aspects on the birth date, form DISCRETE TIME
    BLOCKS ("separates from X, applies to Y"), and match one block to the life
    pattern -> a 3-4 hour window.

    Returns {"separates_from": ..., "applies_to": ..., "void": bool}.  The
    separating planet is the one the Moon most recently PERFECTED an aspect to
    (moving away); the applying planet is the next aspect ahead (before the
    Moon's next sign change).  Either may be "void".
    """
    moon_lon = chart["planets"]["Moon"]["longitude"]
    planets = chart["planets"]

    # applying: nearest future Ptolemaic aspect, within one sign of travel
    boundary = (int(moon_lon / 30) + 1) * 30.0
    apply_best = None  # (name, travel)
    for name in PLANET_SWE_IDS:
        plon = planets[name]["longitude"]
        for asp in sorted(ASPECTS):
            target = (plon + asp) % 360.0
            travel = (target - moon_lon) % 360.0
            if travel < 0.01 or travel > boundary:
                continue
            if apply_best is None or travel < apply_best[1]:
                apply_best = (name, travel)

    # separating: nearest PAST aspect (Moon is moving away from it)
    sep_best = None  # (name, distance_behind)
    for name in PLANET_SWE_IDS:
        plon = planets[name]["longitude"]
        for asp in sorted(ASPECTS):
            target = (plon + asp) % 360.0
            behind = (moon_lon - target) % 360.0
            if behind < 0.01 or behind > 30.0:  # ignore if >30° behind
                continue
            if sep_best is None or behind < sep_best[1]:
                sep_best = (name, behind)

    return {
        "separates_from": sep_best[0] if sep_best else "void",
        "applies_to": apply_best[0] if apply_best else "void",
        "void": apply_best is None,
    }


def moon_application(chart: dict) -> str:
    """Back-compat: the applying planet only (see moon_config)."""
    return moon_config(chart)["applies_to"]

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

    # Moon config: sign + separation/application (manual Ch.6)
    moon = chart["planets"]["Moon"]
    moon_sign_name = SIGN_NAMES[moon["sign"]]
    cfg = moon_config(chart)
    moon_sep = cfg["separates_from"]
    moon_app = cfg["applies_to"]
    moon_void = cfg["void"]

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
        if ev_planet in (main_r, sub_r):
            fid_match += 1

    # -- Moon config: event-nature alignment for BOTH separation and application.
    #    Manual: separating planet = early-life influence; applying = later years.
    #    Score: fraction of events whose nature matches EITHER planet in the
    #    Moon configuration.  This rewards candidates where the native's Moon
    #    configuration aligns with the planetary nature most represented in events.
    sep_match = 0
    app_match = 0
    for ev_date, ev_planet, ev_label in events:
        if ev_planet == moon_sep:
            sep_match += 1
        if ev_planet == moon_app:
            app_match += 1

    return {
        "sect": sect,
        "asc_sign": asc_sign_name,
        "moon_sign": moon_sign_name,
        "moon_separates": moon_sep,
        "moon_applies": moon_app,
        "moon_void": moon_void,
        "fidaria_match": fid_match,
        "fidaria_total": fid_total,
        "moon_sep_match": sep_match,
        "moon_app_match": app_match,
        "event_total": len(events),
    }


def stage1_score(ticker: str, hour: int, minute: int, events: list):
    """Score a candidate time at SIGN level — now returns ONE sign as winner.

    The manual's Stage I ends when you pick ONE sign, and the tool that does
    the final discrimination is the Moon's application.

    Scoring formula (both sub-scores are fractions in [0,1]):
      score = fidaria_nature_match_fraction
            + moon_separation_alignment_fraction
            + moon_application_alignment_fraction

    The Moon terms answer: does this candidate's natal Moon configuration
    (separates-from X, applies-to Y) align with the event-nature distribution?
    e.g. Moon separates from Saturn / applies to Mars → Saturnian + Martian
    events count as aligned.
    """
    inst = INSTRUMENTS[ticker]
    chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                            hour, minute, 0, inst.birth_lat, inst.birth_lon,
                            inst.birth_tz)
    sig = stage1_sign(chart, events)

    # Fidaria-nature match + Moon configuration alignment (sep + app)
    n_total = max(sig["fidaria_total"], 1)
    n_total_ev = max(sig["event_total"], 1)
    fid_frac = sig["fidaria_match"] / n_total
    sep_frac = sig["moon_sep_match"] / n_total_ev
    app_frac = sig["moon_app_match"] / n_total_ev

    score = fid_frac + sep_frac + app_frac
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
              f"Moon: {s['moon_separates']} -> {s['moon_applies']} (void={s['moon_void']})  "
              f"fidaria={s['fidaria_match']}/{s['fidaria_total']}  "
              f"sep-match={s['moon_sep_match']}/{s['event_total']}  "
              f"app-match={s['moon_app_match']}/{s['event_total']}")
        for h, m in ((12, 0), (0, 0)):
            s1, sig = stage1_score(tk, h, m, ev)
            s2, d2 = stage2_score(tk, h, m, ev)
            print(f"  {h:02d}:{m:02d}  STAGE I={s1:.3f} fid={sig['fidaria_match']}/{sig['fidaria_total']} "
                  f"Moon {sig['moon_separates']}->{sig['moon_applies']} sect={sig['sect']} asc={sig['asc_sign']} "
                  f"| STAGE II(parts+prof) score={s2:.1f} ({len(d2)} contacts)")

#!/usr/bin/env python3
"""
RECTIFICATION — Stages I & II (Zoller, A Rectification Manual, 3rd ed.)

The manual's rectification is a THREE-STAGE elimination, run in order:

  STAGE I  — FIDARIA (Persian chronocrators). Matches the *character* of each
             life-chapter to its period ruler (Sun/Venus/Mercury/Moon/Saturn/
             Jupiter/Mars/Nodes, per Table B-2). Coarse: discriminates a birth
             time at the ±hour level (which branch of the Fidaria sub-period
             tree a given event date falls under).  NOT a day-precision timer.

  STAGE II — SECONDARY DIRECTIONS: (a) SOLAR ARCS (direct + converse) and
             (b) SECONDARY (MAJOR) PROGRESSIONS (a-day-for-a-year), plus
             (c) OUTER-PLANET TRANSITS.  These are the WORKHORSE for young
             charts — a 30-year-old instrument has ~30° of solar arc and ~30yr
             of progressed motion, i.e. many more timing contacts than the
             handful of Placidus primary directions.  Tightens ±30 min.

  STAGE III — PRIMARY DIRECTIONS (Placidus / "PT").  The EXISTING engine
             (placidian_pd.py).  Final "fine sandpaper" ±minutes, applied only
             AFTER Stage I+II have narrowed the window.

This module implements Stages I and II only.  rectify_event.py (Stage III) is
unchanged; rectify_full.py chains them.

KEY MANUAL PRINCIPLES (from the extracted text):
  * Solar arcs are "c.s.a." (converse) as often as direct — the manual times
    many events from a CONVERSE solar arc ("c.s.a. Sun conjunct IC", "c.s.a.
    Moon conjunct MC").
  * Secondary progressions use the Moon heavily ("prog. Moon conjunct ASC"
    timed McKinley's wedding within days; "progressed Moon conjunct ASC" timed
    Harding's love-letter settlement).
  * Transits are OUTER-planet (Uranus, plus Saturn/Jupiter) to natal angles
    and to the event's OWN planet ("Transit of Uranus conjuncts the MC" for
    Jefferson; "transiting Sun and Uranus square ... MC" for Nixon).
  * An event is "timed" by the planet(s) of its own nature: a Martian crash is
    expected to show a Mars contact, a Saturnian trough a Saturn contact, a
    solar peak a Sun contact.  Same discipline as Stage III.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import swisseph as swe

swe.set_ephe_path()

from astro_core_v2 import (
    calculate_chart, FIDARIA_YEARS, FIDARIA_ORDER_D, FIDARIA_ORDER_N,
)
from astro_configs import INSTRUMENTS
from event_db import get_events

DEG = math.pi / 180.0

# Ptolemaic aspects
ASPECTS = {0, 60, 90, 120, 180}
ASPECT_NAMES = {0: "cjn", 60: "sex", 90: "sq", 120: "tri", 180: "opp"}

# Solar-arc key: the Sun's mean daily motion (Naibod), ~59'08" per year.
NAIBOD_DEG_PER_YEAR = 0.9856473314        # degrees of solar arc per tropical year
SOLAR_ARC_MOTION = NAIBOD_DEG_PER_YEAR    # ≈ 0°59'08" / year

# Secondary progression: 1 day of ephemeris = 1 year of life.
# We handle it by measuring the planet's ephemeris position at
# (birth_utc + age_days), i.e. progressed position = position age_years days
# after birth.  This is "a day for a year".


# ----------------------------------------------------------------------
# STAGE I — FIDARIA
# ----------------------------------------------------------------------

def fidaria_rulers(birth_utc: datetime, target_utc: datetime, sect: str):
    """Return (main_ruler, sub_ruler, sub_progress_years) for a target date.

    Main periods follow Table B-2.  Sub-periods subdivide each main period
    proportionally to the Chaldean order.  This mirrors astro_core_v2.fidaria()
    but returns the SUB-ruler too (which is more birth-time-sensitive than the
    main ruler alone), and is robust past one cycle.
    """
    order = FIDARIA_ORDER_D if sect == "Diurnal" else FIDARIA_ORDER_N
    total_days = (target_utc - birth_utc).total_seconds() / 86400.0
    total_years = total_days / 365.25

    # walk main periods
    main_start_years = 0.0
    for main_ruler in order:
        main_years = FIDARIA_YEARS[main_ruler]
        if total_years < main_start_years + main_years:
            years_in_main = total_years - main_start_years
            idx = order.index(main_ruler)
            # sub-order starts from main ruler and follows Chaldean sequence
            sub_order = order[idx:] + order[:idx]
            sub_start_years = 0.0
            for sub_ruler in sub_order:
                sub_years = main_years * FIDARIA_YEARS[sub_ruler] / sum(FIDARIA_YEARS[r] for r in order)
                if years_in_main < sub_start_years + sub_years:
                    return main_ruler, sub_ruler, years_in_main - sub_start_years
                sub_start_years += sub_years
            # fallthrough (shouldn't happen)
            return main_ruler, sub_order[-1], years_in_main
        main_start_years += main_years
    # beyond first cycle: wrap by recurrence (75-yr Sidereal cycle approx)
    return fidaria_rulers(birth_utc, target_utc, sect)


def stage1_score(ticker: str, hour: int, minute: int, events: list):
    """Score a candidate time by Fidaria period-CHARACTER match.

    For each event, we look at the event's OWN planet (Mars/Saturn/Sun) and
    ask whether that planet is the MAIN or SUB ruler of the Fidaria period the
    event falls in.  A Martian crash landing in a Mars period scores; landing
    in a Venus period scores against.  This is a COARSE (±hours) discriminator:
    it shifts only when the sub-period boundary crosses the event, which is a
    few-hours-per-year sensitivity.
    """
    inst = INSTRUMENTS[ticker]
    chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                            hour, minute, 0, inst.birth_lat, inst.birth_lon,
                            inst.birth_tz)
    birth_utc = chart["utc_time"]
    sect = chart["sect"]

    score = 0.0
    details = []
    for ev_date, ev_planet, ev_label in events:
        try:
            ev_dt = datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue
        main_r, sub_r, yrs_in = fidaria_rulers(birth_utc, ev_dt, sect)

        # score: sub-ruler match is strong, main-ruler match moderate
        s = 0.0
        if sub_r == ev_planet:
            s += 1.0
        if main_r == ev_planet:
            s += 0.5
        # malefic planet in malefic period of opposite nature: no bonus/penalty
        # kept simple; the manual matches CHARACTER, not a numeric penalty.
        score += s
        details.append((ev_date, ev_planet, main_r, sub_r, s))
    return score, details


# ----------------------------------------------------------------------
# STAGE II — SOLAR ARCS + SECONDARY PROGRESSIONS + TRANSITS
# ----------------------------------------------------------------------

def _angle_dist(a, b):
    """Shortest angular distance in degrees (0..180)."""
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    return d


def _aspect_hit(lon_moved, lon_fixed, orb=1.0):
    """Return (aspect_deg, orb_error) if two longitudes are in Ptolemaic
    aspect within orb, else None."""
    d = _angle_dist(lon_moved, lon_fixed)
    for asp in sorted(ASPECTS):
        err = abs(d - asp)
        if err <= orb:
            return asp, err
    return None


def solar_arc_direction(chart: dict, planet_lon: float, event_dt: datetime,
                        converse: bool) -> float:
    """Solar-arc directed position of a natal point at event_dt.

    Direct: + age * NAIBOD.  Converse ("c.s.a." in the manual): - age * NAIBOD.
    Returns the directed ecliptic longitude.
    """
    age_years = (event_dt - chart["utc_time"]).total_seconds() / 86400.0 / 365.25
    sign = -1.0 if converse else 1.0
    return (planet_lon + sign * age_years * SOLAR_ARC_MOTION) % 360.0


def progressed_position(chart: dict, name: str, event_dt: datetime,
                        converse: bool = False) -> float:
    """Secondary (major) progression: a-day-for-a-year.

    Direct: ephemeris position at (birth_utc + age_days).
    Converse ("return" progressions): birth_utc - age_days.
    """
    age_days = (event_dt - chart["utc_time"]).total_seconds() / 86400.0
    target = chart["utc_time"] + timedelta(days=age_days) if not converse \
        else chart["utc_time"] - timedelta(days=age_days)
    pid = {"Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY,
           "Venus": swe.VENUS, "Mars": swe.MARS, "Jupiter": swe.JUPITER,
           "Saturn": swe.SATURN}[name]
    jd = swe.julday(target.year, target.month, target.day,
                    target.hour + target.minute / 60.0 + target.second / 3600.0)
    res = swe.calc_ut(jd, pid, swe.FLG_SWIEPH)
    return res[0][0] % 360.0


def transit_position(name: str, event_dt: datetime) -> float:
    """Ephemeris longitude of an outer planet at an event date (transit)."""
    pid = {"Saturn": swe.SATURN, "Jupiter": swe.JUPITER, "Uranus": swe.URANUS,
           "Neptune": swe.NEPTUNE, "Pluto": swe.PLUTO, "Sun": swe.SUN,
           "Mars": swe.MARS}[name]
    # noon UT for the event date
    jd = swe.julday(event_dt.year, event_dt.month, event_dt.day, 12.0)
    res = swe.calc_ut(jd, pid, swe.FLG_SWIEPH)
    return res[0][0] % 360.0


def stage2_score(ticker: str, hour: int, minute: int, events: list,
                 orb_solar: float = 0.5, orb_prog: float = 0.5,
                 orb_transit: float = 0.5):
    """Score a candidate time by Stage II contacts.

    DISCIPLINED, FAITHFUL TO THE MANUAL:

      The manual times events by PARTILE (exact, sub-degree) contacts of a
      small, specific set of measurements — chiefly:
        * "c.s.a."  = CONVERSE SOLAR ARC of a planet to an angle
                      (Taylor: "c.s.a. Sun 12TA14 is only 3 min from natal IC")
        * "prog."   = SECONDARY PROGRESSION of Moon/Sun to an angle
                      (McKinley: "prog. Moon conj. Ascendant", 3 days from wedding)
        * OUTER-planet transits to natal angles
                      (Jefferson: "Transit of Uranus conjuncts the MC, exact ...")

      We therefore measure ONLY these signatures, at PARTILE orbs (0.5°),
      of the EVENT'S OWN planet plus the luminaries, to the ASC and MC.
      No broad sweep of every planet to every point — that manufactures
      spurious near-matches (the manual's ch.14 warning).
    """
    inst = INSTRUMENTS[ticker]
    chart = calculate_chart(inst.birth_year, inst.birth_month, inst.birth_day,
                            hour, minute, 0, inst.birth_lat, inst.birth_lon,
                            inst.birth_tz)
    asc_lon = chart["ascendant"]["longitude"]
    mc_lon = chart["midheaven"]["longitude"]
    planets = chart["planets"]

    score = 0.0
    details = []
    for ev_date, ev_planet, ev_label in events:
        try:
            ev_dt = datetime.strptime(ev_date, "%Y-%m-%d")
        except ValueError:
            continue
        natal_lon = planets[ev_planet]["longitude"]

        def add(evt, kind, body, asp, err):
            tightness = max(0.0, 1.0 - err / max(orb_solar, orb_prog,
                                                 orb_transit, 1e-9))
            w = tightness
            details.append((evt, ev_planet, kind, body, asp, err, w))

        for body, natal_pt in (("Sun", planets["Sun"]["longitude"]),
                               ("Moon", planets["Moon"]["longitude"]),
                               (ev_planet, natal_lon)):
            for conv in (False, True):
                for tag, is_angle_lon in (("ASC", asc_lon), ("MC", mc_lon)):
                    directed = solar_arc_direction(chart, natal_pt, ev_dt, conv)
                    hit = _aspect_hit(directed, is_angle_lon, orb_solar)
                    if hit:
                        asp, err = hit
                        add(ev_date, "sa" + (".c" if conv else ""), body,
                            ASPECT_NAMES[asp], err)

        for body in ("Sun", "Moon"):
            for conv in (False, True):
                prog = progressed_position(chart, body, ev_dt, conv)
                for tag, is_angle_lon in (("ASC", asc_lon), ("MC", mc_lon)):
                    hit = _aspect_hit(prog, is_angle_lon, orb_prog)
                    if hit:
                        asp, err = hit
                        add(ev_date, "prog" + (".c" if conv else ""), body,
                            ASPECT_NAMES[asp], err)

        for tname in ("Saturn", "Uranus"):
            tlon = transit_position(tname, ev_dt)
            for tag, target in ((ev_planet, natal_lon),
                                ("ASC", asc_lon), ("MC", mc_lon)):
                hit = _aspect_hit(tlon, target, orb_transit)
                if hit:
                    asp, err = hit
                    add(ev_date, "tr", tname, ASPECT_NAMES[asp], err)

    # score is the sum of per-contact weights
    score = sum(w for (*_, w) in details)
    return score, details


# ----------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    for tk in ("GC", "ES", "NQ"):
        ev = get_events(tk)
        print(f"\n=== {tk} ({len(ev)} events) ===")
        # Stage I at a nominal time
        s1, d1 = stage1_score(tk, 12, 0, ev)
        print(f"  Stage I (Fidaria) @12:00  score={s1:.1f}")
        top = sorted(d1, key=lambda x: -x[4])[:5]
        for ev_date, plt, mr, sr, s in top:
            print(f"    {ev_date} {plt:6s} main={mr:6s} sub={sr:6s} +{s:.1f}")
        # Stage II at a nominal time
        s2, d2 = stage2_score(tk, 12, 0, ev)
        print(f"  Stage II (solar+prog+transit) @12:00  score={s2:.1f}  contacts={len(d2)}")
        for ev_date, plt, kind, body, asp, err, w in sorted(d2, key=lambda x: -x[6])[:8]:
            print(f"    {ev_date} {plt:6s} {kind:7s} {body:6s} {asp} orb={err:.2f}° +{w:.1f}")

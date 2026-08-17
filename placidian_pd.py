#!/usr/bin/env python3
"""
PLACIDIAN (PTOLEMY / "PT") PRIMARY DIRECTIONS — faithful engine.

Implements the Placidus "under the pole" primary-direction algorithm as
described by Zoller's *A Rectification Manual* and the Janus/Morinus family of
software under the "Ptolemy / Placidus" (PT) label.

The manual's core formula is the horary-circle-point( HCP ) arc:

        arc = RA_prom - RA_hcp

with

        RA_hcp = MP_sig + arcsin( tan(dec_prom) * tan(phi) * cos(OA_ASC - MP_sig) )

where
  * MP_sig      = the Placidus MUNDANE POSITION of the significator
                  (its proportional meridian placement along its own semi-arc,
                   projected onto the celestial equator),
  * OA_ASC      = RAMC + 90            (oblique ascension of the Ascendant),
  * phi         = observer geographic latitude,
  * dec_prom    = declination of the promittor (aspect) point.

This is EXACTLY the algorithm published by morinus-astrology.com
("Formulas for primary direction in Placidus house system"), equation (1),
and it is the same family used by the manual's Janus 4.3 reference engine.
It reduces to the classic Ptolemaic "zodiacal, no-latitude, proportional
semi-arc" direction when latitudes are zeroed (the manual's PT default).

Notation (manual p.viii):
  * left of "=>"  = PROMITTOR   (the MOVED point; can be a planet or an aspect)
  * right of "=>" = SIGNIFICATOR (the FIXED point)
  * d. = direct motion (RA increasing, diurnal);  c. = converse (RA decreasing)
  * dex = dexter aspect (retrograde direction, longitude - aspect)
  * sin = sinister aspect (longitude + aspect)
  * (l=XX) = the point carries the natural latitude of body XX; absence = zero lat

SELF-CONTAINED: only swisseph (pyswisseph) + stdlib. No Morinus imports.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import swisseph as swe

DEG = math.pi / 180.0

# Ptolemaic aspects (degrees of longitude)
CONJ = 0
SEXTILE = 60
SQUARE = 90
TRINE = 120
OPPOSITION = 180

ASPECTS = {
    "conj": 0, "conjunction": 0,
    "sextile": 60, "sex": 60,
    "square": 90, "sq": 90,
    "trine": 120, "tri": 120,
    "opposition": 180, "opp": 180,
}

NAIBOD = 0.9856  # degrees of arc per tropical year (59'08")
PTOLEMY_KEY = 1.0  # 1 degree = 1 year (manual effectively uses this)


# ----------------------------------------------------------------------
# Coordinate transforms
# ----------------------------------------------------------------------
def ecl_to_equ(lon_deg: float, lat_deg: float, obliquity_deg: float) -> "tuple[float,float]":
    """Ecliptic (longitude, latitude) -> equatorial (RA, declination), degrees."""
    lon = lon_deg * DEG
    lat = lat_deg * DEG
    eps = obliquity_deg * DEG
    ra = math.atan2(math.sin(lon) * math.cos(eps) - math.tan(lat) * math.sin(eps),
                    math.cos(lon))
    dec = math.asin(math.sin(lat) * math.cos(eps) + math.cos(lat) * math.sin(eps) * math.sin(lon))
    return math.degrees(ra) % 360.0, math.degrees(dec)


def get_obliquity(jd_ut: float) -> float:
    """True obliquity of the ecliptic (degrees) at a given Julian day."""
    return swe.calc_ut(jd_ut, swe.ECL_NUT, 0)[0][0]


# ----------------------------------------------------------------------
# Placidus speculum helpers
# ----------------------------------------------------------------------
def ascensional_difference(decl_deg: float, geo_lat_deg: float) -> float:
    """AD = asin( tan(phi) * tan(decl) ). Returns degrees (can be negative)."""
    val = math.tan(geo_lat_deg * DEG) * math.tan(decl_deg * DEG)
    val = max(-1.0, min(1.0, val))
    return math.degrees(math.asin(val))


def placidus_mundane_position(ra_deg: float, decl_deg: float, ramc: float,
                              geo_lat_deg: float) -> float:
    """Placidus MUNDANE POSITION (MP) of a point, projected to the equator.

    Returns the RA of the equatorial point that carries the same PROPORTIONAL
    meridian distance (R = MD/SA) along its own semi-arc as the given point.
    """
    raic = (ramc + 180.0) % 360.0

    ad = ascensional_difference(decl_deg, geo_lat_deg)
    dsa = 90.0 + ad
    nsa = 90.0 - ad

    # upper vs lower meridian distance
    umd = abs(ra_deg - ramc)
    if umd > 180.0:
        umd = 360.0 - umd
    lmd = abs(ra_deg - raic)
    if lmd > 180.0:
        lmd = 360.0 - lmd

    above_horizon = umd <= dsa
    if above_horizon:
        sa = dsa
        md = umd
        mer_ref = ramc
    else:
        sa = nsa
        md = lmd
        mer_ref = raic

    if abs(sa) < 1e-12:
        # circumpolar edge — no finite semi-arc
        return None

    r = md / sa
    mp = (mer_ref + 90.0 * r) % 360.0
    return mp


# ----------------------------------------------------------------------
# The core Placidus direction
# ----------------------------------------------------------------------
def placidus_arc(prom_ra: float, prom_dec: float, sig_ra: float, sig_dec: float,
                 ramc: float, geo_lat_deg: float, motion: str = "direct") -> "float|None":
    """Placidus (under-the-pole) primary-direction arc in equatorial degrees.

    promittor aspect point (RA, dec) is directed to the significator (RA, dec).
    Returns the arc in degrees of right ascension (≈ years under Ptolemy key).

    motion: 'direct' (diurnal, RA increasing) or 'converse'.
    """
    mp_sig = placidus_mundane_position(sig_ra, sig_dec, ramc, geo_lat_deg)
    if mp_sig is None:
        return None

    oa_asc = (ramc + 90.0) % 360.0

    inner = (math.tan(prom_dec * DEG)
             * math.tan(geo_lat_deg * DEG)
             * math.cos((oa_asc - mp_sig) * DEG))
    if abs(inner) > 1.0:
        return None  # promittor cannot reach significator's circle of position
    ra_hcp = (math.degrees(math.asin(inner)) + mp_sig) % 360.0

    if motion == "direct":
        arc = (prom_ra - ra_hcp) % 360.0
    else:  # converse
        arc = (ra_hcp - prom_ra) % 360.0

    return arc


# ----------------------------------------------------------------------
# High-level direction API
# ----------------------------------------------------------------------
def compute_ramc(chart: dict) -> float:
    """Right Ascension of the Midheaven for a chart (from MC ecliptic lon + obliquity).

    Accepts a chart dict shaped like astro_core_v2.calculate_chart output.
    """
    mc_lon = chart["midheaven"]["longitude"]
    # recompute obliquity at chart's utc_time for a self-consistent RAMC
    ut = chart["utc_time"]
    jd = swe.julday(ut.year, ut.month, ut.day,
                    ut.hour + ut.minute / 60.0 + ut.second / 3600.0)
    obl = get_obliquity(jd)
    ramc, _ = ecl_to_equ(mc_lon, 0.0, obl)
    return ramc


def point_lonlat(chart: dict, name: str) -> "tuple[float,float]":
    """Resolve a point name -> (longitude, latitude).

    'ASC' / 'MC' are angles (zero latitude). Otherwise a planet name in chart['planets'].
    """
    if name == "ASC":
        return chart["ascendant"]["longitude"], 0.0
    if name == "MC":
        return chart["midheaven"]["longitude"], 0.0
    p = chart["planets"][name]
    return p["longitude"], p["latitude"]


def direction(
    chart: dict,
    promittor: str,
    aspect_deg: float,
    significator: str,
    motion: str = "direct",
    aspect_dir: str = "sinister",   # 'sinister' (+aspect) or 'dexter' (-aspect)
    use_lat_prom: bool = False,
    use_lat_sig: bool = False,
) -> "dict|None":
    """Compute one Placidus primary direction.

    Returns a dict with arc_deg, arc_years (Ptolemy & Naibod), and date,
    or None if the direction cannot rise/set (no finite arc).

    The MANUAL default for PT is zodiacal, no latitude (use_lat_*=False).
    Pass use_lat_prom=True for "(l=promittor)" and use_lat_sig=True for "(l=sig)".
    """
    ut = chart["utc_time"]
    jd = swe.julday(ut.year, ut.month, ut.day,
                    ut.hour + ut.minute / 60.0 + ut.second / 3600.0)
    obl = get_obliquity(jd)
    geo_lat = chart.get("latitude", 40.0)
    ramc = compute_ramc(chart)

    # significator (FIXED)
    sig_lon, sig_lat = point_lonlat(chart, significator)
    if not use_lat_sig:
        sig_lat = 0.0
    sig_ra, sig_dec = ecl_to_equ(sig_lon, sig_lat, obl)

    # promittor aspect point (MOVED)
    prom_lon, prom_lat = point_lonlat(chart, promittor)
    if not use_lat_prom:
        prom_lat = 0.0
    if aspect_dir == "dexter":
        aspect_deg = -aspect_deg
    prom_aspect_lon = (prom_lon + aspect_deg) % 360.0
    prom_ra, prom_dec = ecl_to_equ(prom_aspect_lon, prom_lat, obl)

    arc = placidus_arc(prom_ra, prom_dec, sig_ra, sig_dec, ramc, geo_lat, motion)
    if arc is None:
        return None

    arc_years_ptolemy = arc / PTOLEMY_KEY
    arc_years_naibod = arc / NAIBOD
    dt = ut + timedelta(days=arc_years_ptolemy * 365.25)

    return {
        "arc_deg": arc,
        "arc_years": arc_years_ptolemy,
        "arc_years_naibod": arc_years_naibod,
        "date": dt,
        "promittor": promittor,
        "aspect": aspect_deg if aspect_dir == "sinister" else -aspect_deg,
        "significator": significator,
        "motion": motion,
        "ramc": ramc,
        "obliquity": obl,
    }


# ----------------------------------------------------------------------
# Primary Direction Sequence (latitude variants, manual p.viii)
# ----------------------------------------------------------------------
def direction_sequence(chart: dict, promittor: str, aspect_deg: float,
                       significator: str, motion: str = "direct",
                       aspect_dir: str = "sinister") -> list:
    """All latitude variants for a direction.

    * significator is an angle (ASC/MC): 2 dates (prom full-lat, prom zero-lat).
    * significator is a planet: 4 dates (all prom/sig lat combinations).
    """
    is_angle = significator in ("ASC", "MC")
    out = []
    combos = [
        ("full:full", True, True),
        ("full:zero", True, False),
        ("zero:full", False, True),
        ("zero:zero", False, False),
    ]
    for label, lp, ls in combos:
        if is_angle and ls:
            continue  # angle always zero latitude
        d = direction(chart, promittor, aspect_deg, significator, motion,
                      aspect_dir, use_lat_prom=lp, use_lat_sig=ls)
        if d is not None:
            d["lat_variant"] = label
            out.append(d)
    return out


# ----------------------------------------------------------------------
# VALIDATION
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from astro_core_v2 import calculate_chart

    print("=" * 64)
    print(" PLACIDUS (PT) PRIMARY DIRECTION — VALIDATION")
    print("=" * 64)

    # George Washington, rectified birth
    ch = calculate_chart(1732, 2, 22, 5, 38, 57, 38.2289, -76.9811, -5.132)
    print("\n[Washington] birth UTC:", ch["utc_time"])
    print("  ASC = %.4f  MC = %.4f" % (
        ch["ascendant"]["longitude"], ch["midheaven"]["longitude"]))
    print("  RAMC = %.4f" % compute_ramc(ch))
    m = ch["planets"]["Moon"]; s = ch["planets"]["Saturn"]
    print("  Moon   lon=%.4f lat=%.4f" % (m["longitude"], m["latitude"]))
    print("  Saturn lon=%.4f lat=%.4f" % (s["longitude"], s["latitude"]))

    print("\n  Manual: 'sex. Saturn (dex) d. => Moon' -> 29-Jul-1752 (arc ~20.14 deg)")
    for lat_name, lp, ls, in [
        ("zero:zero (Ptolemy default)", False, False),
        ("full:zero (l=SA)", True, False),
        ("zero:full (l=MO)", False, True),
        ("full:full", True, True),
    ]:
        d = direction(ch, "Saturn", 60, "Moon", "direct", "dexter",
                      use_lat_prom=lp, use_lat_sig=ls)
        if d:
            print("    %-24s arc=%6.3f deg  date=%s" % (
                lat_name, d["arc_deg"], d["date"].strftime("%d-%b-%Y")))
        else:
            print("    %-24s -> no finite arc" % lat_name)

    # ---- Multi-example validation (manual 3rd-edition preface, authoritative) ----
    print("\n" + "=" * 64)
    print(" MULTI-EXAMPLE VALIDATION (manual, 3rd ed. preface)")
    print("=" * 64)

    from datetime import datetime as _dt

    taft = calculate_chart(1857, 9, 15, 20, 2, 26, 39.161, -84.457, -(5 + 37.5 / 60))
    truman = calculate_chart(1884, 5, 8, 15, 53, 12, 37.495, -94.276, -6)

    suite = [
        # (name, chart, prom, asp, sig, motion, adir, lp, ls, expected)
        ("Washington dex.sex Sat d.=>Moon", ch, "Saturn", 60, "Moon", "direct", "dexter", False, False, "1752-07-29"),
        ("Truman Sun c.=>MC", truman, "Sun", 0, "MC", "converse", "sinister", False, False, "1939-04-23"),
        ("Taft dex.trine Sat d.=>MC", taft, "Saturn", 120, "MC", "direct", "dexter", False, False, "1918-03-31"),
        ("Taft dex.square Jup d.=>MC", taft, "Jupiter", 90, "MC", "direct", "dexter", False, False, "1880-05-18"),
    ]
    print("  %-30s | %7s | %-11s | %-11s | %s" % ("direction", "arc", "computed", "manual", "err"))
    for name, c, prom, asp, sig, motion, adir, lp, ls, expected in suite:
        d = direction(c, prom, asp, sig, motion, adir, use_lat_prom=lp, use_lat_sig=ls)
        if d is None:
            print("  %-30s |     -- | (no arc)" % name)
            continue
        exp = _dt.strptime(expected, "%Y-%m-%d")
        err = abs((d["date"] - exp).days)
        print("  %-30s | %6.2f° | %-11s | %-11s | %dd" % (
            name, d["arc_deg"], d["date"].strftime("%Y-%m-%d"), expected, err))

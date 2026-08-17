#!/usr/bin/env python3
"""
REGIOMONTANUS PRIMARY DIRECTIONS — faithful implementation of the Morinus
reference algorithm (IngenieriaAstrologica/Morinus planets.py :: computeRegiomontanSpeculum
+ getZD + regiomontanpd.py :: toPlanet).

Formulas (exact, from reference):
  adlat   = asin( tan(lat_bod) * tan(decl) )
  DSA     = 90 + adlat        (diurnal semi-arc)
  NSA     = -(90 - adlat)     (nocturnal semi-arc, negative by convention)
  md      = meridian distance, from MC (above horizon) or IC (below)
  zd      = Regiomontanus zenith distance (see get_zd)
  pole    = asin( sin(geo_lat) * sin(zd) )
  Q       = asin( tan(decl) * tan(pole) )
  W       = RA - Q (eastern hemisphere) or RA + Q (western)
  arc     = W_promissor - W_significator   (direct motion)

  Then years = arc / key, using Naibod (0.985607° per year) — but the manual
  effectively reports 1 degree = 1 year; we keep Naibod and convert.
"""
import math
from datetime import datetime, timedelta

DEG = math.pi / 180.0

# ----------------------------------------------------------------------
# Coordinate transform
# ----------------------------------------------------------------------
def ecl_to_equ(lon_deg, lat_deg, obliquity=23.4392911):
    lon = lon_deg * DEG; lat = lat_deg * DEG; eps = obliquity * DEG
    ra = math.atan2(math.sin(lon)*math.cos(eps) - math.tan(lat)*math.sin(eps), math.cos(lon))
    dec = math.asin(math.sin(lat)*math.cos(eps) + math.cos(lat)*math.sin(eps)*math.sin(lon))
    return math.degrees(ra) % 360.0, math.degrees(dec)


# ----------------------------------------------------------------------
# Regiomontanus speculum for a single body
# ----------------------------------------------------------------------
def get_zd(md, geo_lat, decl, umd):
    """Regiomontanus zenith distance (Morinus getZD)."""
    zd = 0.0
    if abs(md - 90.0) < 1e-9:
        zd = 90.0 - math.degrees(math.atan(math.sin(abs(geo_lat * DEG)) * math.tan(decl * DEG)))
    elif md < 90.0:
        A = math.degrees(math.atan(math.cos(geo_lat * DEG) * math.tan(md * DEG)))
        B = math.degrees(math.atan(math.tan(abs(geo_lat) * DEG) * math.cos(md * DEG)))
        C = 0.0
        if (decl < 0 and geo_lat < 0) or (decl >= 0 and geo_lat >= 0):
            if umd: C = B - abs(decl)
            else:   C = B + abs(decl)
        elif (decl < 0 and geo_lat > 0) or (decl > 0 and geo_lat < 0):
            if umd: C = B + abs(decl)
            else:   C = B - abs(decl)
        F = math.degrees(math.atan(math.sin(abs(geo_lat) * DEG) * math.sin(md * DEG) * math.tan(C * DEG)))
        zd = A + F
    return zd


def speculum(ra, decl, ramc, raic, geo_lat, lat_bod):
    """Compute the Regiomontanus W (place) for a body.

    Returns dict with: ra, decl, pole, q, W, eastern, above_horizon, md, zd.
    """
    # eastern hemisphere determination
    eastern = True
    if ramc > raic:
        if raic < ra < ramc:
            eastern = False
    else:
        if (raic < ra < 360.0) or (0.0 < ra < ramc):
            eastern = False

    # adlat
    adlat = 0.0
    val = math.tan(lat_bod * DEG) * math.tan(decl * DEG)
    if abs(val) <= 1.0:
        adlat = math.degrees(math.asin(val))

    # meridian distance (from MC) and anti-meridian distance (from IC)
    med = abs(ramc - ra)
    if med > 180.0: med = 360.0 - med
    icd = abs(raic - ra)
    if icd > 180.0: icd = 360.0 - icd

    # semi-arc
    dsa = 90.0 + adlat
    nsa = 90.0 - adlat

    above_horizon = True
    md = med
    if med > dsa:
        above_horizon = False
        md = icd
        md = -md

    # zenith distance uses the absolute md (< 90 within a quadrant)
    abs_md = abs(md)
    if abs_md > 90.0:
        abs_md = 180.0 - abs_md
    umd = (md < 0.0)

    zd = get_zd(abs_md, geo_lat, decl, umd)

    # pole
    pole = math.degrees(math.asin(math.sin(geo_lat * DEG) * math.sin(zd * DEG)))

    # Q
    q = math.degrees(math.asin(math.tan(decl * DEG) * math.tan(pole * DEG)))

    # W
    if eastern:
        W = ra - q
    else:
        W = ra + q
    W = W % 360.0

    return dict(ra=ra, decl=decl, pole=pole, q=q, W=W, eastern=eastern,
                above_horizon=above_horizon, md=md, zd=zd)


# ----------------------------------------------------------------------
# Direction of a promittor-aspect to a significator
# ----------------------------------------------------------------------
def direction_arc(prom_lon, prom_lat, sig_lon, sig_lat, ramc, geo_lat,
                  motion='direct', use_lat_prom=True, use_lat_sig=True):
    """Return arc in equatorial DEGREES (divide by key for years).

    prom = promittor aspect point (the MOVED point).
    sig  = significator (the FIXED point).

    EXACT reference algorithm (Morinus getZodW):
      1. significator speculum -> (pole, eastern)
      2. promittor W computed UNDER THE SIGNIFICATOR'S pole & eastern
      3. arc = W_prom - W_sig  (direct)
    """
    raic = (ramc + 180.0) % 360.0

    # significator speculum (fixed) — its pole & eastern define the plane
    sig_ra, sig_dec = ecl_to_equ(sig_lon, sig_lat if use_lat_sig else 0.0)
    ss = speculum(sig_ra, sig_dec, ramc, raic, geo_lat, sig_lat if use_lat_sig else 0.0)

    # promittor W under the significator's pole & eastern
    prom_ra, prom_dec = ecl_to_equ(prom_lon, prom_lat if use_lat_prom else 0.0)
    pole = ss['pole']; eastern = ss['eastern']

    q = math.degrees(math.asin(math.tan(prom_dec * DEG) * math.tan(pole * DEG)))
    if eastern:
        wprom = prom_ra - q
    else:
        wprom = prom_ra + q
    wprom = wprom % 360.0

    wsig = ss['W']

    if motion == 'direct':
        arc = (wprom - wsig) % 360.0
    else:
        arc = (wsig - wprom) % 360.0

    return arc


NAIBOD = 0.9856  # degrees per year (59'08" = 0.9856°)

def arc_to_years(arc_deg):
    return arc_deg / NAIBOD


# ----------------------------------------------------------------------
# High-level: compute direction date for a chart + spec
# ----------------------------------------------------------------------
def direction_date(chart, promittor, aspect_deg, significator, motion='direct',
                   use_lat_prom=True, use_lat_sig=True):
    """chart must have 'midheaven' (with longitude), 'ascendant', 'planets' (lon+lat),
    'latitude', 'utc_time'. Returns (arc_deg, arc_years, date)."""
    geo_lat = chart.get('latitude', 40.0)

    # significator (FIXED)
    if significator == 'ASC':
        sig_lon = chart['ascendant']['longitude']; sig_lat = 0.0
    elif significator == 'MC':
        sig_lon = chart['midheaven']['longitude']; sig_lat = 0.0
    else:
        sig_lon = chart['planets'][significator]['longitude']
        sig_lat = chart['planets'][significator]['latitude'] if use_lat_sig else 0.0

    # promittor aspect point (MOVED)
    prom_lon = (chart['planets'][promittor]['longitude'] + aspect_deg) % 360.0
    prom_lat = chart['planets'][promittor]['latitude'] if use_lat_prom else 0.0

    # RAMC = right ascension of the MC (approximate by MC longitude RA)
    ramc, _ = ecl_to_equ(chart['midheaven']['longitude'], 0.0)

    arc = direction_arc(prom_lon, prom_lat, sig_lon, sig_lat, ramc, geo_lat,
                        motion, use_lat_prom, use_lat_sig)
    years = arc_to_years(arc)
    dt = chart['utc_time'] + timedelta(days=years * 365.25)
    return arc, years, dt


# ----------------------------------------------------------------------
# VALIDATION against the manual
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from astro_core_v2 import calculate_chart
    # GW: 22-Feb-1732, 5:38:57 LMT, Wakefield Corner VA (38n13'44 =38.2289, 76w58'52=-76.9811)
    # LMT tz = lon/15 = -5.132
    ch = calculate_chart(1732, 2, 22, 5, 38, 57, 38.2289, -76.9811, -5.132)
    print("=== VALIDATION: George Washington ===")
    print(f"  birth UTC: {ch['utc_time']}")
    print(f"  ASC={ch['ascendant']['longitude']:.4f}  MC={ch['midheaven']['longitude']:.4f}")
    m = ch['planets']['Moon']; s = ch['planets']['Saturn']
    print(f"  Moon lon={m['longitude']:.4f} lat={m['latitude']:.4f}")
    print(f"  Saturn lon={s['longitude']:.4f} lat={s['latitude']:.4f}")

    # Manual: PT dex sextile Saturn (l=SA) d. => Moon (l=MO)
    # promittor = sextile Saturn (Saturn+60, full lat); significator = Moon (zero lat)
    arc, years, dt = direction_date(ch, 'Saturn', 60, 'Moon', 'direct', True, False)
    print(f"\n  PT sextile Saturn d.=>Moon (l=SA):")
    print(f"    arc={arc:.3f}°  years={years:.3f}")
    print(f"    date={dt.strftime('%d-%b-%Y')}")
    print(f"    MANUAL says: 29-Jul-1752")

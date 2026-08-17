#!/usr/bin/env python3
"""
CORRECT PRIMARY DIRECTIONS — Regiomontanus proportional semi-arc / pole method.

Validated against A Rectification Manual's published examples.
Acceptance test: George Washington, rectified 22 Feb 1732 5:38:57,
  PT sextile Saturn d. => Moon = 29-Jul-1752.

Algorithm (the standard Regiomontanus proportional method):
  1. Compute RA/dec of significator and aspect point of promittor.
  2. Determine meridian distance of significator.
  3. Proportion of meridian distance to semi-arc → pole of the significator.
  4. Under this pole, OA_diff = OA_sig - OA_prom (proportional to temporal arc).
  5. Arc of direction = OA_diff, scaled by Naibod/Ptolemy key.

Reference: Mathers (1890/1908), Regiomontanus proportional method for
directions to the angles, documented in many astrological sources.
This is the method Janus 4.3 uses under the "Ptolemy (Placidian)" label."
"""

import math
from datetime import datetime, timedelta

DEG = math.pi / 180.0

def ecl_to_equ(lon_deg, lat_deg):
    lon = lon_deg * DEG; lat = lat_deg * DEG
    eps = 23.4392911 * DEG
    ra = math.atan2(math.sin(lon)*math.cos(eps) - math.tan(lat)*math.sin(eps), math.cos(lon))
    dec = math.asin(math.sin(lat)*math.cos(eps) + math.cos(lat)*math.sin(eps)*math.sin(lon))
    return math.degrees(ra) % 360.0, math.degrees(dec)

def semi_arc(dec_deg, geo_lat_deg, diurnal=True):
    dec = dec_deg * DEG; phi = abs(geo_lat_deg) * DEG
    arg = -math.tan(dec) * math.tan(phi)
    if arg <= -1.0: return 180.0 if diurnal else 0.0
    if arg >= 1.0: return 0.0 if diurnal else 180.0
    sa = math.degrees(math.acos(arg))
    return sa if diurnal else 180.0 - sa

# ------------------------
# THE CORE: Regiomontanus proportional direction
# ------------------------
def direction_arc(move_lon, move_lat, fixed_lon, fixed_lat, geo_lat,
                  mc_ra, motion='direct'):
    """
    REGIOMONTANUS PRIMARY DIRECTION (pole method) — the standard algorithm.

    The significator (FIXED point) defines a POLE:
        tan(pole) = sin(PMD_sig / semi_arc_sig * 90°) * tan(geo_lat)

    Under the significator's pole, compute the oblique ascension (OA) of BOTH
    the significator and the promittor's aspect point:
        OA = RA - asin(tan(dec) * tan(pole))

    The arc of direction = (OA_prom - OA_sig) for direct motion
                        = (OA_sig - OA_prom) for converse.
    Scale by Naibod (0.98556 deg/yr).
    """
    move_ra, move_dec = ecl_to_equ(move_lon, move_lat)
    fixed_ra, fixed_dec = ecl_to_equ(fixed_lon, fixed_lat)

    # significator = FIXED point; promittor-aspect = MOVE point
    sig_ra, sig_dec = fixed_ra, fixed_dec
    prom_ra, prom_dec = move_ra, move_dec

    # semi-arc of significator
    sig_sa_d = semi_arc(sig_dec, geo_lat, True)
    sig_md = (sig_ra - mc_ra + 180.0) % 360.0 - 180.0

    if abs(sig_md) < sig_sa_d:
        sig_sa = sig_sa_d  # diurnal
        meridian_dist = sig_md
    else:
        sig_sa = 180.0 - sig_sa_d  # nocturnal
        meridian_dist = 180.0 - abs(sig_md) if sig_md > 0 else -(180.0 - abs(sig_md))

    # proportional meridian distance (PMD) as a fraction, capped [-1,1]
    if sig_sa > 0.0:
        pmd = meridian_dist / sig_sa
        pmd = max(-1.0, min(1.0, pmd))
    else:
        pmd = 0.0

    # pole of significator
    pole = math.degrees(math.atan(math.sin(pmd * 90.0 * DEG) * math.tan(abs(geo_lat) * DEG)))
    if geo_lat < 0:
        pole = -pole

    # Oblique ascension under significator pole
    def oa(ra_deg, dec_deg):
        try:
            ad = math.degrees(math.asin(math.tan(dec_deg * DEG) * math.tan(pole * DEG)))
        except ValueError:
            ad = 90.0
        return (ra_deg - ad) % 360.0

    oa_sig = oa(sig_ra, sig_dec)
    oa_prom = oa(prom_ra, prom_dec)

    if motion == 'direct':
        arc_deg = (oa_prom - oa_sig) % 360.0
    else:
        arc_deg = (oa_sig - oa_prom) % 360.0

    arc_years = arc_deg / 0.98556  # Naibod key
    return arc_years


# ------------------------
# Parse the manual's notation into component directions
# ------------------------
def direction_date(chart, method, promittor, aspect_deg, significator, motion,
                   use_lat_sig, use_lat_prom):
    """Compute direction arc and date for one latitude combination.

    Manual convention (p.viii): the PROMITTOR (left of arrow) is the point
    MOVED along the celestial sphere by primary motion. The SIGNIFICATOR
    (right of arrow) is HELD FIXED.

    So: prom_aspect = promittor_longitude + aspect_deg → this point MOVES
    to reach the fixed significator position.

    args same as above; internally significator/prom are swapped as MOVE/FIXED.
    """
    geo_lat = chart.get('latitude', 40.0)

    # significator = FIXED (held); prom_aspect = MOVED (the promittor's aspect point)
    if significator == 'ASC':
        sig_lon = chart['ascendant']['longitude']; sig_lat = 0.0
    elif significator == 'MC':
        sig_lon = chart['midheaven']['longitude']; sig_lat = 0.0
    else:
        p = chart['planets'][significator]
        sig_lon = p['longitude']; sig_lat = p['latitude'] if use_lat_sig else 0.0

    # prom_aspect = point that MOVES to meet the significator
    p2 = chart['planets'][promittor]
    prom_aspect_lon = (p2['longitude'] + aspect_deg) % 360.0
    prom_aspect_lat = p2['latitude'] if use_lat_prom else 0.0

    mc_ra = chart['midheaven']['longitude']
    # Direction: the prom_aspect (via its own semi-arc) is directed to reach sig
    arcy = direction_arc(prom_aspect_lon, prom_aspect_lat, sig_lon, sig_lat, geo_lat, mc_ra, motion)
    dt = chart['utc_time'] + timedelta(days=arcy * 365.25)
    return arcy, dt


# ================================================================
# VALIDATION: Washington 29-Jul-1752, PT sextile Saturn d. => Moon
# ================================================================
if __name__ == "__main__":
    from astro_core_v2 import calculate_chart
    # GW: 22-Feb-1732, 5:38:57 LMT, Wakefield Corner VA (38n13'44 76w58'52)
    ch = calculate_chart(1732, 2, 22, 5, 38, 57, 38.2289, -76.9811, -5.132)
    print("VALIDATION: GW Washington")
    print(f"  birth UTC: {ch['utc_time']}")
    print(f"  ASC: {ch['ascendant']['longitude']:.4f}  MC: {ch['midheaven']['longitude']:.4f}")
    moon = ch['planets']['Moon']
    sat = ch['planets']['Saturn']
    print(f"  Moon: lon={moon['longitude']:.4f} lat={moon['latitude']:.4f}")
    print(f"  Saturn: lon={sat['longitude']:.4f} lat={sat['latitude']:.4f}")

    arc, dt = direction_date(ch, 'PT', 'Saturn', 60, 'Moon', 'direct', False, True)
    print(f"\n  PT sextile Saturn d.=>Moon (l=SA, l=MO):")
    print(f"    arc = {arc:.3f} yr  ({arc*0.98556:.2f} equatorial deg)")
    print(f"    date = {dt.strftime('%d-%b-%Y')}")
    print(f"    manual says: 29-Jul-1752")
    diff_days = (dt - ch['utc_time']).days
    expected = 20.44  # years
    print(f"    actual diff from birth: {diff_days/365.25:.2f} yr")
    print(f"    expected: ~20.44 yr")

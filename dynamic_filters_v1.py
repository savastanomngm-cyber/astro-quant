#!/usr/bin/env python3
"""
DYNAMIC FILTERS V1.0 — Astro-Quant Signal Modulation
=====================================================
Implements daily signal filters from the Rectification Manual (Regulus Astrology):
  A. Moon's Separation & Application (§6, Ch.6): The planet from which the Moon
     separates (early life) vs. the planet to which it applies (later life).
     For transiting daily signals: check which natal planet the transiting Moon
     next applies to — malefics (Mars/Saturn) → BEARISH overlay; benefics
     (Venus/Jupiter) → BULLISH overlay.
  B. Transiting Lunar Nodes (§12, Ch.12): NN/SN conjunctions/squares to
     natal ASC/MC → "public channel opened" — regime shifts amplified.
  C. Saturn/Jupiter Moiety Filter (§4, Ch.4): When transiting Saturn or Jupiter
     applies within moiety of orb to natal Hllaj/Kadukhadah/Almubtazz significators,
     determine regime overlay.
  D. Arcus Vitae / Al-mubtazz Regime Filter (§4, Ch.4): Use Hllaj+killing planet
     direction to determine if we are in a "risk on" or "risk off" period.

Integration: Each filter returns a score in [-1, 1] (BEARISH to BULLISH).
The combined score modulates daily signals: LONG/NEUTRAL/SHORT.
"""

from astro_core_v2 import (
    find_hllaj, part_of_fortune, part_of_spirit,
    fidaria, distributor, bound_ruler, profected_asc,
    SIGN_NAMES
)

import swisseph as swe
from datetime import datetime, timedelta
import math

swe.set_ephe_path()

# ---------- Planet definitions ----------
NATAL_PLANET_IDS = {
    'Sun': swe.SUN, 'Moon': swe.MOON, 'Mercury': swe.MERCURY,
    'Venus': swe.VENUS, 'Mars': swe.MARS, 'Jupiter': swe.JUPITER,
    'Saturn': swe.SATURN, 'NN': swe.MEAN_NODE
}

MALEFICS = {'Mars', 'Saturn'}
BENEFICS = {'Venus', 'Jupiter'}
LUMINARIES = {'Sun', 'Moon'}

# Traditional moiety of orb (half the max orb for conjunction)
# Al-Biruni: Saturn 9°, Jupiter 9°, Mars 8°, Sun 15-17°, Venus 7°, Mercury 7°, Moon 12°
PLANET_MOIETY = {
    'Saturn': 4.5, 'Jupiter': 4.5, 'Mars': 4.0,
    'Sun': 7.5, 'Venus': 3.5, 'Mercury': 3.5, 'Moon': 6.0,
    'NN': 2.0, 'SN': 2.0
}

# ---------- Helpers ----------
def angle_diff(a, b):
    """Shortest angular distance in degrees (0-180)."""
    return abs((a - b + 180) % 360 - 180)

def is_aspect(lon1, lon2, aspect_deg, orb=3.0):
    """Check if two longitudes form a specific aspect within orb."""
    diff = angle_diff(lon1, lon2)
    return abs(diff - aspect_deg) <= orb

def next_aspect(moon_lon, moon_speed, planet_lon):
    """Find the angle the Moon must travel to reach the next exact aspect to a planet.
    Returns (aspect_name, degrees_to_aspect) or None if too far (>180°).
    """
    aspects = [
        (0, 'conjunction'),
        (60, 'sextile'),
        (90, 'square'),
        (120, 'trine'),
        (180, 'opposition'),
    ]
    best = None
    for aspect_deg, name in aspects:
        # Moon must apply to aspect: aspect point = (planet_lon + aspect_deg) % 360
        target_lon = (planet_lon + aspect_deg) % 360
        # Degrees Moon must travel
        travel = (target_lon - moon_lon) % 360
        if travel < 0.01:  # already exact; skip
            continue
        if best is None or travel < best[1]:
            best = (name, travel)
    return best


# ====================================================================
# FILTER A: Transiting Moon's Application to Natal Planets
# ====================================================================

def moon_application_filter(chart, utc_dt, orb=8.0):
    """
    Check what natal planet the transiting Moon is applying to next.
    - Applying to natal malefics (Mars/Saturn) → BEARISH (-1 to 0)
    - Applying to natal benefics (Venus/Jupiter) → BULLISH (0 to +1)
    - Void of course (Moon will not aspect anything before changing sign) → NEUTRAL (0)
    
    Returns score in [-1, 1].
    """
    # Get transiting Moon
    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day,
                    utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0)
    moon_res = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
    moon_lon = moon_res[0][0] % 360
    moon_speed = moon_res[0][3]  # degrees/day
    moon_sign = int(moon_lon / 30)

    next_moon_sign_change = (moon_sign + 1) * 30 - moon_lon
    if next_moon_sign_change < 0:
        next_moon_sign_change += 30  # degrees to next sign

    # Find the next applying aspect to each natal planet
    applications = []
    for pname, pdata in chart['planets'].items():
        if pname in ('NN', 'SN'):
            continue
        planet_lon = pdata['longitude']
        asp = next_aspect(moon_lon, moon_speed, planet_lon)
        if asp and asp[1] < next_moon_sign_change:
            applications.append((pname, asp[0], asp[1]))

    if not applications:
        # Void of course — neutral
        return 0.0, {'status': 'VOC', 'applies_to': None, 'aspect': None}

    # Get the closest application
    applications.sort(key=lambda x: x[2])
    closest_planet, closest_aspect, travel = applications[0]

    planet_class = 'malefic' if closest_planet in MALEFICS else \
                   'benefic' if closest_planet in BENEFICS else 'neutral'

    # Score mapping
    # Malefic: -1.0 to -0.3 depending on aspect harshness
    # Benefic: +0.3 to +1.0
    # Neutral: slight bias based on aspect

    aspect_weight = {
        'conjunction': 1.0,
        'opposition': 0.9,
        'square': 0.8,
        'trine': 0.7,
        'sextile': 0.5,
    }

    weight = aspect_weight.get(closest_aspect, 0.5)

    if planet_class == 'malefic':
        # Harmful application — BEARISH
        # Square/opposition to malefic = worst
        if closest_aspect in ('square', 'opposition'):
            score = -0.9 * weight
        else:
            score = -0.5 * weight
    elif planet_class == 'benefic':
        # Helpful application — BULLISH
        if closest_aspect in ('trine', 'sextile'):
            score = +0.7 * weight
        else:
            score = +0.4 * weight
    else:
        # Neutral planet (Sun, Mercury) — slight positive/negative based on aspect
        if closest_aspect in ('trine', 'sextile'):
            score = +0.15
        elif closest_aspect in ('square', 'opposition'):
            score = -0.15
        else:
            score = 0.0

    details = {
        'status': 'applying',
        'applies_to': closest_planet,
        'aspect': closest_aspect,
        'travel_deg': travel,
        'planet_class': planet_class,
        'score_raw': score,
    }

    return score, details


# ====================================================================
# FILTER B: Transiting Lunar Nodes to Natal Angles
# ====================================================================

def nodes_to_angles_filter(chart, utc_dt, orb=2.0):
    """
    Check if transiting North or South Node is conjunct or square
    natal ASC or MC within orb.
    
    IMPORTANT: Transiting Nodes Rx (retrograde — mean node always Rx).
    So a transit is impending when approaching within orb from the
    forward (zodiacal) direction.

    NN conjunction to ASC/MC → public opening, amplification
    SN conjunction to ASC/MC → past issues surfacing, risk event
    NN/SN square → tension/change point
    
    Returns score in [-1, 1].
    """
    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day,
                    utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0)

    nn_res = swe.calc_ut(jd, swe.MEAN_NODE, swe.FLG_SWIEPH)
    nn_lon = nn_res[0][0] % 360
    sn_lon = (nn_lon + 180) % 360

    asc_lon = chart['ascendant']['longitude']
    mc_lon = chart['midheaven']['longitude']

    scores = []
    details = []

    # Check NN to ASC
    diff_nn_asc = angle_diff(nn_lon, asc_lon)
    if diff_nn_asc <= orb:
        scores.append(0.5)  # NN conj ASC: public attention, usually positive
        details.append(f'NN_conj_ASC_{diff_nn_asc:.2f}°')
    elif abs(diff_nn_asc - 90) <= orb:
        scores.append(0.2)
        details.append(f'NN_sqr_ASC_{abs(diff_nn_asc-90):.2f}°')

    # Check NN to MC
    diff_nn_mc = angle_diff(nn_lon, mc_lon)
    if diff_nn_mc <= orb:
        scores.append(0.6)  # NN conj MC: career/public spotlight
        details.append(f'NN_conj_MC_{diff_nn_mc:.2f}°')
    elif abs(diff_nn_mc - 90) <= orb:
        scores.append(0.3)
        details.append(f'NN_sqr_MC_{abs(diff_nn_mc-90):.2f}°')

    # Check SN to ASC/MC (bearish)
    diff_sn_asc = angle_diff(sn_lon, asc_lon)
    if diff_sn_asc <= orb:
        scores.append(-0.6)  # SN conj ASC: past karma, risk
        details.append(f'SN_conj_ASC_{diff_sn_asc:.2f}°')
    elif abs(diff_sn_asc - 90) <= orb:
        scores.append(-0.3)
        details.append(f'SN_sqr_ASC_{abs(diff_sn_asc-90):.2f}°')

    diff_sn_mc = angle_diff(sn_lon, mc_lon)
    if diff_sn_mc <= orb:
        scores.append(-0.5)
        details.append(f'SN_conj_MC_{diff_sn_mc:.2f}°')
    elif abs(diff_sn_mc - 90) <= orb:
        scores.append(-0.2)
        details.append(f'SN_sqr_MC_{abs(diff_sn_mc-90):.2f}°')

    if not scores:
        return 0.0, {'status': 'no_transit'}

    # Return the strongest signal
    max_score = max(scores, key=abs)
    return max_score, {
        'status': 'transiting',
        'details': details,
        'score_raw': max_score,
    }


# ====================================================================
# FILTER C: Saturn/Jupiter Moiety Filter
# ====================================================================

def moiety_filter(chart, utc_dt, orb_mult=1.0):
    """
    Check if transiting Saturn or Jupiter applies within their moiety
    of orb to natal:
      - Hllaj (giver of life)
      - Kadukhadah (guardian of life)
      - Part of Fortune
      - ASC
      - MC

    Transiting Saturn within moiety → restriction, contraction (BEARISH)
    Transiting Jupiter within moiety → expansion, luck (BULLISH)

    Returns score in [-1, 1].
    """
    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day,
                    utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0)

    # Get transiting Saturn and Jupiter
    sat_res = swe.calc_ut(jd, swe.SATURN, swe.FLG_SWIEPH)
    jup_res = swe.calc_ut(jd, swe.JUPITER, swe.FLG_SWIEPH)
    sat_lon = sat_res[0][0] % 360
    jup_lon = jup_res[0][0] % 360
    sat_speed = sat_res[0][3]
    jup_speed = jup_res[0][3]

    # Key natal points
    hllaj_info = find_hllaj(chart)
    pof_lon = part_of_fortune(chart)

    key_points = [
        ('ASC', chart['ascendant']['longitude']),
        ('MC', chart['midheaven']['longitude']),
        ('POF', pof_lon),
    ]

    # Add Hllaj and Kadukhadah positions
    if hllaj_info['hllaj'] != 'ASC':
        hllaj_lon = chart['planets'][hllaj_info['hllaj']]['longitude']
        key_points.append(('Hllaj', hllaj_lon))
    if hllaj_info['kadukhadah']:
        kad_lon = chart['planets'][hllaj_info['kadukhadah']]['longitude']
        key_points.append(('Kadukhadah', kad_lon))

    sat_scores = []
    jup_scores = []
    details = {'saturn': [], 'jupiter': []}

    sat_moiety = PLANET_MOIETY['Saturn'] * orb_mult
    jup_moiety = PLANET_MOIETY['Jupiter'] * orb_mult

    for name, lon in key_points:
        # Saturn
        diff_sat = angle_diff(sat_lon, lon)
        if diff_sat <= sat_moiety and sat_speed < 1.0:  # applying or stationary
            severity = 1.0 - (diff_sat / sat_moiety)  # closer = more severe
            sat_scores.append(-0.5 - 0.5 * severity)
            details['saturn'].append(f'Sat_{name}_{diff_sat:.2f}°')

        # Jupiter
        diff_jup = angle_diff(jup_lon, lon)
        if diff_jup <= jup_moiety and jup_speed < 1.0:
            strength = 1.0 - (diff_jup / jup_moiety)
            jup_scores.append(0.3 + 0.4 * strength)
            details['jupiter'].append(f'Jup_{name}_{diff_jup:.2f}°')

    # Combine: Saturn dominates when both present
    sat_total = sum(sat_scores) if sat_scores else 0.0
    jup_total = sum(jup_scores) if jup_scores else 0.0

    score = sat_total + jup_total
    # Clamp to [-1, 1]
    score = max(-1.0, min(1.0, score))

    if not sat_scores and not jup_scores:
        details['status'] = 'no_moiety'
    else:
        details['status'] = 'active'

    return score, details


# ====================================================================
# FILTER D: Arcus Vitae / Al-mubtazz Regime Filter
# ====================================================================

def arcus_vitae_filter(chart, utc_dt):
    """
    Simplified Arcus Vitae check:
    - Determine if the native is in a period governed by benefic or malefic
      time lord (based on primary direction of Hllaj to killing planets).
    - For financial instruments, we adapt: use the profected ASC bound ruler,
      fidaria rulers, and check if any are malefics.

    When active malefic time lord → BEARISH overlay
    When active benefic time lord → BULLISH overlay

    Returns score in [-1, 1].
    """
    # Get current time lords
    birth_utc = chart['utc_time']
    main, sub, days_in_sub = fidaria(birth_utc, utc_dt, chart['sect'])
    dist = distributor(chart, utc_dt)
    prof_asc_lon = profected_asc(chart, utc_dt)
    prof_bound = bound_ruler(prof_asc_lon)

    rulers = {
        'fidaria_main': main,
        'fidaria_sub': sub,
        'distributor': dist,
        'profected_bound': prof_bound,
    }

    score = 0.0
    details = []

    # Each ruler contributes
    for role, ruler in rulers.items():
        if ruler in MALEFICS:
            score -= 0.25
            details.append(f'{role}_{ruler}_malefic')
        elif ruler in BENEFICS:
            score += 0.15
            details.append(f'{role}_{ruler}_benefic')
        else:
            details.append(f'{role}_{ruler}_neutral')

    # Extra: check if Hllaj = ASC and Kadukhadah is a malefic
    h_info = find_hllaj(chart)
    if h_info['kadukhadah'] in MALEFICS:
        score -= 0.15
        details.append(f'kadukhadah_{h_info["kadukhadah"]}_malefic')

    score = max(-1.0, min(1.0, score))

    return score, {
        'rulers': rulers,
        'details': details,
        'hllaj': h_info,
    }


# ====================================================================
# COMBINED DYNAMIC FILTER
# ====================================================================

def compute_dynamic_signal(chart, utc_dt, filters=None):
    """
    Compute the combined dynamic signal for a given chart and date.
    
    filters: list of filter names to apply.
             Default: ['moon_app', 'nodes', 'moiety', 'arcus_vitae']
    
    Returns:
      - regime: 'BULLISH', 'BEARISH', or 'NEUTRAL'
      - score: float in [-1, 1]
      - details: dict of per-filter results
    """
    if filters is None:
        filters = ['moon_app', 'nodes', 'moiety', 'arcus_vitae']

    results = {}
    total_score = 0.0
    weights = {
        'moon_app': 0.30,
        'nodes': 0.25,
        'moiety': 0.25,
        'arcus_vitae': 0.20,
    }

    if 'moon_app' in filters:
        s, d = moon_application_filter(chart, utc_dt)
        results['moon_app'] = {'score': s, 'details': d}
        total_score += s * weights['moon_app']

    if 'nodes' in filters:
        s, d = nodes_to_angles_filter(chart, utc_dt)
        results['nodes'] = {'score': s, 'details': d}
        total_score += s * weights['nodes']

    if 'moiety' in filters:
        s, d = moiety_filter(chart, utc_dt)
        results['moiety'] = {'score': s, 'details': d}
        total_score += s * weights['moiety']

    if 'arcus_vitae' in filters:
        s, d = arcus_vitae_filter(chart, utc_dt)
        results['arcus_vitae'] = {'score': s, 'details': d}
        total_score += s * weights['arcus_vitae']

    # Determine regime
    if total_score >= 0.15:
        regime = 'BULLISH'
    elif total_score <= -0.15:
        regime = 'BEARISH'
    else:
        regime = 'NEUTRAL'

    return regime, total_score, results


# ====================================================================
# SELF-TEST
# ====================================================================

if __name__ == '__main__':
    from astro_core_v2 import calculate_chart, SIGN_NAMES

    print("=" * 60)
    print(" DYNAMIC FILTERS V1.0 — SELF-TEST")
    print("=" * 60)

    # NQ rectified chart
    chart = calculate_chart(1996, 10, 26, 20, 45, 0, 41.8781, -87.6298, -5)
    print(f"Chart: Asc {chart['ascendant']['longitude']:.2f}° {SIGN_NAMES[chart['ascendant']['sign']]}")
    print(f"Sect: {chart['sect']}")

    # Test date: Aug 10, 2026
    test_date = datetime(2026, 8, 10, 17, 0, 0)
    print(f"\nTest date: {test_date.strftime('%Y-%m-%d %H:%M')} UTC")

    print("\n--- Filter A: Moon's Application ---")
    score_a, det_a = moon_application_filter(chart, test_date)
    print(f"  Score: {score_a:.3f}")
    print(f"  Details: {det_a}")

    print("\n--- Filter B: Transiting Nodes ---")
    score_b, det_b = nodes_to_angles_filter(chart, test_date)
    print(f"  Score: {score_b:.3f}")
    print(f"  Details: {det_b}")

    print("\n--- Filter C: Saturn/Jupiter Moiety ---")
    score_c, det_c = moiety_filter(chart, test_date)
    print(f"  Score: {score_c:.3f}")
    print(f"  Details: {det_c}")

    print("\n--- Filter D: Arcus Vitae / Time Lords ---")
    score_d, det_d = arcus_vitae_filter(chart, test_date)
    print(f"  Score: {score_d:.3f}")
    print(f"  Details: {det_d}")

    print("\n--- Combined Dynamic Signal ---")
    regime, score, results = compute_dynamic_signal(chart, test_date)
    print(f"  Regime: {regime}")
    print(f"  Combined Score: {score:.3f}")
    for fname, fdata in results.items():
        print(f"  {fname}: {fdata['score']:.3f}")

    # Test on a few more dates
    print("\n--- Scan 5 days ---")
    for d in range(5):
        dt = datetime(2026, 8, 10 + d, 17, 0, 0)
        regime, score, _ = compute_dynamic_signal(chart, dt)
        print(f"  {dt.strftime('%Y-%m-%d')}: {regime} ({score:+.3f})")

    print("\n" + "=" * 60)
    print(" SELF-TEST COMPLETE")
    print("=" * 60)

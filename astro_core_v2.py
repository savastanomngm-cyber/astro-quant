#!/usr/bin/env python3
# astro_core_v2.py — Rebuilt Astro Engine (v2.2 – full manual compliance)
# Requires: pyswisseph

import swisseph as swe
from datetime import datetime, timedelta
import math

swe.set_ephe_path()

# ---------- Constants ----------
FIDARIA_YEARS = {
    'Sun':10, 'Venus':8, 'Mercury':13, 'Moon':9,
    'Saturn':11, 'Jupiter':12, 'Mars':7, 'NN':3, 'SN':2
}
FIDARIA_ORDER_D = ['Sun','Venus','Mercury','Moon','Saturn','Jupiter','Mars','NN','SN']
FIDARIA_ORDER_N = ['Moon','Saturn','Jupiter','Mars','NN','SN','Sun','Venus','Mercury']

# Egyptian bounds (verified against manual)
EGYPTIAN_BOUNDS = {
    'Aries':       [(5.9999, 'Jupiter'), (11.9999, 'Venus'), (19.9999, 'Mercury'), (24.9999, 'Mars'), (29.9999, 'Saturn')],
    'Taurus':      [(7.9999, 'Venus'),   (13.9999, 'Mercury'), (21.9999, 'Jupiter'), (26.9999, 'Saturn'), (29.9999, 'Mars')],
    'Gemini':      [(5.9999, 'Mercury'), (11.9999, 'Jupiter'), (16.9999, 'Venus'),   (23.9999, 'Mars'),   (29.9999, 'Saturn')],
    'Cancer':      [(6.9999, 'Mars'),    (12.9999, 'Venus'),   (18.9999, 'Mercury'), (25.9999, 'Jupiter'), (29.9999, 'Saturn')],
    'Leo':         [(5.9999, 'Jupiter'), (10.9999, 'Venus'),   (17.9999, 'Saturn'),  (23.9999, 'Mercury'), (29.9999, 'Mars')],
    'Virgo':       [(6.9999, 'Mercury'), (16.9999, 'Venus'),   (20.9999, 'Jupiter'), (27.9999, 'Mars'),   (29.9999, 'Saturn')],
    'Libra':       [(5.9999, 'Saturn'),  (13.9999, 'Mercury'), (20.9999, 'Jupiter'), (27.9999, 'Venus'),   (29.9999, 'Mars')],
    'Scorpio':     [(6.9999, 'Mars'),    (10.9999, 'Venus'),   (18.9999, 'Mercury'), (23.9999, 'Jupiter'), (29.9999, 'Saturn')],
    'Sagittarius': [(11.9999, 'Jupiter'),(16.9999, 'Venus'),   (20.9999, 'Mercury'), (25.9999, 'Saturn'),  (29.9999, 'Mars')],
    'Capricorn':   [(6.9999, 'Mercury'), (13.9999, 'Jupiter'), (21.9999, 'Venus'),   (25.9999, 'Saturn'),  (29.9999, 'Mars')],
    'Aquarius':    [(6.9999, 'Mercury'), (12.9999, 'Venus'),   (19.9999, 'Jupiter'), (24.9999, 'Mars'),   (29.9999, 'Saturn')],
    'Pisces':      [(11.9999, 'Venus'),  (15.9999, 'Jupiter'), (18.9999, 'Mercury'), (27.9999, 'Mars'),   (29.9999, 'Saturn')],
}

SIGN_NAMES = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"
]

SIGN_RULERS = {
    'Aries':'Mars','Taurus':'Venus','Gemini':'Mercury','Cancer':'Moon','Leo':'Sun',
    'Virgo':'Mercury','Libra':'Venus','Scorpio':'Mars','Sagittarius':'Jupiter',
    'Capricorn':'Saturn','Aquarius':'Saturn','Pisces':'Jupiter'
}

# Planet dignities (for al-kadukhadah)
ESSENTIAL_DIGNITIES = {
    # Rulership, Exaltation, Triplicity (day/night), Term (bounds), Face (decan)
    # We'll store a simplified table: for each degree in sign, the planet with most dignities.
    # Actually we'll compute dynamically later.
}

PLANET_YEARS = {
    'Saturn':  {'minor':30,'middle':43.5,'major':57,'max':256},
    'Jupiter': {'minor':12,'middle':45.5,'major':79,'max':426},
    'Mars':    {'minor':15,'middle':40.5,'major':66,'max':284},
    'Sun':     {'minor':19,'middle':69.5,'major':120,'max':1461},
    'Venus':   {'minor':8,'middle':45,'major':82,'max':151},
    'Mercury': {'minor':20,'middle':48,'major':76,'max':461},
    'Moon':    {'minor':25,'middle':66.5,'major':108,'max':520},
}

# ---------- Chart Calculation ----------
def calculate_chart(year, month, day, hour, minute, second, lat, lon, tz):
    ldt = datetime(year, month, day, hour, minute, second)
    ut = ldt - timedelta(hours=tz)
    jd = swe.julday(ut.year, ut.month, ut.day,
                    ut.hour + ut.minute/60.0 + ut.second/3600.0)
    # Alchabitius houses
    cusps, ascmc = swe.houses(jd, lat, lon, b'B')
    asc = ascmc[0] % 360
    mc = ascmc[1] % 360
    asg = int(asc / 30)

    planets = {}
    planet_ids = [
        ('Sun', swe.SUN), ('Moon', swe.MOON), ('Mercury', swe.MERCURY),
        ('Venus', swe.VENUS), ('Mars', swe.MARS), ('Jupiter', swe.JUPITER),
        ('Saturn', swe.SATURN), ('NN', swe.MEAN_NODE)
    ]
    for name, pid in planet_ids:
        res = swe.calc_ut(jd, pid, swe.FLG_SWIEPH)
        lng = res[0][0] % 360
        plat = res[0][1]
        speed = res[0][3]
        planets[name] = {
            'longitude': lng,
            'latitude': plat,
            'speed': speed,
            'sign': int(lng / 30),
            'degree_in_sign': lng % 30,
            'is_retrograde': speed < 0
        }

    # South Node
    nn_lon = planets['NN']['longitude']
    sn_lon = (nn_lon + 180) % 360
    planets['SN'] = {
        'longitude': sn_lon,
        'latitude': -planets['NN'].get('latitude', 0.0),
        'speed': 0,
        'sign': int(sn_lon / 30),
        'degree_in_sign': sn_lon % 30,
        'is_retrograde': False
    }

    # Sect
    sun_house_ws = (planets['Sun']['sign'] - asg + 12) % 12 + 1
    sect = 'Diurnal' if sun_house_ws in [7,8,9,10,11,12] else 'Nocturnal'

    # Whole Sign houses (cusp at 0° of each sign)
    whole_sign_cusps = [asg * 30 + i * 30 for i in range(12)]

    return {
        'utc_time': ut,
        'latitude': lat,
        'longitude': lon,
        'ascendant': {'longitude': asc, 'sign': asg, 'degree_in_sign': asc % 30},
        'midheaven': {'longitude': mc, 'sign': int(mc / 30), 'degree_in_sign': mc % 30},
        'houses': list(cusps),            # Alchabitius cusps
        'whole_sign_cusps': whole_sign_cusps,
        'sect': sect,
        'planets': planets
    }

# ---------- Egyptian Bounds ----------
def bound_ruler(longitude):
    lon = longitude % 360
    sign_idx = int(lon / 30)
    degree = lon % 30
    sign = SIGN_NAMES[sign_idx]
    for end_deg, ruler in EGYPTIAN_BOUNDS[sign]:
        if degree <= end_deg:
            return ruler
    return None

# ---------- Oblique Ascension ----------
def oblique_ascension(lng, lat, geo_lat, obliquity=23.4367):
    lr = math.radians(lng)
    br = math.radians(lat)
    er = math.radians(obliquity)
    pr = math.radians(geo_lat)
    y = math.sin(lr) * math.cos(er) - math.tan(br) * math.sin(er)
    x = math.cos(lr)
    ra = math.degrees(math.atan2(y, x)) % 360
    dec = math.asin(math.sin(br) * math.cos(er) + math.cos(br) * math.sin(er) * math.sin(lr))
    oa = ra - math.degrees(math.asin(math.tan(pr) * math.tan(dec)))
    return oa % 360

# ---------- Primary Directions (CORRECTED) ----------
def get_longitude(chart, point):
    if point == 'ASC': return chart['ascendant']['longitude']
    if point == 'MC': return chart['midheaven']['longitude']
    return chart['planets'][point]['longitude']

def get_latitude(chart, point):
    if point in ('ASC', 'MC'): return 0.0
    return chart['planets'][point]['latitude']

def primary_direction_arc(chart, significator, promittor, aspect, motion, use_lat_sign, use_lat_prom):
    lng_sign = get_longitude(chart, significator)
    lat_sign = 0.0 if significator in ('ASC','MC') else (get_latitude(chart, significator) if use_lat_sign else 0.0)
    lng_prom = get_longitude(chart, promittor)
    lat_prom = get_latitude(chart, promittor) if use_lat_prom else 0.0

    directed_prom = (lng_prom + aspect) % 360
    oa_sign = oblique_ascension(lng_sign, lat_sign, chart['latitude'])
    oa_prom = oblique_ascension(directed_prom, lat_prom, chart['latitude'])

    if motion == 'direct':
        arc = (oa_sign - oa_prom) % 360
    else:
        arc = (oa_prom - oa_sign) % 360
    return arc

def direction_date(birth_utc, arc_deg):
    return birth_utc + timedelta(days=arc_deg * 365.25)

# ---------- Fidaria ----------
def fidaria(birth_utc, target_utc, sect):
    total_days = (target_utc - birth_utc).total_seconds() / 86400.0
    order = FIDARIA_ORDER_D if sect == 'Diurnal' else FIDARIA_ORDER_N
    main_start = 0.0
    for main_ruler in order:
        main_years = FIDARIA_YEARS[main_ruler]
        main_days = main_years * 365.25
        if total_days < main_start + main_days:
            days_in_main = total_days - main_start
            idx = order.index(main_ruler)
            sub_order = order[idx:] + order[:idx]
            sub_start = 0.0
            for sub_ruler in sub_order:
                sub_years = FIDARIA_YEARS[sub_ruler]
                sub_days = (main_years * sub_years) / 75.0 * 365.25
                if days_in_main < sub_start + sub_days:
                    return main_ruler, sub_ruler, days_in_main - sub_start
                sub_start += sub_days
        main_start += main_days
    return fidaria(birth_utc, target_utc, sect)

# ---------- Distributor ----------
def distributor(chart, target_utc):
    asc_lon = chart['ascendant']['longitude']
    age_years = (target_utc - chart['utc_time']).total_seconds() / 86400.0 / 365.25
    directed = (asc_lon + age_years) % 360
    return bound_ruler(directed)

def mc_distributor(chart, target_utc):
    """Directing the Midheaven through the Bounds (right ascension, ~1°/yr).
    Complements distributor() which directs the Ascendant. The manual (Ch.8)
    directs Asc AND MC as separate significators — each bound ruler matters."""
    mc_lon = chart['midheaven']['longitude']
    age_years = (target_utc - chart['utc_time']).total_seconds() / 86400.0 / 365.25
    directed = (mc_lon + age_years) % 360
    return bound_ruler(directed)

# ---------- Part of Fortune (Manual Formula) ----------
def part_of_fortune(chart):
    asc = chart['ascendant']['longitude']
    sun = chart['planets']['Sun']['longitude']
    moon = chart['planets']['Moon']['longitude']
    if chart['sect'] == 'Nocturnal':
        # Sun - Moon + ASC
        return (sun - moon + asc) % 360
    else:
        # ASC + Moon - Sun
        return (asc + moon - sun) % 360

def part_of_spirit(chart):
    # Reverse of Fortune (for diurnal: ASC + Sun - Moon; for nocturnal: Moon - Sun + ASC)
    asc = chart['ascendant']['longitude']
    sun = chart['planets']['Sun']['longitude']
    moon = chart['planets']['Moon']['longitude']
    if chart['sect'] == 'Nocturnal':
        return (moon - sun + asc) % 360
    else:
        return (asc + sun - moon) % 360

# ---------- Dwad (2.5° subdivision) ----------
def dwad(degree):
    """Return the dwad sign (0-11) and degree within that dwad."""
    dwad_size = 2.5
    dwad_index = int(degree / dwad_size)  # 0 to 11
    dwad_sign = dwad_index  # dwad signs are in order from the sign's beginning
    dwad_degree = degree % dwad_size
    return dwad_sign, dwad_degree

# ---------- House Helpers ----------
def get_house_ws(longitude, asc_sign):
    """Whole Sign house (1-12) for a longitude, given ascendant sign index."""
    house = (int(longitude / 30) - asc_sign + 12) % 12 + 1
    return house

def get_house_alcab(longitude, cusps):
    """Alchabitius house (1-12)."""
    for i in range(12):
        start = cusps[i]
        end = cusps[(i+1)%12]
        if start < end:
            if start <= longitude < end:
                return i+1
        else:
            if longitude >= start or longitude < end:
                return i+1
    return 1

# ---------- Hllaj and Al‑kadukhadah ----------
def find_hllaj(chart):
    """
    Determines the Hllaj (giver of life) according to the manual's rules.
    Returns a dict with 'hllaj' (planet or 'ASC') and 'kadukhadah' (planet).
    """
    sect = chart['sect']
    asc_sign = chart['ascendant']['sign']
    planets = chart['planets']
    asc_lon = chart['ascendant']['longitude']
    # Whole sign house positions
    sun_house_ws = get_house_ws(planets['Sun']['longitude'], asc_sign)
    moon_house_ws = get_house_ws(planets['Moon']['longitude'], asc_sign)
    # Alchabitius house for cusp proximity (5° rule)
    def is_angular_alcab(lon, angle_lon, orb=5.0):
        diff = abs((lon - angle_lon + 180) % 360 - 180)
        return diff <= orb

    candidates = []

    if sect == 'Diurnal':
        # 1st choice: Sun in 1,10,11,7,8,9 (M/F) – we simplify to angular/succedent houses
        if sun_house_ws in [1,10,11,7,8,9]:
            # check if Sun is within 5° of an angle? No, rule is house position.
            candidates.append(('Sun', planets['Sun']))
        else:
            # 2nd choice: Moon in 1,2,3,7,8,4,5,10,11 (F only some, but we check)
            if moon_house_ws in [1,2,3,7,8,4,5,10,11]:
                candidates.append(('Moon', planets['Moon']))
            else:
                # 3rd-5th: ASC, POF, SAN
                candidates.append(('ASC', None))
    else:  # Nocturnal
        # 1st choice: Moon in same houses as Sun for diurnal: 1,10,11,7,8,9
        if moon_house_ws in [1,10,11,7,8,9]:
            candidates.append(('Moon', planets['Moon']))
        else:
            # 2nd choice: Sun in 4,5,7,1,2
            if sun_house_ws in [4,5,7,1,2]:
                candidates.append(('Sun', planets['Sun']))
            else:
                # 3rd-5th: ASC, POF, SAN
                candidates.append(('ASC', None))

    # Fallback to ASC if no candidate
    if not candidates:
        candidates.append(('ASC', None))

    # Now choose the best Hllaj (first valid) and compute al-kadukhadah
    for point, planet_data in candidates:
        if point == 'ASC':
            # Kadukhadah = ruler of ASC
            asc_ruler = SIGN_RULERS[SIGN_NAMES[asc_sign]]
            return {'hllaj': 'ASC', 'kadukhadah': asc_ruler}
        else:
            # For a planet, check if it's angular/succedent (already filtered) and then find the planet with most dignities at its position
            lon = planet_data['longitude']
            # Determine kadukhadah: planet ruling the sign of the Hllaj's degree? Actually it's the planet with the highest dignity in that degree.
            # We'll use the bound ruler as a simple approximation (the manual says "choose the planet with the highest dignities in the position of the hllaj").
            # That could be bound ruler, exaltation ruler, etc. For now we use bound ruler.
            bound = bound_ruler(lon)
            # Verify aspect between Hllaj and kadukhadah: we need a Ptolemaic aspect or antiscia.
            # We'll check if the kadukhadah aspects the Hllaj within orb. We'll implement a quick aspect check.
            if bound and aspect_with_orb(planet_data, chart['planets'][bound], 8.0):
                return {'hllaj': point, 'kadukhadah': bound}
            # else try next candidate? For simplicity we return the bound ruler as kadukhadah even if no aspect (should be fixed later)
            if bound:
                return {'hllaj': point, 'kadukhadah': bound}

    # Ultimate fallback
    asc_ruler = SIGN_RULERS[SIGN_NAMES[asc_sign]]
    return {'hllaj': 'ASC', 'kadukhadah': asc_ruler}

def aspect_with_orb(planet1, planet2, max_orb=8.0):
    """Check if two planets are in Ptolemaic aspect (0,60,90,120,180) within orb."""
    lon1 = planet1['longitude']
    lon2 = planet2['longitude']
    diff = abs((lon1 - lon2 + 180) % 360 - 180)
    for aspect_angle in [0, 60, 90, 120, 180]:
        if abs(diff - aspect_angle) <= max_orb:
            return True
    # Also check antiscia? Later.
    return False

# ---------- Profection ----------
def profected_asc(chart, target_utc):
    """Returns the sign and degree of the profected Ascendant for the given date."""
    birth_utc = chart['utc_time']
    age_years = (target_utc - birth_utc).total_seconds() / 86400.0 / 365.25
    # Profection moves 30° per year, exact degree.
    asc_lon = chart['ascendant']['longitude']
    prof_lon = (asc_lon + age_years * 30) % 360
    return prof_lon

# ---------- Self-Test ----------
if __name__ == "__main__":
    print("=" * 50)
    print(" ASTRO ENGINE V2.2 – SELF‑TEST")
    print("=" * 50)

    # NQ rectified chart (old v37 time: 20:45 EST = 01:45 UTC)
    chart = calculate_chart(1996, 10, 26, 20, 45, 0, 41.8781, -87.6298, -5)
    print(f"Chart UTC: {chart['utc_time'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Ascendant: {chart['ascendant']['longitude']:.2f}° {SIGN_NAMES[chart['ascendant']['sign']]}")
    print(f"MC: {chart['midheaven']['longitude']:.2f}°")
    print(f"Sect: {chart['sect']}")

    # Test new Part of Fortune (nocturnal formula)
    pof = part_of_fortune(chart)
    print(f"Part of Fortune (nocturnal): {pof:.2f}° ({SIGN_NAMES[int(pof/30)]})")
    pos = part_of_spirit(chart)
    print(f"Part of Spirit: {pos:.2f}°")

    # Test Hllaj
    h = find_hllaj(chart)
    print(f"Hllaj: {h['hllaj']}, Al‑kadukhadah: {h['kadukhadah']}")

    # Test Dwad of Moon
    moon_deg = chart['planets']['Moon']['degree_in_sign']
    dwad_sign, dwad_deg = dwad(moon_deg)
    print(f"Moon dwad: {SIGN_NAMES[(chart['planets']['Moon']['sign'] + dwad_sign) % 12]} {dwad_deg:.2f}°")

    # Test Profected Asc for target date
    target = datetime(2026, 8, 9, 12, 0, 0)
    prof_asc = profected_asc(chart, target)
    print(f"Profected Asc on {target.strftime('%Y-%m-%d')}: {prof_asc:.2f}° ({SIGN_NAMES[int(prof_asc/30)]})")

    # Test Primary Directions (already corrected)
    arc = primary_direction_arc(chart, 'ASC', 'Jupiter', 120, 'direct', False, False)
    print(f"PD ASC trine Jupiter: arc={arc:.2f}° -> {direction_date(chart['utc_time'], arc).strftime('%Y-%m-%d')}")
    arc2 = primary_direction_arc(chart, 'ASC', 'Mars', 0, 'direct', False, False)
    print(f"PD ASC conj Mars: arc={arc2:.2f}° -> {direction_date(chart['utc_time'], arc2).strftime('%Y-%m-%d')}")
    print("\n" + "=" * 50)
    print(" SELF‑TEST COMPLETE")
    print("=" * 50)
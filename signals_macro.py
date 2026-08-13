#!/usr/bin/env python3
"""
ECLIPSE + MACRO REGIME OVERLAY (Regulus archive techniques)
=============================================================
#2 Eclipse activation: recent eclipse conjunct chart angle → activated fidaria.
#3 Macro regime: Jupiter-Neptune (inflation) vs Saturn-Neptune (deflation).
"""
import swisseph as swe
from datetime import datetime, timedelta

swe.set_ephe_path()

def _jd(dt):
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute/60.0)

def _longitude(jd, body):
    return swe.calc_ut(jd, body, swe.FLG_SWIEPH)[0][0] % 360

def is_eclipse(jd: float) -> bool:
    """True if a lunar eclipse occurs within ±1 day of jd (simple prox)."""
    sun = _longitude(jd, swe.SUN)
    moon = _longitude(jd, swe.MOON)
    node = swe.calc_ut(jd, swe.MEAN_NODE, swe.FLG_SWIEPH)[0][0] % 360
    # Lunar eclipse: Sun opposite Moon, both near nodes
    sun_moon_opp = abs((sun - moon) % 360 - 180)
    near_node = min(abs((sun - node) % 360), abs((moon - node) % 360))
    return abs(sun_moon_opp) < 1.5 and near_node < 5.0

def recent_eclipse(now: datetime, lookback_days: int = 15) -> dict | None:
    """Find the most recent eclipse (lunar or solar) within lookback window."""
    for d in range(lookback_days, -1, -1):
        dt = now - timedelta(days=d)
        if is_eclipse(_jd(dt)):
            return {"date": dt.strftime("%Y-%m-%d"), "eclipse": "lunar/solar"}
    return None

def eclipse_hits_angle(chart: dict, eclipse_lon: float, orb: float = 3.0) -> str | None:
    """Check if an eclipse degree hits a chart angle (ASC/MC/DSC/IC)."""
    asc = chart["ascendant"]["longitude"] % 360
    mc = chart["midheaven"]["longitude"] % 360
    angles = {"ASC": asc, "MC": mc, "DSC": (asc+180)%360, "IC": (mc+180)%360}
    for name, lon in angles.items():
        diff = abs(eclipse_lon - lon) % 360
        if diff > 180: diff = 360 - diff
        if diff <= orb:
            return name
    return None

def macro_regime(now: datetime) -> dict:
    """Jupiter-Neptune (inflation) vs Saturn-Neptune (deflation) regime."""
    jd = _jd(now)
    jup = _longitude(jd, swe.JUPITER)
    sat = _longitude(jd, swe.SATURN)
    nep = _longitude(jd, swe.NEPTUNE)

    def aspect_diff(a, b):
        for asp in [0, 60, 90, 120, 180]:
            d = abs((a - b) % 360 - asp)
            d = min(d, 360 - d)
            if d < 6.0:
                return asp, d
        return None, None

    jn, jn_orb = aspect_diff(jup, nep)
    sn, sn_orb = aspect_diff(sat, nep)

    result = {"jupiter_neptune": jn, "saturn_neptune": sn}
    if jn is not None and (sn is None or jn_orb < sn_orb):
        result["regime"] = "INFLATION"
        result["bias"] = "favor GC (gold), commodities — avoid bonds"
    elif sn is not None:
        result["regime"] = "DEFLATION"
        result["bias"] = "favor treasuries/bonds — reduce gold"
    else:
        result["regime"] = "NEUTRAL"
        result["bias"] = "no macro tilt"
    return result

if __name__ == "__main__":
    now = datetime.now()
    mr = macro_regime(now)
    print(f"Macro regime: {mr['regime']}  ({mr['bias']})")
    print(f"  Jupiter-Neptune aspect: {mr['jupiter_neptune']}")
    print(f"  Saturn-Neptune aspect:  {mr['saturn_neptune']}")
    ecl = recent_eclipse(now)
    if ecl:
        print(f"Recent eclipse: {ecl}")
    else:
        print("No eclipse in last 15 days")

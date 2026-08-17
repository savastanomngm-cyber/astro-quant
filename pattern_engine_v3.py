#!/usr/bin/env python3
"""
PATTERN ENGINE V3 — Statistical Pattern Learning
===================================================
Upgraded pattern learning with:
  - Multi-horizon support (3, 5, 7 day)
  - Statistical significance testing (t-test vs p-value)
  - Profit factor computation
  - Horizon deduplication (keeps best)
  - SHORT signal amplification (lower edge threshold)
  - Regime context (above/below 200MA)
  - Rectification support via rectified_times_v3.json
"""

from __future__ import annotations
import json, math, os
from collections import defaultdict
from datetime import datetime, timedelta

import swisseph as swe
swe.set_ephe_path()

from astro_core_v2 import (
    calculate_chart, fidaria, distributor, bound_ruler,
    profected_asc, SIGN_NAMES,
)


def load_rectified() -> dict:
    """Load rectified birth times from rectified_times_v3.json."""
    paths = [
        os.path.join(os.path.dirname(__file__), "rectified_times_v3.json"),
        "rectified_times_v3.json",
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    # Fallback: hardcoded rectified times (v37 → v3)
    return {
        "NQ": {"hour": 21, "min": 0, "sec": 0},
        "ES": {"hour": 14, "min": 30, "sec": 0},
        "GC": {"hour": 4, "min": 0, "sec": 0},
        "ITA": {"hour": 9, "min": 30, "sec": 0},
        "PPA": {"hour": 9, "min": 30, "sec": 0},
        "SOXX": {"hour": 9, "min": 30, "sec": 0},
    }


# Moon's next applying aspect helper

def _moon_applying_to(jd, moon_lon):
    """What natal planet does the transiting Moon next aspect by Ptolemaic aspect?"""
    planets = {
        "Sun": swe.SUN, "Mercury": swe.MERCURY, "Venus": swe.VENUS,
        "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN,
    }
    aspects = [
        (0, "conjunction"), (60, "sextile"), (90, "square"),
        (120, "trine"), (180, "opposition"),
    ]
    planet_names = {
        swe.SUN: "Sun", swe.MERCURY: "Mercury", swe.VENUS: "Venus",
        swe.MARS: "Mars", swe.JUPITER: "Jupiter", swe.SATURN: "Saturn",
    }
    best = None
    next_sign_boundary = (int(moon_lon / 30) + 1) * 30
    for name, pid in planets.items():
        pres = swe.calc_ut(jd, pid, swe.FLG_SWIEPH)
        plon = pres[0][0] % 360
        for aspect_deg, aspect_name in aspects:
            target = (plon + aspect_deg) % 360
            travel = (target - moon_lon) % 360
            if travel < 0.01:
                continue
            if travel > next_sign_boundary:  # won't reach before sign change
                continue
            if best is None or travel < best[1]:
                best = (planet_names.get(pid, name), travel)
    return best[0] if best else "void"


def get_state(chart, utc_dt):
    """
    Compute the astro state for a given UTC datetime.

    Returns dict with: main, sub, dist, house, moon_phase, moon_sign,
    plus new fields: sect, bull_bear_regime
    """
    # Fidaria
    birth_utc = chart.get("utc_time", chart.get("as_of"))
    if birth_utc is None:
        # Estimate from chart data
        birth_utc = utc_dt - timedelta(days=365 * 25)  # rough

    main, sub, days_in_sub = fidaria(birth_utc, utc_dt, chart.get("sect", "Diurnal"))

    # Distributor
    dist = distributor(chart, utc_dt)
    # MC directed through the bounds (manual Ch.8 — Asc AND MC are separate significators)
    from astro_core_v2 import mc_distributor
    mc_bound = mc_distributor(chart, utc_dt)

    # Profected ASC + bound ruler
    prof_lon = profected_asc(chart, utc_dt)
    prof_sign = int(prof_lon / 30)
    prof_bound = bound_ruler(prof_lon)

    # House (whole sign from profected ASC)
    asc_sign = chart["ascendant"]["sign"] if isinstance(chart.get("ascendant"), dict) else chart["ascendant"].sign_index
    house = (prof_sign - asc_sign + 12) % 12 + 1

    # Moon phase
    jd = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day,
                    utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0)
    moon_lon = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)[0][0] % 360
    sun_lon = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)[0][0] % 360
    moon_phase_angle = (moon_lon - sun_lon) % 360
    moon_phase_idx = int(moon_phase_angle / 45) % 8  # 0-7 (New → Last Quarter)
    moon_sign = int(moon_lon / 30)

    # Moon's application: which planet the Moon will next aspect by Ptolemaic aspect
    moon_applies = _moon_applying_to(jd, moon_lon)

    # Regime detection: compare current price to 200-day moving average
    # (computed externally and passed in, or flagged as unknown)
    regime = "unknown"

    return {
        "main": main,
        "sub": sub,
        "dist": dist,
        "mc_bound": mc_bound,
        "house": house,
        "moon_phase": f"MP{moon_phase_idx}",
        "moon_sign": moon_sign,
        "moon_applies": moon_applies,
        "prof_bound": prof_bound,
        "sect": chart.get("sect", "Diurnal"),
        "bull_bear": regime,
        "days_in_sub": days_in_sub,
    }


def state_key(st, horizon: int = 7) -> str:
    """
    Build a state key for pattern matching.
    FAST-ONLY key (see critical finding: Fidaria/bound don't recur across
    train/test in a single backtest window). Components:
      H{house}       — profected house (12 values, recurs yearly)
      {moon_phase}   — MP0-7 (8 values, ~3.5 day cycle, recurs)
      MA{planet}     — moon_applies (fastest, daily)
      {horizon}d
    The slow rulers (main/sub/dist,~10yr+) are READ from st for persona traits
    but NOT part of the matching key, so personas can recur and be tested OOS.
    """
    ma = st.get("moon_applies", "void")
    return f"H{st['house']}_{st['moon_phase']}_MA{ma}_{horizon}d"


# ====================================================================
# PATTERN BUILDING
# ====================================================================

def build_patterns(chart, dd, dates, horizons=(3, 5, 7)):
    """
    Build raw pattern returns for each state/horizon combination.
    """
    pats = defaultdict(list)
    n = len(dates)

    # Compute simple moving average for regime detection
    closes = []
    for d in dates:
        if d in dd:
            closes.append(dd[d]["close"])
    ma200 = []
    for i in range(len(closes)):
        if i >= 199:
            ma200.append(sum(closes[i - 199 : i + 1]) / 200)
        else:
            ma200.append(closes[i])

    for i in range(n - max(horizons) - 1):
        sd = dates[i]
        if sd not in dd:
            continue

        signal_utc = datetime.strptime(sd, "%Y-%m-%d").replace(hour=17)
        try:
            st = get_state(chart, signal_utc)
        except Exception:
            continue

        # Determine regime context
        current_close = dd[sd]["close"]
        regime = "bull" if i < len(ma200) and current_close > ma200[i] else "bear"

        entry_open = dd[dates[i + 1]]["open"]

        for hz in horizons:
            exit_idx = i + 1 + hz
            if exit_idx >= n:
                continue
            exit_close = dd[dates[exit_idx]]["close"]
            r = exit_close / entry_open - 1.0

            sk = state_key(st, hz)
            pats[sk].append({
                "return": r,
                "regime": regime,
                "date": sd,
            })

    return dict(pats)


# ====================================================================
# PATTERN LEARNING (the upgraded core)
# ====================================================================

def learn_patterns(
    pats,
    min_n: int = 12,
    max_p: float = 0.02,
    min_edge: float = 0.52,
    dedup_horizons: bool = True,
    amplify_short: bool = True,
) -> dict:
    """
    Learn valid patterns from raw return data.
    """
    learned = {}

    for sk, samples in pats.items():
        n = len(samples)
        if n < min_n:
            continue

        returns = [s["return"] for s in samples]

        # Basic stats
        mean_ret = sum(returns) / n
        std_ret = (sum((r - mean_ret) ** 2 for r in returns) / (n - 1)) ** 0.5 if n > 1 else 0.01

        # Determine direction
        if mean_ret > 0:
            direction = "LONG"
            edge_threshold = min_edge
        else:
            direction = "SHORT"
            if isinstance(amplify_short, (int, float)):
                edge_threshold = float(amplify_short)
            elif amplify_short:
                edge_threshold = 0.35
            else:
                edge_threshold = min_edge

        # Win rate
        wins = [r for r in returns if (direction == "LONG" and r > 0) or (direction == "SHORT" and r < 0)]
        win_rate = len(wins) / n

        # Edge check
        if win_rate < edge_threshold:
            continue

        # Average move (absolute)
        avg_move = abs(mean_ret)

        # Profit factor (fixed: guards against ZeroDivision and caps no-loss PF)
        gross_wins = sum(abs(r) for r in wins)
        losses = [r for r in returns if (direction == "LONG" and r <= 0) or (direction == "SHORT" and r >= 0)]
        gross_losses = sum(abs(r) for r in losses) if losses else 0.0
        if gross_losses > 0:
            profit_factor = gross_wins / gross_losses
        elif gross_wins > 0:
            profit_factor = 10.0
        else:
            profit_factor = 0.0

        # Statistical significance
        if std_ret > 0:
            t_stat = mean_ret / (std_ret / math.sqrt(n))
            from math import erfc
            p_value = float(erfc(abs(t_stat) / math.sqrt(2)))
        else:
            t_stat = 0.0
            p_value = 1.0

        if p_value > max_p:
            continue

        # Regime context
        n_bull = sum(1 for s in samples if s["regime"] == "bull")
        n_bear = n - n_bull

        # Score: composite metric
        score = (win_rate - 0.5) * (avg_move / max(0.001, std_ret)) * math.sqrt(n) * (-math.log10(max(p_value, 1e-300)))

        learned[sk] = {
            "direction": direction,
            "horizon": 7,
            "n_samples": n,
            "n_bull": n_bull,
            "n_bear": n_bear,
            "win_rate": win_rate,
            "avg_move": avg_move,
            "std_move": std_ret,
            "profit_factor": profit_factor,
            "p_value": p_value,
            "t_stat": t_stat,
            "score": score,
            "regime_bull_pct": n_bull / n if n else 0,
        }

    if dedup_horizons and learned:
        # Group by base key (without horizon), keep best
        grouped = defaultdict(list)
        for sk, data in learned.items():
            base = "_".join(sk.split("_")[:-1])
            grouped[base].append((sk, data))
        deduped = {}
        for base, entries in grouped.items():
            entries.sort(key=lambda x: x[1]["score"], reverse=True)
            deduped[entries[0][0]] = entries[0][1]
        learned = deduped

    return learned


def pattern_summary(patterns, top_n=5):
    """Print summary statistics for learned patterns."""
    if not patterns:
        print("  No patterns found.")
        return
    n = len(patterns)
    longs = [p for p in patterns.values() if p["direction"] == "LONG"]
    shorts = [p for p in patterns.values() if p["direction"] == "SHORT"]
    summary = {
        "total": n,
        "long_count": len(longs),
        "short_count": len(shorts),
        "avg_win_rate": sum(p["win_rate"] for p in patterns.values()) / n,
        "avg_n": sum(p["n_samples"] for p in patterns.values()) / n,
        "avg_avg_move": sum(p["avg_move"] for p in patterns.values()) / n,
    }
    return summary


if __name__ == "__main__":
    print("Pattern Engine V3 — self-test")
    # Quick test: does learning work on synthetic data?
    pats = {
        "Sun_Venus_Mercury_H5_MP2_7d": [
            {"return": 0.02, "regime": "bull", "date": "2020-01-01"}
            for _ in range(15)
        ] + [{"return": -0.005, "regime": "bull", "date": "2020-03-01"} for _ in range(5)],
    }
    learned = learn_patterns(pats, min_n=12, max_p=0.01, min_edge=0.52)
    print(f"  Learned: {len(learned)} patterns")
    if learned:
        p = list(learned.values())[0]
        print(f"  WR={p['win_rate']:.1%} PF={p['profit_factor']:.2f} p={p['p_value']:.2e}")

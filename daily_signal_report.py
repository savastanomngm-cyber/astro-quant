#!/usr/bin/env python3
"""
DAILY SIGNAL REPORT — Astro-Quant Persona-Based Signal Generator
=================================================================
Generates daily trading signals using astro persona matching
with fallback chain: exact → prefix → main+moon → main → best-pf.

Also applies Moon application filter and HMM regime detection.
"""

import os, sys
from datetime import datetime, timedelta

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import yfinance as yf
import pandas as pd
import math

from astro_configs import INSTRUMENTS
from astro_knowledge import chart_to_snapshot
from pattern_engine_v3 import build_patterns as bp, learn_patterns as lp, get_state, state_key, load_rectified
from astro_personas import generate_trader_personas_from_learned


def generate_daily_signal(ticker, date_str=None, min_wr=0.50, min_pf=1.0):
    """Generate today's signal for one ticker."""
    # SHORT signals broken across all futures — long-only is the robust configuration.
    _use_s = False if ticker in {"GC", "NQ", "ES"} else True

    inst = INSTRUMENTS.get(ticker)
    if not inst: return None
    rect = load_rectified().get(ticker)
    if not rect: return None
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                      rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    from astro_core_v2 import calculate_chart as cc
    chart_dict = cc(local_dt.year, local_dt.month, local_dt.day,
                    local_dt.hour, local_dt.minute, local_dt.second,
                    inst.birth_lat, inst.birth_lon, inst.birth_tz)
    chart_snap = chart_to_snapshot(ticker=ticker, chart_dict=chart_dict,
                                    birth_utc=utc_dt, tz_offset=inst.birth_tz,
                                    lat=inst.birth_lat, lon=inst.birth_lon)
    try:
        symbol = inst.data_symbol if inst and inst.data_symbol else f"{ticker}=F"
        data = None
        import time as _t
        for attempt in range(3):
            try:
                tkr = yf.Ticker(symbol)
                data = tkr.history(start="2010-01-01")
                if data is not None and not data.empty: break
            except: pass
            if attempt < 2: _t.sleep(2 + attempt)
        if data is None or data.empty: return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        dd = {}; all_dates = []
        for idx, row in data.iterrows():
            ds = idx.strftime("%Y-%m-%d")
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            if o <= 0 or c <= 0: continue
            dd[ds] = {"open": o, "high": h, "low": l, "close": c}
            all_dates.append(ds)
        pats = bp(chart_dict, dd, all_dates, horizons=[3,5,7])
        learned_raw = lp(pats, min_n=12, max_p=0.02, min_edge=0.52)
    except Exception: return None
    # Disable LLM by default (use_llm=False) to keep daily signal fast + token-light
    personas = generate_trader_personas_from_learned(learned_raw, ticker, chart_snap, use_llm=False)
    personas_dict = {p.persona_id: p for p in personas}
    today = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
    signal_utc = today.replace(hour=17)
    st = get_state(chart_dict, signal_utc)
    persona = None; match_type = "exact"
    def _best(candidates):
        return max(candidates, key=lambda x: min(x[1].historical_pf, 20) * math.log(max(x[1].n_samples, 2)))[1]
    for hz in [3,5,7]:
        sk = state_key(st, hz)
        if sk in personas_dict: persona = personas_dict[sk]; match_type = "exact"; break
    # Fast-only key (H{house}_{moon_phase}_MA{planet}_{horizon}d):
    # fallbacks relax moon_applies first, then house, then moon_phase.
    if not persona:
        # same house + moon_phase, any moon_applies (prefix by fast tuple)
        prefix = f"H{st['house']}_{st['moon_phase']}_"
        candidates = [(pid, p) for pid, p in personas_dict.items() if pid.startswith(prefix)]
        if candidates: persona = _best(candidates); match_type = "prefix"
    if not persona:
        # same moon_phase, any house/applies
        candidates = [(pid, p) for pid, p in personas_dict.items() if f"_{st['moon_phase']}_" in pid]
        if candidates: persona = _best(candidates); match_type = "moon"
    if not persona:
        # same house, any moon_phase/applies
        candidates = [(pid, p) for pid, p in personas_dict.items() if pid.startswith(f"H{st['house']}_")]
        if candidates: persona = _best(candidates); match_type = "house"
    if not persona: return None
    if persona.historical_win_rate < min_wr: return None
    if persona.historical_pf < min_pf: return None
    if not _use_s and persona.pattern_direction == "SHORT": return None

    # NQ trend gate: refuse LONG when below 200-day MA
    if ticker == "NQ" and persona.pattern_direction == "LONG":
        ds = today.strftime("%Y-%m-%d")
        if ds in dd:
            closes = [dd[d]["close"] for d in sorted(all_dates) if d <= ds]
            if len(closes) >= 200:
                ma200 = sum(closes[-200:]) / 200
                if dd[ds]["open"] < ma200: return None

    moon_applies = st.get("moon_applies", "void")
    moon_mult = 1.0
    # Quant-validated (466 OOS trades, corrected bounds):
    #   Moon applying to the luminaries or Mercury ⇒ PF < 1.0 in most cells.
    #   These are HARD SKIPS, not soft multipliers.
    if moon_applies in ("Sun", "Mercury", "void"):
        return None
    if moon_applies in ("Jupiter", "Venus"):
        moon_mult = 1.15
    elif moon_applies in ("Saturn", "Mars"):
        moon_mult = 0.85

    # Fidaria sub-period ruler (Rectification Manual Ch.7, validated: p<0.04):
    #   Saturn sub = 69% WR (size up). Jupiter/Moon sub = 41-43% WR (caution/skip).
    fid_sub = st.get("sub", "?")
    fid_mult = 1.0
    if fid_sub == "Saturn":
        fid_mult = 1.20
    elif fid_sub in ("Jupiter", "Moon"):
        fid_mult = 0.80

    # ── Directed-Bound Regime Gate (Rectification Manual Ch.8 + Dr. H video) ──
    # The directed Ascendant/MC moving through the Egyptian bounds is the
    # "stage" / background Time-Lord.  A SATURN-ruled bound = command-and-control,
    # deregulation, contraction (video's 2026-28 Saturn-Virgo era: hollowing,
    # disruption of big-data/ML monopolies).  Restrict speculative LONGS there.
    # Mars-ruled bound = forceful/extractive (allowed, but reduce size).
    dist = st.get("dist", "?")
    mc_b = st.get("mc_bound", "?")
    bound_rulers = {r for r in (dist, mc_b) if r}
    bound_note = f"bound:{dist}/{mc_b}"
    bound_mult = 1.0
    if persona.pattern_direction == "LONG":
        if "Saturn" in bound_rulers:
            # contraction regime — block plain speculative longs
            return None
        if "Mars" in bound_rulers:
            bound_mult = 0.85  # volatile/extractive — reduce size

    pf = max(0.5, persona.historical_pf)
    tp_mult = min(6.0, max(1.2, 1.5 + math.log(pf + 0.5)))
    stop_pct = persona.stop_tightness
    # Cap stop/TP at realistic futures levels via ATR sizing:
    # actual index futures stops are ~1-2 ATR, and TP at 2R — NOT the persona's
    # 5-8% stop / unbounded 21% TP (which is unwritable for real accounts).
    try:
        from sizing import atr_pct, compute_stop_tp
        closes = [dd[d]["close"] for d in sorted(all_dates) if d in dd][-60:]
        atr = atr_pct(closes, 14)
        stop_pct, tp_pct = compute_stop_tp(stop_pct, atr, rt_ratio=2.0)
    except Exception:
        stop_pct, tp_pct = min(stop_pct, 0.02), stop_pct * 2.0
    # Real persona-derived execution guidance (previously hardcoded/empty)
    from astro_matraix_backtest import _entry_timing, _timeframe_for_persona, _execution_note
    try:
        entry_timing = _entry_timing(persona)
        timeframe = _timeframe_for_persona(persona)
        note = _execution_note(persona)
    except Exception:
        entry_timing, timeframe, note = "market_open", "daily", ""
    return {
        "ticker": ticker, "date": today.strftime("%Y-%m-%d"),
        "direction": persona.pattern_direction,
        "conviction": round(persona.conviction_mult * moon_mult * fid_mult * bound_mult, 2),
        "moon_applies": moon_applies,
        "bound_rulers": bound_note,
        "fidaria_sub": fid_sub,
        "sl_pct": f"{stop_pct:.1%}",
        "tp_pct": f"{stop_pct * tp_mult:.1%}",
        "hold_days": persona.max_hold_days,
        "position_pct": f"{persona.position_size_pct:.0%}",
        "persona_id": persona.persona_id,
        "risk_tolerance": persona.risk_tolerance,
        "pf": round(persona.historical_pf, 2),
        "wr": f"{persona.historical_win_rate:.0%}",
        "n_samples": persona.n_samples,
        "entry_timing": entry_timing,
        "timeframe": timeframe,
        "note": note,
        "match_type": match_type,
    }
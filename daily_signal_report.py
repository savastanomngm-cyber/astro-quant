#!/usr/bin/env python3
"""
DAILY SIGNAL REPORT — Telegram-formatted Persona Signals
==========================================================
Run:   python3 daily_signal_report.py
Cron:  0 13 * * 1-5 cd /Users/axio/Desktop/Fifa/astro-quant54 && python3 daily_signal_report.py

Generates today's MatrAIx persona signals for NQ, ES, GC with fallback
matching for states not in the training database.

FALLBACK ORDER (when exact state not found):
  1. Same fidaria main + sub + distributor (any horizon)
  2. Same fidaria main ruler + same moon phase
  3. Same fidaria main ruler only
  4. Same moon phase only
  5. No signal

Output: prints formatted Telegram message + saves to ~/.astro-quant/daily_signals.json
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure the current directory is in path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import yfinance as yf
import pandas as pd

from astro_core_v2 import calculate_chart as _cc_no_direct_use
from pattern_engine_v3 import (
    load_rectified, get_state, state_key,
    build_patterns as bp, learn_patterns as lp,
    pattern_summary,
)
from astro_personas import generate_trader_personas_from_learned
from astro_matraix_backtest import (
    chart_to_snapshot,
    INSTRUMENTS, _entry_timing, _timeframe_for_persona, _execution_note,
)
from trader_persona_schema import ALL_DIMENSIONS

# ====================================================================
# CONFIG
# ====================================================================

TICKERS = ["NQ", "ES", "GC"]
MIN_WR = 0.50
MIN_PF = 1.0
USE_SHORT = True
# GC SHORT signals empirically broken — override for this ticker
TICKER_NO_SHORT = {"GC"}

# ====================================================================
# CORE LOGIC
# ====================================================================

def generate_daily_signal(
    ticker: str,
    date_str: str | None = None,
    min_wr: float = 0.50,
    min_pf: float = 1.0,
) -> dict | None:
    """
    Generate today's signal for one ticker.
    
    PRIORITY 1: Use the standard generate_live_signals() — exact state match.
    PRIORITY 2: Fallback matching when state not in training data.
    
    Returns dict with signal fields, or None if no valid signal found.
    """
    from astro_matraix_backtest import generate_live_signals as gls

    # ---- TRY STANDARD GENERATOR FIRST (exact match) ----
    try:
        sigs = gls(
            ticker=ticker,
            date_str=date_str,
            min_win_rate=min_wr,
            min_pf=min_pf,
            use_short=USE_SHORT and ticker not in TICKER_NO_SHORT,
        )
        if sigs:
            s = sigs[0]
            s["match_type"] = "exact"
            return s
    except Exception:
        pass

    # GC SHORT override for fallback path too
    if ticker in TICKER_NO_SHORT:
        _use_s = False
    else:
        _use_s = USE_SHORT

    # ---- FALLBACK: build from scratch with relaxed matching ----
    inst = INSTRUMENTS.get(ticker)
    if not inst:
        return None
    rect = load_rectified().get(ticker)
    if not rect:
        return None

    utc_dt = datetime(
        inst.birth_year, inst.birth_month, inst.birth_day,
        rect["hour"], rect["min"], rect["sec"]
    )
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    from astro_core_v2 import calculate_chart as cc
    chart_dict = cc(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    chart_snap = chart_to_snapshot(
        ticker=ticker, chart_dict=chart_dict,
        birth_utc=utc_dt, tz_offset=inst.birth_tz,
        lat=inst.birth_lat, lon=inst.birth_lon,
    )

    try:
        data = yf.download(f"{ticker}=F", start="2010-01-01", progress=False, auto_adjust=True)
        if data.empty: return None
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
    except Exception:
        return None

    personas = generate_trader_personas_from_learned(learned_raw, ticker, chart_snap)
    personas_dict = {p.persona_id: p for p in personas}

    if date_str:
        today = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        today = datetime.now()
    signal_utc = today.replace(hour=17)
    st = get_state(chart_dict, signal_utc)

    persona = None
    match_type = "exact"

    def _best(candidates):
        # Weight: balance high PF with large N. PF capped at 20 to avoid tiny-N dominance.
        import math
        return max(candidates, key=lambda x: min(x[1].historical_pf, 20) * math.log(max(x[1].n_samples, 2)))[1]

    # 1. Exact
    for hz in [3, 5, 7]:
        sk = state_key(st, hz)
        if sk in personas_dict:
            persona = personas_dict[sk]; match_type = "exact"; break

    # 2. Prefix
    if not persona:
        prefix = f"{st['main']}_{st['sub']}_{st['dist']}_"
        candidates = [(pid, p) for pid, p in personas_dict.items() if pid.startswith(prefix)]
        if candidates:
            persona = _best(candidates); match_type = "prefix"

    # 3. Main+moon
    if not persona:
        candidates = [(pid, p) for pid, p in personas_dict.items()
                      if pid.startswith(st['main']) and f"_{st['moon_phase']}_" in pid]
        if candidates:
            persona = _best(candidates); match_type = "main+moon"

    # 4. Main only
    if not persona:
        candidates = [(pid, p) for pid, p in personas_dict.items() if pid.startswith(st['main'])]
        if candidates:
            persona = _best(candidates); match_type = "main"

    # 5. Moon only
    if not persona:
        candidates = [(pid, p) for pid, p in personas_dict.items() if f"_{st['moon_phase']}_" in pid]
        if candidates:
            persona = _best(candidates); match_type = "moon"

    if not persona:
        return None

    if persona.historical_win_rate < min_wr: return None
    if persona.historical_pf < min_pf: return None
    if not _use_s and persona.pattern_direction == "SHORT": return None

    import math
    pf = max(0.5, persona.historical_pf)
    tp_mult = min(6.0, max(1.2, 1.5 + math.log(pf + 0.5)))
    stop_pct = persona.stop_tightness

    return {
        "ticker": ticker,
        "date": today.strftime("%Y-%m-%d"),
        "direction": persona.pattern_direction,
        "conviction": round(persona.conviction_mult, 2),
        "sl_pct": f"{stop_pct:.1%}",
        "tp_pct": f"{stop_pct * tp_mult:.1%}",
        "hold_days": persona.max_hold_days,
        "position_pct": f"{persona.position_size_pct:.0%}",
        "persona_id": persona.persona_id,
        "risk_tolerance": persona.risk_tolerance,
        "pf": round(persona.historical_pf, 2),
        "wr": f"{persona.historical_win_rate:.0%}",
        "n_samples": persona.n_samples,
        "entry_timing": _entry_timing(persona),
        "timeframe": _timeframe_for_persona(persona),
        "note": _execution_note(persona),
        "match_type": match_type,
    }

    # Try HMM regime detection
    try:
        from astro_hmm import load_hmm_params, predict_regime, observation_index
        params = load_hmm_params(ticker)
        if params:
            is_default = abs(params.A[0][0] - 0.70) < 0.001 and abs(params.A[3][3] - 0.30) < 0.001
            if not is_default:
                mock_obs = [observation_index(sig['direction'], sig['direction'] == 'LONG', 0.01)]
                info = predict_regime(params, mock_obs)
                sig['hmm_regime'] = info['current_regime']
                sig['hmm_recommendation'] = info['recommendation']
    except Exception:
        pass

    return sig

# ====================================================================
# FORMATTERS
# ====================================================================

def format_signal_line(sig: dict) -> str:
    """Format one signal as a Telegram markdown line."""
    d = sig["direction"]
    emoji = "🟢" if d == "LONG" else "🔴" if d == "SHORT" else "⚪"
    match_tag = ""
    if sig.get("match_type") != "exact":
        match_tag = f" ⚠fallback:{sig['match_type']}"

    return (
        f"{emoji} *{sig['ticker']}*: {d} | "
        f"WR={sig['wr']} PF={sig['pf']} | "
        f"{sig['conviction']}x conv | "
        f"SL={sig['sl_pct']} TP={sig['tp_pct']} | "
        f"{sig['hold_days']}d hold"
        f"{match_tag}"
    )


def format_full_report(signals: dict) -> str:
    """Format the complete Telegram message."""
    today = datetime.now().strftime("%a, %d %b %Y")
    lines = [f"📊 *AstroMiroQuant Daily Signals* — {today}", ""]

    for ticker in TICKERS:
        sig = signals.get(ticker)
        if sig:
            line = format_signal_line(sig)
            # Append HMM regime if available
            hmm_info = sig.get("hmm_regime")
            if hmm_info:
                line += f" | {hmm_info} regime"
            lines.append(line)
        else:
            lines.append(f"⚪ *{ticker}*: No signal — filters not met")

    # HMM summary line
    regimes = []
    for ticker in TICKERS:
        sig = signals.get(ticker)
        if sig and sig.get("hmm_regime"):
            regimes.append(f"{ticker}:{sig['hmm_regime']}")
    if regimes:
        lines.append("")
        lines.append(f"📈 *Regimes:* {' | '.join(regimes)}")

    # Fallback warning
    any_fallback = any(
        s.get("match_type") != "exact"
        for s in signals.values() if s
    )
    if any_fallback:
        lines.append("")
        lines.append(
            "⚠️ Fallback matching used — today's astro state "
            "is new (not in training data). Consider half sizing."
        )

    lines.append("")
    lines.append("_Auto-generated by AstroMiroQuant v0.62_")

    return "\n".join(lines)

# ====================================================================
# MAIN
# ====================================================================

def main():
    """Run all tickers and print the report."""
    print("=" * 50)
    print(" AstroMiroQuant — Daily Signal Report")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    signals = {}
    for ticker in TICKERS:
        print(f"\n  {ticker}...", end=" ", flush=True)
        try:
            sig = generate_daily_signal(ticker)
            if sig:
                print(
                    f"{sig['direction']} WR={sig['wr']} PF={sig['pf']} "
                    f"(match: {sig.get('match_type', '?')})"
                )
                signals[ticker] = sig
            else:
                print("NO SIGNAL")
        except Exception as e:
            print(f"ERROR: {e}")

    print("\n" + "=" * 50)
    print(format_full_report(signals))
    
    # === Lower-TF signals (1H + 4H) ===
    print(f"\n{'─'*45}")
    print("  LOWER TIMEFRAME SIGNALS (1H / 4H)")
    lt_signals = {}
    for ticker in TICKERS:
        for bs in ["1h", "4h"]:
            try:
                from astro_mtf import generate_mtf_live_signal
                sig = generate_mtf_live_signal(ticker=ticker, bar_size=bs, min_n=8)
                if sig:
                    emoji = "🟢" if sig["direction"] == "LONG" else "🔴"
                    print(f"  {emoji} {ticker} {bs}: {sig['direction']} PF={sig['pf']} WR={sig['wr']} ({sig['match_type']})")
                    lt_signals[f"{ticker}_{bs}"] = sig
                else:
                    print(f"  ⚪ {ticker} {bs}: no signal")
            except Exception as e:
                print(f"  ⚪ {ticker} {bs}: error — {e}")
    
    print("=" * 50)

    # Save to file
    memory_dir = os.path.expanduser("~/.astro-quant")
    os.makedirs(memory_dir, exist_ok=True)
    save_path = os.path.join(memory_dir, "daily_signals.json")
    all_signals = {"daily": signals, "lower_tf": lt_signals}
    with open(save_path, "w") as f:
        json.dump(all_signals, f, indent=2, default=str)
    print(f"\n  Saved to {save_path}")

    return signals


if __name__ == "__main__":
    main()
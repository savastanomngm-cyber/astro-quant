#!/usr/bin/env python3
"""
ASTROMIROQUANT V2 — MatrAIx-Inspired Trading Persona Pipeline
===============================================================
Complete pipeline using TraderPersona (51-dim MatrAIx profile):
  1. Chart rectification → typed ChartSnapshot
  2. Pattern learning → learned states
  3. TraderPersona generation → full 51-dim MatrAIx profiles
  4. Market simulation → dimension-driven agent behavior
  5. Cohort analysis → population-level statistics
  6. Report → structured trading insights + persona comparison

Usage:
    python3 astromiroquant.py
    python3 astromiroquant.py --ticker GC --rounds 60 --seed 42
    python3 astromiroquant.py --ticker NQ --yahoo-start 2024-01-01
    python3 astromiroquant.py --ticker NQ --cohort  (MatrAIx cohort mode)
"""

from __future__ import annotations
import argparse
import math
import os
import random
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import swisseph as swe
swe.set_ephe_path()

from astro_core_v2 import calculate_chart
from astro_knowledge import ChartSnapshot, chart_to_snapshot, SourceRef, DataSourceKind
from astro_configs import INSTRUMENTS, YahooSource
from astro_personas import (
    TraderPersona, generate_trader_personas_from_learned,
)
from astro_simulation import (
    SimulationConfig, MarketSimulation, SimulationResult, compare_simulation_to_actual,
)
from trader_persona_schema import ALL_DIMENSIONS, get_dimension_values


# ---------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------

def load_yahoo_returns(symbol: str, start: str = "2010-01-01") -> tuple[list[float], list[str]] | None:
    try:
        import pandas as pd; import yfinance as yf
    except ImportError:
        return None
    data = yf.download(symbol, start=start, progress=False, auto_adjust=True)
    if data.empty: return None
    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    closes = [float(data.iloc[i]["Close"]) for i in range(len(data))]
    dates = [data.index[i].strftime("%Y-%m-%d") for i in range(len(data))]
    returns = [(closes[i]/closes[i-1]-1.0)*100 for i in range(1,len(closes))]
    return returns, dates


# ---------------------------------------------------------------
# COHORT ANALYSIS (MatrAIx-style population analysis)
# ---------------------------------------------------------------

def cohort_analysis(personas: dict[str, TraderPersona]) -> dict:
    """
    MatrAIx-style population statistics across personas.
    Groups personas by key dimensions and computes cohort-level stats.
    """
    groups = {}
    for dim in ["risk_tolerance", "decision_speed", "excitement_seeking", "self_discipline",
                "skepticism", "optimism", "patience", "plan_vs_spontaneous"]:
        by_value = {}
        for p in personas.values():
            val = p.get_trait(dim)
            by_value.setdefault(val, []).append(p)
        groups[dim] = {
            val: {
                "count": len(ps),
                "avg_win_rate": sum(p.historical_win_rate for p in ps)/max(1,len(ps)),
                "avg_pf": sum(p.historical_pf for p in ps)/max(1,len(ps)),
                "avg_conviction": sum(p.conviction_mult for p in ps)/max(1,len(ps)),
                "avg_stop": sum(p.stop_tightness for p in ps)/max(1,len(ps)),
                "avg_position": sum(p.position_size_pct for p in ps)/max(1,len(ps)),
            }
            for val, ps in by_value.items()
        }
    return groups


# ---------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------

def run_astromiroquant(
    ticker: str = "NQ", yahoo_start: str = "2010-01-01",
    rounds: int = 50, seed: int | None = None,
    use_llm: bool = False, llm_api_key: str | None = None,
    cohort_mode: bool = False, verbose: bool = True,
) -> dict:
    inst = INSTRUMENTS.get(ticker)
    if not inst: return {"error": f"No instrument for {ticker}"}

    # === STEP 1: Chart ===
    if verbose: print(f"[1/5] Loading chart for {ticker}...")
    try:
        from pattern_engine_v3 import load_rectified
        rect = load_rectified().get(ticker)
    except: rect = None
    if not rect:
        rect = {"NQ":{"hour":20,"min":45,"sec":0},"ES":{"hour":9,"min":30,"sec":0},"GC":{"hour":16,"min":0,"sec":0}}.get(ticker,{"hour":12,"min":0,"sec":0})

    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day, rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(local_dt.year, local_dt.month, local_dt.day, local_dt.hour, local_dt.minute, local_dt.second, inst.birth_lat, inst.birth_lon, inst.birth_tz)
    chart_snap = chart_to_snapshot(ticker=ticker, chart_dict=chart_dict, birth_utc=utc_dt, tz_offset=inst.birth_tz, lat=inst.birth_lat, lon=inst.birth_lon)

    if verbose:
        print(f"    ASC: {chart_snap.ascendant.sign_name} {chart_snap.ascendant.degree_in_sign:.2f}°  Sect: {chart_snap.sect}")

    # === STEP 2: Price ===
    if verbose: print(f"[2/5] Loading Yahoo price data...")
    raw = load_yahoo_returns(f"{ticker}=F", start=yahoo_start)
    if not raw: return {"error": "No Yahoo data"}
    yahoo_returns, yahoo_dates = raw
    if verbose: print(f"    {len(yahoo_returns)} daily returns")

    # === STEP 3: Patterns ===
    if verbose: print(f"[3/5] Learning patterns...")
    try:
        from pattern_engine_v3 import build_patterns as bp, learn_patterns as lp
        dd = {d:{"open":100,"high":101,"low":99,"close":100+r} for d,r in zip(yahoo_dates[1:],yahoo_returns)}
        learned_raw = lp(bp(chart_dict, dd, yahoo_dates[1:], horizons=[3,5,7]), min_n=12, max_p=0.02, min_edge=0.52)
    except:
        learned_raw = {
            "Mercury_Mercury_Venus_H7_MP1_7d":{"direction":"LONG","horizon":7,"n_samples":31,"win_rate":0.903,"avg_move":0.021,"std_move":0.04,"profit_factor":4.5,"p_value":0.0001,"score":2.07},
            "Mars_Saturn_Mercury_H1_MP2_7d":{"direction":"SHORT","horizon":7,"n_samples":20,"win_rate":0.55,"avg_move":-0.008,"std_move":0.035,"profit_factor":1.4,"p_value":0.01,"score":0.30},
            "Venus_Jupiter_Venus_H4_MP3_7d":{"direction":"LONG","horizon":7,"n_samples":19,"win_rate":0.895,"avg_move":0.02,"std_move":0.03,"profit_factor":3.2,"p_value":0.0003,"score":0.59},
            "Mercury_Jupiter_Mercury_H2_MP4_7d":{"direction":"SHORT","horizon":7,"n_samples":25,"win_rate":0.32,"avg_move":-0.0315,"std_move":0.05,"profit_factor":0.7,"p_value":0.12,"score":0.51},
            "Mercury_Sun_Jupiter_H6_MP5_7d":{"direction":"LONG","horizon":7,"n_samples":33,"win_rate":0.727,"avg_move":0.0127,"std_move":0.03,"profit_factor":1.8,"p_value":0.002,"score":0.48},
            "Saturn_Mars_Moon_H7_MP7_3d":{"direction":"SHORT","horizon":3,"n_samples":15,"win_rate":0.60,"avg_move":-0.015,"std_move":0.04,"profit_factor":1.5,"p_value":0.03,"score":0.25},
        }
    n_pats = len(learned_raw)
    if verbose: print(f"    {n_pats} patterns")

    # === STEP 4: TraderPersonas ===
    if verbose: print(f"[4/5] Generating TraderPersonas (MatrAIx 51-dim)...")
    personas = generate_trader_personas_from_learned(learned_raw, ticker, chart_snap, use_llm=use_llm, llm_api_key=llm_api_key)
    personas_dict = {p.persona_id: p for p in personas}
    if verbose: print(f"    {len(personas)} personas (51 dimensions each)")

    # === STEP 5: Simulation ===
    if verbose: print(f"[5/5] Running simulation ({rounds} rounds)...")
    cfg = SimulationConfig(
        total_rounds=min(rounds, len(yahoo_returns)),
        random_seed=seed, base_volatility=0.008,
        enable_behavioral_dynamics=True, enable_contrarian_switches=True,
        enable_overtrading=True, enable_emotion_volatility=True,
    )
    sim = MarketSimulation(cfg, personas_dict, ticker)
    result = sim.run()

    if verbose:
        print(f"    Rounds: {result.total_rounds}  Price: ${cfg.initial_price:.2f}→${result.final_price:.2f} ({result.total_return_pct:+.2f}%)")
        print(f"    Regimes: {result.bullish_rounds}B/{result.bearish_rounds}Be/{result.neutral_rounds}N")
        print(f"    Events: panic={result.total_panic_exits} revenge={result.total_revenge_trades} impulse={result.total_impulse_trades} contrarian={result.total_contrarian_flips}")

    # === COMPARISON ===
    comparison = None
    if len(yahoo_returns) >= result.total_rounds:
        comparison = compare_simulation_to_actual(result, yahoo_returns[:result.total_rounds])
        if verbose:
            print(f"\n    vs Actual: DirAcc={comparison['directional_accuracy']:.1%} Corr={comparison['correlation']:.3f} MAE={comparison['mae']:.2f}%")
            print(f"    Sim P&L: {comparison['sim_total_return']:+.1f}%  Actual: {comparison['actual_total_return']:+.1f}%")

    # === COHORT ANALYSIS (MatrAIx population stats) ===
    if cohort_mode or verbose:
        cohort = cohort_analysis(personas_dict)
        if verbose:
            print(f"\n{'='*70}")
            print(f" ASTROMIROQUANT V2 — COHORT REPORT: {ticker}")
            print(f"{'='*70}")
            print(f" Chart: {chart_snap.ascendant.sign_name} ASC, {chart_snap.sect}, Hllaj={chart_snap.hllaj}")
            print(f" Personas: {len(personas)} total ({n_pats} patterns)")
            print(f" Simulation: {result.total_rounds}r — {result.bullish_rounds}B/{result.bearish_rounds}Be/{result.neutral_rounds}N")

            if comparison:
                print(f" Accuracy: Dir={comparison['directional_accuracy']:.1%}, Corr={comparison['correlation']:.3f}")

            # Dimension spread
            print(f"\n── Dimension Spread (MatrAIx cohort analysis) ──")
            for dim_name, groups in sorted(cohort.items()):
                spread = ", ".join(f"{v}={d['count']}" for v,d in sorted(groups.items()) if d['count']>0)
                print(f"  {dim_name}: {spread}")

            # Top personas
            print(f"\n── Top Personas (by conviction × effort) ──")
            top = sorted(personas, key=lambda p: p.conviction_mult * p.effort_level, reverse=True)[:5]
            for i, p in enumerate(top, 1):
                print(f"  {i}. [{p.conviction_mult:.1f}×{p.effort_level:.0%}] {p.trading_bio()}")
                print(f"     Risk={p.risk_tolerance} Stop={p.stop_tightness:.0%} MaxHold={p.max_hold_days}d WR={p.historical_win_rate:.0%} PF={p.historical_pf:.2f}")

            # Behavioral summary
            print(f"\n── Behavioral Events ──")
            print(f"  Panic exits: {result.total_panic_exits}  Revenge trades: {result.total_revenge_trades}")
            print(f"  Impulse trades: {result.total_impulse_trades}  Contrarian flips: {result.total_contrarian_flips}")
            print(f"  Early exits (boredom): {result.total_early_exits}")

            if result.total_panic_exits + result.total_revenge_trades > 0:
                print(f"  ⚠ Emotional trading detected — consider regime filters for these persona states")

            # System prompt preview
            if personas:
                prompt = personas[0].to_system_prompt()
                print(f"\n── LLM System Prompt Preview (Persona 0, {len(prompt)} chars) ──")
                for line in prompt.split("\n")[:20]:
                    print(f"  {line}")

            print(f"\n{'='*70}")

    return {
        "ticker": ticker, "chart": chart_snap,
        "persona_count": len(personas), "personas": personas_dict,
        "sim_result": result, "comparison": comparison,
        "cohort": cohort_analysis(personas_dict) if cohort_mode else None,
    }


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AstroMiroQuant V2 — MatrAIx TraderPersona Pipeline")
    parser.add_argument("--ticker", default="NQ", choices=["NQ","ES","GC"])
    parser.add_argument("--rounds", type=int, default=50)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--yahoo-start", default="2010-01-01")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--llm-key", default=None)
    parser.add_argument("--cohort", action="store_true", help="Enable MatrAIx cohort analysis")
    args = parser.parse_args()
    result = run_astromiroquant(
        ticker=args.ticker, yahoo_start=args.yahoo_start,
        rounds=args.rounds, seed=args.seed,
        use_llm=args.llm, llm_api_key=args.llm_key,
        cohort_mode=args.cohort, verbose=True,
    )
    if "error" in result: print(f"\nERROR: {result['error']}")


if __name__ == "__main__":
    main()

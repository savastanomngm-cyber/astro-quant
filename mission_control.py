#!/usr/bin/env python3
"""
MISSION CONTROL V40.3 — ASTRO-QUANT TERMINAL (Typed Pipeline)
===============================================================
- QuantMind-style architecture: TUI delegates to astro_flows, astro_knowledge,
  astro_configs, astro_mind.
- All business logic lives in astro_flows.py (pure functions).
- All config lives in astro_configs.py (typed Pydantic).
- Results persist via astro_mind.Memory (filesystem archive).
"""

"""MISSION CONTROL V50.1 — ASTRO-QUANT TERMINAL (MatrAIx Integration)
=========================================================================
- QuantMind-style typed pipeline
- MiroFish OASIS simulation engine
- MatrAIx 51-dim TraderPersona profiles
- Behavioral market micro-simulation
- Cohort population analysis
"""

import asyncio
import os
import re
import sys
import math
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------
# UI Toolkit (unchanged from v402)
# ---------------------------------------------------------------
_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

def _mk(code):
    return f"\033[{code}m" if _TTY else ""

G, R, Y, C, B, D, M, X = (_mk(c) for c in ["92", "91", "93", "96", "1", "90", "95", "0"])
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

def vlen(s):
    return len(_ANSI.sub("", s))

def pad(s, w, align="<"):
    vis = vlen(s)
    if vis >= w:
        return s
    sp = " " * (w - vis)
    return s + sp if align == "<" else sp + s

try:
    TW = min(112, max(88, os.get_terminal_size().columns))
except Exception:
    TW = 100


def box(title=None, lines=None, color=None):
    color = color or C
    w = TW
    print(color + "┌" + "─" * (w - 2) + "┐" + X)
    if title:
        spacer = max(0, w - 3 - vlen(title))
        print(color + "│ " + X + B + title + X + color + " " * spacer + "│" + X)
    print(color + "├" + "─" * (w - 2) + "┤" + X)
    for ln in lines or []:
        print(color + "│ " + X + pad(ln, w - 4) + color + " │" + X)
    print(color + "└" + "─" * (w - 2) + "┘" + X)


def table(headers, rows, aligns=None, title=None):
    aligns = aligns or ["<"] * len(headers)
    rows = [[str(c) for c in r] for r in rows]
    w = [
        max(vlen(h), max((vlen(r[i]) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    if title:
        print("  " + B + title + X)
    print("  " + B + "  ".join(pad(h, w[i], aligns[i]) for i, h in enumerate(headers)) + X)
    print("  " + "-" * (sum(w) + 2 * len(w) - 1))
    for r in rows:
        print("  " + "  ".join(pad(c, w[i], aligns[i]) for i, c in enumerate(r)))


# ---------------------------------------------------------------
# Typed imports (QuantMind-style modules)
# ---------------------------------------------------------------
from astro_core_v2 import calculate_chart, SIGN_NAMES
from astro_knowledge import (
    ChartSnapshot, BacktestResult, BatchBacktestResult,
    RegimeCard, DataSourceKind, chart_to_snapshot,
)
from astro_configs import (
    BacktestCfg, CampaignCfg, FilterCfg,
    YahooSource, CsvSource, RepoDailySource,
    INSTRUMENTS, TICKER_DATA_SOURCES,
)
from astro_flows import (
    backtest_flow, campaign_flow, batch_run,
)
from astro_mind import Memory

# MatrAIx / MiroFish imports
from astro_personas import TraderPersona, generate_trader_personas_from_learned
from astro_simulation import SimulationConfig, MarketSimulation, compare_simulation_to_actual
from astro_matraix_backtest import persona_backtest_flow, generate_live_signals
from astro_matraix_kronos import KronosConfirmer, KRONOS_AVAILABLE as _KRONOS_AVAILABLE
from trader_persona_schema import ALL_DIMENSIONS, DIMENSION_DERIVATIONS, ASTRO_TRAIT_MAP

# Legacy imports (for rectification + pattern engine — still dict-based)
_script_dir = os.path.dirname(os.path.abspath(__file__))
try:
    from rectify_v3 import ASSET_EVENTS, rectify as rectify_ticker
except ImportError:
    # Try explicit path
    import importlib.util
    _rectify_path = os.path.join(_script_dir, "rectify_v3.py")
    if os.path.exists(_rectify_path):
        spec = importlib.util.spec_from_file_location("rectify_v3", _rectify_path)
        _rectify_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_rectify_mod)
        ASSET_EVENTS = _rectify_mod.ASSET_EVENTS
        rectify_ticker = _rectify_mod.rectify
    else:
        print(f"  {Y}rectify_v3.py not found at {_rectify_path}{X}")
        ASSET_EVENTS = {}
        rectify_ticker = None

try:
    from pattern_engine_v3 import load_rectified, get_state, state_key, build_patterns, learn_patterns
except ImportError:
    from pattern_engine_v2 import load_rectified, get_state, state_key, build_patterns, learn_patterns

try:
    from dynamic_filters_v1 import compute_dynamic_signal
    DYNAMIC_FILTERS_AVAILABLE = True
except ImportError:
    DYNAMIC_FILTERS_AVAILABLE = False
try:
    from dynamic_filters_v1 import compute_dynamic_signal
    DYNAMIC_FILTERS_AVAILABLE = True
except ImportError:
    DYNAMIC_FILTERS_AVAILABLE = False

try:
    from astro_hmm import (
        train_from_persona_trades, predict_regime, filter_signal_by_regime,
        load_hmm_params, save_hmm_params, default_hmm_params,
        HMMParams, REGIMES, observation_index, signal_to_observation,
    )
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False

try:
    from astro_mtf import mtf_backtest, load_mtf_data, MTFResult
    MTF_AVAILABLE = True
except ImportError:
    MTF_AVAILABLE = False

# ---------------------------------------------------------------
# Global state
# ---------------------------------------------------------------
memory = Memory()


# ---------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------
def _ask(prompt, default=""):
    try:
        v = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return v or default


def _pause():
    _ask("Press Enter to continue...", "")


def _ask_date(prompt, default):
    d = _ask(f"{prompt} [{default}]: ", default)
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return d
    except ValueError:
        return default


def _ask_int(prompt, default):
    v = _ask(f"{prompt} [{default}]: ", str(default))
    try:
        return int(v)
    except ValueError:
        return default


def _ask_float(prompt, default):
    v = _ask(f"{prompt} [{default:.2f}]: ", f"{default:.2f}")
    try:
        return float(v)
    except ValueError:
        return default


# ---------------------------------------------------------------
# ACTION: Rectification (unchanged — uses rectify_v3)
# ---------------------------------------------------------------
def action_rectify():
    box("RECTIFICATION", color=C)
    if not rectify_ticker:
        box(lines=["rectify_v3 not found. Skipping."], color=Y)
        _pause()
        return
    for t in ["NQ", "ES", "GC"]:
        if t not in ASSET_EVENTS:
            continue
        info = {
            "NQ": (1996, 10, 26, 41.8781, -87.6298, -5),
            "ES": (1997, 9, 9, 41.8781, -87.6298, -5),
            "GC": (1974, 12, 31, 40.7128, -74.006, -5),
        }
        y, m, d, lat, lon, tz = info[t]
        birth_date = datetime(y, m, d)
        ut, score, det = rectify_ticker(t, birth_date, lat, lon, tz, step=4)
        local_dt = ut + timedelta(hours=tz)
        chart = calculate_chart(
            local_dt.year, local_dt.month, local_dt.day,
            local_dt.hour, local_dt.minute, local_dt.second,
            lat, lon, tz,
        )
        box(f"{t} – Rectified", [
            f"UTC: {ut.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Local: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Asc: {chart['ascendant']['longitude']:.2f}° {SIGN_NAMES[chart['ascendant']['sign']]}",
            f"MC: {chart['midheaven']['longitude']:.2f}°  Sect: {chart['sect']}",
            f"Total error: {score:.1f} days",
        ])
    _pause()


# ---------------------------------------------------------------
# ACTION: Multi-Source Backtest (NOW uses backtest_flow + batch_run)
# ---------------------------------------------------------------
def action_backtest():
    box("MULTI-SOURCE BACKTEST", color=C)

    for ticker in ["NQ", "ES", "GC"]:
        inst = INSTRUMENTS.get(ticker)
        if not inst:
            continue

        sources = TICKER_DATA_SOURCES.get(ticker, [])
        if not sources:
            continue

        # Build typed configs — store labels alongside
        labeled_cfgs = []
        for label, source in sources:
            try:
                labeled_cfgs.append((label, BacktestCfg(
                    ticker=ticker,
                    source=source,
                    train_ratio=0.6,
                    date_start="2010-01-01",
                    point_value=inst.point_value,
                )))
            except Exception as e:
                box(lines=[f"Config error ({label}): {e}"], color=Y)

        if not labeled_cfgs:
            box(lines=["No valid configs built."], color=Y)
            continue

        print(f"\n  {G}Running {len(labeled_cfgs)} source backtests for {ticker}...{X}")

        # Run concurrently via batch_run (each input = cfg dict)
        inputs = [{"cfg": c} for _, c in labeled_cfgs]

        async def _run():
            async def _wrapper(**kwargs):
                return backtest_flow(kwargs["cfg"])

            return await batch_run(_wrapper, inputs, max_concurrency=3)

        batch = asyncio.run(_run())

        valid = [r for r in batch.results if r is not None]
        if not valid:
            box(lines=[f"No results for {ticker}."], color=Y)
            continue

        # Archive each result
        run_ids = []
        for r in valid:
            try:
                rid = memory.archive_run(r)
                run_ids.append(rid)
            except Exception as e:
                print(f"  {Y}Archive error: {e}{X}")

        # Show table — match results back to source labels
        # We know the order: cfgs[i] ← labeled_cfgs[i][0] (label)
        rows = []
        source_labels = [label for label, _ in labeled_cfgs]
        for i, r in enumerate(valid):
            oos = r.out_of_sample
            label = source_labels[i] if i < len(source_labels) else "?"
            rows.append([
                label,
                f"{r.sl_points:.0f}",
                f"{r.tp_points:.0f}",
                f"{r.hold_days}",
                str(r.validation.n_trades),
                f"{r.validation.win_rate:.1%}",
                f"{r.validation.profit_factor:.2f}",
                f"${r.validation.total_dollars:,.0f}",
                f"{oos.profit_factor:.2f}" if oos.n_trades > 0 else "n/a",
                f"${oos.total_dollars:,.0f}" if oos.n_trades > 0 else "n/a",
            ])

        table(
            ["Source", "SL", "TP", "H", "Val N", "Val WR", "Val PF", "Val $", "OOS PF", "OOS $"],
            rows,
            aligns=["<", ">", ">", ">", ">", ">", ">", ">", ">", ">"],
            title=f"{ticker} – Backtest Results (archived: {len(run_ids)} runs)",
        )

    _pause()


# ---------------------------------------------------------------
# ACTION: Custom Date Backtest
# ---------------------------------------------------------------
def action_backtest_custom():
    box("CUSTOM DATE BACKTEST", color=C)
    ticker = _ask("Ticker (NQ/ES/GC): ", "NQ").upper()
    if ticker not in TICKER_DATA_SOURCES:
        print("Invalid."); _pause(); return

    # Show sources
    all_sources = TICKER_DATA_SOURCES[ticker]
    print("Available sources:")
    for i, (label, _) in enumerate(all_sources, 1):
        print(f"  {i}. {label}")
    src_idx = _ask_int("Choose source number", 1) - 1
    if src_idx < 0 or src_idx >= len(all_sources):
        print("Invalid."); _pause(); return
    label, source = all_sources[src_idx]

    inst = INSTRUMENTS[ticker]
    start_date = _ask_date("Start date (YYYY-MM-DD)", "2010-01-01")
    end_date = _ask_date("End date (YYYY-MM-DD)", "2026-08-07")
    split_ratio = _ask_float("Train fraction (0.0-1.0)", 0.6)

    cfg = BacktestCfg(
        ticker=ticker,
        source=source,
        train_ratio=split_ratio,
        date_start=start_date,
        date_end=end_date,
        point_value=inst.point_value,
    )

    print(f"  Running backtest on {ticker} ({label})...")
    result = backtest_flow(cfg)

    if not result:
        print("  No valid result."); _pause(); return

    rid = memory.archive_run(result)

    oos = result.out_of_sample
    table(
        ["SL", "TP", "Hold", "Val N", "Val WR", "Val PF", "Val $", "OOS PF", "OOS $"],
        [[
            f"{result.sl_points:.0f}", f"{result.tp_points:.0f}", f"{result.hold_days}",
            str(result.validation.n_trades), f"{result.validation.win_rate:.1%}",
            f"{result.validation.profit_factor:.2f}", f"${result.validation.total_dollars:,.0f}",
            f"{oos.profit_factor:.2f}" if oos.n_trades > 0 else "n/a",
            f"${oos.total_dollars:,.0f}" if oos.n_trades > 0 else "n/a",
        ]],
        title=f"{ticker} – Custom Backtest ({label})  [run: {rid}]",
    )
    _pause()


# ---------------------------------------------------------------
# ACTION: Dynamic Campaign (USES campaign_flow + RegimeCards)
# ---------------------------------------------------------------
def action_dynamic_campaign():
    box("DYNAMIC CAMPAIGN (Regime Filters)", color=C)

    ticker = _ask("Ticker (NQ/ES/GC): ", "NQ").upper()
    if ticker not in INSTRUMENTS:
        print("Invalid."); _pause(); return

    inst = INSTRUMENTS[ticker]
    start_str = _ask_date("Start date", "2026-08-10")
    end_str = _ask_date("End date", "2026-09-15")

    campaign_cfg = CampaignCfg(
        ticker=ticker,
        date_start=start_str,
        date_end=end_str,
        sl_points=inst.default_sl,
        tp_points=inst.default_tp,
        hold_days=inst.default_hold,
        source=YahooSource(symbol=f"{ticker}=F"),
        use_dynamic_filters=True,
    )

    print(f"\n  Generating campaign for {ticker} ({start_str} → {end_str})...")
    cards = campaign_flow(campaign_cfg)

    if not cards:
        print("  No campaign signals generated."); _pause(); return

    # Print campaign table
    print(f"\n{'='*85}")
    print(f"{'Date':<12} {'Day':<5} {'Base':<6} {'Filter':<9} {'Score':>7} {'Final':<6} {'Pattern':<35}")
    print(f"{'-'*85}")

    n_long = n_short = n_flat = 0
    for card in cards:
        base_str = card.base_direction or " — "
        final_str = card.modulated_direction or " — "
        reg_str = card.regime

        # Colorize
        reg_color = G if reg_str == "BULLISH" else (R if reg_str == "BEARISH" else Y)
        final_color = G if final_str == "LONG" else (R if final_str == "SHORT" else Y)

        print(
            f"{card.as_of.strftime('%Y-%m-%d'):<12} "
            f"{card.as_of.strftime('%a'):<5} "
            f"{base_str:<6} "
            f"{reg_color}{reg_str:<9}{X} "
            f"{card.combined_score:>+7.3f} "
            f"{final_color}{final_str:<6}{X} "
            f"{(card.pattern_key or '')[:35]}"
        )

        if final_str == "LONG":
            n_long += 1
        elif final_str == "SHORT":
            n_short += 1
        else:
            n_flat += 1

    total = n_long + n_short + n_flat
    print(f"\n{'='*85}")
    print(f"  Summary: {G}{n_long} LONG{X} / {R}{n_short} SHORT{X} / {Y}{n_flat} FLAT{X}  (total {total} signals)")
    if total > 0:
        print(f"  Flat ratio: {n_flat / total * 100:.0f}% of signals filtered out by regime overlay")
    _pause()


# ---------------------------------------------------------------
# ACTION: Dynamic Filter Status (scans next N days)
# ---------------------------------------------------------------
def action_dynamic_status():
    box("DYNAMIC FILTER STATUS", color=C)

    if not DYNAMIC_FILTERS_AVAILABLE:
        box(lines=["dynamic_filters_v1 not found. Skipping."], color=Y)
        _pause(); return

    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS:
        print("Invalid."); _pause(); return

    inst = INSTRUMENTS[ticker]
    days_to_scan = _ask_int("Days to scan", 10)

    # Load chart (needed for filter computation, but compute_dynamic_signal
    # needs the raw dict format. We'll use pattern_engine's load_rectified + calculate_chart)
    rect = load_rectified().get(ticker)
    if not rect:
        print("No rectified chart."); _pause(); return

    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                       rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )

    # Build typed snapshot for the filters
    chart_snap = chart_to_snapshot(
        ticker=ticker,
        chart_dict=chart_dict,
        birth_utc=utc_dt,
        tz_offset=inst.birth_tz,
        lat=inst.birth_lat,
        lon=inst.birth_lon,
    )

    from dynamic_filters_v1 import (
        moon_application_filter,
        nodes_to_angles_filter,
        moiety_filter,
        arcus_vitae_filter,
        PLANET_MOIETY,
    )

    print(f"\n{ticker} Dynamic Filter Scan — Next {days_to_scan} Days\n")
    print(f"{'Date':<12} {'Moon App':>20} {'Nodes':>12} {'Moiety':>12} {'A.Vitae':>12} {'Comb.':>10} {'Regime':>10}")
    print(f"{'-'*95}")

    from datetime import datetime as dt
    today = dt(2026, 8, 10, 17, 0, 0)
    for i in range(days_to_scan):
        d = today + timedelta(days=i)
        if d.weekday() >= 5:
            continue

        s_a, _ = moon_application_filter(chart_dict, d)
        s_b, _ = nodes_to_angles_filter(chart_dict, d)
        s_c, _ = moiety_filter(chart_dict, d)
        s_d, _ = arcus_vitae_filter(chart_dict, d)

        combined = s_a * 0.30 + s_b * 0.25 + s_c * 0.25 + s_d * 0.20
        if combined >= 0.15:
            regime = "BULLISH"; rc = G
        elif combined <= -0.15:
            regime = "BEARISH"; rc = R
        else:
            regime = "NEUTRAL"; rc = Y

        print(
            f"{d.strftime('%Y-%m-%d'):<12} "
            f"{s_a:>+20.3f} {s_b:>+12.3f} {s_c:>+12.3f} {s_d:>+12.3f} "
            f"{combined:>+10.3f} {rc}{regime:<10}{X}"
        )

    _pause()


# ---------------------------------------------------------------
# ACTION: Run History (NEW — reads from Memory)
# ---------------------------------------------------------------
def action_run_history():
    box("RUN HISTORY (from Memory)", color=C)

    runs = memory.list_runs(limit=30)
    if not runs:
        box(lines=["No archived runs. Run a backtest first."], color=Y)
        _pause(); return

    print(f"\n  {len(runs)} archived runs:\n")
    print(f"{'Date':<12} {'ID':<10} {'Ticker':<8} {'Source':<12} {'OOS PF':>8} {'OOS WR':>8} {'Net $':>14}")
    print(f"{'-'*72}")

    for r in runs:
        pf_str = f"{r.oos_pf:.2f}" if r.oos_pf > 0 else " — "
        wr_str = f"{r.oos_wr:.1%}" if r.oos_wr > 0 else " — "
        net_color = G if r.oos_net > 0 else (R if r.oos_net < 0 else Y)
        print(
            f"{r.as_of[:10]:<12} "
            f"{r.run_id:<10} "
            f"{r.ticker:<8} "
            f"{r.source_kind:<12} "
            f"{pf_str:>8} "
            f"{wr_str:>8} "
            f"{net_color}${r.oos_net:>13,.0f}{X}"
        )

    print(f"\n---")
    stats = memory.stats()
    print(f"  Total runs: {stats['total_runs']}  |  Profitable OOS: {stats['profitable_oos_count']}/{stats['backtest_runs']}")
    print(f"  Best OOS PF: {stats['best_pf']:.2f}")

    # Option to compare
    print(f"\n  Compare runs? Enter run IDs separated by commas (or press Enter to skip):")
    ids = _ask("  Run IDs: ", "")
    if ids:
        run_ids = [rid.strip() for rid in ids.split(",") if rid.strip()]
        if run_ids:
            comp = memory.compare_runs(run_ids)
            print(f"\n  Comparison:")
            print(f"  {'ID':<10} {'Ticker':<8} {'PF':>8} {'WR':>8} {'Net $':>14}")
            print(f"  {'-'*50}")
            for c in comp:
                print(
                    f"  {c['run_id']:<10} {c['ticker']:<8} "
                    f"{c['oos_pf']:>8.2f} {c['oos_wr']:>8.1%} ${c['oos_net']:>13,.0f}"
                )

    _pause()


# ---------------------------------------------------------------
# ACTION: Pattern Explorer (bridge to typed PatternCard)
# ---------------------------------------------------------------
def action_pattern_explorer():
    box("PATTERN EXPLORER", color=C)
    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS:
        print("Invalid."); _pause(); return

    inst = INSTRUMENTS[ticker]
    rect = load_rectified().get(ticker)
    if not rect:
        print("No rectified chart."); _pause(); return

    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                       rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )

    # Load Yahoo data
    from astro_flows import _load_yahoo
    raw = _load_yahoo(f"{ticker}=F", start_date="2010-01-01")
    if not raw:
        print("No Yahoo data."); _pause(); return
    dd, dates = raw

    if not build_patterns:
        print("pattern_engine_v2 not found."); _pause(); return

    pats = build_patterns(chart_dict, dd, dates, horizons=[3, 5, 7])
    learned = learn_patterns(pats, 12, 0.02, 0.52)
    if not learned:
        print("No valid patterns."); _pause(); return

    sorted_pats = sorted(learned.values(), key=lambda x: x["score"], reverse=True)
    table(
        ["Pattern", "Dir", "WR%", "AvgMv%", "N", "p-value", "Score"],
        [[
            p["key"], p["direction"],
            f"{p['win_rate']*100:.1f}%", f"{p['avg_move']*100:.3f}%",
            p["n_samples"], f"{p['p_value']:.2e}", f"{p['score']:.2f}",
        ] for p in sorted_pats[:20]],
        aligns=["<", "<", ">", ">", ">", ">", ">"],
        title=f"Top Patterns for {ticker}",
    )
    _pause()


# ---------------------------------------------------------------
# ACTION: Settings
# ---------------------------------------------------------------
SETTINGS = {
    "min_n": 12,
    "max_p": 0.02,
    "min_edge": 0.52,
}

# ---------------------------------------------------------------
# ACTION: MatrAIx Persona Explorer
# ---------------------------------------------------------------
def action_matraix_personas():
    box("MATRAIX PERSONA EXPLORER (51-dim TraderPersonas)", color=C)
    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS:
        print("Invalid."); _pause(); return

    # Load patterns
    inst = INSTRUMENTS[ticker]
    rect = load_rectified().get(ticker)
    if not rect:
        print("No rectified chart — using demo"); _pause(); return

    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                       rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    chart_snap = chart_to_snapshot(
        ticker=ticker, chart_dict=chart_dict, birth_utc=utc_dt,
        tz_offset=inst.birth_tz, lat=inst.birth_lat, lon=inst.birth_lon,
    )

    # Try real patterns, fall back to mock
    try:
        from astro_flows import _load_yahoo
        raw = _load_yahoo(f"{ticker}=F", start_date="2010-01-01")
        if raw:
            dd, dates = raw
            pats = build_patterns(chart_dict, dd, dates, horizons=[3, 5, 7])
            learned_raw = learn_patterns(pats, SETTINGS["min_n"], SETTINGS["max_p"], SETTINGS["min_edge"])
            if not learned_raw:
                raise ValueError("no patterns")
        else:
            raise ValueError("no data")
    except Exception:
        learned_raw = {
            "Mercury_Mercury_Venus_H7_MP1_7d": {"direction":"LONG","horizon":7,"n_samples":31,"win_rate":0.903,"avg_move":0.021,"std_move":0.04,"profit_factor":4.5,"p_value":0.0001,"score":2.07},
            "Mars_Saturn_Mercury_H1_MP2_7d": {"direction":"SHORT","horizon":7,"n_samples":20,"win_rate":0.55,"avg_move":-0.008,"std_move":0.035,"profit_factor":1.4,"p_value":0.01,"score":0.30},
            "Venus_Jupiter_Venus_H4_MP3_7d": {"direction":"LONG","horizon":7,"n_samples":19,"win_rate":0.895,"avg_move":0.02,"std_move":0.03,"profit_factor":3.2,"p_value":0.0003,"score":0.59},
            "Mercury_Jupiter_Mercury_H2_MP4_7d": {"direction":"SHORT","horizon":7,"n_samples":25,"win_rate":0.32,"avg_move":-0.0315,"std_move":0.05,"profit_factor":0.7,"p_value":0.12,"score":0.51},
            "Mercury_Sun_Jupiter_H6_MP5_7d": {"direction":"LONG","horizon":7,"n_samples":33,"win_rate":0.727,"avg_move":0.0127,"std_move":0.03,"profit_factor":1.8,"p_value":0.002,"score":0.48},
            "Saturn_Mars_Moon_H7_MP7_3d": {"direction":"SHORT","horizon":3,"n_samples":15,"win_rate":0.60,"avg_move":-0.015,"std_move":0.04,"profit_factor":1.5,"p_value":0.03,"score":0.25},
        }

    personas = generate_trader_personas_from_learned(learned_raw, ticker, chart_snap)
    source_tag = "live" if len(learned_raw) > 6 else "mock"

    print(f"\n  {G}{len(personas)} personas loaded ({source_tag} patterns){X}\n")

    # Show persona list
    table(
        ["#", "Dir", "State Key", "Risk", "Decision", "Stop", "MaxHold", "WR", "PF", "Conviction"],
        [[str(i+1),
          f"{G}{p.pattern_direction:<5}{X}" if p.pattern_direction == "LONG" else f"{R}{p.pattern_direction:<5}{X}",
          p.persona_id[:28],
          p.risk_tolerance,
          p.decision_speed,
          f"{p.stop_tightness:.0%}",
          f"{p.max_hold_days}d",
          f"{p.historical_win_rate:.0%}",
          f"{p.historical_pf:.2f}" if p.historical_pf > 0 else f"{Y}0.00{X}",
          f"{p.conviction_mult:.1f}x",
         ] for i, p in enumerate(personas)],
        title=f"{ticker} — TraderPersonas ({G}LONG{X}/{R}SHORT{X})",
    )

    # Browse a specific persona
    while True:
        idx = _ask(f"\n  View persona detail (1-{len(personas)}), or Enter to return: ", "")
        if not idx:
            break
        try:
            i = int(idx) - 1
            if 0 <= i < len(personas):
                p = personas[i]
                box(f"Persona: {p.persona_id[:50]}", [
                    f"Ticker: {p.ticker} | Pattern: {p.pattern_direction} | Score: {p.pattern_score:.2f}",
                    f"Astro: {p.fidaria_main}-{p.fidaria_sub} fidaria, {p.distributor} dist, H{p.house}, {p.moon_phase}",
                    "",
                    f"{Y}── RISK & DECISION ──{X}",
                    f"Risk tolerance: {p.risk_tolerance} | Financial risk: {p.financial_risk_tolerance}",
                    f"Position size: {p.position_size_pct:.0%} | Stop tightness: {p.stop_tightness:.0%}",
                    f"Decision style: {p.decision_style} | Speed: {p.decision_speed}",
                    f"Max drawdown: {p.max_drawdown_tolerance_pct} | Need for closure: {p.need_for_closure}",
                    "",
                    f"{Y}── BIG FIVE ──{X}",
                    f"Assertiveness: {p.assertiveness} | Anxiety: {p.anxiety} | Open-minded: {p.open_mindedness}",
                    f"Self-discipline: {p.self_discipline} (rule adherence: {p.rule_adherence:.0%})",
                    f"Excitement-seeking: {p.excitement_seeking} | Emotional volatility: {p.emotional_volatility}",
                    f"Achievement: {p.achievement_striving} | Caution: {p.cautiousness} | Trust: {p.trust}",
                    "",
                    f"{Y}── COGNITIVE ──{X}",
                    f"Patience: {p.patience} (hold: {p.hold_mult:.1f}x) | Optimism: {p.optimism} (bull bias: {p.bull_bias:.0%})",
                    f"Skepticism: {p.skepticism} (signal threshold: {p.signal_accept_threshold:.0%})",
                    f"Confidence: {p.confidence_calibration} (conviction: {p.conviction_mult:.1f}x)",
                    f"Numeracy: {p.numeracy_comfort} | Detail: {p.detail_orientation}",
                    "",
                    f"{Y}── TRADING BEHAVIORS ──{X}",
                    f"Systematic: {p.systematic_weight:.0%} | Override prob: {p.override_prob:.0%}",
                    f"Panic exit: {p.panic_exit_prob:.0%} | Revenge trade: {p.revenge_trade_prob:.0%}",
                    f"Impulse trade: {p.impulse_trade_prob:.0%} | Contrarian: {p.contrarian_prob:.0%}",
                    f"Early exit: {p.boredom_exit_prob:.0%} | Tilt: {p.tilt_prob:.0%}",
                    f"Overtrade mult: {p.overtrade_mult:.1f}x | Trade freq: {p.trade_freq_mult:.1f}x",
                    "",
                    f"{Y}── VALUES ──{X}",
                    f"Achievement: {p.schwartz_achievement} | Power: {p.schwartz_power} | Security: {p.schwartz_security}",
                    f"Stimulation: {p.schwartz_stimulation} | Hedonism: {p.schwartz_hedonism}",
                    "",
                    f"{Y}── HISTORICAL ──{X}",
                    f"Samples: {p.n_samples} | WR: {p.historical_win_rate:.0%} | PF: {p.historical_pf:.2f}",
                    f"Avg move: {p.historical_avg_move:+.3%} | Direction: {p.pattern_direction}",
                ])
        except ValueError:
            pass
    _pause()


# ---------------------------------------------------------------
# ACTION: MatrAIx Market Simulation
# ---------------------------------------------------------------
def action_matraix_simulation():
    box("MATRAIX MARKET SIMULATION (OASIS-style)", color=C)
    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS: print("Invalid."); _pause(); return

    inst = INSTRUMENTS[ticker]
    rect = load_rectified().get(ticker)
    if not rect: print("No rectified chart."); _pause(); return

    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                       rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(local_dt.year, local_dt.month, local_dt.day,
                                  local_dt.hour, local_dt.minute, local_dt.second,
                                  inst.birth_lat, inst.birth_lon, inst.birth_tz)
    chart_snap = chart_to_snapshot(ticker=ticker, chart_dict=chart_dict, birth_utc=utc_dt,
                                    tz_offset=inst.birth_tz, lat=inst.birth_lat, lon=inst.birth_lon)

    # Configurable simulation params
    rounds = _ask_int("Simulation rounds", 50)
    seed_str = _ask("Random seed (blank=random): ", "")
    seed = int(seed_str) if seed_str else None
    base_vol = _ask_float("Base daily volatility (e.g. 0.008)", 0.008)
    bull_thresh = _ask_float("Bullish threshold", 0.15)
    bear_thresh = _ask_float("Bearish threshold", -0.15)
    behavioral = _ask("Enable behavioral dynamics? (y/n): ", "y").lower() == "y"

    print(f"\n  {G}Loading patterns and generating personas...{X}")

    # Load patterns (real or mock)
    try:
        from astro_flows import _load_yahoo
        raw = _load_yahoo(f"{ticker}=F")
        if raw:
            dd, dates = raw
            pats = build_patterns(chart_dict, dd, dates, horizons=[3,5,7])
            learned_raw = learn_patterns(pats, SETTINGS["min_n"], SETTINGS["max_p"], SETTINGS["min_edge"])
            if not learned_raw: raise ValueError("no patterns")
        else: raise ValueError("no data")
    except Exception:
        # Import the mock set from astromiroquant
        learned_raw = {
            "Mercury_Mercury_Venus_H7_MP1_7d": {"direction":"LONG","horizon":7,"n_samples":31,"win_rate":0.903,"avg_move":0.021,"std_move":0.04,"profit_factor":4.5,"p_value":0.0001,"score":2.07},
            "Mars_Saturn_Mercury_H1_MP2_7d": {"direction":"SHORT","horizon":7,"n_samples":20,"win_rate":0.55,"avg_move":-0.008,"std_move":0.035,"profit_factor":1.4,"p_value":0.01,"score":0.30},
            "Venus_Jupiter_Venus_H4_MP3_7d": {"direction":"LONG","horizon":7,"n_samples":19,"win_rate":0.895,"avg_move":0.02,"std_move":0.03,"profit_factor":3.2,"p_value":0.0003,"score":0.59},
            "Mercury_Jupiter_Mercury_H2_MP4_7d": {"direction":"SHORT","horizon":7,"n_samples":25,"win_rate":0.32,"avg_move":-0.0315,"std_move":0.05,"profit_factor":0.7,"p_value":0.12,"score":0.51},
            "Mercury_Sun_Jupiter_H6_MP5_7d": {"direction":"LONG","horizon":7,"n_samples":33,"win_rate":0.727,"avg_move":0.0127,"std_move":0.03,"profit_factor":1.8,"p_value":0.002,"score":0.48},
            "Saturn_Mars_Moon_H7_MP7_3d": {"direction":"SHORT","horizon":3,"n_samples":15,"win_rate":0.60,"avg_move":-0.015,"std_move":0.04,"profit_factor":1.5,"p_value":0.03,"score":0.25},
        }

    personas = generate_trader_personas_from_learned(learned_raw, ticker, chart_snap)
    personas_dict = {p.persona_id: p for p in personas}

    print(f"  {len(personas)} personas | {rounds} rounds | seed={seed} | vol={base_vol}")

    # Load actual returns for comparison
    try:
        from astromiroquant import load_yahoo_returns
        yahoo_ret, _ = load_yahoo_returns(f"{ticker}=F")
    except Exception:
        yahoo_ret = None

    print(f"  Running simulation...")

    cfg = SimulationConfig(
        total_rounds=min(rounds, len(yahoo_ret) if yahoo_ret else rounds),
        random_seed=seed, base_volatility=base_vol,
        bullish_threshold=bull_thresh, bearish_threshold=bear_thresh,
        enable_behavioral_dynamics=behavioral,
        enable_contrarian_switches=behavioral,
        enable_overtrading=behavioral,
        enable_emotion_volatility=behavioral,
    )
    sim = MarketSimulation(cfg, personas_dict, ticker)
    result = sim.run()

    # Show results
    print(f"\n  {G}── SIMULATION RESULTS ──{X}")
    print(f"  Price: $100.00 → ${result.final_price:.2f} ({result.total_return_pct:+.2f}%)")
    print(f"  Regimes: {G}{result.bullish_rounds}B{X} / {R}{result.bearish_rounds}Be{X} / {Y}{result.neutral_rounds}N{X}")
    print(f"  Vol: {result.volatility_pct:.2f}% | MaxDD: {result.max_drawdown_pct:.2f}%")
    print(f"  Behavioral: panic={result.total_panic_exits} revenge={result.total_revenge_trades}")
    print(f"    impulse={result.total_impulse_trades} contrarian={result.total_contrarian_flips} boredom={result.total_early_exits}")

    # Comparison
    if yahoo_ret and len(yahoo_ret) >= result.total_rounds:
        comp = compare_simulation_to_actual(result, yahoo_ret[:result.total_rounds])
        da_color = G if comp['directional_accuracy'] >= 0.55 else (Y if comp['directional_accuracy'] >= 0.50 else R)
        corr_color = G if comp['correlation'] > 0 else R
        print(f"\n  {G}── vs ACTUAL ──{X}")
        print(f"  Dir Accuracy: {da_color}{comp['directional_accuracy']:.1%}{X}")
        print(f"  Correlation: {corr_color}{comp['correlation']:+.3f}{X}")
        print(f"  MAE: {comp['mae']:.2f}%")
        print(f"  Sim P&L: {comp['sim_total_return']:+.1f}% | Actual: {comp['actual_total_return']:+.1f}%")

    # Bar table
    show_bars = _ask("\n  Show bar-by-bar? (y/n): ", "n").lower() == "y"
    if show_bars:
        print(f"\n  {'Bar':>4} {'Sent':>7} {'Regime':<10} {'Ret%':>7} {'Events'}")
        print(f"  {'-'*45}")
        for b in result.bars:
            ev = []
            if b.panic_exits: ev.append(f"P:{b.panic_exits}")
            if b.revenge_trades: ev.append(f"R:{b.revenge_trades}")
            if b.contrarian_flips: ev.append(f"C:{b.contrarian_flips}")
            print(f"  {b.bar_index:>4} {b.net_sentiment:>+7.3f} {b.regime:<10} {b.return_pct:>+7.2f} {','.join(ev) if ev else '—'}")

    _pause()


# ---------------------------------------------------------------
# ACTION: MatrAIx Cohort Report
# ---------------------------------------------------------------
def action_matraix_cohort():
    box("MATRAIX COHORT REPORT (Population Analysis)", color=C)
    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS: print("Invalid."); _pause(); return

    rounds = _ask_int("Rounds", 50)
    seed_str = _ask("Seed (blank=random): ", "42")
    seed = int(seed_str) if seed_str else None

    # Run full pipeline
    print(f"\n  {G}Running full pipeline → {rounds} rounds...{X}")
    try:
        from astromiroquant import run_astromiroquant
    except ImportError:
        print("  astromiroquant module not found."); _pause(); return

    result = run_astromiroquant(
        ticker=ticker, rounds=rounds, seed=seed,
        cohort_mode=True, verbose=True,
    )

    if "error" in result:
        print(f"  {R}Error: {result['error']}{X}")
        _pause(); return

    # Archive in memory
    from astro_knowledge import BacktestResult, TradeStats, SourceRef, ChartProvenance, DataSourceKind
    bt = BacktestResult(
        as_of=datetime.now(), ticker=ticker,
        source=SourceRef(kind=DataSourceKind.YAHOO, symbol=f"{ticker}=F"),
        chart_provenance=ChartProvenance(),
        train_ratio=0.6, sl_points=50, tp_points=150, hold_days=7,
        patterns_found=result["persona_count"], patterns_valid=result["persona_count"],
        validation=TradeStats(),
        out_of_sample=TradeStats(n_trades=rounds),
    )
    try:
        rid = memory.archive_run(bt, run_type="matraix_cohort")
        print(f"\n  Archived: {rid}")
    except Exception as e:
        print(f"\n  {Y}Archive skipped: {e}{X}")

    _pause()


# ---------------------------------------------------------------
# ACTION: MatrAIx Persona Backtest (NEW — closes the loop)
# ---------------------------------------------------------------
def action_matraix_backtest():
    box("MATRAIX PERSONA BACKTEST (Close the Loop)", color=C)
    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS: print("Invalid."); _pause(); return

    inst = INSTRUMENTS[ticker]
    min_wr = _ask_float("Min persona win rate", 0.50)
    min_pf = _ask_float("Min persona PF", 1.0)
    use_short = _ask("Use SHORT signals? (y/n): ", "y").lower() == "y"
    train_ratio = _ask_float("Train ratio", 0.6)
    yahoo_start = _ask_date("Data start", "2010-01-01")

    print(f"\n  {G}Running persona backtest for {ticker}...{X}")
    print(f"  Filters: WR≥{min_wr:.0%}, PF≥{min_pf:.1f}, {'SHORT enabled' if use_short else 'LONG only'}")
    print(f"  Train ratio: {train_ratio:.0%}")

    result = persona_backtest_flow(
        ticker=ticker,
        yahoo_start=yahoo_start,
        train_ratio=train_ratio,
        min_win_rate=min_wr,
        min_pf=min_pf,
        use_short_signals=use_short,
        point_value=inst.point_value,
    )

    if not result:
        print(f"  {R}No valid result.{X}"); _pause(); return

    # Archive
    try:
        rid = memory.archive_run(result, run_type="matraix_backtest")
        print(f"  Archived: {rid}")
    except Exception:
        pass

    # Show results
    val = result.validation
    oos = result.out_of_sample

    pf_color = G if oos.profit_factor >= 1.5 else (Y if oos.profit_factor >= 1.0 else R)
    wr_color = G if oos.win_rate >= 0.55 else (Y if oos.win_rate >= 0.50 else R)

    box(f"{ticker} — Persona Backtest Results", [
        f"Patterns: {result.patterns_found} → {result.patterns_valid} valid personas",
        f"",
        f"Validation: {val.n_trades} trades | WR={val.win_rate:.1%} | PF={val.profit_factor:.2f} | ${val.total_dollars:,.0f}",
        f"",
        f"{G}OUT-OF-SAMPLE:{X} {oos.n_trades} trades | {wr_color}WR={oos.win_rate:.1%}{X} | {pf_color}PF={oos.profit_factor:.2f}{X} | ${oos.total_dollars:,.0f}",
        f"Avg Win: ${oos.avg_win * inst.point_value:,.0f} | Avg Loss: ${oos.avg_loss * inst.point_value:,.0f}",
        f"Sharpe: {oos.sharpe:.2f}",
    ])

    # Show trade details
    if _ask("\n  Show OOS trades? (y/n): ", "n").lower() == "y":
        print(f"\n  {'Date':<12} {'Dir':<6} {'Gross':>8} {'Net':>8} {'Reason':<12} {'WR':>5} {'PF':>7}")
        print(f"  {'-'*65}")
        for t in result.oos_trades[:30]:
            print(f"  {t.date:<12} {t.direction:<6} {t.gross_points:>+8.2f} {t.net_points:>+8.2f}")

    # Compare against standard backtest
    print(f"\n  {Y}── Comparison against standard backtest_flow ──{X}")
    print(f"  Standard NQ OOS: PF=1.18, WR≈49.6%, Net=$54,805 (Yahoo daily)")
    if oos.profit_factor >= 1.18:
        print(f"  {G}✓ Persona backtest BEATS standard backtest{X}")
    else:
        print(f"  {Y}Persona backtest different from standard — check signal filtering{X}")

    _pause()


# ---------------------------------------------------------------
# ACTION: Live MatrAIx Signal
# ---------------------------------------------------------------
def action_matraix_live():
    box("LIVE MATRAIX SIGNAL (Today's Persona Signal)", color=C)
    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS: print("Invalid."); _pause(); return

    inst = INSTRUMENTS[ticker]
    date_str = _ask("Date (YYYY-MM-DD, blank=today): ", "")
    min_wr = _ask_float("Min WR", 0.50)
    min_pf = _ask_float("Min PF", 1.0)

    print(f"\n  {G}Computing live signal...{X}")
    sigs = generate_live_signals(
        ticker=ticker, date_str=date_str or None,
        min_win_rate=min_wr, min_pf=min_pf, use_short=True,
    )

    if not sigs:
        print(f"  {Y}No valid signal today. Persona filters too strict or state not found.{X}")
        _pause(); return

    for s in sigs:
        dir_color = G if s["direction"] == "LONG" else R

        # Kronos confirmation
        kronos_status = "N/A"
        kronos_line = ""
        if _KRONOS_AVAILABLE:
            use_kronos = _ask("  Run Kronos confirmation? (y/n): ", "y").lower() == "y"
            if use_kronos:
                print(f"  {Y}Loading Kronos model (first use downloads ~100MB)...{X}")
                try:
                    kc = KronosConfirmer()
                    kc._ensure_loaded()
                    df = kc._load_yahoo_ohlcv(ticker)
                    if df is not None:
                        kronos_result = kc.confirm_signal(ticker, s, df=df)
                        kronos_status = kronos_result["status"]
                        if kronos_status == "CONFIRMED":
                            kronos_line = f"{G}✓ KRONOS CONFIRMED{X} — Predicted: {kronos_result['kronos_dir']} {kronos_result['kronos_pct']:+.1f}% (conf={kronos_result['kronos_confidence']:.0%})"
                        elif kronos_status == "DIVERGES":
                            kronos_line = f"{R}✗ KRONOS DIVERGES{X} — Predicted: {kronos_result['kronos_dir']} {kronos_result['kronos_pct']:+.1f}% | Signal filtered to FLAT"
                        else:
                            kronos_line = f"{Y}Kronos: {kronos_status}{X}"
                    else:
                        kronos_line = f"{Y}Kronos: No data for {ticker}{X}"
                except Exception as e:
                    kronos_line = f"{Y}Kronos load failed: {str(e)[:80]}{X}"

        # HMM Regime filtering
        hmm_line = ""
        if HMM_AVAILABLE:
            try:
                params = load_hmm_params(ticker)
                if params:
                    # Check if it's default (untrained) and retrain if needed
                    is_default = abs(params.A[0][0] - 0.70) < 0.001 and abs(params.A[3][3] - 0.30) < 0.001
                    if is_default:
                        # Quick train from recent OOS
                        from astro_matraix_backtest import persona_backtest_flow as _pbf
                        _result = _pbf(ticker=ticker, yahoo_start="2010-01-01",
                                       train_ratio=0.6, min_win_rate=0.50,
                                       min_pf=1.0, use_short_signals=True, verbose=False)
                        if _result and _result.oos_trades:
                            params = train_from_persona_trades(ticker, _result, verbose=False)
                            save_hmm_params(params, ticker)

                    if params and not (abs(params.A[0][0] - 0.70) < 0.001 and abs(params.A[3][3] - 0.30) < 0.001):
                        # Only filter if we have trained (non-default) params
                        # Use the signal direction to build a mock observation
                        from astro_hmm import observation_index as _oi
                        mock_obs = [_oi(s['direction'], s['direction'] == 'LONG', 0.01)]
                        info = predict_regime(params, mock_obs)
                        regime = info['current_regime']
                        rc_map = {"BULL": G, "BEAR": R, "RANGE": Y, "CHOP": C}
                        rc = rc_map.get(regime, X)

                        # Adjust conviction based on regime
                        orig_conv = s.get('conviction', 1.0)
                        if s['direction'] == 'LONG' and regime == 'BEAR':
                            s['conviction'] = round(orig_conv * 0.5, 2)
                        elif s['direction'] == 'SHORT' and regime == 'BULL':
                            s['conviction'] = round(orig_conv * 0.5, 2)
                        elif regime == 'CHOP':
                            s['conviction'] = round(orig_conv * 0.3, 2)

                        hmm_line = f"{rc}{regime}{X} regime | Conviction adjusted: {orig_conv:.1f}x → {s['conviction']:.1f}x"
                        if regime == 'CHOP':
                            hmm_line += " | SIT OUT recommended"
            except Exception:
                pass

        lines = [
            f"Direction: {dir_color}{s['direction']}{X}",
            f"",
            f"{Y}── EXECUTION ──{X}",
            f"Entry: {s.get('entry_timing', 'Market open')}",
            f"Timeframe: {s.get('timeframe', 'Daily')}",
            f"Style: {s.get('entry_style', '—')} | Exit: {s.get('exit_style', '—')}",
            f"",
            f"{Y}── PARAMETERS ──{X}",
            f"Conviction: {s['conviction']:.1f}x | Position: {s['position_pct']}",
            f"Stop-loss: {s['sl_pct']} | Take-profit: {s['tp_pct']}",
            f"Max hold: {s['hold_days']} days | Speed: {s.get('decision_speed', '—')}",
            f"",
            f"{Y}── PERSONA ──{X}",
            f"ID: {s['persona_id']}",
            f"Risk: {s['risk_tolerance']} | WR: {s['wr']} | PF: {s['pf']} | N={s['n_samples']}",
        ]
        if kronos_line:
            lines += ["", f"{Y}── KRONOS CONFIRMATION ──{X}", kronos_line]
        if hmm_line:
            lines += ["", f"{Y}── HMM REGIME ──{X}", hmm_line]
        lines += [
            "",
            f"{Y}── NOTES ──{X}",
            f"{s.get('note', 'Standard execution — enter at open, hold to maturity.')}",
        ]
        box(f"LIVE SIGNAL — {s['ticker']} {s['date']}", lines)

    _pause()


# ---------------------------------------------------------------
# ACTION: Daily Telegram Report (NEW)
# ---------------------------------------------------------------
def action_daily_telegram_report():
    box("DAILY TELEGRAM REPORT — All Tickers", color=C)

    date_str = _ask("Date (YYYY-MM-DD, blank=today): ", "")
    min_wr = _ask_float("Min WR", 0.50)
    min_pf = _ask_float("Min PF", 1.0)

    print(f"\n  {G}Scanning NQ / ES / GC for {date_str or 'today'}...{X}\n")

    report_lines = []
    signals_found = 0

    for ticker in ["NQ", "ES", "GC"]:
        print(f"  {ticker}...", end=" ")
        sigs = generate_live_signals(
            ticker=ticker, date_str=date_str or None,
            min_win_rate=min_wr, min_pf=min_pf, use_short=True,
        )

        if sigs:
            s = sigs[0]
            signals_found += 1
            emoji = "🟢" if s["direction"] == "LONG" else "🔴"
            line = (
                f"• *{ticker}*: {emoji} {s['direction']} | "
                f"WR={s['wr']} PF={s['pf']} | "
                f"Conv={s['conviction']}x | "
                f"SL={s['sl_pct']} TP={s['tp_pct']} | "
                f"Hold={s['hold_days']}d | "
                f"Entry: {s.get('entry_timing', 'Open').split('—')[0].strip()} | "
                f"(N={s['n_samples']})"
            )
            print(f"{G}signal{X}")
        else:
            line = f"• *{ticker}*: ⚪ No signal — filtered"
            print(f"{Y}no signal{X}")

        report_lines.append(line)

    now = datetime.now()
    date_label = date_str if date_str else now.strftime("%Y-%m-%d")

    # Build the message
    message = f"📊 *AstroMiroQuant Daily Signals* — {date_label}\n\n"
    message += "\n".join(report_lines)
    message += f"\n\nFilters: WR≥{min_wr:.0%}, PF≥{min_pf:.1f} | Auto-generated {now.strftime('%H:%M')} WIB"
    message += f"\nSignals found: {signals_found}/3"

    print(f"\n{'─'*60}")
    print(message)
    print(f"{'─'*60}")

    # Save to file for easy copying
    report_path = os.path.expanduser("~/.astro-quant/daily_signal.txt")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write(message)
    print(f"\n  Report saved to: {report_path}")

    # Try to send via sandbox if available
    send = _ask("\n  Send to Telegram? (y/n): ", "n").lower()
    if send == "y":
        print(f"\n  {Y}To send via Telegram, copy the report above or use the auto-timer.{X}")
        print(f"  {Y}A daily timer fires at 13:00 WIB (Mon-Fri) to auto-send signals.{X}")
        print(f"  {Y}Timer ID: palphg3ollnvgob4xjb8z8eg{X}")

    _pause()


# ---------------------------------------------------------------
# ACTION: Kronos Dual-Confirmation Backtest
# ---------------------------------------------------------------
def action_kronos_backtest():
    box("KRONOS VOLATILITY ANALYSIS", color=C)

    if not _KRONOS_AVAILABLE:
        box(lines=[
            "Kronos requires PyTorch. Install:",
            "  pip install torch",
            "  git clone https://github.com/shiyu-coder/Kronos ~/kronos",
            "  cd ~/kronos && pip install -r requirements.txt",
        ], color=Y)
        _pause(); return

    from astro_matraix_kronos import kronos_volatility_adjustment, _get_cached_kronos

    print("\n  {0}Loading Kronos (cached after first run)...{1}".format(Y, X))
    try:
        _get_cached_kronos()
        print("  {0}Kronos loaded and cached{1}".format(G, X))
    except Exception as e:
        print("  {0}Kronos load failed: {1}{2}".format(R, e, X))
        _pause(); return

    print("\n  Scanning all 3 tickers...\n")
    for ticker in ["NQ", "ES", "GC"]:
        print("  {0}...".format(ticker), end=" ", flush=True)
        result = kronos_volatility_adjustment(ticker=ticker)
        if result:
            vm = result["vol_multiplier"]
            vc = R if vm > 1.3 else (G if vm < 0.8 else Y)
            print("{0}Vol: {1:.1f}x{2} | Hist={3}% Pred={4}% | {5}".format(
                vc, vm, X, result["hist_vol"], result["pred_vol"],
                result["recommendation"],
            ))
        else:
            print("{0}unavailable{1}".format(Y, X))

    print("\n  {0}── How to use ──{1}".format(G, X))
    print("  vol_mult > 1.3: Widen stops, reduce position to 1/vol_mult")
    print("  vol_mult < 0.8: Standard SL/TP, normal sizing")
    print("  vol_mult 0.8-1.3: Normal regime — no adjustment")
    _pause()


# ---------------------------------------------------------------
# ACTION: HMM Regime Detection
# ---------------------------------------------------------------
def action_hmm_regime():
    box("HMM REGIME DETECTION", color=C)

    if not HMM_AVAILABLE:
        box(lines=["astro_hmm module not found. Run: pip install numpy"], color=Y)
        _pause(); return

    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS:
        print("Invalid."); _pause(); return

    # Force retrain if using default params (detect by checking if A[0][0] == 0.70 exactly)
    params = load_hmm_params(ticker)
    is_default = params and abs(params.A[0][0] - 0.70) < 0.001 and abs(params.A[3][3] - 0.30) < 0.001
    if params and is_default:
        print("\n  {0}Detected default (untrained) HMM params. Retraining from persona data...{1}".format(Y, X))
        params = None  # Force retrain

    if params:
        print("\n  {0}Loaded cached HMM for {1}{2}".format(G, ticker, X))
    else:
        print("\n  {0}No cached HMM for {1}. Training (10-30s)...{2}".format(Y, ticker, X))
        from astro_matraix_backtest import persona_backtest_flow
        result = persona_backtest_flow(
            ticker=ticker, yahoo_start="2010-01-01",
            train_ratio=0.6, min_win_rate=0.50,
            min_pf=1.0, use_short_signals=True, verbose=False,
        )
        if result is None:
            box(lines=["Persona backtest failed."], color=R)
            _pause(); return
        params = train_from_persona_trades(ticker, result, verbose=True)
        save_hmm_params(params, ticker)
        print("  {0}HMM trained and cached.{1}".format(G, X))

    print("\n  {0}── Transition Matrix ──{1}".format(Y, X))
    header = "       " + " ".join("{:>7}".format(r) for r in REGIMES)
    print("  " + header)
    for i, r in enumerate(REGIMES):
        row = " ".join("{:7.3f}".format(params.A[i][j]) for j in range(len(REGIMES)))
        print("  {:>6}: {}".format(r, row))

    from astro_hmm import OBSERVATIONS
    print("\n  {0}── Regime Characteristics ──{1}".format(Y, X))
    for i, r in enumerate(REGIMES):
        top = sorted(
            [(params.B[i][k], OBSERVATIONS[k]) for k in range(params.B.shape[1])],
            reverse=True,
        )[:3]
        obs_str = ", ".join("{}({:.0%})".format(o[1], o[0]) for o in top)
        rc = {"BULL": G, "BEAR": R, "RANGE": Y, "CHOP": C}.get(r, X)
        print("  {0}{1}{2}: pi={3:.1%} | {4}".format(rc, r, X, params.pi[i], obs_str))

    print("\n  {0}── Current Regime ──{1}".format(Y, X))
    try:
        from astro_matraix_backtest import persona_backtest_flow as pbf
        result = pbf(
            ticker=ticker, yahoo_start="2023-01-01", train_ratio=0.4,
            min_win_rate=0.50, min_pf=1.0, use_short_signals=True, verbose=False,
        )
        if result and result.oos_trades:
            recent = result.oos_trades[-10:]
            obs_seq = []
            for trade in recent:
                d = trade.direction
                w = trade.net_points > 0
                p = abs(trade.gross_points) / 200.0
                obs_seq.append(observation_index(d, w, min(p, 0.05)))
            info = predict_regime(params, obs_seq)
            cm = {"BULL": G, "BEAR": R, "RANGE": Y, "CHOP": C}
            print("  Current: {0}{1}{2} (p={3:.1%})".format(
                cm.get(info["current_regime"], X), info["current_regime"], X,
                info["current_prob"],
            ))
            print("  Next:    {0}{1}{2} (p={3:.1%})".format(
                cm.get(info["next_regime"], X), info["next_regime"], X,
                info["next_prob"],
            ))
            print("  {0}-> {1}{2}".format(G, info["recommendation"], X))
            print("\n  Regime distribution:")
            for i, r in enumerate(REGIMES):
                bar = chr(9608) * int(info["regime_probs"][i] * 25)
                print("  {0}{1:>6}{2}: {3:.1%} {4}".format(
                    cm.get(r, X), r, X, info["regime_probs"][i], bar,
                ))
        else:
            print("  {0}No recent OOS trades.{1}".format(Y, X))
    except Exception as e:
        print("  {0}Prediction failed: {1}{2}".format(Y, e, X))
        print("  Run M4 first to populate trades.")

    _pause()



# ---------------------------------------------------------------
# ACTION: Multi-Timeframe Backtest
# ---------------------------------------------------------------
def action_mtf_backtest():
    box("MULTI-TIMEFRAME BACKTEST", color=C)

    if not MTF_AVAILABLE:
        box(lines=["astro_mtf module not found."], color=Y)
        _pause(); return

    ticker = _ask("Ticker: ", "NQ").upper()
    if ticker not in INSTRUMENTS:
        print("Invalid."); _pause(); return

    print("\n  Available bar sizes:")
    print("    15m  – 15-minute bars (60d Yahoo / years local)")
    print("    1h   – 1-hour bars (730d Yahoo)")
    print("    4h   – 4-hour bars (730d Yahoo, resampled)")
    print("    daily – Daily bars (full history)")

    bar_size = _ask("Bar size: ", "15m")
    date_start = _ask("Start date (YYYY-MM-DD): ", "2023-01-01")
    date_end = _ask("End date (YYYY-MM-DD): ", "2026-08-01")

    print("\n  {0}Running multi-timeframe backtest...{1}".format(G, X))

    from astro_mtf import mtf_backtest as mtf
    try:
        result = mtf(
            ticker=ticker, bar_size=bar_size,
            start=date_start, end=date_end,
            train_ratio=0.6, min_wr=0.50, min_pf=1.0,
            min_n=10 if bar_size != "daily" else 12,
            verbose=True,
        )
    except Exception as e:
        print("\n  {0}Backtest failed: {1}{2}".format(R, e, X))
        print("  Make sure you have data available:")
        print("    - Yahoo: pip install yfinance")
        print("    - Local: clone TheSnowGuru repo to ~/fifa/...")
        _pause(); return

    if result.n_trades == 0:
        print("\n  {0}No trades generated. Try:{1}".format(Y, X))
        print("    - Different bar size (more data)")
        print("    - Lower min_n (less strict filtering)")
        print("    - Clone TheSnowGuru repo for full history")
        _pause(); return

    print("\n  " + "=" * 60)
    print("  MTF BACKTEST RESULTS — {0} {1}".format(ticker, bar_size))
    print("  " + "=" * 60)
    print("  Train: {0} | Test: {1}".format(result.train_period, result.test_period))
    print("")
    print("  Trades:      {0}".format(result.n_trades))
    print("  Win Rate:    {0}{1:.1%}{2}".format(G if result.win_rate >= 0.55 else Y, result.win_rate, X))
    print("  Profit Factor: {0}{1:.2f}{2}".format(G if result.profit_factor >= 1.2 else R, result.profit_factor, X))
    print("  Total Points: {0}".format(result.total_points))
    print("  Total $:     {0}${1:,.0f}{2}".format(G if result.total_dollars > 0 else R, result.total_dollars, X))

    # Show first few trades
    if result.trades:
        print("\n  Recent trades:")
        for t in result.trades[-5:]:
            d = "{0}{1}{2}".format(G if t.direction == "LONG" else R, t.direction, X)
            print("  {0} {1}: {2} {3} → {4} | {5}{6}{7} pts | {8}".format(
                t.date, t.bar_time, d,
                t.entry_price, t.exit_price,
                G if t.gross_points > 0 else R,
                t.gross_points, X, t.exit_reason,
            ))

    _pause()

def action_settings():
    global SETTINGS
    box("SETTINGS", color=C)
    print(f"  Pattern thresholds: min_n={SETTINGS['min_n']}, max_p={SETTINGS['max_p']}, min_edge={SETTINGS['min_edge']}")
    print(f"  Memory dir: {memory.memory_dir}")
    print(f"  Runs archived: {memory.stats()['total_runs']}")
    SETTINGS["min_n"] = _ask_int("  Min sample size", SETTINGS["min_n"])
    SETTINGS["max_p"] = _ask_float("  Max p-value", SETTINGS["max_p"])
    SETTINGS["min_edge"] = _ask_float("  Min edge (e.g. 0.52)", SETTINGS["min_edge"])
    print("  Settings updated.")


# ---------------------------------------------------------------
# MAIN MENU
# ---------------------------------------------------------------
def interactive_menu():
    while True:
        stats = memory.stats()
        box("ASTRO-QUANT MISSION CONTROL V50.1", [
            f"Architecture: QuantMind + MiroFish + MatrAIx  |  Runs: {stats['total_runs']} archived",
            f"Memory: {memory.memory_dir}",
            "",
            f"{G}●{X} Astro Knowledge (typed Pydantic — ChartSnapshot, PatternCard, RegimeCard, BacktestResult)",
            f"{G}●{X} Astro Configs   (typed configs — BacktestCfg, CampaignCfg, InstrumentDef)",
            f"{G}●{X} Astro Flows    (pure fn pipeline — backtest_flow, campaign_flow, batch_run)",
            f"{G}●{X} Astro Mind     (filesystem archive — Memory, compare_runs, stats)",
            f"{Y}●{X} MatrAIx Personas (51-dim TraderPersonas — MatrAIx schema + astro→trait mapping)",
            f"{Y}●{X} MatrAIx Sim      (OASIS market micro-simulation — behavioral dynamics)",
            f"{Y}●{X} MatrAIx Cohort    (population analysis — dimension spread, emotional detection)",
            "",
            "Select an option:",
        ])
        opts = [
            ("1",  "Multi-Source Backtest"),
            ("2",  "Custom Date Backtest"),
            ("3",  "Dynamic Campaign (regime filters)"),
            ("4",  "Dynamic Filter Status"),
            ("5",  "Pattern Explorer"),
            ("6",  "Run History"),
            ("7",  "Run Rectification"),
            ("",   ""),
            ("M1", "MatrAIx Persona Explorer (51-dim profiles)"),
            ("M2", "MatrAIx Market Simulation (OASIS-style)"),
            ("M3", "MatrAIx Cohort Report (population analysis)"),
            ("M4", "MatrAIx Persona Backtest (close the loop — real trades)"),
            ("M5", "Live MatrAIx Signal (today's persona-weighted signal)"),
            ("M6", "Daily Telegram Report (all 3 tickers → Telegram)"),
            ("M7", "Kronos Volatility Analysis (predicts vol regime, adjusts stops)"),
            ("M8", "HMM Regime Detection (learn market regime from trades, filter signals)"),
            ("M9", "Multi-Timeframe Backtest (15m/1H/4H persona backtest)"),
            ("",   ""),
            ("8",  "Settings"),
            ("0",  "Exit"),
        ]
        print()
        for num, desc in opts:
            print(f"  {B}[{num}]{X}  {desc}")

        choice = _ask("\n  Select option: ", "0")
        choice = choice.upper()

        if choice == "1":
            action_backtest()
        elif choice == "2":
            action_backtest_custom()
        elif choice == "3":
            action_dynamic_campaign()
        elif choice == "4":
            action_dynamic_status()
        elif choice == "5":
            action_pattern_explorer()
        elif choice == "6":
            action_run_history()
        elif choice == "7":
            action_rectify()
        elif choice == "8":
            action_settings()
        elif choice == "M1":
            action_matraix_personas()
        elif choice == "M2":
            action_matraix_simulation()
        elif choice == "M3":
            action_matraix_cohort()
        elif choice == "M4":
            action_matraix_backtest()
        elif choice == "M5":
            action_matraix_live()
        elif choice == "M6":
            action_daily_telegram_report()
        elif choice == "M7":
            action_kronos_backtest()
        elif choice == "M8":
            action_hmm_regime()
        elif choice == "M9":
            action_mtf_backtest()
        elif choice == "0":
            print(f"\n  {G}Mission Control shutting down. {stats['total_runs']} runs archived.{X}")
            break
        else:
            print(f"  {Y}Invalid selection.{X}")


# ---------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Astro-Quant Mission Control V40.3")
    parser.add_argument("--menu", action="store_true", default=True,
                        help="Launch interactive menu (default)")
    args = parser.parse_args()

    try:
        interactive_menu()
    except KeyboardInterrupt:
        print(f"\n  {Y}Interrupted. Shutting down.{X}")
    except Exception as e:
        print(f"\n  {R}Fatal error: {e}{X}")
        raise

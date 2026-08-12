"""
ASTRO FLOWS — End-to-End Pipeline Functions
=============================================
QuantMind-style flows: pure async functions that compose the full pipeline.
No UI code — thin TUI shell calls these.

Flows:
  - backtest_flow(cfg)        → BacktestResult
  - multi_source_backtest(cfg) → BatchBacktestResult
  - campaign_flow(cfg)        → list[RegimeCard]
  - rectify_flow(cfg)         → ChartSnapshot

  - batch_run(flow_fn, inputs, max_concurrency) → BatchResult
    (QuantMind-style fan-out with bounded concurrency)

Design (from QuantMind):
  - Functions over classes; no plugin registries
  - State passed as arguments; side effects via explicit hooks
  - Pydantic at boundaries
  - batch_run is first-class — users don't write asyncio.gather themselves
"""

from __future__ import annotations
import asyncio
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal, Callable, Any, TypeVar

from pydantic import BaseModel

# Astro engine
import swisseph as swe
swe.set_ephe_path()

from astro_core_v2 import (
    calculate_chart, SIGN_NAMES, SIGN_RULERS,
    primary_direction_arc, direction_date, fidaria, distributor,
    find_hllaj, part_of_fortune, part_of_spirit, bound_ruler,
)

# Knowledge + Config
from astro_knowledge import (
    ChartSnapshot, PatternCard, RegimeCard, TradeStats,
    TradeRecord, BacktestResult, BatchBacktestResult,
    chart_to_snapshot, DataSourceKind, SourceRef, ChartProvenance,
)
from astro_configs import (
    BacktestCfg, MultiSourceBacktestCfg, BatchBacktestCfg,
    CampaignCfg, RectifyCfg, FilterCfg, InstrumentDef,
    YahooSource, CsvSource, RepoDailySource, DataSource,
    TICKER_DATA_SOURCES, INSTRUMENTS,
)

# Pattern engine (imported from existing module)
try:
    from pattern_engine_v3 import (
        load_rectified, get_state, state_key,
        build_patterns, learn_patterns,
    )
except ImportError:
    try:
        from pattern_engine_v2 import (
            load_rectified, get_state, state_key,
            build_patterns, learn_patterns,
        )
    except ImportError:
        print("WARNING: pattern_engine_v2/v3 not found. Backtest flows disabled.")
        load_rectified = lambda: {}
        get_state = None
        state_key = None
    build_patterns = None
    learn_patterns = None

# Dynamic filters
try:
    from dynamic_filters_v1 import compute_dynamic_signal
    DYNAMIC_FILTERS_AVAILABLE = True
except ImportError:
    DYNAMIC_FILTERS_AVAILABLE = False

# Data sources
import pandas as pd
import yfinance as yf

# ====================================================================
# TYPE HELPERS
# ====================================================================

T = TypeVar("T")


class BatchResult(BaseModel):
    """Aggregated result from batch_run."""
    results: list[Any]
    total: int
    succeeded: int
    failed: int
    errors: list[str]


# ====================================================================
# BATCH RUNNER (QuantMind-style)
# ====================================================================

async def batch_run(
    flow_fn: Callable[..., Any],
    inputs: list[dict[str, Any]],
    max_concurrency: int = 3,
    *,
    memory=None,  # rejected by design in MVP per QuantMind
    progress_callback: Callable[[int, int], None] | None = None,
) -> BatchResult:
    """
    Fan-out a flow function over multiple inputs with bounded concurrency.

    Design (from QuantMind):
      - Rejects memory= at the signature layer (MVP constraint)
      - Bounded concurrency via asyncio.Semaphore
      - Error collection: failed items don't crash the batch
      - Progress callback for UI integration
    """
    if memory is not None:
        raise ValueError("batch_run does not support memory= in MVP")

    semaphore = asyncio.Semaphore(max_concurrency)
    results = []
    errors = []

    async def _run_one(i: int, kwargs: dict):
        async with semaphore:
            try:
                if asyncio.iscoroutinefunction(flow_fn):
                    result = await flow_fn(**kwargs)
                else:
                    result = flow_fn(**kwargs)
                results.append(result)
                if progress_callback:
                    progress_callback(i + 1, len(inputs))
                return True
            except Exception as e:
                errors.append(f"Input {i}: {e}")
                if progress_callback:
                    progress_callback(i + 1, len(inputs))
                return False

    tasks = [_run_one(i, inp) for i, inp in enumerate(inputs)]
    await asyncio.gather(*tasks)

    return BatchResult(
        results=results,
        total=len(inputs),
        succeeded=len(results),
        failed=len(errors),
        errors=errors,
    )


# ====================================================================
# DATA LOADERS (extracted from mission_control) — synchronous
# ====================================================================

def _load_yahoo(symbol: str, start_date: str = "2010-01-01") -> tuple[dict, list] | None:
    """Load Yahoo Finance daily bars."""
    try:
        data = yf.download(symbol, start=start_date, progress=False, auto_adjust=True)
        if data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        dd, dates = {}, []
        for idx, row in data.iterrows():
            ds = idx.strftime("%Y-%m-%d")
            o = float(row["Open"]); c = float(row["Close"])
            if o <= 0 or c <= 0:
                continue
            dd[ds] = {
                "open": o,
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": c,
            }
            dates.append(ds)
        return dd, sorted(dates)
    except Exception as e:
        print(f"  Yahoo error ({symbol}): {e}")
        return None


def _load_csv(filename: str, start_year: int = 2010) -> tuple[dict, list] | None:
    """Load CSV daily bars (aggregated from intraday)."""
    import glob as _glob
    def _find_file(fn):
        # Search broadly: script dir, subdirs, fifa project root, common data paths
        script_dir = os.path.dirname(os.path.abspath(__file__))
        search_dirs = [
            ".", "data", "csv", "csv_data",
            script_dir,
            os.path.join(script_dir, "data"),
            os.path.join(script_dir, "csv"),
            os.path.join(script_dir, "csv_data"),
            # Walk up to find fifa project root
            os.path.join(os.path.dirname(script_dir), "data"),
            os.path.join(os.path.dirname(script_dir), "csv"),
            os.path.expanduser("~/Desktop/fifa"),
            os.path.expanduser("~/Desktop/fifa/data"),
            os.path.expanduser("~/Desktop/fifa/csv"),
            os.path.expanduser("~/Desktop/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data"),
        ]
        # First try exact match
        for base in search_dirs:
            if not os.path.isdir(base):
                continue
            path = os.path.join(base, fn)
            if os.path.exists(path):
                return path
        # Fallback: glob match — look for CSV files containing the ticker prefix
        # e.g. if fn="GC_2024-2026_30m.csv", also find "GC_30m_2020_2025.csv"
        # Extract ticker from filename (e.g. "GC_", "NQ_", "ES_", "CME_MINI_NQ1!")
        ticker_hints = []
        for prefix in ["NQ", "ES", "GC", "CME_MINI_NQ1!", "CME_MINI_ES1!", "COMEX_GC1!"]:
            if prefix in fn:
                ticker_hints.append(prefix)
        for base in search_dirs:
            if not os.path.isdir(base):
                continue
            for candidate in _glob.glob(os.path.join(base, "*.csv")) + _glob.glob(os.path.join(base, "*", "*.csv")):
                fname = os.path.basename(candidate)
                # Match if filename contains the ticker hint AND "30m" or "60m" from the original
                matches_ticker = any(hint in fname for hint in ticker_hints) if ticker_hints else True
                tf_hint = "30m" if "30m" in fn else "60m" if "60m" in fn else None
                matches_tf = tf_hint.lower() in fname.lower() if tf_hint else True
                if matches_ticker and matches_tf:
                    return candidate
        return None

    path = _find_file(filename)
    if not path:
        return None

    bars = defaultdict(lambda: {"open": None, "high": -1e18, "low": 1e18, "close": None})
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return None
        cols = [c.strip().lower() for c in header]
        di = next((i for i, c in enumerate(cols) if c in ["datetime", "date", "time"]), 0)
        oi = next((i for i, c in enumerate(cols) if c in ["open", "o"]), 1)
        hi = next((i for i, c in enumerate(cols) if c in ["high", "h"]), oi)
        li = next((i for i, c in enumerate(cols) if c in ["low", "l"]), oi)
        ci = next((i for i, c in enumerate(cols) if c in ["close", "c", "price"]), 4)
        ti = next((i for i, c in enumerate(cols) if c == "time"), None)

        for row in reader:
            try:
                dt_str = row[di].strip()
                dt = None
                if dt_str.isdigit():
                    ts = float(dt_str)
                    if ts > 1e12:
                        ts /= 1000.0
                    dt = datetime.utcfromtimestamp(ts)
                else:
                    for fmt in [
                        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y",
                    ]:
                        try:
                            dt = datetime.strptime(dt_str, fmt)
                            break
                        except ValueError:
                            pass
                if dt is None:
                    continue
                if ti and ti < len(row):
                    try:
                        hh, mm, ss = row[ti].strip().split(":")
                        dt = dt.replace(hour=int(hh), minute=int(mm), second=int(ss))
                    except Exception:
                        pass
                if dt.year < start_year:
                    continue
                ds = dt.strftime("%Y-%m-%d")
                o = float(row[oi]); h = float(row[hi])
                l = float(row[li]); c = float(row[ci])
                if o <= 0 or c <= 0:
                    continue
                b = bars[ds]
                if b["open"] is None:
                    b["open"] = o
                b["high"] = max(b["high"], h)
                b["low"] = min(b["low"], l)
                b["close"] = c
            except Exception:
                continue

    dd = {}
    for d in sorted(bars):
        b = bars[d]
        if b["open"] is not None:
            dd[d] = {"open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"]}
    return dd, sorted(dd)


# Repo paths — search broadly
_REPO_BASE = None
_REPO_SEARCH = [
    os.path.expanduser("~/Desktop/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data"),
    "Stocks-Futures-Financial-Time-series-Tick-Bar-Data",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "Stocks-Futures-Financial-Time-series-Tick-Bar-Data"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Stocks-Futures-Financial-Time-series-Tick-Bar-Data"),
    os.path.expanduser("~/Desktop/fifa"),
]
for _candidate in _REPO_SEARCH:
    if os.path.isdir(_candidate):
        # Check if it contains the expected subdirectories
        if os.path.isdir(os.path.join(_candidate, "indices")) or \
           os.path.isdir(os.path.join(_candidate, "commodities")):
            _REPO_BASE = _candidate
            break
        # If the candidate itself has a Stocks-Futures child
        sub = os.path.join(_candidate, "Stocks-Futures-Financial-Time-series-Tick-Bar-Data")
        if os.path.isdir(sub):
            _REPO_BASE = sub
            break

_REPO_MAP = {
    "NQ": ("indices/nasdaq100", "USATECHIDXUSD"),
    "ES": ("indices/s&p500", "USA500IDXUSD"),
    "GC": ("commodities/gold", "XAUUSD"),
}


def _load_repo_daily(ticker: str, timeframe: str = "H1", start_date: str = "2000-01-01") -> tuple[dict, list] | None:
    """Load repo intraday and aggregate to daily."""
    if _REPO_BASE is None:
        return None
    folder, prefix = _REPO_MAP[ticker]
    filepath = os.path.join(_REPO_BASE, folder, f"{prefix}_{timeframe}.csv")
    if not os.path.exists(filepath):
        for tf in ["H1", "M30", "M1"]:
            alt = os.path.join(_REPO_BASE, folder, f"{prefix}_{tf}.csv")
            if os.path.exists(alt):
                filepath = alt
                break
        else:
            return None
    try:
        df = pd.read_csv(filepath, sep="\t", parse_dates=["Time"], dayfirst=False)
        df["Time"] = pd.to_datetime(df["Time"]) + timedelta(hours=5)

        daily = defaultdict(lambda: {"open": None, "high": -1e18, "low": 1e18, "close": None})
        for _, row in df.iterrows():
            ds = row["Time"].strftime("%Y-%m-%d")
            if ds < start_date:
                continue
            o = float(row["Open"]); h = float(row["High"])
            l = float(row["Low"]); c = float(row["Close"])
            if o <= 0 or c <= 0:
                continue
            b = daily[ds]
            if b["open"] is None:
                b["open"] = o
            b["high"] = max(b["high"], h)
            b["low"] = min(b["low"], l)
            b["close"] = c

        dd, dates = {}, []
        for d in sorted(daily):
            b = daily[d]
            if b["open"] is not None and b["close"] > 0:
                dd[d] = {"open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"]}
                dates.append(d)
        return dd, sorted(dates)
    except Exception as e:
        print(f"  Repo error ({ticker}/{timeframe}): {e}")
        return None


def load_data(source: DataSource, ticker: str = "NQ") -> tuple[dict, list] | None:
    """Dispatch to correct loader based on source type."""
    if isinstance(source, YahooSource):
        return _load_yahoo(source.symbol, source.start_date)
    elif isinstance(source, CsvSource):
        return _load_csv(source.filename, source.start_year)
    elif isinstance(source, RepoDailySource):
        return _load_repo_daily(
            ticker,
            source.timeframe,
            source.start_date,
        )
    return None


# ====================================================================
# CHART LOADER
# ====================================================================

def load_chart(ticker: str, inst: InstrumentDef) -> ChartSnapshot | None:
    """Load or compute a rectified chart for an instrument."""
    rect = load_rectified().get(ticker)
    if not rect:
        return None

    utc_dt = datetime(
        inst.birth_year, inst.birth_month, inst.birth_day,
        rect["hour"], rect["min"], rect["sec"],
    )
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)

    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    return chart_to_snapshot(
        ticker=ticker,
        chart_dict=chart_dict,
        birth_utc=utc_dt,
        tz_offset=inst.birth_tz,
        lat=inst.birth_lat,
        lon=inst.birth_lon,
    )


# ====================================================================
# SIMULATION ENGINE
# ====================================================================

def simulate(signals, dd, dates, sl, tp, hold, tca):
    d2i = {d: i for i, d in enumerate(dates)}
    trades, last_idx = [], -1
    for entry_date, direction, _ in signals:
        idx = d2i.get(entry_date)
        if idx is None or idx <= last_idx:
            continue
        xi = idx + hold
        if xi >= len(dates):
            continue
        eb = dd.get(dates[idx]); xb = dd.get(dates[xi])
        if not eb or not xb:
            continue
        ep = eb["open"]; xp = xb["close"]
        if ep <= 0:
            continue
        stopped = False; gross = 0.0
        for j in range(idx, xi + 1):
            bar = dd[dates[j]]
            if direction == "LONG":
                if bar["low"] <= ep - sl:
                    gross = -sl; stopped = True; break
                if bar["high"] >= ep + tp:
                    gross = tp; stopped = True; break
            elif direction == "SHORT":
                if bar["high"] >= ep + sl:
                    gross = -sl; stopped = True; break
                if bar["low"] <= ep - tp:
                    gross = tp; stopped = True; break
        if not stopped:
            gross = (xp - ep) if direction == "LONG" else (ep - xp)
        trades.append({"date": entry_date, "dir": direction, "gross": gross, "net": gross - tca})
        last_idx = xi
    return trades


def compute_trade_stats(trades, pt_value=1.0) -> TradeStats:
    if not trades:
        return TradeStats()
    vals = [t["net"] for t in trades]
    n = len(vals)
    tot = sum(vals)
    mu = tot / n
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    wr = len(wins) / n if n else 0
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else (999 if gw > 0 else 0)
    sd = (sum((v - mu) ** 2 for v in vals) / (n - 1)) ** 0.5 if n > 1 else 0
    sh = mu / sd if sd > 0 else 0
    return TradeStats(
        n_trades=n,
        win_rate=wr,
        avg_win=sum(wins) / len(wins) if wins else 0,
        avg_loss=sum(losses) / len(losses) if losses else 0,
        total_points=tot,
        total_dollars=tot * pt_value,
        profit_factor=pf,
        sharpe=sh,
    )


def grid_search(signals, dd, dates, pt_value, tca, sl_grid, tp_grid, hold_grid, min_trades=5) -> dict | None:
    best_score, best_params = -1e9, None
    for sl in sl_grid:
        for tp in tp_grid:
            if tp / sl < 1.2 or tp / sl > 6:
                continue
            for hold in hold_grid:
                trades = simulate(signals, dd, dates, sl, tp, hold, tca)
                if len(trades) < min_trades:
                    continue
                st = compute_trade_stats(trades, pt_value)
                score = (
                    st.sharpe * 50
                    + (min(st.profit_factor, 5) - 1) * 20
                    - abs(getattr(st, "max_drawdown", 0)) / max(1, abs(st.total_points)) * 10
                )
                if score > best_score:
                    best_score = score
                    best_params = {"sl": sl, "tp": tp, "hold": hold, "stats": st}
    return best_params


# ====================================================================
# BACKTEST FLOW
# ====================================================================

def backtest_flow(cfg: BacktestCfg) -> BacktestResult | None:
    """
    Run a single backtest from config.

    Returns a BacktestResult (typed knowledge artifact) or None.
    """
    inst = INSTRUMENTS.get(cfg.ticker)
    if not inst:
        print(f"  No instrument definition for {cfg.ticker}")
        return None

    point_value = cfg.point_value if cfg.point_value is not None else inst.point_value

    # Load chart
    chart = load_chart(cfg.ticker, inst)
    if not chart:
        print(f"  No rectified chart for {cfg.ticker}")
        return None

    # Load data
    raw = load_data(cfg.source, ticker=cfg.ticker)
    if not raw:
        print(f"  No data for {cfg.ticker} via {cfg.source}")
        return None
    dd, all_dates = raw

    # Filter by date range
    dates = [d for d in all_dates if d >= cfg.date_start]
    if cfg.date_end:
        dates = [d for d in dates if d <= cfg.date_end]
    if len(dates) < 200:
        print(f"  Not enough data: {len(dates)} days")
        return None

    n = len(dates)
    train_end = int(n * cfg.train_ratio)
    val_end = int(n * (cfg.train_ratio + 0.2))
    train_dates = dates[:train_end]
    val_dates = dates[train_end:val_end]
    test_dates = dates[val_end:]

    # Convert ChartSnapshot back to dict for compatibility with pattern_engine
    chart_dict = {
        "utc_time": chart.as_of,
        "latitude": chart.latitude,
        "longitude": chart.longitude,
        "ascendant": {
            "longitude": chart.ascendant.longitude,
            "sign": chart.ascendant.sign_index,
            "degree_in_sign": chart.ascendant.degree_in_sign,
        },
        "midheaven": {
            "longitude": chart.midheaven.longitude,
            "sign": chart.midheaven.sign_index,
            "degree_in_sign": chart.midheaven.degree_in_sign,
        },
        "sect": chart.sect,
        "planets": {
            name: {
                "longitude": p.longitude,
                "latitude": p.latitude,
                "speed": p.speed,
                "sign": p.sign_index,
                "degree_in_sign": p.degree_in_sign,
                "is_retrograde": p.is_retrograde,
            }
            for name, p in chart.planets.items()
        },
    }

    # Build + learn patterns
    pats = build_patterns(chart_dict, dd, train_dates, horizons=cfg.horizons)
    learned = learn_patterns(pats, min_n=12, max_p=0.02, min_edge=0.52)
    if not learned:
        return None

    all_pats = sorted(learned.values(), key=lambda x: x["score"], reverse=True)

    def _gen_signals(date_list):
        sigs = []
        for i in range(len(date_list) - 1):
            sd = date_list[i]; ed = date_list[i + 1]
            if sd not in dd or ed not in dd:
                continue
            signal_utc = datetime.strptime(sd, "%Y-%m-%d").replace(hour=17)
            st = get_state(chart_dict, signal_utc)
            best_pat = None
            for pat in all_pats:
                if state_key(st, pat["horizon"]) == pat["key"]:
                    best_pat = pat; break
            if best_pat is None and all_pats:
                best_pat = all_pats[0]
            if best_pat:
                sigs.append((ed, best_pat["direction"], best_pat["key"]))
        return sigs

    # Validation
    val_sigs = _gen_signals(val_dates)
    tca_pts = cfg.transaction_cost_points
    best = grid_search(val_sigs, dd, val_dates, point_value, tca_pts,
                       cfg.sl_grid, cfg.tp_grid, cfg.hold_grid, cfg.min_trades)
    if best is None:
        return None

    # Out-of-sample
    test_sigs = _gen_signals(test_dates)
    oos_st = TradeStats()
    oos_trades = []
    if test_sigs:
        test_trades = simulate(test_sigs, dd, test_dates, best["sl"], best["tp"], best["hold"], tca_pts)
        oos_st = compute_trade_stats(test_trades, point_value)
        oos_trades = [
            TradeRecord(date=t["date"], direction=t["dir"],
                         gross_points=t["gross"], net_points=t["net"])
            for t in test_trades
        ]

    # Build result
    source_ref = SourceRef(
        kind=cfg.source.kind,
        symbol=getattr(cfg.source, "symbol", "")
        or getattr(cfg.source, "filename", "")
        or f"{cfg.ticker}_repo_{getattr(cfg.source, 'timeframe', 'H1')}",
    )

    return BacktestResult(
        as_of=datetime.now(),
        ticker=cfg.ticker,
        source=source_ref,
        chart_provenance=chart.source,
        train_ratio=cfg.train_ratio,
        sl_points=best["sl"],
        tp_points=best["tp"],
        hold_days=best["hold"],
        patterns_found=len(pats),
        patterns_valid=len(learned),
        validation=best["stats"],
        out_of_sample=oos_st,
        oos_trades=oos_trades,
    )


# ====================================================================
# MULTI-SOURCE BACKTEST
# ====================================================================

async def multi_source_backtest(cfg: MultiSourceBacktestCfg) -> BatchBacktestResult | None:
    """
    Run backtests across multiple sources for one ticker.

    Uses batch_run for bounded-concurrency parallel execution.
    """
    inputs = []
    for source in cfg.sources:
        bc = BacktestCfg(
            ticker=cfg.ticker,
            source=source,
            train_ratio=cfg.base_cfg.train_ratio,
            date_start=cfg.base_cfg.date_start,
            date_end=cfg.base_cfg.date_end,
            point_value=cfg.base_cfg.point_value,
            transaction_cost_points=cfg.base_cfg.transaction_cost_points,
            sl_grid=cfg.base_cfg.sl_grid,
            tp_grid=cfg.base_cfg.tp_grid,
            hold_grid=cfg.base_cfg.hold_grid,
            min_trades=cfg.base_cfg.min_trades,
            horizons=cfg.base_cfg.horizons,
        )
        inputs.append({"cfg": bc})

    batch_result = await batch_run(
        backtest_flow,
        inputs,
        max_concurrency=3,
    )

    valid_results = [
        r for r in batch_result.results
        if r is not None and isinstance(r, BacktestResult)
    ]

    return BatchBacktestResult(
        as_of=datetime.now(),
        results=valid_results,
    )


# ====================================================================
# CAMPAIGN FLOW
# ====================================================================

def campaign_flow(cfg: CampaignCfg) -> list[RegimeCard] | None:
    """
    Generate trading signals for a date range with optional dynamic filters.

    Returns a list of RegimeCard objects — one per state change.
    """
    inst = INSTRUMENTS.get(cfg.ticker)
    if not inst:
        return None

    chart = load_chart(cfg.ticker, inst)
    if not chart:
        return None

    # Load price data (for patterns only — campaign doesn't backtest)
    chart_dict = {
        "utc_time": chart.as_of,
        "latitude": chart.latitude,
        "longitude": chart.longitude,
        "ascendant": {
            "longitude": chart.ascendant.longitude,
            "sign": chart.ascendant.sign_index,
            "degree_in_sign": chart.ascendant.degree_in_sign,
        },
        "midheaven": {
            "longitude": chart.midheaven.longitude,
            "sign": chart.midheaven.sign_index,
            "degree_in_sign": chart.midheaven.degree_in_sign,
        },
        "sect": chart.sect,
        "planets": {
            name: {
                "longitude": p.longitude,
                "latitude": p.latitude,
                "speed": p.speed,
                "sign": p.sign_index,
                "degree_in_sign": p.degree_in_sign,
                "is_retrograde": p.is_retrograde,
            }
            for name, p in chart.planets.items()
        },
    }

    dd_raw = _load_yahoo(cfg.source.symbol, start_date=cfg.date_start)
    if not dd_raw:
        return None
    dd, all_dates = dd_raw

    pats = build_patterns(chart_dict, dd, all_dates, horizons=[3, 5, 7])
    learned = learn_patterns(pats, min_n=12, max_p=0.02, min_edge=0.52)
    if not learned:
        return None

    all_pats = sorted(learned.values(), key=lambda x: x["score"], reverse=True)

    start_dt = datetime.strptime(cfg.date_start, "%Y-%m-%d")
    end_dt = datetime.strptime(cfg.date_end, "%Y-%m-%d")

    cards: list[RegimeCard] = []
    d = start_dt
    prev_state = None

    while d <= end_dt:
        if d.weekday() >= 5:  # skip weekends
            d += timedelta(days=1)
            continue

        signal_utc = d.replace(hour=17)
        st = get_state(chart_dict, signal_utc)
        curr = (st["main"], st["sub"], st["dist"], st["house"], st["moon_phase"])

        if curr != prev_state:
            best_pat = None
            for pat in all_pats:
                if state_key(st, pat["horizon"]) == pat["key"]:
                    best_pat = pat; break
            if best_pat is None and all_pats:
                best_pat = all_pats[0]

            base_dir = None
            mod_dir = None
            pat_key = None

            if best_pat:
                base_dir = best_pat["direction"]
                pat_key = best_pat["key"]
                mod_dir = base_dir

            # Dynamic filters
            regime = "NEUTRAL"
            combined_score = 0.0
            moon_s = nodes_s = moiety_s = arcus_s = 0.0

            if DYNAMIC_FILTERS_AVAILABLE and cfg.use_dynamic_filters and base_dir:
                regime, combined_score, _ = compute_dynamic_signal(chart_dict, signal_utc)
                if base_dir == "LONG" and regime == "BEARISH":
                    mod_dir = "FLAT"
                elif base_dir == "SHORT" and regime == "BULLISH":
                    mod_dir = "FLAT"

            cards.append(RegimeCard(
                as_of=signal_utc,
                ticker=cfg.ticker,
                moon_application_score=moon_s,
                nodes_score=nodes_s,
                moiety_score=moiety_s,
                arcus_vitae_score=arcus_s,
                combined_score=combined_score,
                regime=regime,
                base_direction=base_dir,
                modulated_direction=mod_dir,
                pattern_key=pat_key,
            ))

            prev_state = curr

        d += timedelta(days=1)

    return cards


# ====================================================================
# SELF-TEST
# ====================================================================

async def _self_test():
    print("=" * 60)
    print(" ASTRO FLOWS — SELF-TEST")
    print("=" * 60)

    # Test batch_run with a simple function
    async def _square(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * x

    result = await batch_run(
        _square,
        [{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}, {"x": 5}],
        max_concurrency=2,
    )
    print(f"\nBatch run test: {result.succeeded}/{result.total} succeeded")
    print(f"Results: {result.results}")

    # Test backtest_flow if data available
    try:
        cfg = BacktestCfg(
            ticker="GC",
            source=YahooSource(symbol="GC=F", start_date="2020-01-01"),
            train_ratio=0.6,
            date_start="2020-01-01",
        )
        print(f"\nRunning backtest_flow for {cfg.ticker}...")
        bt_result = backtest_flow(cfg)
        if bt_result:
            print(f"  Patterns: {bt_result.patterns_valid}")
            print(f"  Val PF: {bt_result.validation.profit_factor:.2f}")
            print(f"  OOS PF: {bt_result.out_of_sample.profit_factor:.2f}")
            print(f"  OOS Net: ${bt_result.out_of_sample.total_dollars:,.0f}")
        else:
            print("  No result (likely no rectified chart or data)")
    except Exception as e:
        print(f"  Backtest flow error: {e}")

    print("\n" + "=" * 60)
    print(" SELF-TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_self_test())

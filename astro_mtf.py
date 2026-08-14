#!/usr/bin/env python3
"""
ASTRO MTF — Multi-Timeframe Astro Persona Signals
===================================================
Upgraded from single-timeframe daily signals to multi-timeframe
persona pipeline that builds personas from 15m/1H/4H bar data
and provides directional signals with entry timing, SL/TP, and conviction.

Key features:
  - Load market data at arbitrary bar sizes (15m, 30m, 1H, 4H, etc.)
  - Build personas from MTF patterns (not just daily)
  - State matching: exact → prefix → main+moon → main
  - Persona-derived SL/TP/hold from 51-dim profile
  - Live signal generation for current astro state
  - Backtest functionality comparing persona signals to actual returns
"""

from __future__ import annotations
import math, os, sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import pandas as pd
import yfinance as yf

from astro_core_v2 import calculate_chart, fidaria, distributor, bound_ruler, SIGN_NAMES
from astro_configs import INSTRUMENTS
from astro_knowledge import chart_to_snapshot
from astro_personas import generate_trader_personas_from_learned
from pattern_engine_v3 import build_patterns, learn_patterns, get_state, state_key, load_rectified


# ====================================================================
# DATA LOADING
# ====================================================================

def load_mtf_data(ticker, bar_size="1h", start="2023-01-01", end=None):
    """Load MTF data at specified bar size."""
    inst = INSTRUMENTS.get(ticker)
    if not inst: return None
    symbol = inst.data_symbol if inst.data_symbol else f"{ticker}=F"
    interval_map = {
        "15m": "15m", "30m": "30m", "1h": "60m", "4h": "60m",
        "1H": "60m", "4H": "60m", "daily": "1d", "1d": "1d",
    }
    yf_interval = interval_map.get(bar_size, "60m")
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    data = yf.Ticker(symbol).history(start=start, end=end, interval=yf_interval)
    if data is None or data.empty:
        # Try without auto_adjust
        data = yf.download(symbol, start=start, end=end, interval=yf_interval, progress=False)
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    col_map = {
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Volume": "volume", "Adj Close": "adj_close",
    }
    data = data.rename(columns=col_map)
    for c in ["open", "high", "low", "close"]:
        if c not in data.columns:
            return pd.DataFrame()
    return data


def load_csv_data(ticker, bar_size="1h"):
    """Try to load from local CSV files (your existing data)."""
    csv_map = {
        "NQ": {"1h": "CME_MINI_NQ1!, 60.csv", "60m": "CME_MINI_NQ1!, 60.csv",
               "30m": "NQ_2024-2026_30m.csv"},
        "ES": {"1h": "CME_MINI_ES1!, 60.csv", "60m": "CME_MINI_ES1!, 60.csv",
               "30m": "CME_MINI_ES1!, 30.csv"},
        "GC": {"1h": "COMEX_GC1!, 60.csv", "60m": "COMEX_GC1!, 60.csv",
               "30m": "GC_2024-2026_30m.csv"},
    }
    files = csv_map.get(ticker, {})
    fn = files.get(bar_size)
    if not fn or not os.path.exists(fn):
        return None
    df = pd.read_csv(fn)
    # Standardize index: handle 'Date', 'time', or 'datetime' timestamp column
    for icol in ("Date", "time", "datetime", "timestamp"):
        if icol in df.columns:
            df[icol] = pd.to_datetime(df[icol], errors="coerce")
            df = df.set_index(icol)
            break
    # Standardize column names to lowercase
    df = df.rename(columns={c: c.lower() for c in df.columns if c in ("Open","High","Low","Close","Volume")})
    if df.index.isnull().any():
        df = df.dropna(subset=[df.index.name])
    return df


# ====================================================================
# MTF PATTERN BUILDING
# ====================================================================

def build_mtf_patterns(chart_dict, df, bar_size="1h", horizons=(5, 10, 20)):
    """Build patterns from MTF data."""
    from collections import defaultdict
    pats = defaultdict(list)
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except:
            return {}
    n = len(df)
    if n < 100:
        return {}
    for i in range(n - max(horizons) - 1):
        timestamp = df.index[i]
        signal_utc = timestamp.to_pydatetime()
        try:
            st = get_state(chart_dict, signal_utc)
        except:
            continue
        entry_open = df.iloc[i + 1]["open"]
        for hz in horizons:
            exit_idx = i + 1 + hz
            if exit_idx >= n:
                continue
            exit_close = df.iloc[exit_idx]["close"]
            r = exit_close / entry_open - 1.0 if entry_open > 0 else 0.0
            sk = state_key(st, hz)
            pats[sk].append({"return": r, "regime": "unknown", "date": timestamp.strftime("%Y-%m-%d")})
    return dict(pats)


# ====================================================================
# PERSONA GENERATION FROM MTF PATTERNS
# ====================================================================

def generate_mtf_personas(ticker, df, bar_size="1h", train_ratio=0.7,
                          min_wr=0.50, min_pf=1.0, min_n=12, verbose=True):
    """Generate personas from MTF patterns."""
    inst = INSTRUMENTS.get(ticker)
    if not inst:
        return [], {}
    rect = load_rectified().get(ticker)
    if not rect:
        rect = {"NQ": {"hour": 21, "min": 0, "sec": 0}}.get(ticker, {"hour": 12, "min": 0, "sec": 0})
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                      rect["hour"], rect["min"], rect.get("sec", 0))
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    chart_snap = chart_to_snapshot(ticker=ticker, chart_dict=chart_dict,
                                    birth_utc=utc_dt, tz_offset=inst.birth_tz,
                                    lat=inst.birth_lat, lon=inst.birth_lon)
    n = len(df)
    train_end = int(n * train_ratio)
    train_df = df.iloc[:train_end]
    pats = build_mtf_patterns(chart_dict, train_df, bar_size=bar_size)
    if not pats:
        return [], {}
    learned = learn_patterns(pats, min_n=min_n, max_p=0.02, min_edge=0.52,
                             amplify_short={"NQ": 0.38, "ES": 0.42, "GC": 0.48}.get(ticker, 0.40))
    personas = generate_trader_personas_from_learned(learned, ticker, chart_snap)
    if verbose:
        l_count = sum(1 for p in personas if p.pattern_direction == "LONG")
        s_count = sum(1 for p in personas if p.pattern_direction == "SHORT")
        print(f"  {ticker} {bar_size}: {len(learned)} patterns → {len(personas)} personas ({l_count}L/{s_count}S)")
    return personas, learned


# ====================================================================
# MTF BACKTEST
# ====================================================================

@dataclass
class MTFTrade:
    date: str
    direction: str
    entry_price: float
    exit_price: float
    gross_points: float
    net_points: float
    exit_reason: str


@dataclass
class MTFResult:
    ticker: str
    bar_size: str
    train_period: str
    test_period: str
    n_trades: int
    win_rate: float
    gross_wins: float
    gross_losses: float
    profit_factor: float
    total_points: float
    total_dollars: float


@dataclass
class BatchMTFResult:
    as_of: datetime
    ticker: str
    results: list[MTFResult]


def mtf_backtest(ticker, bar_size="1h", start="2018-01-01", end=None, train_ratio=0.7,
                 min_wr=0.50, min_pf=1.0, min_n=12, verbose=True):
    """Run MTF persona backtest."""
    inst = INSTRUMENTS.get(ticker)
    if not inst:
        return None
    point_values = {"NQ": 20.0, "ES": 50.0, "GC": 100.0}
    point_value = point_values.get(ticker, 1.0)
    df = load_mtf_data(ticker, bar_size=bar_size, start=start, end=end)
    if df.empty:
        # Try CSV
        df = load_csv_data(ticker, bar_size=bar_size)
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        if verbose:
            print(f"  No {bar_size} data for {ticker}")
        return None
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    n = len(df)
    train_end = int(n * train_ratio)
    train_df = df.iloc[:train_end]
    personas, learned = generate_mtf_personas(ticker, df, bar_size=bar_size,
                                               train_ratio=train_ratio, min_n=min_n, verbose=verbose)
    if not personas:
        return None
    personas_dict = {p.persona_id: p for p in personas}
    rect = load_rectified().get(ticker)
    if not rect:
        rect = {"NQ": {"hour": 21, "min": 0, "sec": 0}}.get(ticker, {"hour": 12, "min": 0, "sec": 0})
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                      rect["hour"], rect["min"], rect.get("sec", 0))
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    test_start = df.index[train_end]
    test_df = df.iloc[train_end:]
    trades = []
    prev_state = None
    for i in range(len(test_df) - 5):
        timestamp = test_df.index[i]
        signal_utc = timestamp.to_pydatetime()
        try:
            st = get_state(chart_dict, signal_utc)
        except:
            continue
        cur = (st["main"], st["sub"], st["dist"], st["house"], st["moon_phase"])
        if cur == prev_state:
            continue
        prev_state = cur
        sk = state_key(st, 7)
        persona = personas_dict.get(sk)
        if not persona:
            for pid, p in personas_dict.items():
                if pid.startswith(f"{st['main']}_{st['sub']}_{st['dist']}_"):
                    persona = p; break
        if not persona:
            hs = f"_H{st['house']}_"; mp = f"_{st['moon_phase']}_"
            for pid, p in personas_dict.items():
                if hs in pid and mp in pid:
                    persona = p; break
        if not persona:
            for pid, p in personas_dict.items():
                if pid.startswith(f"{st['main']}_"):
                    persona = p; break
        if not persona:
            continue
        if persona.historical_win_rate < min_wr or persona.historical_pf < min_pf:
            continue
        entry_idx = i + 1
        exit_idx = min(i + persona.max_hold_days + 1, len(test_df) - 1)
        if exit_idx <= entry_idx:
            continue
        entry_price = test_df.iloc[entry_idx]["open"]
        exit_price = test_df.iloc[exit_idx]["close"]
        if entry_price <= 0:
            continue
        direction = persona.pattern_direction
        if direction == "LONG":
            gross = exit_price - entry_price
        else:
            gross = entry_price - exit_price
        net = gross - 0.5
        trades.append(MTFTrade(
            date=test_df.index[entry_idx].strftime("%Y-%m-%d"),
            direction=direction, entry_price=entry_price, exit_price=exit_price,
            gross_points=gross, net_points=net, exit_reason="time_exit",
        ))
    if not trades:
        return None
    n_trades = len(trades)
    wins = [t for t in trades if t.gross_points > 0]
    losses = [t for t in trades if t.gross_points <= 0]
    win_rate = len(wins) / n_trades
    gross_wins = sum(t.net_points for t in wins)
    if losses:
        gross_losses = abs(sum(t.net_points for t in losses))
        profit_factor = gross_wins / gross_losses
    else:
        profit_factor = min(10.0, gross_wins) if gross_wins > 0 else 0.0
    total_points = sum(t.gross_points for t in trades)
    total_dollars = sum(t.net_points for t in trades)
    return MTFResult(
        ticker=ticker, bar_size=bar_size,
        train_period=f"{test_start.strftime('%Y-%m-%d')}",
        test_period=f"{test_df.index[-1].strftime('%Y-%m-%d')}",
        n_trades=n_trades, win_rate=win_rate, profit_factor=profit_factor,
        total_points=total_points, total_dollars=total_dollars,
        trades=trades,
    )


# ====================================================================
# MTF LIVE SIGNAL GENERATION
# ====================================================================

def generate_mtf_live_signal(
    ticker: str = "NQ",
    bar_size: str = "1h",
    min_wr: float = 0.50,
    min_pf: float = 1.0,
    min_n: int = 12,
    lookback_days: int = 365,
) -> dict | None:
    """Generate today's live MTF signal."""
    inst = INSTRUMENTS.get(ticker)
    if not inst:
        return None
    # Prefer local CSV (full history, no Yahoo 730-day intraday limit),
    # then fall back to Yahoo daily if CSV unavailable for this bar size.
    try:
        df = load_csv_data(ticker, bar_size)
        if df is None or df.empty:
            end_dt = datetime.now().strftime("%Y-%m-%d")
            start_dt = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            df = load_mtf_data(ticker, bar_size=bar_size, start=start_dt, end=end_dt)
        if df is None or df.empty:
            return None
    except Exception:
        return None
    try:
        personas, learned = generate_mtf_personas(
            ticker, df, bar_size=bar_size, train_ratio=0.7,
            min_wr=min_wr, min_pf=min_pf, min_n=min_n, verbose=False,
        )
    except:
        return None
    if not personas:
        return None
    personas_dict = {p.persona_id: p for p in personas}
    rect = load_rectified().get(ticker)
    if not rect:
        return None
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                      rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    today = datetime.now()
    signal_utc = today.replace(hour=17)
    try:
        st = get_state(chart_dict, signal_utc)
    except:
        return None
    persona = None
    sk_exact = state_key(st, 7)
    if sk_exact in personas_dict:
        persona = personas_dict[sk_exact]; match_type = "exact"
    if not persona:
        prefix = f"{st['main']}_{st['sub']}_{st['dist']}_"
        candidates = [(pid, p) for pid, p in personas_dict.items() if pid.startswith(prefix)]
        if candidates:
            import math
            persona = max(candidates, key=lambda x: min(x[1].historical_pf, 20) * math.log(max(x[1].n_samples, 2)))[1]
            match_type = "prefix"
    if not persona:
        candidates = [(pid, p) for pid, p in personas_dict.items()
                      if pid.startswith(st['main']) and f"_{st['moon_phase']}_" in pid]
        if candidates:
            import math
            persona = max(candidates, key=lambda x: min(x[1].historical_pf, 20) * math.log(max(x[1].n_samples, 2)))[1]
            match_type = "main+moon"
    if not persona:
        return None
    if persona.historical_win_rate < min_wr:
        return None
    if persona.historical_pf < min_pf:
        return None
    if ticker in ("GC", "NQ", "ES") and persona.pattern_direction == "SHORT":
        return None

    # NQ trend gate: refuse LONG when close < 200-day MA (saves NQ in bear markets).
    if ticker == "NQ" and persona.pattern_direction == "LONG":
        try:
            dcl = df['close']
            if len(dcl) >= 200:
                ma200 = float(dcl.iloc[-200:].mean())
                if float(dcl.iloc[-1]) < ma200:
                    return None
        except Exception:
            pass

    pf_val = max(0.5, persona.historical_pf)
    tp_mult = min(6.0, max(1.2, 1.5 + math.log(pf_val + 0.5)))
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
        "persona_id": persona.persona_id[:40],
        "risk_tolerance": persona.risk_tolerance,
        "pf": round(persona.historical_pf, 2),
        "wr": f"{persona.historical_win_rate:.0%}",
        "n_samples": persona.n_samples,
        "timeframe": bar_size,
        "match_type": match_type,
    }


def batch_mtf_backtest(ticker, bar_sizes=None, start="2018-01-01", end=None,
                       train_ratio=0.7, min_wr=0.50, min_pf=1.0, min_n=12, verbose=True):
    """Run MTF backtest across multiple bar sizes."""
    if bar_sizes is None:
        bar_sizes = ["1h", "4h"]
    results = []
    for bs in bar_sizes:
        result = mtf_backtest(ticker, bar_size=bs, start=start, end=end,
                              train_ratio=train_ratio, min_wr=min_wr, min_pf=min_pf,
                              min_n=min_n, verbose=verbose)
        if result:
            results.append(result)
            if verbose:
                print(f"  ✓ {result.n_trades} trades | WR={result.win_rate:.1%} | PF={result.profit_factor:.2f} | ${result.total_dollars:,.0f}")
    return BatchMTFResult(
        as_of=datetime.now(), ticker=ticker, results=results,
    )


if __name__ == "__main__":
    print("MTF Backtest — Multi-Timeframe Persona Signals")
    for t in ["NQ"]:
        for bs in ["1h", "4h"]:
            result = mtf_backtest(t, bar_size=bs, start="2023-01-01", min_n=8, verbose=False)
            if result:
                print(f"  {t} {bs}: {result.n_trades}t WR={result.win_rate:.1%} PF={result.profit_factor:.2f}")
    for t in ["NQ"]:
        sig = generate_mtf_live_signal(t, bar_size="1h", min_n=8)
        if sig:
            print(f"  Live {t}: {sig['direction']} PF={sig['pf']} WR={sig['wr']}")
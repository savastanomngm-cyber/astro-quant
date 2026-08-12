#!/usr/bin/env python3
"""
ASTRO MULTI-TIMEFRAME — Lower Timeframe Trading Pipeline
===========================================================
Enables astro persona trading on any bar size: 1m, 5m, 15m, 30m, 60m, 240m, Daily.

DATA SOURCES:
  Priority 1 — Local CSV (TheSnowGuru repo format, GMT timestamps)
  Priority 2 — Yahoo Finance (1m limited to 7d, 1H to 730d)

THE KEY INSIGHT:
  The astro state (fidaria, distributor, house, moon phase) changes once per day.
  Lower timeframes reuse the same daily astro state but generate multiple 
  entry signals based on the persona's entry timing + intraday price patterns.

  A 7-day fidaria period on daily bars = 1 trade.
  Same 7-day period on 15min bars = 20+ trades from the same persona.

USAGE:
  from astro_mtf import load_mtf_data, mtf_backtest
  result = mtf_backtest("NQ", bar_size="15m", start="2023-01-01")
"""

from __future__ import annotations
import csv
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))

from astro_core_v2 import calculate_chart
from pattern_engine_v3 import (
    load_rectified, get_state, state_key,
    build_patterns as bp, learn_patterns as lp,
)
from astro_personas import generate_trader_personas_from_learned
from astro_matraix_backtest import (
    chart_to_snapshot, INSTRUMENTS,
    _entry_timing, _timeframe_for_persona, _execution_note,
)

# ====================================================================
# CONFIG — TheSnowGuru local paths
# ====================================================================

SNOWGURU_PATHS = {
    "NQ": [
        "~/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data/indices/nasdaq100",
        "~/Desktop/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data/indices/nasdaq100",
    ],
    "ES": [
        "~/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data/indices/s&p500",
        "~/Desktop/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data/indices/s&p500",
    ],
    "GC": [
        "~/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data/commodities/gold",
        "~/Desktop/fifa/Stocks-Futures-Financial-Time-series-Tick-Bar-Data/commodities/gold",
    ],
}

YF_MAP = {"NQ": "NQ=F", "ES": "ES=F", "GC": "GC=F"}

BAR_SIZE_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "60m", "60m": "60m", "4h": "240m", "240m": "240m",
    "d": "Daily", "daily": "Daily",
}


# ====================================================================
# DATA LOADER
# ====================================================================

def _find_snowguru_dir(ticker: str) -> Optional[str]:
    """Find the local TheSnowGuru data directory for a ticker."""
    for base in SNOWGURU_PATHS.get(ticker, []):
        expanded = os.path.expanduser(base)
        if os.path.isdir(expanded):
            return expanded
    return None


def _parse_snowguru_csv(filepath: str) -> pd.DataFrame:
    """
    Parse TheSnowGuru CSV. Auto-detects format from data.
    """
    # Read raw first line to check structure
    with open(filepath) as f:
        raw = f.readline().strip()
    
    # Count commas vs spaces to determine separator
    commas = raw.count(',')
    spaces = len(raw.split()) - 1
    
    if commas >= 5:
        sep = ','
    elif spaces >= 5:
        sep = r'\s+'
    else:
        sep = r'\s+'
    
    df_raw = pd.read_csv(filepath, header=None, sep=sep, engine="python")
    first_cell = str(df_raw.iloc[0, 0]).strip()
    
    # Is first cell a datetime? If not, skip row 0 as header
    has_header = not (first_cell[0].isdigit() and len(first_cell) >= 10)
    
    if has_header:
        df_raw = pd.read_csv(filepath, header=None, sep=sep, engine="python", skiprows=1)
    
    ncols = df_raw.shape[1]
    
    if ncols >= 7:
        # Format: date time O H L C V [extra...]
        df_raw.columns = ["date", "time", "open", "high", "low", "close", "volume"][:ncols]
    elif ncols == 6:
        # Format: datetime_str O H L C V (date+time combined)
        df_raw.columns = ["dt", "open", "high", "low", "close", "volume"]
        ts_parts = df_raw["dt"].astype(str).str.split(n=1, expand=True)
        df_raw["date"] = ts_parts[0]; df_raw["time"] = ts_parts[1].fillna("00:00:00")
    elif ncols == 2:
        # Format: timestamp, OHLCV (2 cols, OHLCV is one string)
        # Not handled — fall back
        pass
    else:
        raise ValueError(f"Unexpected {ncols} columns in {filepath}. First row: {raw[:100]}")
    
    # Validate: first date value looks like YYYY-MM-DD
    first_date = str(df_raw["date"].iloc[0]).strip()
    if not (first_date[0].isdigit() and len(first_date) >= 8):
        # Might have Date header as row 0, already skipped. Try one more skip.
        df_raw = pd.read_csv(filepath, header=None, sep=sep, engine="python", skiprows=2)
        if ncols >= 7:
            df_raw.columns = ["date", "time", "open", "high", "low", "close", "volume"][:ncols]
    
    # Build timestamp
    date_str = df_raw["date"].astype(str).str.strip()
    time_str = df_raw["time"].astype(str).str.strip() if "time" in df_raw.columns else pd.Series(["00:00:00"]*len(df_raw))
    df_raw["timestamp"] = pd.to_datetime(date_str + " " + time_str, utc=True, format="mixed")
    df_raw = df_raw.set_index("timestamp").sort_index()
    
    # Keep OHLCV only
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df_raw.columns:
            df_raw[col] = 0.0
    df_raw = df_raw[["open", "high", "low", "close", "volume"]]
    for col in df_raw.columns:
        df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")
    
    return df_raw.dropna()


def load_mtf_data(
    ticker: str,
    bar_size: str = "15m",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load multi-timeframe OHLCV data.
    
    Priority:
      1. Local TheSnowGuru CSV directory
      2. Yahoo Finance (limited range)
    
    Args:
        ticker: "NQ", "ES", "GC"
        bar_size: "1m", "5m", "15m", "30m", "1h", "4h", "daily"
        start/end: "YYYY-MM-DD" filter
    
    Returns DataFrame with columns [open, high, low, close, volume]
    """
    bs = BAR_SIZE_MAP.get(bar_size, bar_size)
    
    # Try local TheSnowGuru data first
    sg_dir = _find_snowguru_dir(ticker)
    if sg_dir:
        # Match correct bar size file
        import glob
        # TheSnowGuru filenames contain the timeframe
        bar_patterns = []
        if bs == "Daily":
            bar_patterns = ["*Daily*.csv", "*daily*.csv", "*day*.csv", "*1d*.csv"]
        elif bs == "240m":
            bar_patterns = ["*240m*.csv", "*4h*.csv", "*4H*.csv"]
        elif bs == "60m":
            bar_patterns = ["*60m*.csv", "*1h*.csv", "*1H*.csv"]
        elif bs == "15m":
            bar_patterns = ["*15m*.csv", "*15min*.csv"]
        elif bs == "5m":
            bar_patterns = ["*5m*.csv", "*5min*.csv"]
        else:
            bar_patterns = [f"*{bs}*.csv"]
        
        for bp in bar_patterns:
            files = sorted(glob.glob(os.path.join(sg_dir, bp)))
            if files:
                df = _parse_snowguru_csv(files[0])
                if start:
                    df = df[df.index >= start]
                if end:
                    df = df[df.index <= end]
                if not df.empty:
                    print(f"  Loaded {len(df)} {bs} bars from {files[0]}")
                    return df
        
        # Fallback: try ANY csv in the directory
        files = sorted(glob.glob(os.path.join(sg_dir, "*.csv")))
        if files:
            df = _parse_snowguru_csv(files[0])
            if start: df = df[df.index >= start]
            if end: df = df[df.index <= end]
            if not df.empty:
                print(f"  Loaded {len(df)} bars from {files[0]} (no timeframe match)")
                return df
    
    # Fallback: Yahoo Finance
    yf_map_interval = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "60m": "60m", "240m": "60m",  # Yahoo: 60m max, resample to 4H
        "Daily": "1d",
    }
    yf_interval = yf_map_interval.get(bs, "1d")
    yf_symbol = YF_MAP.get(ticker, f"{ticker}=F")
    
    import yfinance as yf
    # Yahoo limits: 1m=7d, 5m/15m/30m=60d, 1h=730d
    periods = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "60m": "730d"}
    period = periods.get(yf_interval, "max")
    
    data = yf.download(yf_symbol, period=period, interval=yf_interval, progress=False, auto_adjust=True)
    if data.empty:
        raise ValueError(f"No Yahoo data for {yf_symbol} at {yf_interval}")
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    
    df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df["amount"] = df["close"] * df["volume"]
    
    # Resample if needed (Yahoo only has 60m, not 240m)
    if bs == "240m" and yf_interval == "60m":
        df = df.resample("4h").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna()
        if "amount" in df.columns:
            df["amount"] = df["close"] * df["volume"]
    
    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]
    
    print(f"  Loaded {len(df)} {bs} bars from Yahoo for {ticker}")
    return df


# ====================================================================
# MULTI-TIMEFRAME PATTERN BUILDER
# ====================================================================

def build_mtf_patterns(
    ticker: str,
    df: pd.DataFrame,
    chart_dict: dict,
    horizon_bars: list[int] = None,
    min_samples_per_state: int = 5,
    use_perpetual_day: bool = True,
) -> dict:
    """
    Build patterns from multi-timeframe data.
    
    The key insight: astro state changes once per day at 17:00 UTC.
    All bars within that day share the same state.
    Each bar generates a return over `horizon_bars` forward bars.
    
    Args:
        ticker: "NQ", "ES", "GC"
        df: OHLCV DataFrame with DatetimeIndex
        chart_dict: natal chart
        horizon_bars: [5, 10, 20, 40] for 15m = 1.25h, 2.5h, 5h, 10h
        min_samples_per_state: minimum bars in a state period
        use_perpetual_day: compute state once per UTC day, reuse for all bars
    
    Returns:
        dict mapping state_key → [{return, date, bar_time}]
    """
    if horizon_bars is None:
        # Default: adapt to bar size
        # For 15m bars: 5=1.25h, 10=2.5h, 20=5h, 40=10h
        horizon_bars = [5, 10, 20, 40]
    
    pats = defaultdict(list)
    
    # Track the current astro state per UTC day
    state_cache = {}
    n = len(df)
    
    for i in range(n - max(horizon_bars) - 1):
        bar_time = df.index[i]
        
        # Compute astro state for this bar's UTC day at 17:00
        if use_perpetual_day:
            day_key = bar_time.strftime("%Y-%m-%d")
            if day_key not in state_cache:
                signal_utc = datetime(bar_time.year, bar_time.month, bar_time.day, 17, 0)
                try:
                    st = get_state(chart_dict, signal_utc)
                    state_cache[day_key] = st
                except Exception:
                    continue
            st = state_cache[day_key]
        else:
            try:
                st = get_state(chart_dict, bar_time)
            except Exception:
                continue
        
        entry_open = float(df.iloc[i]["open"])
        
        for hb in horizon_bars:
            exit_idx = i + hb
            if exit_idx >= n:
                continue
            
            # Stay within same UTC day? Option for intraday patterns
            exit_time = df.index[exit_idx]
            same_day = bar_time.date() == exit_time.date()
            
            exit_close = float(df.iloc[exit_idx]["close"])
            r = exit_close / entry_open - 1.0
            
            sk = state_key(st, hb)
            pats[sk].append({
                "return": r,
                "date": bar_time.strftime("%Y-%m-%d"),
                "bar_time": bar_time.strftime("%Y-%m-%d %H:%M"),
                "same_day": same_day,
            })
    
    return dict(pats)


# ====================================================================
# MULTI-TIMEFRAME PERSONA GENERATOR
# ====================================================================

def generate_mtf_personas(
    ticker: str,
    df: pd.DataFrame,
    bar_size: str = "15m",
    train_ratio: float = 0.6,
    min_wr: float = 0.50,
    min_pf: float = 1.0,
    min_n: int = 20,
    verbose: bool = True,
) -> tuple:
    """
    Full multi-timeframe persona pipeline.
    
    Returns:
        (personas, learned_patterns)
    """
    inst = INSTRUMENTS.get(ticker)
    if not inst:
        if verbose: print(f"  Unknown ticker: {ticker}")
        return [], {}
    
    rect = load_rectified().get(ticker)
    if not rect:
        if verbose: print(f"  No rectified time for {ticker}")
        return [], {}
    
    # Build chart
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                      rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    chart_snap = chart_to_snapshot(
        ticker=ticker, chart_dict=chart_dict,
        birth_utc=utc_dt, tz_offset=inst.birth_tz,
        lat=inst.birth_lat, lon=inst.birth_lon,
    )
    
    # Build patterns
    bs = BAR_SIZE_MAP.get(bar_size, bar_size)
    if bs in ("15m", "5m"):
        hz = [5, 10, 20, 40]
    elif bs in ("60m", "240m"):
        hz = [3, 5, 10, 20]
    else:
        hz = [1, 3, 5, 7]
    
    if verbose:
        print(f"  Building patterns on {len(df)} {bs} bars, horizons={hz}...")
    
    pats = build_mtf_patterns(ticker, df, chart_dict, horizon_bars=hz)
    
    # Train/test split by date
    all_dates = sorted(set(
        p["date"] for samples in pats.values() for p in samples
    ))
    n_train_dates = int(len(all_dates) * train_ratio)
    train_cutoff = all_dates[n_train_dates] if n_train_dates < len(all_dates) else all_dates[-1]
    
    train_pats = {
        k: [s for s in v if s["date"] < train_cutoff]
        for k, v in pats.items()
    }
    train_pats = {k: v for k, v in train_pats.items() if len(v) >= min_n}
    
    if verbose:
        print(f"  {len(train_pats)} trainable state keys (≥{min_n} samples)")
    
    learned = lp(train_pats, min_n=min_n, max_p=0.05, min_edge=0.52)
    
    if verbose:
        print(f"  {len(learned)} valid patterns after filtering")
    
    personalities = generate_trader_personas_from_learned(learned, ticker, chart_snap)
    
    return personalities, learned


# ====================================================================
# MULTI-TIMEFRAME BACKTEST
# ====================================================================

@dataclass
class MTFTrade:
    date: str
    bar_time: str
    direction: str
    entry_price: float
    exit_price: float
    gross_points: float
    net_points: float
    exit_reason: str
    persona_id: str
    horizon_bars: int
    bar_size: str


@dataclass
class MTFResult:
    ticker: str
    bar_size: str
    train_period: str
    test_period: str
    n_trades: int
    win_rate: float
    profit_factor: float
    total_points: float
    total_dollars: float
    trades: list = field(default_factory=list)


def mtf_backtest(
    ticker: str = "NQ",
    bar_size: str = "15m",
    start: str = "2023-01-01",
    end: str = "2026-08-01",
    train_ratio: float = 0.6,
    min_wr: float = 0.50,
    min_pf: float = 1.0,
    min_n: int = 20,
    point_value: float = None,
    verbose: bool = True,
) -> MTFResult:
    """
    Run a full multi-timeframe persona backtest.
    
    Example:
        result = mtf_backtest("NQ", bar_size="15m", start="2023-01-01")
        print(f"PF={result.profit_factor:.2f}, WR={result.win_rate:.1%}")
    """
    # Point values
    if point_value is None:
        point_value = {"NQ": 20.0, "ES": 50.0, "GC": 100.0}.get(ticker, 1.0)
    
    # Load data
    if verbose:
        print(f"  Loading {bar_size} data for {ticker}...")
    df = load_mtf_data(ticker, bar_size=bar_size, start=start, end=end)
    
    if len(df) < 100:
        if verbose:
            print(f"  Not enough data ({len(df)} bars)")
        return MTFResult(ticker=ticker, bar_size=bar_size, train_period="", test_period="",
                         n_trades=0, win_rate=0, profit_factor=0, total_points=0, total_dollars=0)
    
    # Generate personas
    personalities, learned = generate_mtf_personas(
        ticker, df, bar_size=bar_size,
        train_ratio=train_ratio, min_wr=min_wr, min_pf=min_pf, min_n=min_n,
        verbose=verbose,
    )
    
    if not personalities:
        return MTFResult(ticker=ticker, bar_size=bar_size, train_period="", test_period="",
                         n_trades=0, win_rate=0, profit_factor=0, total_points=0, total_dollars=0)
    
    personas_dict = {p.persona_id: p for p in personalities}
    
    # Simulate trading on test period
    n_dates = len(set(df.index.strftime("%Y-%m-%d")))
    n_train_dates = int(n_dates * train_ratio)
    all_dates = sorted(set(df.index.strftime("%Y-%m-%d")))
    train_end_date = all_dates[n_train_dates] if n_train_dates < len(all_dates) else all_dates[-1]
    
    trades = []
    state_cache = {}
    last_idx = 0
    
    # Needs chart for state computation
    inst = INSTRUMENTS.get(ticker)
    rect = load_rectified().get(ticker)
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                      rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz,
    )
    
    for i in range(len(df) - 20):
        if i < last_idx:
            continue
        
        bar_time = df.index[i]
        bar_date = bar_time.strftime("%Y-%m-%d")
        
        if bar_date < train_end_date:
            continue
        
        # Compute state for this bar
        signal_utc = datetime(bar_time.year, bar_time.month, bar_time.day, 17, 0)
        if bar_date not in state_cache:
            try:
                st = get_state(chart_dict, signal_utc)
                state_cache[bar_date] = st
            except Exception:
                continue
        st = state_cache[bar_date]
        
        # Match persona
        matched = None
        for hb in [5, 10, 20, 40]:
            sk = state_key(st, hb)
            if sk in personas_dict:
                p = personas_dict[sk]
                if p.historical_win_rate >= min_wr and p.historical_pf >= min_pf:
                    matched = (p, hb)
                    break
        
        if matched is None:
            continue
        
        persona, hb = matched
        entry_price = float(df.iloc[i]["open"])
        
        # Compute exit
        exit_idx = i + hb
        if exit_idx >= len(df):
            continue
        
        exit_price_close = float(df.iloc[exit_idx]["close"])
        exit_price_high = float(df.iloc[exit_idx]["high"])
        exit_price_low = float(df.iloc[exit_idx]["low"])
        
        direction = persona.pattern_direction
        stop_pct = persona.stop_tightness
        
        # Determine exit
        exit_reason = "time_exit"
        exit_price = exit_price_close
        net_points = exit_price - entry_price if direction == "LONG" else entry_price - exit_price
        
        # Check stop loss on path
        for j in range(i + 1, exit_idx + 1):
            low_j = float(df.iloc[j]["low"])
            high_j = float(df.iloc[j]["high"])
            
            if direction == "LONG":
                stop_price = entry_price * (1 - stop_pct)
                if low_j <= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                    net_points = stop_price - entry_price
                    break
            else:
                stop_price = entry_price * (1 + stop_pct)
                if high_j >= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                    net_points = entry_price - stop_price
                    break
        
        trades.append(MTFTrade(
            date=bar_date,
            bar_time=bar_time.strftime("%H:%M"),
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_points=net_points,
            net_points=net_points * point_value * 0.9985,  # 0.15% transaction cost
            exit_reason=exit_reason,
            persona_id=persona.persona_id,
            horizon_bars=hb,
            bar_size=bar_size,
        ))
        
        last_idx = exit_idx + 1
    
    # Compute stats
    n = len(trades)
    if n == 0:
        return MTFResult(ticker=ticker, bar_size=bar_size,
                         train_period=f"{start}→{train_end_date}",
                         test_period=f"{train_end_date}→{end}",
                         n_trades=0, win_rate=0, profit_factor=0,
                         total_points=0, total_dollars=0)
    
    wins = [t for t in trades if t.gross_points > 0]
    losses = [t for t in trades if t.gross_points <= 0]
    win_rate = len(wins) / n
    gross_wins = sum(t.net_points for t in wins)
    gross_losses = abs(sum(t.net_points for t in losses)) or 0.001
    profit_factor = gross_wins / gross_losses
    total_points = sum(t.gross_points for t in trades)
    total_dollars = sum(t.net_points for t in trades)
    
    return MTFResult(
        ticker=ticker, bar_size=bar_size,
        train_period=f"{start}→{train_end_date}",
        test_period=f"{train_end_date}→{end}",
        n_trades=n, win_rate=win_rate, profit_factor=profit_factor,
        total_points=total_points, total_dollars=total_dollars,
        trades=trades,
    )


# ====================================================================
# SELF-TEST
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(" ASTRO MULTI-TIMEFRAME — Self-Test")
    print("=" * 60)
    
    # Test with 15m Yahoo data (limited to 60 days)
    for ticker in ["NQ", "ES", "GC"]:
        print(f"\n  {ticker} (15m, 60d Yahoo limit)...")
        try:
            result = mtf_backtest(ticker, bar_size="15m", start="2026-06-01",
                                 train_ratio=0.6, min_n=5, verbose=True)
            if result.n_trades > 0:
                print(f"  ✓ {result.n_trades} trades | WR={result.win_rate:.1%} | PF={result.profit_factor:.2f} | ${result.total_dollars:,.0f}")
            else:
                print(f"  No trades generated")
        except Exception as e:
            print(f"  Error: {e}")
    
    # Test with daily bars for comparison
    print(f"\n  {'='*60}")
    print(f"  Daily bar comparison")
    for ticker in ["NQ"]:
        print(f"\n  {ticker} (daily, 2015-2026)...")
        try:
            result = mtf_backtest(ticker, bar_size="daily", start="2015-01-01",
                                 train_ratio=0.6, min_n=12, verbose=True)
            if result.n_trades > 0:
                print(f"  ✓ {result.n_trades} trades | WR={result.win_rate:.1%} | PF={result.profit_factor:.2f} | ${result.total_dollars:,.0f}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print(" SELF-TEST COMPLETE")
    print("=" * 60)
#!/usr/bin/env python3
"""
ASTRO MATRAIX KRONOS — Dual-Confirmation Signal Engine
=========================================================
Combines astro persona signals with Kronos foundation model predictions.

Architecture:
  1. Astro persona generates directional signal (LONG/SHORT)
  2. Kronos independently predicts next N bars of OHLCV
  3. When both agree → CONFIRMED (higher conviction)
  4. When they disagree → DIVERGES (signal filtered to FLAT)
  5. Kronos-only → Kronos generates a pure ML signal (fallback)

Kronos is a AAAI 2026 foundation model: 12B K-lines, 45+ exchanges,
decoder-only transformer with hierarchical tokenizer. The Kronos-small
model (24.7M params, 512 context) is fast enough for daily use.

Installation (run once on your machine):
    pip install torch pandas numpy huggingface_hub
    # Kronos model downloads from HuggingFace on first use

Usage:
    from astro_matraix_kronos import KronosConfirmer
    kc = KronosConfirmer()
    result = kc.confirm_signal("NQ", astro_signal)
    # → {"status": "CONFIRMED", "kronos_dir": "up", "kronos_pct": +1.2, ...}
"""

from __future__ import annotations
import math
import warnings
from datetime import datetime, timedelta
from typing import Optional, Literal

# Kronos will be imported lazily (user installs separately)
KRONOS_AVAILABLE = False
try:
    import torch
    KRONOS_AVAILABLE = True
except ImportError:
    pass


# ====================================================================
# KRONOS CONFIRMER
# ====================================================================

class KronosConfirmer:
    """
    Wraps Kronos model to confirm or reject astro persona signals.

    Model: Kronos-small (24.7M params) — fast, runs on CPU.
    Tokenizer: Kronos-Tokenizer-base — 20-bit BSQ, 1,024×2 subtokens.

    Download happens automatically from HuggingFace on first use.
    """

    def __init__(
        self,
        model_name: str = "NeoQuasar/Kronos-small",
        tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.tokenizer_name = tokenizer_name
        self.device = device
        self._model = None
        self._tokenizer = None
        self._predictor = None
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy-load Kronos from local clone or HuggingFace."""
        if self._loaded:
            return

        if not KRONOS_AVAILABLE:
            raise RuntimeError(
                "Kronos requires PyTorch. Install: pip install torch"
            )

        import os
        import sys

        # ---- FIND KRONOS REPO ----
        # Priority 1: PYTHONPATH or sys.path already contains it
        # Priority 2: ~/kronos (default clone location)
        # Priority 3: Check common locations
        kronos_repo = None
        search_dirs = [
            os.path.expanduser("~/kronos"),
            os.path.expanduser("~/Kronos"),
            os.path.expanduser("~/Desktop/fifa/kronos"),
            os.path.expanduser("~/Desktop/Fifa/kronos"),
            os.path.join(os.path.dirname(__file__), "..", "kronos"),
            os.path.join(os.path.dirname(__file__), "..", "Kronos"),
        ]
        for d in search_dirs:
            model_dir = os.path.join(d, "model")
            if os.path.isdir(model_dir) and os.path.exists(os.path.join(model_dir, "__init__.py")):
                kronos_repo = d
                break

        if kronos_repo is None:
            raise RuntimeError(
                f"Kronos repo not found. Searched: {search_dirs}\n"
                f"Clone it: git clone https://github.com/shiyu-coder/Kronos ~/kronos\n"
                f"Then: export PYTHONPATH=\"$HOME/kronos:$PYTHONPATH\""
            )

        # Add the repo to sys.path so 'from model import ...' works
        if kronos_repo not in sys.path:
            sys.path.insert(0, kronos_repo)

        # ---- IMPORT KRONOS MODULES ----
        try:
            from model import Kronos, KronosTokenizer, KronosPredictor
        except ImportError:
            # Alternative: try importing kronos package directly
            try:
                from kronos import KronosTokenizer, Kronos, KronosPredictor
            except ImportError:
                raise RuntimeError(
                    f"Found Kronos repo at {kronos_repo} but cannot import from model/\n"
                    f"Make sure you installed requirements: pip install -r ~/kronos/requirements.txt"
                )

        # ---- LOAD TOKENIZER + MODEL FROM HUGGINGFACE ----
        try:
            self._tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_name)
            self._model = Kronos.from_pretrained(self.model_name)
            self._model.to(self.device)
            self._model.eval()
            self._predictor = KronosPredictor(
                self._model, self._tokenizer, max_context=512
            )
            self._loaded = True
            print(f"  ✓ Kronos loaded: {self.model_name} on {self.device}")
        except Exception as e:
            raise RuntimeError(
                f"Kronos model download failed: {e}\n"
                f"Models auto-download from HuggingFace on first use.\n"
                f"Make sure you have internet access and disk space (~100MB)."
            )

    def predict(
        self,
        df,
        pred_len: int = 5,
        lookback: int = 400,
        temperature: float = 0.6,
        top_p: float = 0.9,
        sample_count: int = 5,
    ) -> dict | None:
        """
        Run Kronos prediction on OHLCV data.

        Args:
            df: DataFrame with [open, high, low, close, volume] columns
            pred_len: Number of bars to forecast
            lookback: Number of historical bars for context (max 512 for Kronos-small)
            temperature: Sampling temperature (0.6 optimal for price forecasting)
            top_p: Nucleus sampling threshold
            sample_count: Number of forecast paths (5-10 optimal)

        Returns:
            dict with predicted direction, magnitude, and raw forecast
        """
        self._ensure_loaded()

        import pandas as pd

        if len(df) < lookback:
            lookback = len(df) - pred_len
            if lookback < 50:
                return None

        x_df = df.iloc[-lookback:].copy()
        # Ensure required columns
        for col in ["open", "high", "low", "close"]:
            if col not in x_df.columns:
                return None
        if "volume" not in x_df.columns:
            x_df["volume"] = 0.0
        if "amount" not in x_df.columns:
            x_df["amount"] = 0.0

        # Generate timestamps from the actual DataFrame index
        # CRITICAL: Kronos predictor accesses .dt on timestamps.
        # Must use actual dates from the data, not pd.date_range.
        import pandas as pd

        # Ensure x_df has a proper DatetimeIndex
        if not isinstance(x_df.index, pd.DatetimeIndex):
            # Try to convert
            try:
                x_df.index = pd.to_datetime(x_df.index)
            except Exception:
                # Create a simple integer-based fallback
                x_df = x_df.reset_index(drop=True)

        if isinstance(x_df.index, pd.DatetimeIndex):
            x_timestamp = x_df.index
            last_dt = x_timestamp[-1]
            freq = pd.infer_freq(x_timestamp)
            if freq is None:
                freq = "D"
            y_timestamp = pd.date_range(
                start=last_dt + pd.Timedelta(days=1),
                periods=pred_len,
                freq=freq,
            )
        else:
            # Fallback: use integer index
            last_ts = pd.Timestamp.now()
            x_timestamp = pd.date_range(end=last_ts, periods=lookback, freq="D")
            y_timestamp = pd.date_range(
                start=last_ts + pd.Timedelta(days=1),
                periods=pred_len, freq="D",
            )

        # Ensure x_df has a plain RangeIndex (Kronos expects timestamps as separate Series)
        x_df_clean = x_df.reset_index(drop=True).copy()

        # CRITICAL FIX: Pandas 2.3+ removed .dt from DatetimeIndex.
        # Kronos internally does x_timestamp.dt.year etc., which only works on Series.
        # Convert both to pd.Series before passing.
        x_timestamp = pd.Series(x_timestamp)
        y_timestamp = pd.Series(y_timestamp)

        try:
            pred_df = self._predictor.predict(
                df=x_df_clean[["open", "high", "low", "close", "volume", "amount"]],
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=pred_len,
                T=temperature,
                top_p=top_p,
                sample_count=sample_count,
            )

            # Compute predicted direction using MEDIAN across sample paths (robust)
            current_close = float(x_df_clean["close"].iloc[-1])
            closes_over_path = [
                float(pred_df["close"].iloc[i]) for i in range(len(pred_df))
            ]
            import statistics
            predicted_close = statistics.median(closes_over_path)
            predicted_pct = (predicted_close / current_close - 1.0) * 100
            predicted_dir = "up" if predicted_pct > 0 else "down"

            # Outlier guard: if magnitude is absurd, flag unreliable
            if abs(predicted_pct) > 8.0:
                return {
                    "direction": predicted_dir,
                    "pct_change": round(predicted_pct, 2),
                    "confidence": round(min(confidence, 0.5), 2),
                    "pred_close": round(predicted_close, 2),
                    "current_close": round(current_close, 2),
                    "pred_len": pred_len,
                    "sample_count": sample_count,
                    "unreliable": True,
                }

            # Compute confidence from prediction path statistics
            up_bars = sum(1 for c in closes_over_path if c > current_close)
            confidence = up_bars / max(1, len(closes_over_path))

            return {
                "direction": predicted_dir,
                "pct_change": round(predicted_pct, 2),
                "confidence": round(confidence, 2),
                "pred_close": round(predicted_close, 2),
                "current_close": round(current_close, 2),
                "pred_len": pred_len,
                "sample_count": sample_count,
            }

        except Exception as e:
            warnings.warn(f"Kronos prediction failed: {e}")
            return None

    def confirm_signal(
        self,
        ticker: str,
        astro_signal: dict,
        df=None,
    ) -> dict:
        """
        Confirm or reject an astro persona signal using Kronos.

        Args:
            ticker: "NQ", "ES", "GC"
            astro_signal: output from generate_live_signals()
            df: Optional OHLCV DataFrame. If None, downloads from Yahoo.

        Returns:
            dict with status, kronos direction, and confirmation details
        """
        if df is None:
            df = self._load_yahoo_ohlcv(ticker)

        if df is None or len(df) < 50:
            return {
                "status": "NO_DATA",
                "kronos_dir": None,
                "reason": "Insufficient data for Kronos prediction",
            }

        hold_days = astro_signal.get("hold_days", 5)
        kronos_result = self.predict(df, pred_len=hold_days, lookback=min(400, len(df) - hold_days))

        if kronos_result is None:
            return {
                "status": "KRONOS_FAILED",
                "kronos_dir": None,
                "reason": "Kronos prediction failed",
            }

        astro_dir = astro_signal["direction"]
        kronos_dir = kronos_result["direction"]

        # If Kronos is unreliable (absurd magnitude), treat as neutral — don't override astro
        if kronos_result.get("unreliable"):
            return {
                "status": "UNRELIABLE",
                "kronos_dir": kronos_dir,
                "kronos_pct": kronos_result["pct_change"],
                "kronos_confidence": kronos_result["confidence"],
                "boosted_conviction": astro_signal.get("conviction", 0.5),
                "astro_dir": astro_dir,
                "astro_wr": astro_signal.get("wr", "?"),
                "astro_pf": astro_signal.get("pf", "?"),
            }

        # Determine agreement
        astro_up = astro_dir == "LONG"
        kronos_up = kronos_dir == "up"

        if astro_up == kronos_up:
            status = "CONFIRMED"
            # Amplify conviction: both systems agree
            boosted_conviction = astro_signal.get("conviction", 0.5) * 1.3
        else:
            status = "DIVERGES"
            boosted_conviction = 0.0  # models disagree — sit out

        return {
            "status": status,
            "kronos_dir": kronos_dir,
            "kronos_pct": kronos_result["pct_change"],
            "kronos_confidence": kronos_result["confidence"],
            "kronos_pred_close": kronos_result["pred_close"],
            "kronos_current_close": kronos_result["current_close"],
            "boosted_conviction": round(boosted_conviction, 2),
            "astro_dir": astro_dir,
            "astro_wr": astro_signal.get("wr", "?"),
            "astro_pf": astro_signal.get("pf", "?"),
        }

    def _load_yahoo_ohlcv(self, ticker: str, period: str = "2y"):
        """Download OHLCV data from Yahoo Finance for Kronos input."""
        try:
            import yfinance as yf
            yf_map = {"NQ": "NQ=F", "ES": "ES=F", "GC": "GC=F"}
            symbol = yf_map.get(ticker, f"{ticker}=F")
            data = yf.download(symbol, period=period, progress=False, auto_adjust=True)
            if data.empty:
                return None
            if isinstance(data.columns, yf.download.__class__):
                try:
                    data.columns = data.columns.get_level_values(0)
                except:
                    pass
            # Standardize columns
            df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            df["amount"] = df["close"] * df["volume"]
            return df
        except Exception:
            return None


# ====================================================================
# KRONOS VOLATILITY FILTER (replaces directional confirmation)
# ====================================================================

def kronos_volatility_adjustment(
    ticker: str = "NQ",
    lookback: int = 400,
    pred_len: int = 10,
) -> dict | None:
    """
    Use Kronos to forecast near-term volatility.
    
    Unlike directional confirmation (which didn't work well for US futures),
    Kronos's volatility forecasting beats GARCH by 9% (per AAAI paper).
    
    Returns a volatility multiplier to adjust stops and position sizes:
      - vol_mult > 1.0 → widen stops, reduce position
      - vol_mult < 1.0 → tighten stops, normal position
    """
    if not KRONOS_AVAILABLE:
        return None

    import pandas as pd
    import yfinance as yf

    yf_map = {"NQ": "NQ=F", "ES": "ES=F", "GC": "GC=F"}
    symbol = yf_map.get(ticker, f"{ticker}=F")
    data = yf.download(symbol, period="2y", progress=False, auto_adjust=True)
    if data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df["amount"] = df["close"] * df["volume"]

    if len(df) < lookback:
        return None

    x_df = df.iloc[-lookback:].reset_index(drop=True).copy()
    x_timestamp = pd.Series(df.index[-lookback:])
    
    last_dt = df.index[-1]
    y_timestamp = pd.Series(pd.date_range(
        start=last_dt + pd.Timedelta(days=1),
        periods=pred_len,
        freq=pd.infer_freq(df.index) or "D",
    ))

    try:
        kc = _get_cached_kronos()
        kronos_res = kc.predict(
            x_df, pred_len=pred_len, lookback=lookback,
            temperature=0.9, top_p=0.9, sample_count=3,
        )
        if kronos_res is None:
            return None

        # IMPORTANT: Kronos predict() returns a dict with pred_close = FINAL close.
        # But the predictor also returns the full DataFrame in 'pred_df'.
        # We need the full predicted path for volatility computation.
        # Re-run predict but capture the DataFrame directly.
        
        # Re-run to get the full prediction DataFrame
        x_timestamp = pd.Series(df.index[-lookback:])
        last_dt = df.index[-1]
        y_timestamp = pd.Series(pd.date_range(
            start=last_dt + pd.Timedelta(days=1),
            periods=pred_len,
            freq=pd.infer_freq(df.index) or "D",
        ))
        
        pred_df = kc._predictor.predict(
            df=x_df[["open", "high", "low", "close", "volume", "amount"]],
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=0.9,
            top_p=0.9,
            sample_count=3,
        )
        
        # Extract all predicted closes
        pred_closes = [float(df["close"].iloc[-1])]  # start with current
        for i in range(len(pred_df)):
            pred_closes.append(float(pred_df["close"].iloc[i]))
        
        # Compute returns along predicted path
        returns = []
        for i in range(1, len(pred_closes)):
            returns.append(pred_closes[i] / pred_closes[i-1] - 1.0)
        
        if len(returns) < 2:
            return None

        # Historical vol (last 60 bars)
        hist_returns = df["close"].pct_change().dropna().iloc[-60:]
        hist_vol = float(hist_returns.std())
        
        # Predicted vol
        pred_vol = float(pd.Series(returns).std())
        
        vol_mult = pred_vol / max(0.001, hist_vol)
        vol_mult = max(0.5, min(3.0, vol_mult))
        
        return {
            "hist_vol": round(hist_vol * 100, 2),
            "pred_vol": round(pred_vol * 100, 2),
            "vol_multiplier": round(vol_mult, 2),
            "recommendation": (
                f"↑ High vol expected → widen stops {vol_mult:.1f}x, reduce position" if vol_mult > 1.3
                else f"↓ Low vol expected → tighten stops, normal sizing" if vol_mult < 0.8
                else f"→ Normal vol — standard parameters"
            ),
        }
    except Exception as e:
        return None


# ====================================================================
# CACHED KRONOS LOADER (loads once, reuses)
# ====================================================================

_kronos_cache = None

def _get_cached_kronos():
    """Load Kronos once and cache it."""
    global _kronos_cache
    if _kronos_cache is None:
        _kronos_cache = KronosConfirmer()
        _kronos_cache._ensure_loaded()
    return _kronos_cache

def kronos_directional_backtest(
    ticker: str = "NQ",
    start_date: str = "2020-01-01",
    end_date: str = "2026-08-01",
    step_days: int = 5,
    lookback: int = 400,
    pred_len: int = 7,
    verbose: bool = True,
) -> dict:
    """
    Pure Kronos backtest — no astro component.
    Tests Kronos's standalone directional accuracy on historical data.

    For each prediction window:
      1. Look back `lookback` bars
      2. Kronos predicts next `pred_len` bars
      3. Compare predicted direction vs actual direction
      4. Slide window forward by `step_days`

    Returns accuracy stats comparable to persona backtest.
    """
    if not KRONOS_AVAILABLE:
        return {"error": "Kronos not installed. pip install torch"}

    import pandas as pd
    import yfinance as yf

    yf_map = {"NQ": "NQ=F", "ES": "ES=F", "GC": "GC=F"}
    symbol = yf_map.get(ticker, f"{ticker}=F")

    if verbose:
        print(f"  Loading {ticker} data ({start_date} → {end_date})...")
    data = yf.download(symbol, start=start_date, end=end_date, progress=False, auto_adjust=True)
    if data.empty:
        return {"error": f"No data for {symbol}"}
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df["amount"] = df["close"] * df["volume"]

    if verbose:
        print(f"  Loaded {len(df)} bars. Running Kronos predictions...")

    # Load Kronos once
    kc = KronosConfirmer()
    kc._ensure_loaded()

    predictions = []
    window_start = lookback

    while window_start + pred_len < len(df):
        window_df = df.iloc[window_start - lookback : window_start].copy()
        actual_future = df.iloc[window_start : window_start + pred_len]

        kronos_res = kc.predict(
            window_df,
            pred_len=pred_len,
            lookback=lookback,
            sample_count=3,
        )

        if kronos_res:
            # Actual direction
            actual_close_start = float(df.iloc[window_start]["close"])
            actual_close_end = float(actual_future.iloc[-1]["close"])
            actual_dir = "up" if actual_close_end > actual_close_start else "down"
            actual_pct = (actual_close_end / actual_close_start - 1.0) * 100

            predictions.append({
                "date": str(df.index[window_start].date()),
                "kronos_dir": kronos_res["direction"],
                "actual_dir": actual_dir,
                "correct": kronos_res["direction"] == actual_dir,
                "kronos_pct": kronos_res["pct_change"],
                "actual_pct": round(actual_pct, 2),
                "kronos_confidence": kronos_res["confidence"],
            })

        window_start += step_days

        if verbose and len(predictions) % 20 == 0:
            acc = sum(1 for p in predictions if p["correct"]) / max(1, len(predictions))
            print(f"    {len(predictions)} predictions | Accuracy: {acc:.1%}")

    if not predictions:
        return {"error": "No predictions generated"}

    n = len(predictions)
    correct = sum(1 for p in predictions if p["correct"])
    accuracy = correct / n

    # Subgroup by confidence
    high_conf = [p for p in predictions if p["kronos_confidence"] >= 0.6]
    low_conf = [p for p in predictions if p["kronos_confidence"] < 0.6]

    if verbose:
        print(f"\n  {'='*50}")
        print(f"  KRONOS DIRECTIONAL BACKTEST — {ticker}")
        print(f"  {'='*50}")
        print(f"  Total predictions: {n}")
        print(f"  Directional accuracy: {accuracy:.1%}")
        if high_conf:
            hc_acc = sum(1 for p in high_conf if p["correct"]) / len(high_conf)
            print(f"  High-confidence (≥60%): {len(high_conf)} preds | Acc: {hc_acc:.1%}")
        if low_conf:
            lc_acc = sum(1 for p in low_conf if p["correct"]) / len(low_conf)
            print(f"  Low-confidence (<60%): {len(low_conf)} preds | Acc: {lc_acc:.1%}")

    return {
        "ticker": ticker,
        "n_predictions": n,
        "directional_accuracy": round(accuracy, 4),
        "high_conf_accuracy": round(
            sum(1 for p in high_conf if p["correct"]) / max(1, len(high_conf)), 4
        ) if high_conf else None,
        "low_conf_accuracy": round(
            sum(1 for p in low_conf if p["correct"]) / max(1, len(low_conf)), 4
        ) if low_conf else None,
        "high_conf_count": len(high_conf),
        "predictions": predictions[:10],  # first 10 for display
    }


def dual_confirmation_backtest(
    ticker: str = "NQ",
    start_date: str = "2015-01-01",
    end_date: str = "2026-08-01",
    train_ratio: float = 0.6,
    min_wr: float = 0.50,
    min_pf: float = 1.0,
    use_kronos_confirmation: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Full dual-confirmation backtest: persona signal × Kronos confirmation.

    For each OOS date:
      1. Generate persona signal (astro)
      2. If use_kronos_confirmation: run Kronos prediction
      3. If both agree → trade. If disagree → skip.
      4. Track P&L with persona-derived SL/TP/hold

    Compares: persona-only vs persona+Kronos confirmation.
    """
    from astro_matraix_backtest import persona_backtest_flow, generate_live_signals

    if verbose:
        print(f"  Running persona backtest without Kronos...")
    persona_result = persona_backtest_flow(
        ticker=ticker,
        yahoo_start=start_date,
        train_ratio=train_ratio,
        min_win_rate=min_wr,
        min_pf=min_pf,
        use_short_signals=True,
        verbose=False,
    )

    if persona_result is None:
        return {"error": "Persona backtest failed"}

    if not use_kronos_confirmation or not KRONOS_AVAILABLE:
        return {
            "ticker": ticker,
            "persona_only": {
                "oos_pf": persona_result.out_of_sample.profit_factor,
                "oos_wr": persona_result.out_of_sample.win_rate,
                "oos_net": persona_result.out_of_sample.total_dollars,
                "n_trades": persona_result.out_of_sample.n_trades,
            },
            "kronos_confirmed": None,
            "note": "Kronos not available — persona-only results" if not KRONOS_AVAILABLE else "Kronos disabled",
        }

    if verbose:
        print(f"  Running dual-confirmation backtest...")

    # Load Kronos
    kc = KronosConfirmer()
    try:
        kc._ensure_loaded()
    except RuntimeError as e:
        return {
            "ticker": ticker,
            "persona_only": {
                "oos_pf": persona_result.out_of_sample.profit_factor,
                "oos_wr": persona_result.out_of_sample.win_rate,
                "oos_net": persona_result.out_of_sample.total_dollars,
                "n_trades": persona_result.out_of_sample.n_trades,
            },
            "kronos_confirmed": None,
            "note": f"Kronos load failed: {e}",
        }

    # For each OOS trade date, run Kronos confirmation
    import pandas as pd
    import yfinance as yf
    yf_map = {"NQ": "NQ=F", "ES": "ES=F", "GC": "GC=F"}
    symbol = yf_map.get(ticker, f"{ticker}=F")
    data = yf.download(symbol, start=start_date, end=end_date, progress=False, auto_adjust=True)
    if data.empty:
        return {"error": "No data"}

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df["amount"] = df["close"] * df["volume"]

    confirmed_trades = []
    rejected_count = 0

    for trade in persona_result.oos_trades:
        trade_date_str = trade.date
        trade_date = pd.Timestamp(trade_date_str)

        # Get data up to trade date
        pre_trade = df[df.index < trade_date]
        if len(pre_trade) < 100:
            rejected_count += 1
            continue

        # Build mock signal for Kronos confirmation
        mock_signal = {
            "direction": trade.direction,
            "hold_days": 5,
            "conviction": 0.5,
        }

        result = kc.confirm_signal(
            ticker=ticker,
            astro_signal=mock_signal,
            df=pre_trade,
        )

        if result["status"] == "CONFIRMED":
            confirmed_trades.append(trade)
        else:
            rejected_count += 1

    # Compute stats on confirmed-only trades
    from astro_matraix_backtest import compute_persona_trade_stats
    confirmed_stats = compute_persona_trade_stats(
        [{"net": t.net_points, "date": t.date, "dir": t.direction,
          "gross": t.gross_points} for t in confirmed_trades],
        point_value=20.0 if ticker == "NQ" else (50.0 if ticker == "ES" else 100.0),
    ) if confirmed_trades else None

    total_trades = len(persona_result.oos_trades)
    confirm_rate = len(confirmed_trades) / max(1, total_trades)

    if verbose:
        print(f"\n  {'='*50}")
        print(f"  DUAL-CONFIRMATION BACKTEST — {ticker}")
        print(f"  {'='*50}")
        print(f"  Persona-only: {total_trades} trades | WR={persona_result.out_of_sample.win_rate:.1%} | PF={persona_result.out_of_sample.profit_factor:.2f}")
        if confirmed_stats and confirmed_stats.n_trades > 0:
            print(f"  Kronos-confirmed: {confirmed_stats.n_trades} trades | WR={confirmed_stats.win_rate:.1%} | PF={confirmed_stats.profit_factor:.2f} | ${confirmed_stats.total_dollars:,.0f}")
            print(f"  Rejected by Kronos: {rejected_count} trades ({rejected_count/max(1,total_trades):.0%})")
            print(f"  Confirmation rate: {confirm_rate:.0%}")
            if confirmed_stats.profit_factor > persona_result.out_of_sample.profit_factor:
                print(f"  ✓ Kronos confirmation IMPROVES PF: {persona_result.out_of_sample.profit_factor:.2f} → {confirmed_stats.profit_factor:.2f}")
            else:
                print(f"  Kronos PF: {confirmed_stats.profit_factor:.2f} (persona: {persona_result.out_of_sample.profit_factor:.2f})")
        else:
            print(f"  Kronos-confirmed: 0 trades — all rejected")

    return {
        "ticker": ticker,
        "persona_only": {
            "oos_pf": persona_result.out_of_sample.profit_factor,
            "oos_wr": persona_result.out_of_sample.win_rate,
            "oos_net": persona_result.out_of_sample.total_dollars,
            "n_trades": total_trades,
        },
        "kronos_confirmed": {
            "oos_pf": confirmed_stats.profit_factor if confirmed_stats else 0,
            "oos_wr": confirmed_stats.win_rate if confirmed_stats else 0,
            "oos_net": confirmed_stats.total_dollars if confirmed_stats else 0,
            "n_trades": confirmed_stats.n_trades if confirmed_stats else 0,
        } if confirmed_stats and confirmed_stats.n_trades > 0 else None,
        "rejected_count": rejected_count,
        "confirmation_rate": round(confirm_rate, 4),
    }


# ====================================================================
# SELF-TEST (minimal — requires Kronos on user's machine)
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(" ASTRO MATRAIX KRONOS — Self-Test")
    print("=" * 60)

    if not KRONOS_AVAILABLE:
        print("\n  Kronos requires PyTorch. Install:")
        print("    pip install torch pandas numpy huggingface_hub")
        print("    git clone https://github.com/shiyu-coder/Kronos")
        print("    cd Kronos && pip install -r requirements.txt")
        print("\n  Then run this module again.")
    else:
        print(f"\n  PyTorch available: {torch.__version__}")
        print(f"  Attempting Kronos load...")
        try:
            kc = KronosConfirmer()
            kc._ensure_loaded()
            print(f"  ✓ Kronos loaded successfully")
            print(f"  Model: {kc.model_name}")
            print(f"  Tokenizer: {kc.tokenizer_name}")
        except Exception as e:
            print(f"  Kronos load failed: {e}")
            print(f"\n  To fix:")
            print(f"    1. git clone https://github.com/shiyu-coder/Kronos")
            print(f"    2. cd Kronos && pip install -r requirements.txt")
            print(f"    3. Models auto-download from HuggingFace on first use")

    print("\n" + "=" * 60)
#!/usr/bin/env python3
"""
SHORT-TERM REVERSAL OVERLAY — Renaissance-style
================================================
Per Simons: "~60% of big sudden price rises/drops snap back at least partially"
Checks if current price moved >2 std devs in last 3 days → mean-reversion signal.
Aligns with or warns against the astro signal.

Usage:
  from signals_meanrev import meanrev_signal
  result = meanrev_signal('NQ')
  # → {"signal": "LONG", "z_score": -2.7, "action": "CONFIRMS astro LONG"}
"""
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

def meanrev_signal(ticker: str, symbol: str = None, lookback: int = 20) -> dict | None:
    """Check if price is statistically extreme — due to revert."""
    sym = symbol or f"{ticker}=F"
    try:
        t = yf.Ticker(sym)
        data = t.history(period='2mo')
        if len(data) < lookback + 5: return None
    except:
        return None

    closes = data['Close'].values
    returns = np.diff(closes[-lookback:]) / closes[-lookback:-1]
    latest_return = (closes[-1] - closes[-4]) / closes[-4]  # 3-day return

    mu = np.mean(returns)
    sigma = np.std(returns)
    z = (latest_return - mu) / sigma if sigma > 0 else 0

    if abs(z) < 2.0:
        return {"signal": "NEUTRAL", "z_score": round(z, 2), "action": "no reversal signal"}

    # Negative z = big drop → expect bounce → LONG
    direction = "LONG" if z < -2.0 else "SHORT"
    return {
        "signal": direction, "z_score": round(z, 2),
        "action": f"Mean-reversion: {direction} (z={z:.1f}) — 3-day move is {latest_return:+.1%} vs avg {mu:+.1%}"
    }


if __name__ == "__main__":
    for ticker in ['NQ', 'ES', 'GC']:
        r = meanrev_signal(ticker)
        if r: print(f"{ticker}: {r['action']}")
        else: print(f"{ticker}: no data")
#!/usr/bin/env python3
"""
ASTRO-QUANT SIZING — Real-money position sizing
=================================================
Fixed-risk position sizing for futures micro/mini contracts.

Core principle: risk a fixed *dollar* per trade (1-2% of account), computed
from the stop distance and the contract's dollar-per-point multiplier.

  contracts = risk_budget / (stop_distance_pts * multiplier)

Also applies realistic caps:
  - Max stop = 2 * current ATR (measured on the daily series) — stops wider
    than ~2 ATR are noise/waste and/or unwritable for small accounts.
  - TP is a risk-multiple (default 2R), NOT the persona's unbounded 6x-log.
"""

import math

# Contract specs: multiplier = $ per index/futures point.
# micro = 1/10 of mini. (actual CME specs)
CONTRACT_SPECS = {
    # price_scale = typical price used for ATR% and "points to stop"
    "NQ": {"micro": {"mult": 2.0,  "name": "MNQ"},
           "mini":  {"mult": 20.0, "name": "NQ"}},
    "ES": {"micro": {"mult": 5.0,  "name": "MES"},
           "mini":  {"mult": 50.0, "name": "ES"}},
    "GC": {"micro": {"mult": 10.0, "name": "MGC"},
           "mini":  {"mult": 100.0,"name": "GC"}},
}

DEFAULT_RISK_PCT = 0.01       # 1% of account per trade
DEFAULT_ATR_MULT  = 1.5       # stop = 1.5 * ATR (1-2 ATR typical)
MAX_ATR_MULT     = 2.0        # hard cap on stop width
DEFAULT_R_RATIO  = 2.0        # TP = 2R


def atr_pct(closes, period=14, atr_mult=None):
    """Compute ATR as a fraction of price from a list of daily closes.

    Simplified TR approximation using close-to-close range; adequate for
    stop-sizing. Returns ATR as % of last close (e.g. 0.012 = 1.2%).
    """
    if not closes or len(closes) < 2:
        return 0.02  # fallback 2%
    closes = [float(c) for c in closes]
    n = min(period, len(closes) - 1)
    trs = [abs(closes[i] - closes[i-1]) for i in range(len(closes)-n, len(closes))]
    atr = sum(trs) / max(1, len(trs))
    price = closes[-1]
    return atr / price if price else 0.02


def compute_stop_tp(signal_pct: float, atr_pct: float, conv: float = 1.0,
                    atr_mult: float = None, rt_ratio: float = None):
    """Given the persona's raw stop% and current ATR, return sane SL/TP %'s.

    Returns (stop_pct, tp_pct) where:
      stop_pct = clamp(signal_pct, atr*0.5, atr*MAX_ATR_MULT)
      tp_pct   = stop_pct * rt_ratio   (default 2R)
    The persona stop is only *used if* it's tighter than the ATR cap AND not
    absurdly wide; otherwise we cap at atr*MAX_ATR_MULT.
    """
    atr_mult = atr_mult or DEFAULT_ATR_MULT
    rt_ratio = rt_ratio or DEFAULT_R_RATIO
    signal_pct = abs(float(signal_pct or 0))
    # ATR window this should sit in
    min_stop = signal_pct if 0 < signal_pct < atr_pct * MAX_ATR_MULT else atr_pct
    stop_pct = min(atr_pct * MAX_ATR_MULT, max(atr_pct * 0.5, min_stop))
    # Cap TP at a sane R-multiple; never the persona's unbounded log-mult
    tp_pct = stop_pct * rt_ratio
    return round(stop_pct, 4), round(tp_pct, 4)


def contracts_for(ticker: str, price: float, stop_pct: float, account: float,
                   risk_pct: float = None, unit: str = "mini"):
    """How many contracts (micro or mini) fit the risk budget."""
    risk_pct = risk_pct or DEFAULT_RISK_PCT
    spec = CONTRACT_SPECS.get(ticker)
    if not spec or not price:
        return 0, 0
    mult = spec[unit]["mult"]
    stop_pts = price * stop_pct
    risk_per_cont = stop_pts * mult
    budget = account * risk_pct
    n = budget / risk_per_cont if risk_per_cont > 0 else 0
    return max(0, int(math.floor(n))), risk_per_cont


def display_for(ticker, price, stop_pct, tp_pct, account):
    """Return a readable human sizing summary."""
    out = []
    for unit in ("micro", "mini"):
        n, rpc = contracts_for(ticker, price, stop_pct, account, unit=unit)
        name = CONTRACT_SPECS[ticker][unit]["name"]
        if n >= 1:
            out.append(f"{name} x{n} (~${rpc:,.0f} risk/unit)")
        else:
            out.append(f"{name}: won't fit 1% risk (${rpc:,.0f}/unit vs ${account*DEFAULT_RISK_PCT:,.0f})")
    return " | ".join(out)


if __name__ == "__main__":
    # quick self-test
    atr = atr_pct([100, 101, 99, 102, 100.5, 103, 104, 102], 14)
    print("ATR%%:", round(atr*100,2))
    s, t = compute_stop_tp(0.08, atr)
    print(f"stop {s:.2%} tp {t:.2%}")
    print(display_for("NQ", 20000, 0.02, 0.04, 25000))
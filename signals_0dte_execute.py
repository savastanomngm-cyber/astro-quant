#!/usr/bin/env python3
"""
0DTE OPTIONS EXECUTION MODULE — PAPER TRADING ONLY
===================================================
Builds a real 0DTE (zero days to expiry) option trade from an astro-quant daily
signal — AFTER the conservative gate in signals_0dte.py has said "GO".

Maps the swing signal to an intraday option:
  - Direction (LONG -> CALL, SHORT -> PUT)
  - Expiry = TODAY (0DTE)
  - Underlying: SPY for ES, QQQ for NQ, GLD for GC (yfinance option chain)
  - Strike: nearest strike with delta ~0.35-0.65
  - Premium: risk-capped to a small % of account

PAPER ONLY: computes the trade and prints it. Does NOT place orders.
"""

from __future__ import annotations
import math
import os
from datetime import datetime

import yfinance as yf

ZERO_DTE_UNDERLYING = {"NQ": "QQQ", "ES": "SPY", "GC": "GLD"}
MAX_PREMIUM_PCT = 0.005          # 0.5% of account max per 0DTE
TARGET_DELTA_LO, TARGET_DELTA_HI = 0.30, 0.65

_today = datetime.now()


def _fnum(x):
    """Safe float; NaN/None -> None."""
    if x is None:
        return None
    try:
        v = float(x)
        return v if not math.isnan(v) else None
    except (ValueError, TypeError):
        return None


def build_0dte(ticker: str, direction: str, account: float) -> dict:
    etf = ZERO_DTE_UNDERLYING.get(ticker)
    if not etf:
        return {"error": f"No 0DTE underlying for {ticker}"}
    is_call = direction.upper() == "LONG"

    try:
        tk = yf.Ticker(etf)
        hist = tk.history(period="5d")
        if hist.empty:
            return {"error": "no price data"}
        spot = float(hist["Close"].iloc[-1])
        chain = tk.option_chain(_today.strftime("%Y-%m-%d"))
        opts = chain.calls if is_call else chain.puts
    except Exception as e:
        return {"error": f"chain failed: {e}"}

    if opts is None or opts.empty:
        return {"error": "no option chain today"}

    # Candidate strikes in direction from spot
    if is_call:
        cand = opts[opts["strike"] >= spot]
        side, move = "CALL", +1
    else:
        cand = opts[opts["strike"] <= spot]
        side, move = "PUT", -1
    if cand.empty:
        cand = opts
    cand = cand.sort_values("strike")

    # Pick strike whose delta is in band, closest to 0.50
    best = None; best_delta = None
    for _, row in cand.iterrows():
        d = _fnum(row.get("delta"))
        if d is None:
            continue
        ad = abs(d)
        if TARGET_DELTA_LO <= ad <= TARGET_DELTA_HI:
            if best_delta is None or abs(ad - 0.5) < abs(best_delta - 0.5):
                best, best_delta = row, ad
    if best is None:
        # nearest money fallback
        idx = (cand["strike"] - spot).abs().argmin()
        best = cand.iloc[idx]
        best_delta = _fnum(best.get("delta")) or 0.5
        if not (0.1 <= best_delta <= 0.9):
            return {"error": f"no usable delta ({best_delta:.2f})"}

    strike = float(best["strike"])
    bid = _fnum(best.get("bid")) or _fnum(best.get("lastPrice")) or 0
    ask = _fnum(best.get("ask")) or 0
    mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else (_fnum(best.get("lastPrice")) or bid or 0)
    if mid <= 0:
        return {"error": "no premium on strike"}

    # Risk-capped premium budget
    premium_budget = account * MAX_PREMIUM_PCT
    c1 = premium_budget / (mid * 100.0)
    contracts = max(1, int(math.floor(c1)))
    debit = contracts * mid * 100.0

    theta = _fnum(best.get("theta")) or 0
    theta_loss = abs(theta) * 100 * contracts

    return {
        "underlying": etf,
        "option": f"{etf} {_today.strftime('%y%m%d')} {side} {strike:g}",
        "type": side,
        "strike": round(strike, 2),
        "spot": round(spot, 2),
        "mid_premium": round(mid, 2),
        "bid": round(bid, 2),
        "ask": round(ask, 2),
        "delta": round(best_delta, 3),
        "contracts": contracts,
        "debit_total": round(debit, 2),
        "max_loss": round(debit, 2),                    # 0DTE: whole premium
        "theta_loss_day": round(theta_loss, 2),
        "premium_pct_account": round(debit / account * 100, 2),
        "entry_rule": "enter 9:45-10:30 CT after direction confirms; exit by 3:30 CT",
        "paper_only": True,
    }


def print_0dte(ticker=None, direction=None, account=None):
    account = account or float(os.environ.get("ACCOUNT_SIZE", 25000))
    entry = build_0dte(ticker, direction or "LONG", account)
    if "error" in entry:
        print(f"  {ticker} 0DTE: {entry['error']}")
        return entry
    print("\n  ─── 0DTE PAPER TRADE ───")
    print(f"   {entry['option']}   | Δ {entry['delta']}")
    print(f"   premium ${entry['mid_premium']}  (bid {entry['bid']} / ask {entry['ask']})")
    print(f"   → {entry['contracts']} contract(s) | debit ${entry['debit_total']:,.0f} "
          f"= {entry['premium_pct_account']}% of acct")
    print(f"   max loss ${entry['max_loss']:,.0f} | theta/day ≈ ${entry['theta_loss_day']:,.0f}")
    print(f"   rule: {entry['entry_rule']}  [PAPER — not submitted]")
    return entry


if __name__ == "__main__":
    import sys
    tk = sys.argv[1].upper() if len(sys.argv) > 1 else "NQ"
    d = sys.argv[2].upper() if len(sys.argv) > 2 else "LONG"
    print_0dte(tk, d)
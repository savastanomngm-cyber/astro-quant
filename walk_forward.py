#!/usr/bin/env python3
"""
WALK-FORWARD TRAINER — Weekly retraining for live persona signals.
=============================================================
Retrains persona patterns and HMM params on rolling window,
archives old results, and produces a diff against prior.

Usage:
  python3 walk_forward.py                  # all tickers
  python3 walk_forward.py NQ               # single ticker
  python3 walk_forward.py --hmm-only       # HMM only, no persona retrain
"""

from __future__ import annotations
import json, os, sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

FUTURES = ["NQ", "ES", "GC"]
ETFS = ["ITA", "PPA", "SOXX", "BOTZ"]
MEMORY_DIR = os.path.expanduser("~/.astro-quant/walkforward")

def _ensure_dir():
    os.makedirs(MEMORY_DIR, exist_ok=True)

def train_one(ticker: str, retrain_hmm: bool = True) -> dict | None:
    from astro_matraix_backtest import persona_backtest_flow
    from astro_hmm import train_from_persona_trades, save_hmm_params

    print(f"  {ticker}...", end=" ", flush=True)
    try:
        r = persona_backtest_flow(ticker=ticker, verbose=False)
    except Exception as e:
        print(f"FAILED: {e}")
        return None
    if not r or not r.out_of_sample.n_trades:
        print("no trades")
        return None

    oos = r.out_of_sample
    print(f"PF={oos.profit_factor:.2f} WR={oos.win_rate:.1%} Sharpe={oos.sharpe} DD={oos.max_drawdown}% ${oos.total_dollars:,.0f} {oos.n_trades}t")

    if retrain_hmm:
        try:
            hmm = train_from_persona_trades(ticker, r, verbose=False)
            save_hmm_params(hmm, ticker)
        except: pass

    return {
        "ticker": ticker, "as_of": datetime.now().isoformat(),
        "oos_pf": round(oos.profit_factor, 2),
        "oos_wr": round(oos.win_rate, 3),
        "oos_sharpe": oos.sharpe,
        "oos_dd": oos.max_drawdown,
        "oos_pnl": round(oos.total_dollars, 0),
        "oos_trades": oos.n_trades,
        "patterns": getattr(r, 'patterns_valid', 0),
    }

def main():
    _ensure_dir()
    hmm_only = "--hmm-only" in sys.argv
    tickers = FUTURES + ETFS
    if len(sys.argv) >= 2 and sys.argv[1].upper() in ["NQ","ES","GC","ITA","PPA","SOXX","BOTZ"]:
        tickers = [sys.argv[1].upper()]

    print(f"{'─'*55}")
    print(f"  WALK-FORWARD RETRAIN{' (HMM only)' if hmm_only else ''}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'─'*55}")

    results = {}
    for t in tickers:
        results[t] = train_one(t, retrain_hmm=not hmm_only)

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(MEMORY_DIR, f"wf_{stamp}.json")
    valid = {k: v for k, v in results.items() if v}
    with open(path, "w") as f:
        json.dump(valid, f, indent=2)
    print(f"\n  Saved: {path}")

    # diff vs prior
    files = sorted(Path(MEMORY_DIR).glob("wf_*.json"))
    if len(files) >= 2:
        prev_path = files[-2]
        with open(prev_path) as f:
            prev = json.load(f)
        print(f"  Δ from {prev_path.name}:")
        for t in tickers:
            cur = valid.get(t, {})
            old = prev.get(t, {})
            if cur and old:
                pf_d = cur["oos_pf"] - old["oos_pf"]
                d = "▲" if pf_d > 0 else "▼" if pf_d < 0 else "─"
                print(f"    {t}: PF {old['oos_pf']:.2f}→{cur['oos_pf']:.2f} {d}{abs(pf_d):.2f} | DD {old['oos_dd']}%→{cur['oos_dd']}%")
            elif cur and not old:
                print(f"    {t}: NEW → PF={cur['oos_pf']:.2f}")
            elif old and not cur:
                print(f"    {t}: GONE (was PF={old['oos_pf']:.2f})")

if __name__ == "__main__":
    main()
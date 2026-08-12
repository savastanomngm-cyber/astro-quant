#!/usr/bin/env python3
"""
ASTRO-QUANT MASTER TRADE — One command, all you need.
======================================================
  python3 trade.py                    # today
  python3 trade.py 2024-03-15         # single date
  python3 trade.py 2024-03-15 2024-03-20  # date range
"""
import os, sys
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

TICKERS = ["NQ", "ES", "GC", "ITA", "PPA", "AIQ", "SHLD"]
E = lambda d: "🟢" if d == "LONG" else "🔴" if d == "SHORT" else "⚪"

def _sig(ticker, tf, date_str):
    if tf == "daily":
        from daily_signal_report import generate_daily_signal
        return generate_daily_signal(ticker, date_str=date_str, min_wr=0.50, min_pf=1.0)
    from astro_mtf import generate_mtf_live_signal
    return generate_mtf_live_signal(ticker, bar_size=tf, min_wr=0.50, min_pf=1.0, min_n=8)

def _hmm(ticker):
    try:
        from astro_hmm import load_hmm_params, predict_regime, observation_index
        h = load_hmm_params(ticker)
        if h and abs(h.A[0][0] - 0.70) > 0.001:
            return predict_regime(h, [observation_index("LONG", True, 0.01)])["current_regime"]
    except: pass
    return "default"

def _run_one(date_str):
    label = date_str or datetime.now().strftime("%Y-%m-%d")
    regimes = {t: _hmm(t) for t in TICKERS}

    print(f"  HMM: {' │ '.join(f'{t}:{r}' for t,r in regimes.items())}")
    print()
    print(f"  {'TICKER':<6} {'TF':<7} {'DIR':<8} {'PF':<8} {'WR':<7} {'CONV':<6} {'SL':<8} {'TP':<8} {'HOLD':<6} {'MATCH'}")
    print(f"  {'─'*6} {'─'*7} {'─'*8} {'─'*8} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*6} {'─'*9}")
    all_sigs = {}
    for t in TICKERS:
        for tf in ["daily", "1h", "4h"]:
            s = _sig(t, tf, date_str)
            all_sigs[(t, tf)] = s
            if s:
                print(f"  {t:<6} {tf:<7} {E(s['direction'])} {s['direction']:<6} {s['pf']:<8} {s['wr']:<7} {s['conviction']:<6} {s['sl_pct']:<8} {s['tp_pct']:<8} {str(s.get('hold_days', s.get('hold_bars','?'))):<6} {s.get('match_type','?')}")
            else:
                print(f"  {t:<6} {tf:<7} ⚪  NO SIGNAL")

    print(f"\n  {'─'*55}")
    print(f"  POSITION SIZING")
    print(f"  {'─'*55}")
    for t in TICKERS:
        g = sum(1 for tf in ["daily","1h","4h"] if (s:=all_sigs.get((t,tf))) and s["direction"]=="LONG")
        y = sum(1 for tf in ["daily","1h","4h"] if not all_sigs.get((t,tf)))
        r = sum(1 for tf in ["daily","1h","4h"] if (s:=all_sigs.get((t,tf))) and s["direction"]=="SHORT")
        if g == 0: a = "SIT OUT"
        elif g == 3 and y == 0: a = "FULL"
        elif g >= 2: a = "HALF"
        elif g == 1 and y == 2: a = "MONITOR"
        else: a = "SIT OUT"
        note = " ⚠BEAR" if regimes.get(t) == "BEAR" else ""
        sd = all_sigs.get((t, "daily"))
        ts = f"SL={sd['sl_pct']} TP={sd['tp_pct']} {sd.get('hold_days','?')}d" if sd else ""
        print(f"  {t}: {a}  {ts}{note}")

    nq = all_sigs.get(("NQ","daily"), {})
    if nq.get("match_type") != "exact":
        print(f"\n  ⚠ NQ fallback — half size on NQ")
    return all_sigs

def main():
    if len(sys.argv) >= 3:
        from datetime import timedelta
        d1 = datetime.strptime(sys.argv[1], "%Y-%m-%d")
        d2 = datetime.strptime(sys.argv[2], "%Y-%m-%d")
        if d1 > d2: d1, d2 = d2, d1
        dates = []; d = d1
        while d <= d2:
            dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
    elif len(sys.argv) == 2:
        dates = [sys.argv[1]]
    else:
        dates = [None]

    label = sys.argv[1] if len(sys.argv)==2 else f"{sys.argv[1]}→{sys.argv[2]}" if len(sys.argv)>=3 else datetime.now().strftime("%Y-%m-%d")
    for i, ds in enumerate(dates):
        if len(dates) > 1:
            print(f"\n{'─'*55}")
            print(f"  >>> {ds} <<<")
        _run_one(ds)

    print(f"\n  v0.62 — {label}")

if __name__ == "__main__":
    main()
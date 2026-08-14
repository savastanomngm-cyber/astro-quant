#!/usr/bin/env python3
"""
ASTRO-QUANT PREDICTION — Forecast a date range
================================================
Forward-looking: given a start + end date, project what the astro system
expects the market to do over that window. NOT a backtest (which shows what
happened) — this is a prediction of a future window.

For each trading day in the range:
  - compute the astro state
  - generate the persona signal (which learned pattern matches)
  - record direction + conviction

Then aggregate into:
  - net directional bias (LONG days vs SHORT days vs neutral)
  - conviction-weighted forecast + verdict
  - day-by-day table

Usage:
  python3 predict.py NQ 2026-08-14 2026-08-28
  python3 predict.py GC 2026-08-14 2026-09-14
"""

import os, sys, math
from datetime import datetime, timedelta

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import pandas as pd
import yfinance as yf

from astro_configs import INSTRUMENTS
from astro_knowledge import chart_to_snapshot
from pattern_engine_v3 import load_rectified, get_state, state_key
from pattern_engine_v3 import build_patterns as bp, learn_patterns as lp
from astro_personas import generate_trader_personas_from_learned
from astro_core_v2 import calculate_chart

# ANSI colors (best-effort)
_tty = sys.stdout.isatty()
G = "\033[92m" if _tty else ""
R = "\033[91m" if _tty else ""
Y = "\033[93m" if _tty else ""
X = "\033[0m" if _tty else ""

_context_cache = {}
_cur_ticker = "NQ"


def _signal_for_day(ctx, day_dt):
    """Project the signal for a specific day in the future window."""
    chart = ctx["chart"]
    personas = ctx["personas"]
    dd = ctx["dd"]
    all_dates = ctx["all_dates"]

    signal_utc = day_dt.replace(hour=17)
    try:
        st = get_state(chart, signal_utc)
    except Exception:
        return None

    persona = None; match_type = "none"
    def _best(cands):
        return max(cands, key=lambda x: min(x[1].historical_pf, 20) * math.log(max(x[1].n_samples, 2)))[1]

    for hz in [3, 5, 7]:
        sk = state_key(st, hz)
        if sk in personas:
            persona = personas[sk]; match_type = "exact"; break
    if not persona:
        prefix = f"{st['main']}_{st['sub']}_{st['dist']}_"
        cands = [(pid, p) for pid, p in personas.items() if pid.startswith(prefix)]
        if cands: persona = _best(cands); match_type = "prefix"
    if not persona:
        cands = [(pid, p) for pid, p in personas.items() if pid.startswith(st["main"])]
        if cands: persona = _best(cands); match_type = "main"
    if not persona:
        return None

    if persona.historical_win_rate < 0.50 or persona.historical_pf < 1.0:
        return None

    # NQ trend gate: no LONG when below 200-day MA.
    # For future dates (beyond today), use the latest available close.
    if _cur_ticker == "NQ" and persona.pattern_direction == "LONG":
        ds = day_dt.strftime("%Y-%m-%d")
        closes = [dd[d]["close"] for d in sorted(all_dates) if d <= ds]
        if len(closes) >= 200:
            ma200 = sum(closes[-200:]) / 200
            # if ds is a future date (not in dd), compare last close to MA
            last_close = closes[-1]
            if (dd[ds]["open"] if ds in dd else last_close) < ma200:
                return None

    moon = st.get("moon_applies", "void")
    moon_mult = 1.0
    if moon in ("Jupiter", "Venus"): moon_mult = 1.15
    elif moon in ("Saturn", "Mars"): moon_mult = 0.85

    return {
        "date": day_dt.strftime("%Y-%m-%d"),
        "direction": persona.pattern_direction,
        "conviction": round(persona.conviction_mult * moon_mult, 2),
        "pf": persona.historical_pf,
        "wr": persona.historical_win_rate,
        "moon": moon,
        "avg_move": abs(persona.historical_avg_move),
        "match": match_type,
    }


def _build_context(ticker):
    if ticker in _context_cache:
        return _context_cache[ticker]
    inst = INSTRUMENTS.get(ticker)
    if not inst:
        return None
    rect = load_rectified().get(ticker)
    if not rect:
        rect = {"NQ": {"hour": 21, "min": 0, "sec": 0}, "ES": {"hour": 14, "min": 30, "sec": 0},
                "GC": {"hour": 4, "min": 0, "sec": 0}}.get(ticker, {"hour": 12, "min": 0, "sec": 0})
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                      rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart = calculate_chart(local_dt.year, local_dt.month, local_dt.day,
                            local_dt.hour, local_dt.minute, local_dt.second,
                            inst.birth_lat, inst.birth_lon, inst.birth_tz)

    symbol = inst.data_symbol if inst.data_symbol else f"{ticker}=F"
    data = None
    for _ in range(3):
        try:
            data = yf.Ticker(symbol).history(start="2010-01-01")
            if data is not None and not data.empty:
                break
        except Exception:
            pass
    if data is None or data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    dd = {}; all_dates = []
    for idx, row in data.iterrows():
        ds = idx.strftime("%Y-%m-%d")
        try:
            o = float(row["Open"]); h = float(row["High"])
            l = float(row["Low"]); c = float(row["Close"])
        except Exception:
            continue
        if o <= 0 or c <= 0: continue
        dd[ds] = {"open": o, "high": h, "low": l, "close": c}
        all_dates.append(ds)

    pats = bp(chart, dd, all_dates, horizons=[3, 5, 7])
    learned_raw = lp(pats, min_n=12, max_p=0.02, min_edge=0.52)
    chart_snap = chart_to_snapshot(ticker=ticker, chart_dict=chart,
                                    birth_utc=utc_dt, tz_offset=inst.birth_tz,
                                    lat=inst.birth_lat, lon=inst.birth_lon)
    personas = generate_trader_personas_from_learned(learned_raw, ticker, chart_snap)
    personas_dict = {p.persona_id: p for p in personas}

    ctx = {"chart": chart, "personas": personas_dict, "dd": dd, "all_dates": all_dates}
    _context_cache[ticker] = ctx
    return ctx


def predict(ticker, start_str, end_str, verbose=True):
    """Predict the directional bias for the date range."""
    global _cur_ticker
    _cur_ticker = ticker
    ctx = _build_context(ticker)
    if not ctx:
        print(f"  No pattern context for {ticker}"); return

    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days = [d for d in days if d.weekday() < 5]

    results = [sig for d in days if (sig := _signal_for_day(ctx, d))]

    longs = [r for r in results if r["direction"] == "LONG"]
    shorts = [r for r in results if r["direction"] == "SHORT"]
    neutral = len(days) - len(results)

    print(f"\n  {G}PREDICTION — {ticker}  ({start_str} → {end_str}){X}")
    print(f"  {'='*60}")
    print(f"  Trading days: {len(days)} | Signals: {len(results)} "
          f"({len(longs)}L / {len(shorts)}S / {neutral} no-signal)")

    if not results:
        print(f"  {Y}No signals cover this window (astro states unmapped).{X}")
        return

    long_conv = sum(r["conviction"] for r in longs)
    short_conv = sum(r["conviction"] for r in shorts)
    net = long_conv - short_conv

    # Projected move: sum of conviction-weighted avg moves (LONG +, SHORT -)
    proj = sum(r["avg_move"] * r["conviction"] for r in longs) - sum(r["avg_move"] * r["conviction"] for r in shorts)

    if net >= 0.5:
        verdict, vc = "BULLISH", G
    elif net <= -0.5:
        verdict, vc = "BEARISH", R
    else:
        verdict, vc = "NEUTRAL", Y

    print(f"  LONG avg conv: {long_conv/max(1,len(longs)):+.2f}" if longs else "  No LONG signals")
    print(f"  SHORT avg conv: {short_conv/max(1,len(shorts)):+.2f}" if shorts else "  No SHORT signals")
    print(f"  Net conviction bias: {net:+.2f}  |  Projected move: {proj:+.3%} (window)")
    print(f"  → {vc}{verdict}{X}")

    if verbose:
        print(f"\n  Day-by-day:")
        for r in results:
            e = "🟢" if r["direction"] == "LONG" else "🔴"
            print(f"    {r['date']}  {e} {r['direction']:<6} conv={r['conviction']:.2f} "
                  f"PF={r['pf']:.2f} WR={r['wr']:.0%} 🌙→{r['moon']} ({r['match']})")

    return {"ticker": ticker, "net_conviction": net, "projected_move": proj,
            "verdict": verdict, "n_long": len(longs), "n_short": len(shorts),
            "days": results}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 predict.py TICKER START END")
        print("  e.g. python3 predict.py NQ 2026-08-14 2026-08-28")
        sys.exit(1)
    t = sys.argv[1].upper(); s = sys.argv[2]; e = sys.argv[3]
    predict(t, s, e)
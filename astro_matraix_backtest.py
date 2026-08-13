#!/usr/bin/env python3
"""
ASTRO MATRAIX BACKTEST — Persona-Weighted Signal Engine
===========================================================
Closes the loop: persona-generated signals → actual trades → P&L.

Instead of:
  - Grid search over SL/TP/hold
  - One-size-fits-all parameters

We use:
  - Each persona's derived SL/TP/hold from its 51-dim profile
  - Conviction-weighted position sizing
  - Signal filtering by PF/WR thresholds
  - SHORT signals from bearish personas

This is the final piece — the persona simulation output becomes executable
trading signals that can be compared against existing backtest_flow results.
"""

from __future__ import annotations
import math
import random
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional

from astro_knowledge import (
    ChartSnapshot, PatternCard, TradeStats, TradeRecord,
    BacktestResult, SourceRef, ChartProvenance, DataSourceKind,
    chart_to_snapshot,
)
from astro_configs import INSTRUMENTS, YahooSource, InstrumentDef
from astro_personas import (
    TraderPersona, generate_trader_personas_from_learned,
)


def simulate_persona_weighted(
    signals: list[dict],
    dd: dict[str, dict],
    dates: list[str],
    point_value: float,
    tca_points: float = 0.5,
    min_win_rate: float = 0.50,
    min_pf: float = 1.0,
) -> list[dict]:
    """Execute trades using persona-derived parameters."""
    d2i = {d: i for i, d in enumerate(dates)}
    trades = []
    last_idx = -1
    for sig in signals:
        entry_date = sig["date"]
        direction = sig["direction"]
        persona = sig.get("persona")
        conviction = sig.get("conviction", 0.5)
        if persona:
            if persona.historical_win_rate < min_win_rate: continue
            if persona.historical_pf < min_pf: continue
        idx = d2i.get(entry_date)
        if idx is None or idx <= last_idx: continue
        if persona:
            stop_pct = persona.stop_tightness
            ticker_vol_map = {"NQ": 1.30, "ES": 0.85, "GC": 0.95}
            vol_scale = ticker_vol_map.get(persona.ticker, 1.0)
            stop_pct = stop_pct * vol_scale
            pf = persona.historical_pf if persona.historical_pf > 0 else 1.0
            tp_multiplier = min(6.0, max(1.2, 1.5 + math.log(pf + 0.5)))
            tp_pct = stop_pct * tp_multiplier
            hold_days = persona.max_hold_days
            hold_days = max(1, min(hold_days, 60))
            position_pct = persona.position_size_pct * (0.5 + 0.5 * conviction)
            position_pct = min(0.50, position_pct)
        else:
            stop_pct = 0.05; tp_pct = 0.15; hold_days = 7; position_pct = 0.10
        xi = idx + hold_days
        if xi >= len(dates): continue
        eb = dd.get(dates[idx]); xb = dd.get(dates[xi])
        if not eb or not xb: continue
        ep = eb["open"]; xp = xb["close"]
        if ep <= 0: continue
        sl = ep * stop_pct; tp = ep * tp_pct
        stopped = False; gross = 0.0; exit_reason = "hold"
        for j in range(idx, xi + 1):
            bar = dd[dates[j]]
            if direction == "LONG":
                if bar["low"] <= ep - sl: gross = -sl; stopped = True; exit_reason = "stop_loss"; break
                if bar["high"] >= ep + tp: gross = tp; stopped = True; exit_reason = "take_profit"; break
            else:
                if bar["high"] >= ep + sl: gross = -sl; stopped = True; exit_reason = "stop_loss"; break
                if bar["low"] <= ep - tp: gross = tp; stopped = True; exit_reason = "take_profit"; break
        if not stopped:
            gross = (xp - ep) if direction == "LONG" else (ep - xp)
            exit_reason = "time_exit"
        gross_scaled = gross * (position_pct / persona.position_size_pct) if persona else gross
        net = gross_scaled - tca_points
        trades.append({"date": entry_date, "dir": direction, "gross": gross, "gross_scaled": gross_scaled,
            "net": net, "sl_points": round(sl,2), "tp_points": round(tp,2), "hold_days": hold_days,
            "position_pct": round(position_pct,3), "exit_reason": exit_reason,
            "persona_id": persona.persona_id[:40] if persona else "unknown",
            "pf": persona.historical_pf if persona else 0,
            "wr": persona.historical_win_rate if persona else 0,
            "conviction": round(conviction,3)})
        last_idx = xi
    return trades


def compute_persona_trade_stats(
    trades: list[dict],
    point_value: float = 1.0,
    starting_capital: float = 100_000.0,
) -> TradeStats:
    """Compute stats from persona-weighted trades with fixed drawdown on equity curve."""
    if not trades: return TradeStats()
    n = len(trades)
    dollar_pnl = [t["net"] * point_value for t in trades]
    equity = starting_capital; peak = starting_capital; max_dd = 0.0
    for pnl in dollar_pnl:
        equity += pnl
        if equity > peak: peak = equity
        if equity <= 0: max_dd = 1.0; continue
        dd = 1.0 - equity / peak if peak > 0 else 0.0
        if dd > max_dd: max_dd = dd
    vals = [t["net"] for t in trades]
    wins = [v for v in vals if v > 0]; losses = [v for v in vals if v <= 0]
    wr = len(wins) / n if n else 0
    gw = sum(wins); gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else (999.0 if gw > 0 else 0.0)
    per_trade_ret = [pnl / starting_capital for pnl in dollar_pnl]
    mu = sum(per_trade_ret) / n if n else 0.0
    sd = (sum((r - mu) ** 2 for r in per_trade_ret) / (n - 1)) ** 0.5 if n > 1 else 0.0
    sh = (mu / sd) * (252 ** 0.5) if sd > 0 else 0.0
    final_equity = equity
    total_dollars = final_equity - starting_capital
    return TradeStats(
        n_trades=n, win_rate=wr,
        avg_win=sum(wins)/len(wins) if wins else 0,
        avg_loss=sum(losses)/len(losses) if losses else 0,
        total_points=sum(vals), total_dollars=total_dollars,
        profit_factor=pf, sharpe=round(sh,2),
        max_drawdown=round(max_dd*100,1),
    )


def persona_backtest_flow(
    ticker: str = "NQ", yahoo_start: str = "2010-01-01", train_ratio: float = 0.6,
    min_win_rate: float = 0.50, min_pf: float = 1.0, min_conviction: float = 0.4,
    use_short_signals: bool = True, point_value: Optional[float] = None, verbose: bool = True,
) -> BacktestResult | None:
    if ticker in ("GC", "NQ", "ES") and use_short_signals:
        if verbose: print(f"  ⚠ {ticker} SHORT signals disabled (empirically broken — long-only is robust)")
        use_short_signals = False
    inst = INSTRUMENTS.get(ticker)
    if not inst: return None
    if point_value is None: point_value = inst.point_value
    if verbose: print("  Loading chart...")
    try:
        from pattern_engine_v3 import load_rectified
        rect = load_rectified().get(ticker)
    except: rect = None
    if not rect:
        rect = {"NQ":{"hour":20,"min":45,"sec":0},"ES":{"hour":9,"min":30,"sec":0},"GC":{"hour":16,"min":0,"sec":0}}.get(ticker,{"hour":12,"min":0,"sec":0})
    utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day, rect["hour"], rect["min"], rect["sec"])
    local_dt = utc_dt + timedelta(hours=inst.birth_tz)
    chart_dict = __import__('astro_core_v2', fromlist=['calculate_chart']).calculate_chart(
        local_dt.year, local_dt.month, local_dt.day, local_dt.hour, local_dt.minute, local_dt.second,
        inst.birth_lat, inst.birth_lon, inst.birth_tz)
    chart_snap = chart_to_snapshot(ticker=ticker, chart_dict=chart_dict, birth_utc=utc_dt,
                                    tz_offset=inst.birth_tz, lat=inst.birth_lat, lon=inst.birth_lon)
    if verbose: print("  Loading Yahoo data...")
    try:
        import time as _time
        symbol = inst.data_symbol if (hasattr(inst,'data_symbol') and inst.data_symbol) else f"{ticker}=F"
        data = None
        for attempt in range(3):
            try:
                tkr = yf.Ticker(symbol)
                data = tkr.history(start=yahoo_start)
                if data is not None and not data.empty: break
            except Exception:
                if attempt < 2: _time.sleep(2 + attempt * 2)
        if data is None or data.empty:
            if verbose: print(f"  No data for {symbol}"); return None
        if verbose: print(f"  Got {len(data)} rows")
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        dd = {}; all_dates = []
        for idx, row in data.iterrows():
            ds = idx.strftime("%Y-%m-%d")
            try: o = float(row["Open"]); h = float(row["High"]); l = float(row["Low"]); c = float(row["Close"])
            except: continue
            if o <= 0 or c <= 0: continue
            dd[ds] = {"open":o,"high":h,"low":l,"close":c}; all_dates.append(ds)
    except Exception as e:
        if verbose: print(f"  Yahoo error: {e}"); return None
    dates = [d for d in all_dates if d >= yahoo_start]
    n = len(dates)
    if n < 200: return None
    train_end = int(n * train_ratio); val_end = int(n * (train_ratio + 0.2))
    train_dates = dates[:train_end]; val_dates = dates[train_end:val_end]; test_dates = dates[val_end:]
    if verbose: print(f"  Learning patterns on {len(train_dates)} train days...")
    try:
        from pattern_engine_v3 import build_patterns as bp, learn_patterns as lp, get_state, state_key
        pats = bp(chart_dict, dd, train_dates, horizons=[3,5,7])
        short_edge = {"GC":0.48,"NQ":0.38,"ES":0.42}.get(ticker,0.40)
        learned_raw = lp(pats, min_n=12, max_p=0.01, min_edge=0.52, amplify_short=short_edge)
        if not learned_raw: print("  No patterns learned"); return None
    except Exception as e: print(f"  Pattern engine error: {e}"); return None
    if verbose: print(f"  Generating personas from {len(learned_raw)} patterns...")
    personas = generate_trader_personas_from_learned(learned_raw, ticker, chart_snap)
    personas_dict = {p.persona_id: p for p in personas}
    if verbose: print(f"    {len(personas)} personas — {sum(1 for p in personas if p.pattern_direction=='LONG')}L / {sum(1 for p in personas if p.pattern_direction=='SHORT')}S")
    def gen_persona_signals(date_list):
        signals = []; prev_state = None
        for i in range(len(date_list)-1):
            sd = date_list[i]; ed = date_list[i+1]
            if sd not in dd or ed not in dd: continue
            signal_utc = datetime.strptime(sd,"%Y-%m-%d").replace(hour=17)
            st = get_state(chart_dict, signal_utc)
            curr = (st["main"], st["sub"], st["dist"], st["house"], st["moon_phase"])
            if curr == prev_state: continue
            prev_state = curr
            sk = state_key(st,7)
            persona = personas_dict.get(sk)
            if not persona:
                for pid,p in personas_dict.items():
                    if pid.startswith(f"{st['main']}_{st['sub']}_{st['dist']}_"): persona=p; break
            if not persona:
                hs = f"_H{st['house']}_"; mp = f"_{st['moon_phase']}_"
                for pid,p in personas_dict.items():
                    if hs in pid and mp in pid: persona=p; break
            if not persona:
                for pid,p in personas_dict.items():
                    if pid.startswith(f"{st['main']}_"): persona=p; break
            if not persona:
                best = max(personas_dict.values(), key=lambda p:p.historical_pf, default=None)
                if best and best.historical_pf >= min_pf: persona = best
            if not persona: continue
            if persona.historical_win_rate < min_win_rate: continue
            if persona.historical_pf < min_pf: continue
            if persona.conviction_mult < min_conviction: continue
            if not use_short_signals and persona.pattern_direction == "SHORT": continue
            signals.append({"date":ed,"direction":persona.pattern_direction,"persona":persona,"state_key":sk,"conviction":persona.conviction_mult})
        return signals
    if verbose: print("  Generating signals...")
    val_signals = gen_persona_signals(val_dates)
    test_signals = gen_persona_signals(test_dates)
    if verbose: print(f"    Val signals: {len(val_signals)} | Test signals: {len(test_signals)}")
    tca = 0.5
    val_trades = simulate_persona_weighted(val_signals, dd, val_dates, point_value, tca, min_win_rate=min_win_rate, min_pf=min_pf)
    test_trades = simulate_persona_weighted(test_signals, dd, test_dates, point_value, tca, min_win_rate=min_win_rate, min_pf=min_pf)
    val_stats = compute_persona_trade_stats(val_trades, point_value)
    oos_stats = compute_persona_trade_stats(test_trades, point_value)
    if verbose:
        print(f"\n  {'='*50}")
        print(f"  PERSONA BACKTEST RESULTS — {ticker}")
        print(f"  {'='*50}")
        print(f"  Patterns: {len(learned_raw)} → {len(personas)} personas")
        print(f"  Val: {val_stats.n_trades}t | WR={val_stats.win_rate:.1%} | PF={val_stats.profit_factor:.2f} | Sharpe={val_stats.sharpe} | DD={val_stats.max_drawdown}% | ${val_stats.total_dollars:,.0f}")
        print(f"  OOS: {oos_stats.n_trades}t | WR={oos_stats.win_rate:.1%} | PF={oos_stats.profit_factor:.2f} | Sharpe={oos_stats.sharpe} | DD={oos_stats.max_drawdown}% | ${oos_stats.total_dollars:,.0f}")
        if test_trades:
            reasons = {}
            for t in test_trades: reasons[t["exit_reason"]] = reasons.get(t["exit_reason"],0)+1
            print(f"  Exit reasons: {reasons}")
    source_ref = SourceRef(kind=DataSourceKind.YAHOO, symbol=symbol)
    return BacktestResult(
        as_of=datetime.now(), ticker=ticker, source=source_ref,
        chart_provenance=ChartProvenance(method="persona_matraix_v1"),
        train_ratio=train_ratio,
        sl_points=1, tp_points=1, hold_days=1,
        patterns_found=len(learned_raw), patterns_valid=len(personas),
        validation=val_stats, out_of_sample=oos_stats,
        oos_trades=[TradeRecord(date=t["date"], direction=t["dir"], gross_points=t["gross"], net_points=t["net"]) for t in test_trades])


def generate_live_signals(ticker="NQ", date_str=None, min_win_rate=0.50, min_pf=1.0, use_short=True):
    if ticker == "GC" and use_short: use_short = False
    try:
        from daily_signal_report import generate_daily_signal as _gds
        sig = _gds(ticker, date_str=date_str, min_wr=min_win_rate, min_pf=min_pf)
        if sig: return [sig]
    except Exception: pass
    return []


def _entry_timing(persona):
    timing_map = {"snap_decisions":"Open — enter immediately","quick":"Open+30m — enter on first direction confirmation","balanced":"Open+2h — wait for pullback/retest","deliberate":"Mid-session — wait for structure","agonizes":"Late/next day — multiple timeframes must align"}
    base = timing_map.get(persona.decision_speed, "Open — enter at market open")
    if persona.patience in ("high","very_high"): base += " (extended patience)"
    elif persona.patience in ("very_low","low"): base += " (low patience)"
    return base

def _timeframe_for_persona(persona):
    hold = persona.max_hold_days; speed = persona.decision_speed; detail = persona.detail_orientation
    tf = "H1" if hold <= 3 else ("H4" if hold <= 7 else ("Daily" if hold <= 20 else "Daily/Weekly"))
    if detail in ("high","very_high"): tf += " + M15"
    if speed in ("snap_decisions","quick"): tf += " + M5"
    return tf

def _execution_note(persona):
    notes = []
    notes.append(f"Enter: {_entry_timing(persona)}"); notes.append(f"TF: {_timeframe_for_persona(persona)}")
    notes.append(f"SL: {persona.stop_tightness:.1%} | TP: open | Max hold: {persona.max_hold_days}d")
    notes.append(f"Position: {persona.position_size_pct:.0%} of capital")
    if persona.panic_exit_prob > 0.15: notes.append("⚠ High panic-exit — set hard SL")
    if persona.revenge_trade_prob > 0.15: notes.append("⚠ Revenge-trade risk — step away 24h after loss")
    if persona.overtrade_mult > 1.3: notes.append("⚠ Overtrading — max 1 entry per signal")
    if persona.rule_adherence < 0.6: notes.append("⚠ Low rule adherence — use bracket orders")
    if persona.historical_pf > 3.0: notes.append("✓ Elite pattern — trust the signal")
    if persona.historical_win_rate > 0.75: notes.append(f"✓ High hit rate ({persona.historical_win_rate:.0%})")
    return " | ".join(notes)


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    print(f"ASTRO MATRAIX BACKTEST — {ticker}")
    result = persona_backtest_flow(ticker=ticker, min_win_rate=0.50, min_pf=1.0, use_short_signals=True)
    if result:
        print(f"✓ OOS: PF={result.out_of_sample.profit_factor:.2f} WR={result.out_of_sample.win_rate:.1%} Net=${result.out_of_sample.total_dollars:,.0f}")
    print("Live signals:")
    sigs = generate_live_signals(ticker, min_win_rate=0.50, min_pf=1.0)
    for s in sigs:
        print(f"  {ticker}: {s['direction']} conv={s['conviction']} SL={s['sl_pct']}")
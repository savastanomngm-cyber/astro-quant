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

FUTURES = ["NQ", "ES", "GC"]
ETF_TRACKERS = ["ITA", "PPA", "SOXX"]  # BOTZ removed — PF=0.50, DD=4540%, too young
E = lambda d: "🟢" if d == "LONG" else "🔴" if d == "SHORT" else "⚪"

def _sig(ticker, tf, date_str):
    if tf == "daily":
        from daily_signal_report import generate_daily_signal
        return generate_daily_signal(ticker, date_str=date_str, min_wr=0.50, min_pf=1.0)
    from astro_mtf import generate_mtf_live_signal
    return generate_mtf_live_signal(ticker, bar_size=tf, min_wr=0.50, min_pf=1.0, min_n=8, lookback_days=730)

def _hmm(ticker):
    try:
        from astro_hmm import load_hmm_params
        from astro_matraix_backtest import persona_backtest_flow
        from astro_hmm import observation_index
        h = load_hmm_params(ticker)
        if not h or abs(h.A[0][0] - 0.70) < 0.001:
            return "default"
        # Decode the REAL recent OOS trade history (like M8), not a fake token
        r = persona_backtest_flow(ticker=ticker, verbose=False)
        if r and r.oos_trades:
            obs = [observation_index(t.direction, t.net_points > 0,
                                     min(abs(t.gross_points)/100.0, 0.05))
                   for t in r.oos_trades[-20:]]
            from astro_hmm import viterbi, REGIMES
            path, _ = viterbi(h, obs)
            return REGIMES[path[-1]]
    except Exception:
        pass
    return "default"

def _run_group(label, tickers, date_str, show_tf=True):
    regimes = {t: _hmm(t) for t in tickers}
    print(f"  HMM: {' │ '.join(f'{t}:{r}' for t,r in regimes.items())}")
    print()

    # Macro regime + eclipse (Regulus)
    if tickers == FUTURES:
        try:
            from signals_macro import macro_regime, recent_eclipse
            mr = macro_regime(datetime.now())
            ecl = recent_eclipse(datetime.now())
            macro_line = f"  🌐 Macro: {mr['regime']} — {mr['bias']}"
            if ecl:
                macro_line += f" | 🌑 Eclipse {ecl['date']}"
            print(macro_line)
            print()
        except Exception:
            pass

    tfs = ["daily", "1h", "4h"] if show_tf else ["daily"]
    print(f"  {'TICKER':<6} {'TF':<7} {'DIR':<8} {'PF':<8} {'WR':<7} {'CONV':<6} {'SL':<8} {'TP':<8} {'HOLD':<6} {'MATCH'}")
    print(f"  {'─'*6} {'─'*7} {'─'*8} {'─'*8} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*6} {'─'*9}")
    all_sigs = {}
    for t in tickers:
        for tf in tfs:
            s = _sig(t, tf, date_str)
            all_sigs[(t, tf)] = s
            if s:
                moon = s.get("moon_applies", "")
                moon_tag = f" 🌙→{moon}" if moon else ""
                print(f"  {t:<6} {tf:<7} {E(s['direction'])} {s['direction']:<6} {s['pf']:<8} {s['wr']:<7} {s['conviction']:<6} {s['sl_pct']:<8} {s['tp_pct']:<8} {str(s.get('hold_days', s.get('hold_bars','?'))):<6} {s.get('match_type','?')}{moon_tag}")
            else:
                print(f"  {t:<6} {tf:<7} ⚪  NO SIGNAL")

    # GC/NQ coupling detector
    print(f"\n  {'─'*55}")
    print(f"  GC/NQ COUPLING ANALYSIS")
    print(f"  {'─'*55}")
    if tickers == FUTURES and 'GC' in tickers and 'NQ' in tickers:
        try:
            from coupling_detector import detect_coupling, format_coupling_display
            gc_daily = all_sigs.get(('GC', 'daily'))
            nq_daily = all_sigs.get(('NQ', 'daily'))
            if gc_daily and nq_daily:
                coupling_info = detect_coupling(gc_daily, nq_daily)
                print(f"  {format_coupling_display(coupling_info)}")
            else:
                print(f"  ❓ Missing GC or NQ signal")
        except Exception as e:
            print(f"  ❌ Coupling detection error: {str(e)[:40]}")
    else:
        print(f"  (N/A — not futures or missing GC/NQ)")

    print(f"\n  {'─'*55}")
    print(f"  POSITION SIZING")
    print(f"  {'─'*55}")

    # Pre-compute Kronos verdicts for futures so sizing can use them
    kronos_map = {}
    if tickers == FUTURES:
        import sys as _s, os as _o
        _s.path.insert(0, _o.path.expanduser(_o.path.join(_o.path.dirname(__file__), '..', 'kronos')))
        try:
            from astro_matraix_kronos import KronosConfirmer
            kc = KronosConfirmer(); kc._ensure_loaded()
            import yfinance as yf
            for t in tickers:
                sd = all_sigs.get((t, "daily"))
                if not sd: continue
                inst = __import__('astro_configs').INSTRUMENTS.get(t)
                sym = inst.data_symbol or f'{t}=F'
                data = yf.Ticker(sym).history(period='90d')
                if data.empty: continue
                df = data[['Open','High','Low','Close','Volume']].copy()
                df.columns = ['open','high','low','close','volume']
                kronos_map[t] = kc.confirm_signal(t, {'direction':sd['direction'],'conviction':sd['conviction'],
                    'sl_pct':sd['sl_pct'],'tp_pct':sd['tp_pct']}, df=df)
        except Exception:
            pass

    for t in tickers:
        g = sum(1 for tf in tfs if (s:=all_sigs.get((t,tf))) and s["direction"]=="LONG")
        y = sum(1 for tf in tfs if not all_sigs.get((t,tf)))
        r = sum(1 for tf in tfs if (s:=all_sigs.get((t,tf))) and s["direction"]=="SHORT")
        if g == 0: a = "SIT OUT"
        elif g == len(tfs) and y == 0: a = "FULL"
        elif g >= 2: a = "HALF"
        elif g == 1 and y >= 1: a = "MONITOR"
        elif r > g: a = "SIT OUT (SHORT dominates)"
        else: a = "SIT OUT"

        # Fold in HMM + Kronos + Moon application
        regime = regimes.get(t, "default")
        kron = kronos_map.get(t)
        note = ""
        if regime == "BEAR":
            note += " ⚠BEAR"
            if a == "FULL": a = "HALF"
        elif regime == "CHOP":
            note += " ⚠CHOP"
            if a == "FULL": a = "HALF"
        if kron:
            if kron["status"] == "DIVERGES":
                note += " ⚠KRONOS-DIVERGES"
                a = "MONITOR" if a in ("FULL","HALF") else "SIT OUT"
            elif kron["status"] == "UNRELIABLE":
                note += " ⚠KRONOS-UNRELIABLE"

            # GC + Kronos CONFIRMED = SHORT signal (backtested: 41% WR / PF 2.05,
            # and GC-confirmed LONG = 44% WR / PF 0.70 — the single worst long cell).
            # Kronos CONFIRMED is INVERTED for GC specifically (NQ/ES confirmations are bullish).
            if t == "GC" and kron["status"] == "CONFIRMED":
                note += " 🔻GC-CONFIRMED→SHORT (half size, asymmetric hedge)"
                a = "SHORT (GC)"

        # Moon application overlay (Rectification Manual, dynamic_filters_v1 §6):
        # applying to a malefic (Mars/Saturn) → caution (half size);
        # applying to a benefic (Jupiter/Venus) → no reduction.
        sd = all_sigs.get((t, "daily"))
        moon = (sd or {}).get("moon_applies", "")
        if moon in ("Saturn", "Mars"):
            note += " ⚠MOON-MALEFIC"
            if a == "FULL": a = "HALF"
        elif moon in ("Jupiter", "Venus"):
            note += " ☾MOON-BENEFIC"

        ts = f"SL={sd['sl_pct']} TP={sd['tp_pct']} {sd.get('hold_days','?')}d" if sd else ""
        print(f"  {t:<6s}: {a:<22s} {ts}{note}")

    # Execution guidance (persona-derived: entry timing, timeframe, hold, note)
    print(f"\n  {'─'*55}")
    print(f"  PERSONA EXECUTION GUIDANCE")
    print(f"  {'─'*55}")
    for t in tickers:
        sd = all_sigs.get((t, "daily"))
        if not sd:
            print(f"  {t:<6}: no daily signal")
            continue
        print(f"  {t:<6}  {sd.get('timeframe','daily')}")
        print(f"    ▶ Enter: {sd.get('entry_timing','?')}")
        print(f"    ⏱ Hold:  {sd.get('hold_days','?')}d | SL {sd.get('sl_pct','?')} | TP {sd.get('tp_pct','?')} | Pos {sd.get('position_pct','?')}")
        # Real contract sizing (micro vs mini) for a given account size
        try:
            from sizing import display_for
            acct = float(os.environ.get("ACCOUNT_SIZE", 25000))
            inst = __import__('astro_configs').INSTRUMENTS.get(t)
            px = None
            try:
                import yfinance as yf
                sym = inst.data_symbol or f'{t}=F'
                px = float(yf.Ticker(sym).history(period='2d')['Close'].iloc[-1])
            except Exception:
                pass
            if px:
                sl = float(sd['sl_pct'].rstrip('%')) / 100.0
                acct_line = display_for(t, px, sl, 0.0, acct)
                print(f"    💰 ${acct:,.0f} acct → {acct_line}")
        except Exception:
            pass
        note = sd.get('note')
        if note:
            print(f"    ℹ {note}")

    # Kronos confirmation for futures
    if tickers == FUTURES:
        print(f"\n  {'─'*55}")
        print(f"  KRONOS VOL CONFIRMATION")
        print(f"  {'─'*55}")
        for t in tickers:
            r = kronos_map.get(t)
            if not r:
                print(f"  ? {t}: no Kronos")
                continue
            status = r['status']
            if status == 'CONFIRMED':
                e = '✓'
            elif status == 'DIVERGES':
                e = '✗'
            elif status == 'UNRELIABLE':
                e = '!'
            elif status == 'NEUTRAL':
                e = '○'  # too near zero — no opinion, defer to astro
            else:  # KRONOS_UNAVAILABLE / NO_DATA — no opinion, defer to astro
                e = '·'
            print(f"  {e} {t}: {status} | Kronos {r['kronos_dir']} {r['kronos_pct']:+.1f}% | Conv {r['boosted_conviction']}x")

    # Mean-reversion overlay (Renaissance-style)
    if tickers == FUTURES:
        print(f"\n  {'─'*55}")
        print(f"  MEAN-REVERSION CHECK (Renaissance)")
        print(f"  {'─'*55}")
        try:
            from signals_meanrev import meanrev_signal
            for t in tickers:
                sd = all_sigs.get((t, "daily"))
                if not sd: continue
                inst = __import__('astro_configs').INSTRUMENTS.get(t)
                sym = inst.data_symbol or f'{t}=F'
                mr = meanrev_signal(t, symbol=sym)
                if mr and mr['signal'] != 'NEUTRAL':
                    match = '✅' if mr['signal'] == sd['direction'] else '⚠'
                    print(f"  {match} {t}: {mr['action']}")
                elif mr:
                    print(f"  - {t}: no reversal extreme (z={mr['z_score']})")
                else:
                    print(f"  - {t}: no data")
        except Exception as e:
            print(f"  Mean-rev unavailable: {e}")

    # 0DTE filter (unchanged)
    if tickers == FUTURES:
        print(f"\n  {'─'*55}")
        print(f"  0DTE ELIGIBILITY")
        print(f"  {'─'*55}")
        try:
            from signals_0dte import evaluate_0dte
            for t in tickers:
                sd = all_sigs.get((t, "daily"))
                if not sd: 
                    print(f"  - {t}: no signal")
                    continue
                # Use corrected HMM (from _hmm function above) + precomputed Kronos
                regime = regimes.get(t, "default")
                kron = kronos_map.get(t)
                moon = sd.get("moon_applies", "void")
                r = evaluate_0dte(sd, kron, {"regime": regime}, moon)
                tag = f"{'✅ 0DTE OK' if r['ok'] else '❌ block'}"
                print(f"  {tag} {t}: {r['suggested']} | {r['reason']}")
                # Paper 0DTE option pick when gate passes (PAPER ONLY)
                if r['ok']:
                    try:
                        from signals_0dte_execute import build_0dte
                        acct = float(os.environ.get("ACCOUNT_SIZE", 25000))
                        e = build_0dte(t, sd['direction'], acct)
                        if 'error' in e:
                            print(f"       (no option: {e['error']})")
                        else:
                            print(f"       → {e['option']} Δ{e['delta']} ${e['mid_premium']} x{e['contracts']} "
                                  f"debit ${e['debit_total']:,.0f} [{e['premium_pct_account']}% acct] PAPER")
                    except Exception as ex:
                        print(f"       (0DTE pick failed: {ex})")
        except Exception as e:
            print(f"  0DTE unavailable: {e}")

    nq = all_sigs.get(("NQ", "daily"), {})
    if "NQ" in tickers and nq.get("match_type") != "exact":
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
        ds = ds or datetime.now().strftime("%Y-%m-%d")
        if len(dates) > 1:
            print(f"\n{'─'*55}")
            print(f"  >>> {ds} <<<")

        print(f"\n{'█'*55}")
        print(f"  FUTURES — {ds}")
        print(f"{'█'*55}")
        _run_group("FUTURES", FUTURES, ds, show_tf=True)

    print(f"\n  v0.64 — {label}")

if __name__ == "__main__":
    main()
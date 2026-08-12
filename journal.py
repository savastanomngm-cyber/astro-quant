#!/usr/bin/env python3
"""
ASTRO-QUANT TRADE JOURNAL — Track every signal, entry, and exit.
==============================================================
  python3 journal.py                      # view dashboard
  python3 journal.py log NQ LONG 1.0      # log a trade you took
  python3 journal.py close NQ +1250       # close with P&L
  python3 journal.py skip NQ              # log a signal you skipped
  python3 journal.py stats                # lifetime stats
  python3 journal.py export               # CSV export
"""
import os, sys, json
from datetime import datetime, timedelta
from pathlib import Path

JOURNAL_DIR = os.path.expanduser("~/.astro-quant/journal")
JOURNAL_FILE = os.path.join(JOURNAL_DIR, "trades.json")

def _load():
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE) as f:
            return json.load(f)
    return {"trades": [], "stats": {"total_pnl": 0, "wins": 0, "losses": 0, "skipped": 0}}

def _save(data):
    with open(JOURNAL_FILE, "w") as f:
        json.dump(data, f, indent=2)

def cmd_dashboard():
    data = _load()
    trades = data["trades"]
    stats = data["stats"]
    if not trades:
        print("No trades logged yet. Use: python3 journal.py log NQ LONG")
        return

    open_trades = [t for t in trades if t["status"] == "open"]
    closed = [t for t in trades if t["status"] == "closed"]
    skipped = [t for t in trades if t["status"] == "skipped"]

    print(f"╔{'═'*55}╗")
    print(f"║  TRADE JOURNAL  —  {stats['total_pnl']:+,.0f} lifetime P&L  ║")
    print(f"║  {len(closed)} closed | {len(open_trades)} open | {len(skipped)} skipped  ║")
    print(f"╚{'═'*55}╝\n")

    if open_trades:
        print(f"  OPEN POSITIONS:")
        for t in open_trades:
            days = (datetime.now() - datetime.fromisoformat(t["date"])).days
            print(f"  {t['ticker']:<6} {t['direction']:<6} entry={t['entry_date']} ({days}d ago)  SL={t['sl']} TP={t['tp']}")

    if closed:
        print(f"\n  RECENTLY CLOSED:")
        for t in closed[-10:]:
            d = datetime.fromisoformat(t["close_date"]).strftime("%b %d")
            pnl_s = f"+${t['pnl']:,.0f}" if t['pnl'] > 0 else f"-${abs(t['pnl']):,.0f}"
            print(f"  {t['ticker']:<6} {t['direction']:<6} {t['entry_date']} → {d}  {pnl_s}  {t['exit_reason']}")

    wr = stats["wins"] / max(1, stats["wins"] + stats["losses"])
    print(f"\n  Win rate: {wr:.0%} ({stats['wins']}W / {stats['losses']}L / {stats['skipped']} skipped)")

def cmd_log():
    if len(sys.argv) < 4:
        print("Usage: python3 journal.py log TICKER DIRECTION CONVICTION [SL] [TP] [HOLD]")
        return
    ticker = sys.argv[2].upper()
    direction = sys.argv[3].upper()
    conv = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    sl = sys.argv[5] if len(sys.argv) > 5 else "?"
    tp = sys.argv[6] if len(sys.argv) > 6 else "?"
    hold = sys.argv[7] if len(sys.argv) > 7 else "?"

    data = _load()
    data["trades"].append({
        "ticker": ticker, "direction": direction, "conviction": conv,
        "sl": sl, "tp": tp, "hold": hold,
        "date": datetime.now().isoformat(),
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "open", "pnl": 0, "close_date": None, "exit_reason": None,
    })
    _save(data)
    print(f"  Logged: {ticker} {direction} (conv={conv}x, SL={sl}, TP={tp})")
    print(f"  Active positions: {sum(1 for t in data['trades'] if t['status']=='open')}")

def cmd_close():
    if len(sys.argv) < 4:
        print("Usage: python3 journal.py close TICKER PNL [reason]")
        return
    ticker = sys.argv[2].upper()
    pnl = float(sys.argv[3])
    reason = sys.argv[4] if len(sys.argv) > 4 else "manual"

    data = _load()
    open_trades = [t for t in data["trades"] if t["status"] == "open" and t["ticker"] == ticker]
    if not open_trades:
        print(f"  No open trades for {ticker}")
        return

    t = open_trades[-1]
    t["status"] = "closed"
    t["pnl"] = pnl
    t["close_date"] = datetime.now().isoformat()
    t["exit_reason"] = reason
    data["stats"]["total_pnl"] += pnl
    if pnl > 0:
        data["stats"]["wins"] += 1
    else:
        data["stats"]["losses"] += 1
    _save(data)
    pnl_s = f"+${pnl:,.0f}" if pnl > 0 else f"-${abs(pnl):,.0f}"
    print(f"  Closed: {ticker} → {pnl_s} ({reason})")
    print(f"  Lifetime P&L: {data['stats']['total_pnl']:+,.0f}")

def cmd_skip():
    ticker = sys.argv[2].upper() if len(sys.argv) > 2 else "?"
    data = _load()
    data["trades"].append({
        "ticker": ticker, "direction": "SKIPPED",
        "date": datetime.now().isoformat(),
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "skipped",
    })
    data["stats"]["skipped"] += 1
    _save(data)
    print(f"  Skipped: {ticker}")

def cmd_stats():
    data = _load()
    stats = data["stats"]
    trades = [t for t in data["trades"] if t["status"] == "closed"]
    print(f"  Lifetime P&L: {stats['total_pnl']:+,.0f}")
    print(f"  Closed: {stats['wins']}W / {stats['losses']}L / {stats['skipped']} skipped")
    wr = stats["wins"] / max(1, stats["wins"] + stats["losses"])
    print(f"  Win rate: {wr:.0%}")
    if trades:
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        avg_w = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_l = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0
        print(f"  Avg win: ${avg_w:,.0f}  Avg loss: ${avg_l:,.0f}")
        if avg_l > 0:
            print(f"  Profit factor: {sum(t['pnl'] for t in wins) / abs(sum(t['pnl'] for t in losses)):.2f}" if losses else "  PF: ∞")

def cmd_export():
    data = _load()
    path = os.path.join(JOURNAL_DIR, f"export_{datetime.now().strftime('%Y%m%d')}.csv")
    with open(path, "w") as f:
        f.write("ticker,direction,entry_date,close_date,pnl,exit_reason,status\n")
        for t in data["trades"]:
            f.write(f"{t['ticker']},{t['direction']},{t['entry_date']},{t.get('close_date','')},{t.get('pnl',0)},{t.get('exit_reason','')},{t['status']}\n")
    print(f"  Exported: {path}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    {"dashboard": cmd_dashboard, "log": cmd_log, "close": cmd_close,
     "skip": cmd_skip, "stats": cmd_stats, "export": cmd_export}.get(cmd, cmd_dashboard)()
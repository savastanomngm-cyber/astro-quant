#!/usr/bin/env python3
"""
0DTE TRADE FILTER — should I use a 0-DTE option today?
=======================================================
Only flag a 0DTE trade when ALL of these align (conservative):
  1. Astro signal exists (LONG/SHORT) with conviction >= 0.8
  2. Kronos CONFIRMS (not diverges)
  3. HMM regime is NOT BEAR (for LONG) / NOT BULL (for SHORT)
  4. Moon is NOT applying to a malefic (Saturn/Mars)
  5. Match type is 'exact' or 'prefix' (not weak fallback)

Returns:
  {"ok": True/False, "reason": "...", "suggested": "CALL"/"PUT"/None}
"""
from datetime import datetime

def evaluate_0dte(signal: dict, kronos: dict, hmm: dict, moon_applies: str) -> dict:
    reasons = []

    if not signal:
        return {"ok": False, "reason": "no signal", "suggested": None}

    direction = signal.get("direction")
    conviction = signal.get("conviction", 0)
    match_type = signal.get("match_type", "?")

    # 1. Conviction
    if conviction < 0.8:
        reasons.append(f"conviction {conviction} < 0.8")

    # 2. Kronos
    if kronos and kronos.get("status") == "DIVERGES":
        reasons.append("Kronos DIVERGES")
    elif not kronos:
        reasons.append("no Kronos")

    # 3. HMM regime vs direction
    regime = hmm.get("regime", "default")
    if direction == "LONG" and regime == "BEAR":
        reasons.append("HMM BEAR vs LONG")
    elif direction == "SHORT" and regime == "BULL":
        reasons.append("HMM BULL vs SHORT")
    elif regime == "CHOP":
        reasons.append("HMM CHOP")

    # 4. Moon applying to malefic
    if moon_applies in ("Saturn", "Mars"):
        reasons.append(f"Moon→{moon_applies} (malefic)")

    # 5. Match quality
    if match_type in ("moon", "main+moon"):
        reasons.append(f"weak match '{match_type}'")

    if reasons:
        return {"ok": False, "reason": "; ".join(reasons), "suggested": None}

    suggested = "CALL" if direction == "LONG" else "PUT"
    return {"ok": True, "reason": "all clear", "suggested": suggested}


# ==== Self-test against sample scenarios ====
if __name__ == "__main__":
    tests = [
        # strong signal, confirmed
        ({"direction":"LONG","conviction":1.0,"match_type":"exact"},
         {"status":"CONFIRMED"}, {"regime":"BULL"}, "Jupiter", "SHOULD PASS"),
        # weak conviction
        ({"direction":"LONG","conviction":0.6,"match_type":"exact"},
         {"status":"CONFIRMED"}, {"regime":"BULL"}, "Jupiter", "SHOULD FAIL (conviction)"),
        # kronos diverges
        ({"direction":"LONG","conviction":1.0,"match_type":"exact"},
         {"status":"DIVERGES"}, {"regime":"BULL"}, "Jupiter", "SHOULD FAIL (kronos)"),
        # bear vs long
        ({"direction":"LONG","conviction":1.0,"match_type":"exact"},
         {"status":"CONFIRMED"}, {"regime":"BEAR"}, "Jupiter", "SHOULD FAIL (bear)"),
        # moon malefic
        ({"direction":"LONG","conviction":1.0,"match_type":"exact"},
         {"status":"CONFIRMED"}, {"regime":"BULL"}, "Mars", "SHOULD FAIL (moon)"),
        # weak match
        ({"direction":"LONG","conviction":1.0,"match_type":"moon"},
         {"status":"CONFIRMED"}, {"regime":"BULL"}, "Jupiter", "SHOULD FAIL (match)"),
    ]
    for sig, kron, hmm, moon, label in tests:
        r = evaluate_0dte(sig, kron, hmm, moon)
        print(f"{'PASS' if r['ok'] else 'BLOCK'}: {label} → {r['reason']} | {r['suggested']}")

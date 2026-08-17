import json, os, numpy as np
from collections import defaultdict
from scipy.stats import chi2_contingency

recs = json.load(open(".correlation_cache_multifold.json"))
for r in recs: r["win"] = 1 if r["pnl"]>0 else 0

# Fold x ticker for ALL three
by_ft = defaultdict(lambda: {"n":0,"wins":0,"pnl":[]})
for r in recs:
    k=(r["fold"],r["ticker"]); by_ft[k]["n"]+=1; by_ft[k]["wins"]+=r["win"]; by_ft[k]["pnl"].append(r["pnl"])

print("FOLD x TICKER — win rate by fold type (all tickers)")
print(f"{'fold':>10} {'ticker':>6} {'n':>5} {'WR':>7} {'PF':>7}")
for tk in ["GC","NQ","ES"]:
    for fold in ["exact","prefix"]:
        d=by_ft.get((fold,tk),{"n":0,"wins":0,"pnl":[0]})
        if d["n"]<5: continue
        wr=d["wins"]/d["n"]*100
        wins=[p for p in d["pnl"] if p>0]; losses=[p for p in d["pnl"] if p<=0]
        pf=sum(wins)/abs(sum(losses)) if losses else 99
        print(f"{fold:>10} {tk:>6} {d['n']:>5} {wr:>6.0f}% {pf:>7.2f}")

# Chi2 per ticker
print("\nCHI2 TEST: exact vs prefix (significance)")
for tk in ["GC","NQ","ES"]:
    e=by_ft.get(("exact",tk),{"n":0,"wins":0})
    p=by_ft.get(("prefix",tk),{"n":0,"wins":0})
    if e["n"]<5 or p["n"]<5: continue
    el=e["n"]-e["wins"]; pl=p["n"]-p["wins"]
    table=[[e["wins"],el],[p["wins"],pl]]
    try:
        c2,pv,*_=chi2_contingency(table)
        print(f"  {tk}: exact {e['wins']}/{e['n']}={e['wins']/e['n']*100:.0f}% vs prefix {p['wins']}/{p['n']}={p['wins']/p['n']*100:.0f}%  p={pv:.4f} {'✓' if pv<0.05 else 'NS'}")
    except:
        print(f"  {tk}: chi2 fail")

# Total cached info
tickers = sorted(set(r["ticker"] for r in recs))
print(f"\nCache: {len(recs)} trades, tickers: {tickers}")
for tk in tickers:
    n = sum(1 for r in recs if r["ticker"]==tk)
    print(f"  {tk}: {n} trades")

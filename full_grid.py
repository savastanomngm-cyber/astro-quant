import json, numpy as np
from itertools import product
recs = json.load(open(".correlation_cache_multifold.json"))
for r in recs: r["win"]=1 if r["pnl"]>0 else 0

folds=sorted(set(r["fold"] for r in recs))
moons=sorted(set(r["moon"] for r in recs))
krons=sorted(set(r["kronos"] for r in recs))
tickers=sorted(set(r["ticker"] for r in recs))

res=[]
for f,m,k,t in product(folds,moons,krons,tickers):
    s=[r for r in recs if r["fold"]==f and r["moon"]==m and r["kronos"]==k and r["ticker"]==t]
    if len(s)<8: continue
    wins=[r for r in s if r["pnl"]>0]; loss=[r for r in s if r["pnl"]<=0]
    pf=sum(r["pnl"] for r in wins)/abs(sum(r["pnl"] for r in loss)) if loss else 99
    wr=len(wins)/len(s)
    res.append((pf,f,m,k,t,len(s),wr,round(np.mean([r["pnl"] for r in s]))))

res.sort(key=lambda x:-x[0])
print(f"Combos n>=8: {len(res)}")
print(f"{'PF':>6} {'fold':>10} {'moon':>8} {'kronos':>11} {'tk':>3} {'n':>4} {'WR':>6} {'avg':>7}")
for pf,f,m,k,t,n,wr,avg in res[:40]:
    print(f"{pf:>6.2f} {f:>10} {m:>8} {k:>11} {t:>3} {n:>4} {wr*100:>5.0f}% {avg:>+7}")

# also bottom (worst) combos
print("\n--- WORST ---")
for pf,f,m,k,t,n,wr,avg in res[-12:]:
    print(f"{pf:>6.2f} {f:>10} {m:>8} {k:>11} {t:>3} {n:>4} {wr*100:>5.0f}% {avg:>+7}")

# tally fold counts to confirm ES exact significance
print("\n--- ES exact breakdown ---")
es_exact=[r for r in recs if r["ticker"]=="ES" and r["fold"]=="exact"]
es_rest=[r for r in recs if r["ticker"]=="ES" and r["fold"]!="exact"]
print(f"ES exact: {sum(r['win'] for r in es_exact)}/{len(es_exact)} = {sum(r['win'] for r in es_exact)/len(es_exact)*100:.0f}%  (n={len(es_exact)})")
print(f"ES other: {sum(r['win'] for r in es_rest)}/{len(es_rest)} = {sum(r['win'] for r in es_rest)/len(es_rest)*100:.0f}%  (n={len(es_rest)})")

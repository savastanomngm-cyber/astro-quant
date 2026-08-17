import json, numpy as np
from collections import defaultdict
from itertools import product
from scipy.stats import chi2_contingency

recs = json.load(open(".correlation_cache_multifold.json"))
for r in recs: r["win"]=1 if r["pnl"]>0 else 0
T = ["GC","NQ","ES"]

def agg(recs, keyfn, min_n=10):
    d=defaultdict(lambda:{"n":0,"w":0,"pnl":[]})
    for r in recs:
        k=keyfn(r); d[k]["n"]+=1; d[k]["w"]+=r["win"]; d[k]["pnl"].append(r["pnl"])
    out=[]
    for k,v in d.items():
        if v["n"]<min_n: continue
        wr=v["w"]/v["n"]; wins=[p for p in v["pnl"] if p>0]; loss=[p for p in v["pnl"] if p<=0]
        pf=sum(wins)/abs(sum(loss)) if loss else 99
        out.append((k,v["n"],wr,pf,np.mean(v["pnl"])))
    return sorted(out,key=lambda x:-x[2])

# 1. FOLD x TICKER
print("="*70); print("FOLD x TICKER (n>=10)"); print("="*70)
for k,n,wr,pf,avg in agg(recs, lambda r:(r["fold"],r["ticker"])):
    print(f"  {k[0]:>10} {k[1]:>4} n={n:>4} WR={wr*100:>5.0f}% PF={pf:>6.2f} avg={avg:+6.0f}")

# 2. MOON x TICKER
print("\n"+"="*70); print("MOON x TICKER (n>=10)"); print("="*70)
for k,n,wr,pf,avg in agg(recs, lambda r:(r["moon"],r["ticker"])):
    print(f"  {k[0]:>8} {k[1]:>4} n={n:>4} WR={wr*100:>5.0f}% PF={pf:>6.2f} avg={avg:+6.0f}")

# 3. KRONOS x TICKER
print("\n"+"="*70); print("KRONOS x TICKER (n>=10)"); print("="*70)
for k,n,wr,pf,avg in agg(recs, lambda r:(r["kronos"],r["ticker"])):
    print(f"  {k[0]:>12} {k[1]:>4} n={n:>4} WR={wr*100:>5.0f}% PF={pf:>6.2f} avg={avg:+6.0f}")

# 4. CONVICTION x TICKER
print("\n"+"="*70); print("CONVICTION x TICKER (n>=10)"); print("="*70)
for k,n,wr,pf,avg in agg(recs, lambda r:(r["conviction"],r["ticker"])):
    print(f"  {k[0]:>8} {k[1]:>4} n={n:>4} WR={wr*100:>5.0f}% PF={pf:>6.2f} avg={avg:+6.0f}")

# 5. Chi2 significance per factor (pooled across tickers)
print("\n"+"="*70); print("SIGNIFICANCE (chi2, pooled)"); print("="*70)
for factor in ["fold","moon","kronos","conviction"]:
    cats = sorted(set(r[factor] for r in recs))
    if len(cats)<2: continue
    # compare each cat vs rest
    for c in cats:
        a=[r for r in recs if r[factor]==c]; b=[r for r in recs if r[factor]!=c]
        if len(a)<10 or len(b)<10: continue
        aw=sum(x["win"] for x in a); al=len(a)-aw
        bw=sum(x["win"] for x in b); bl=len(b)-bw
        c2,pv,*_=chi2_contingency([[aw,al],[bw,bl]])
        flag="SIG" if pv<0.05 else "ns"
        print(f"  {factor}='{c}': {aw}/{len(a)}={aw/len(a)*100:.0f}% vs rest {bw}/{len(b)}={bw/len(b)*100:.0f}%  p={pv:.4f} {flag}")

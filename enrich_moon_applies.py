"""Add moon_applies field to cached enriched trades (lazy: compute for each date).
This directly tests the Rectification Manual's claim: Moon applies to benefic/malefic → WR/PF difference."""
import sys, os; sys.path.insert(0,'.'); sys.path.insert(0, os.path.expanduser('~/workspace/kronos'))
import json; from collections import defaultdict; import numpy as np
from datetime import datetime
from pattern_engine_v3 import load_rectified, get_state, state_key

recs = json.load(open('.correlation_cache_multifold.json'))

# Compute moon_applies per record using the rectified chart at date+17:00
from astro_configs import INSTRUMENTS
from astro_core_v2 import calculate_chart

# Pre-load charts
charts = {}
for t in ['GC','NQ','ES']:
    inst = INSTRUMENTS[t]
    rect = load_rectified().get(t)
    if not rect: continue
    utc_dt = datetime(inst.birth_year,inst.birth_month,inst.birth_day,rect['hour'],rect['min'],rect['sec'])
    local_dt = utc_dt + __import__('datetime').timedelta(hours=inst.birth_tz)
    chart_dict = calculate_chart(local_dt.year,local_dt.month,local_dt.day,local_dt.hour,local_dt.minute,local_dt.second,inst.birth_lat,inst.birth_lon,inst.birth_tz)
    charts[t] = chart_dict

enriched = 0
for r in recs:
    t = r['ticker']
    ds = r['date']
    chart = charts.get(t)
    if not chart: r['moon_applies']='unknown'; continue
    d = datetime.strptime(ds,'%Y-%m-%d').replace(hour=17)
    st = get_state(chart, d)
    r['moon_applies'] = st.get('moon_applies','void')
    r['win'] = 1 if r['pnl']>0 else 0
    enriched += 1
    if enriched % 200 == 0: print(f"  {enriched} done...", flush=True)

print(f'Enriched {len(recs)} records with moon_applies')

# Cross-tab
for t in ['GC','NQ','ES']:
    sub=[r for r in recs if r['ticker']==t]
    print(f'\n===== {t} (n={len(sub)}) =====')
    d=defaultdict(lambda:[[],[]])
    for r in sub:
        ma=r.get('moon_applies','void')
        d[ma][0].append(r['pnl']); d[ma][1].append(r['win'])
    # also: benefic vs malefic
    def cat(ma):
        if ma in ('Venus','Jupiter'): return 'benefic'
        if ma in ('Saturn','Mars'): return 'malefic'
        return 'neutral'
    bm=defaultdict(lambda:[[],[]])
    for r in sub:
        c=cat(r.get('moon_applies','void'))
        bm[c][0].append(r['pnl']); bm[c][1].append(r['win'])
    for label,dstore in [('per-planet',d),('benefic/malefic',bm)]:
        print(f'  --- {label} ---')
        for k,(pnls,wins) in sorted(dstore.items(),key=lambda kv: sum(kv[1][1])/max(1,len(kv[1][1])), reverse=True):
            n=len(pnls)
            if n<5: continue
            wr=sum(wins)/n
            gw=sum(p for p in pnls if p>0); gl=abs(sum(p for p in pnls if p<=0))
            pf=gw/gl if gl>0 else 99
            print(f'    {k:>10}: n={n:>4} WR={wr*100:>5.0f}% PF={pf:>6.2f} avg={np.mean(pnls):+6.0f}')

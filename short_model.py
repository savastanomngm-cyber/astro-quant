"""Rule-based SHORT model — short the anti-long conditions with real short P&L.
Reuses the enriched cache (638 trades with fold/moon/kronos) + real OHLC for short simulation."""
import sys, os; sys.path.insert(0,'.')
import json, numpy as np
from collections import defaultdict
import yfinance as yf, pandas as pd
from astro_configs import INSTRUMENTS

# load enriched records: each has date, ticker, pnl(LONG), fold/moon/kronos/conviction
recs = json.load(open('.correlation_cache_multifold.json'))

def load_ohlc(ticker):
    inst=INSTRUMENTS[ticker]; sym=inst.data_symbol or f'{ticker}=F'
    d=yf.Ticker(sym).history(start='2010-01-01')
    if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
    d=d[['Open','High','Low','Close']]
    return d

def short_trade(ticker, entry_date, dd_index, stop_pct=0.01, tp_pct=0.03, hold=10):
    """Simulate a SHORT from entry_date open. Return points P&L (as % * some scale)."""
    # We'll work in raw price; return dollar-ish via index points
    pass

# Build OHLC dictionaries per ticker keyed by date
ohlc = {}
for t in ['GC','NQ','ES']:
    d = load_ohlc(t)
    m = {}
    for idx,row in d.iterrows():
        m[idx.strftime('%Y-%m-%d')] = (float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']))
    sortkeys = sorted(m.keys())
    ohlc[t] = (m, sortkeys)
    print(f'{t}: {len(sortkeys)} bars loaded', flush=True)

# Candidate short conditions (from the anti-long analysis)
conditions = {
    'neutral_moon':        lambda r: r['moon']=='neutral',
    'gc_confirmed':        lambda r: r['ticker']=='GC' and r['kronos']=='CONFIRMED',
    'es_mainmoon':         lambda r: r['ticker']=='ES' and r['fold']=='main+moon',
    'nq_mainmoon':         lambda r: r['ticker']=='NQ' and r['fold']=='main+moon',
    'gc_neutral_conf':     lambda r: r['ticker']=='GC' and r['moon']=='neutral' and r['kronos']=='CONFIRMED',
    'gc_pref_malefic_conf':lambda r: r['ticker']=='GC' and r['fold']=='prefix' and r['moon']=='malefic' and r['kronos']=='CONFIRMED',
    'neutral_all':         lambda r: r['moon']=='neutral',
    'malefic_diverges_gc': lambda r: r['ticker']=='GC' and r['moon']=='malefic' and r['kronos']=='DIVERGES',
}

def simulate_short(ticker, entry_date, stop_pct, tp_pct, hold):
    """Return net points (in price units) of a short."""
    m, keys = ohlc[ticker]
    if entry_date not in m: return None, 'no_entry'
    # find index
    try: i = keys.index(entry_date)
    except ValueError: return None,'no_entry'
    o,h,l,c = m[entry_date]
    ep = o
    sl = ep*(1+stop_pct); tp = ep*(1-tp_pct)
    end = min(i+hold, len(keys)-1)
    for j in range(i, end+1):
        _,bh,bl,_ = m[keys[j]]
        if bh >= sl: return -(stop_pct*ep), 'stop'   # short stopped out (price rose)
        if bl <= tp: return +(tp_pct*ep), 'target'   # short took profit (price fell)
    xc = m[keys[end]][3]
    return (ep - xc), 'time'   # short profit = entry - exit

print("\n=== SHORT MODEL BACKTEST (real short P&L) ===")
print(f"{'condition':>24} {'tkr':>3} {'n':>4} {'WR':>6} {'PF':>6} {'avg_pts':>8} {'exit':>22}")
all_results=[]
for name, fn in conditions.items():
    matches=[r for r in recs if fn(r)]
    if not matches: continue
    bytk = defaultdict(list)
    for r in matches: bytk[r['ticker']].append(r)
    for tk, rs in bytk.items():
        tr=[]; exits=defaultdict(int)
        for r in rs:
            pnl, why = simulate_short(tk, r['date'], 0.01, 0.03, 10)
            if pnl is not None:
                tr.append(pnl); exits[why]+=1
        if not tr: continue
        w=sum(1 for p in tr if p>0); n=len(tr)
        wr=w/n
        gw=sum(p for p in tr if p>0); gl=abs(sum(p for p in tr if p<=0))
        pf=gw/gl if gl>0 else (99 if gw>0 else 0)
        avg=np.mean(tr)
        exstr=' '.join(f'{k}{v}' for k,v in sorted(exits.items()))
        all_results.append((name,tk,n,wr,pf,avg,exstr))
        print(f"{name:>24} {tk:>3} {n:>4} {wr*100:>5.0f}% {pf:>6.2f} {avg:>+8.1f} {exstr:>22}")

print(f"\n=== summary: conditions with short WR > 50% and PF > 1.1 ===")
for name,tk,n,wr,pf,avg,ex in sorted(all_results, key=lambda x:-x[3]):
    if wr>0.50 and pf>1.1:
        print(f"  {name} {tk}: WR={wr*100:.0f}% PF={pf:.2f} avg={avg:+.1f} (n={n})")

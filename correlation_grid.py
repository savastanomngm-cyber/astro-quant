#!/usr/bin/env python3
"""
CORRELATION GRID — find most profitable signal combinations.
Joins OOS persona trades with fold/moon/kronos/conviction,
then grids all combinations and ranks by profit factor.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.expanduser('~/workspace/kronos'))
import numpy as np
import json, os
from datetime import datetime, timedelta
from collections import defaultdict
import yfinance as yf
from itertools import product

CACHE = os.path.join(os.path.dirname(__file__), '.correlation_cache.json')

from astro_matraix_backtest import persona_backtest_flow
from daily_signal_report import generate_daily_signal
from astro_matraix_kronos import KronosConfirmer
import astro_configs as ac

kc = KronosConfirmer(); kc._ensure_loaded()

def moon_cat(m):
    """benefic / malefic / neutral"""
    return 'benefic' if m in ('Jupiter','Venus') else ('malefic' if m in ('Saturn','Mars') else 'neutral')

def fold_cat(mt):
    """Simplify match_type to fold tier"""
    if mt in ('exact','prefix','main+moon','main','moon'): return mt
    return mt

def conv_band(c):
    """high/mid/low."""
    c=float(c) if c else 0.5
    return 'high' if c>=0.7 else ('low' if c<0.3 else 'mid')

def kronos_for(ticker, date_str, df_all):
    """Kronos status at a given date. df_all = OHLC sorted price history."""
    d = datetime.strptime(date_str,'%Y-%m-%d')
    if df_all.index.tz is not None:
        d = d.replace(tzinfo=df_all.index.tz)
    w = df_all.loc[:d].tail(120)
    if len(w)<30: return 'NEUTRAL'
    try:
        k = kc.confirm_signal(ticker, {'direction':'LONG','conviction':0.7,
            'sl_pct':0.007,'tp_pct':0.02}, df=w)
        return k.get('status')
    except: return 'NEUTRAL'

def load_price(ticker):
    inst = ac.INSTRUMENTS[ticker]
    sym = inst.data_symbol or f'{ticker}=F'
    data = yf.Ticker(sym).history(start='2017-01-01')[['Open','High','Low','Close','Volume']].copy()
    data.columns=['open','high','low','close','volume']
    return data.sort_index()

def enrich(ticker, start):
    """Pull OOS trades + signals per date, enrich with fold/moon/kronos."""
    print(f"  {ticker}: backtest...", flush=True)
    br = persona_backtest_flow(ticker=ticker, yahoo_start=start,
                               use_short_signals=True, verbose=False)
    if not br or not br.out_of_sample or not br.oos_trades:
        print(f"    no OOS"); return []
    trades = br.oos_trades
    print(f"    {len(trades)} OOS trades, loading signals...", flush=True)
    df_price = load_price(ticker)

    # Generate signal for EACH OOS trade date (slow, ~3-5s per date)
    records = []
    for t in trades:
        date_str = t.date
        # Generate signal
        sig = generate_daily_signal(ticker, date_str=date_str)
        if not sig:
            # fall back to generic
            rec = {'date':date_str, 'pnl':t.net_points, 'fold':'unknown',
                   'moon':'neutral', 'kronos':'NEUTRAL', 'conviction':'mid',
                   'ticker':ticker}
        else:
            k = kronos_for(ticker, date_str, df_price)
            rec = {'date':date_str, 'pnl':t.net_points,
                   'fold':fold_cat(sig.get('match_type','unknown')),
                   'moon':moon_cat(sig.get('moon_applies','void')),
                   'kronos':k,
                   'conviction':conv_band(sig.get('conviction',0.5)),
                   'ticker':ticker}
        records.append(rec)
    return records

def grid(records, min_n=5):
    """Grid fold x moon x kronos x ticker and rank by PF."""
    folds    = sorted(set(r['fold'] for r in records))
    moons    = sorted(set(r['moon'] for r in records))
    kronoses = sorted(set(r['kronos'] for r in records))
    tickers  = sorted(set(r['ticker'] for r in records))
    results = []
    for f, m, k, tk in product(folds, moons, kronoses, tickers):
        subset = [r for r in records if r['fold']==f and r['moon']==m and r['kronos']==k and r['ticker']==tk]
        if len(subset) < min_n: continue
        nets = [r['pnl'] for r in subset]
        n=len(nets)
        wins=[x for x in nets if x>0]; losses=[x for x in nets if x<=0]
        wr = len(wins)/n
        gw=sum(wins); gl=abs(sum(losses))
        pf = gw/gl if gl>0 else 99.0
        results.append((pf, f, m, k, tk, n, wr, np.mean(nets), len(wins)))
    results.sort(reverse=True, key=lambda x:x[0])
    return results

def main():
    print("="*100)
    print("CORRELATION GRID: fold × moon × kronos × ticker (≥5 trades stable)")
    print("="*100)
    all_recs = []
    if os.path.exists(CACHE):
        all_recs = json.load(open(CACHE))
        print(f"Loaded {len(all_recs)} enriched trades from cache")
    else:
        for ticker in ['NQ','GC']:
            recs = enrich(ticker, '2019-01-01')
            all_recs += recs
        json.dump(all_recs, open(CACHE,'w'))
        print(f"Enriched + cached {len(all_recs)} trades")
    print(f"\nTotal enriched trades: {len(all_recs)}")
    results = grid(all_recs, min_n=5)
    print(f"Combos with ≥5 trades: {len(results)}")
    print(f"\n{'rank':>4} {'PF':>6} {'WR':>6} {'n':>4} {'avg':>8} {'fold':>10} {'moon':>8} {'kronos':>11} {'ticker':>6}")
    print("-"*100)
    for i,(pf,f,m,k,tk,n,wr,avg,wins) in enumerate(results[:35]):
        print(f"{i+1:>4} {pf:>6.2f} {wr:>5.0%} {n:>4} {avg:>+7.0f} {f:>10} {m:>8} {k:>11} {tk:>6}")
    # Save CSV
    import csv
    with open('/home/user/workspace/astro-quant/correlation_grid_results.csv','w',newline='') as fh:
        w=csv.writer(fh)
        w.writerow(['rank','PF','WR','n','avg_pnl','fold','moon','kronos','ticker'])
        for i,(pf,f,m,k,tk,n,wr,avg,wins) in enumerate(results):
            w.writerow([i+1,f"{pf:.2f}",f"{wr:.2%}",n,f"{avg:.1f}",f,m,k,tk])
    print(f"\n✓ Saved {len(results)} combos to correlation_grid_results.csv")

if __name__ == '__main__':
    main()
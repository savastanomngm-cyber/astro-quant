#!/usr/bin/env python3
"""
CORRELATION GRID — find most profitable signal combinations.
Pulls OOS trades across MULTIPLE non-overlapping walk-forward folds
so that GC, NQ, and ES all get balanced representation (200-300+ trades).

Joins each OOS trade with its fold/moon/kronos/conviction from the
daily signal + Kronos, then grids all combinations and ranks by PF.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.expanduser('~/workspace/kronos'))
import numpy as np
import json
from datetime import datetime, timedelta
from itertools import product
import yfinance as yf

from astro_matraix_backtest import persona_backtest_flow
from daily_signal_report import generate_daily_signal
from astro_matraix_kronos import KronosConfirmer
import astro_configs as ac

kc = KronosConfirmer(); kc._ensure_loaded()
CACHE = os.path.join(os.path.dirname(__file__), '.correlation_cache_multifold.json')

# ── helpers ──────────────────────────────────────────────────────────
def moon_cat(m):
    return 'benefic' if m in ('Jupiter','Venus') else ('malefic' if m in ('Saturn','Mars') else 'neutral')

def fold_cat(mt):
    return mt if mt in ('exact','prefix','main+moon','main','moon') else mt

def conv_band(c):
    c=float(c) if c else 0.5
    return 'high' if c>=0.7 else ('low' if c<0.3 else 'mid')

def kronos_for(ticker, date_str, df_price):
    d = datetime.strptime(date_str,'%Y-%m-%d')
    if df_price.index.tz is not None:
        d = d.replace(tzinfo=df_price.index.tz)
    w = df_price.loc[:d].tail(120)
    if len(w) < 30: return 'NEUTRAL'
    try:
        k = kc.confirm_signal(ticker, {'direction':'LONG','conviction':0.7,
            'sl_pct':0.007,'tp_pct':0.02}, df=w)
        return k.get('status')
    except: return 'NEUTRAL'

def load_price(ticker):
    inst = ac.INSTRUMENTS[ticker]
    sym = inst.data_symbol or f'{ticker}=F'
    data = yf.Ticker(sym).history(start='2010-01-01')[['Open','High','Low','Close','Volume']].copy()
    data.columns=['open','high','low','close','volume']
    return data.sort_index()

# ── multi-fold enrichment ────────────────────────────────────────────
def enrich_multifold(tickers=('NQ','GC'), folds=('2010-01-01','2015-01-01','2020-01-01')):
    """Run persona_backtest_flow for each fold start, collect all OOS trades, enrich each."""
    all_recs = []
    for start in folds:
        for ticker in tickers:
            print(f"  {ticker} @ fold start {start}...", flush=True, end=" ")
            try:
                br = persona_backtest_flow(ticker=ticker, yahoo_start=start,
                                           use_short_signals=True, verbose=False)
            except Exception as e:
                print(f"backtest err: {e}")
                continue
            if not br or not br.out_of_sample or not br.oos_trades:
                print(f"no OOS")
                continue
            trades = br.oos_trades
            print(f"{len(trades)} OOS trades", flush=True)
            df_price = load_price(ticker)
            for t in trades:
                date_str = t.date
                sig = generate_daily_signal(ticker, date_str=date_str)
                if not sig:
                    rec = {'date':date_str, 'pnl':t.net_points, 'fold':'unknown',
                           'moon':'neutral', 'kronos':'NEUTRAL', 'conviction':'mid', 'ticker':ticker}
                else:
                    k = kronos_for(ticker, date_str, df_price)
                    rec = {'date':date_str, 'pnl':t.net_points,
                           'fold':fold_cat(sig.get('match_type','unknown')),
                           'moon':moon_cat(sig.get('moon_applies','void')),
                           'kronos':k,
                           'conviction':conv_band(sig.get('conviction',0.5)),
                           'ticker':ticker}
                all_recs.append(rec)
    return all_recs

# ── grid ─────────────────────────────────────────────────────────────
def grid(records, min_n=8):
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

# ── main ─────────────────────────────────────────────────────────────
def main():
    print("="*100)
    print("CORRELATION GRID: fold × moon × kronos × ticker  (multi-fold, ≥8 trades)")
    print("="*100)
    all_recs = []
    if os.path.exists(CACHE):
        all_recs = json.load(open(CACHE))
        print(f"Loaded {len(all_recs)} enriched trades from cache")
    else:
        all_recs = enrich_multifold()
        json.dump(all_recs, open(CACHE,'w'))
        print(f"\nEnriched + cached {len(all_recs)} trades")

    print(f"\nTotal enriched trades (OOS across folds): {len(all_recs)}")
    # Summary by ticker
    for tk in sorted(set(r['ticker'] for r in all_recs)):
        subt = [r for r in all_recs if r['ticker']==tk]
        print(f"  {tk}: {len(subt)} trades")

    results = grid(all_recs, min_n=8)
    print(f"\nCombos with ≥8 trades: {len(results)}")
    print(f"\n{'rank':>4} {'PF':>6} {'WR':>6} {'n':>4} {'avg':>8} {'fold':>10} {'moon':>8} {'kronos':>11} {'ticker':>6}")
    print("-"*100)
    for i,(pf,f,m,k,tk,n,wr,avg,wins) in enumerate(results[:40]):
        print(f"{i+1:>4} {pf:>6.2f} {wr:>5.0%} {n:>4} {avg:>+7.0f} {f:>10} {m:>8} {k:>11} {tk:>6}")

    import csv
    out = os.path.join(os.path.dirname(__file__), 'correlation_grid_results.csv')
    with open(out,'w',newline='') as fh:
        w=csv.writer(fh)
        w.writerow(['rank','PF','WR','n','avg_pnl','fold','moon','kronos','ticker'])
        for i,(pf,f,m,k,tk,n,wr,avg,wins) in enumerate(results):
            w.writerow([i+1,f"{pf:.2f}",f"{wr:.2%}",n,f"{avg:.1f}",f,m,k,tk])
    print(f"\n✓ Saved {len(results)} combos → {out}")

if __name__ == '__main__':
    main()
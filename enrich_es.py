import sys, os
sys.path.insert(0,'.')
sys.path.insert(0, os.path.expanduser('~/workspace/kronos'))
import json
from datetime import datetime
import yfinance as yf
from astro_matraix_backtest import persona_backtest_flow
from daily_signal_report import generate_daily_signal
from astro_matraix_kronos import KronosConfirmer
import astro_configs as ac

kc = KronosConfirmer(); kc._ensure_loaded()
CACHE = os.path.join(os.path.dirname(__file__), '.correlation_cache_multifold.json')

def moon_cat(m):
    return 'benefic' if m in ('Jupiter','Venus') else ('malefic' if m in ('Saturn','Mars') else 'neutral')
def fold_cat(mt):
    return mt if mt in ('exact','prefix','main+moon','main','moon') else mt
def conv_band(c):
    c=float(c) if c else 0.5
    return 'high' if c>=0.7 else ('low' if c<0.3 else 'mid')
def kronos_for(ticker, date_str, df_price):
    d = datetime.strptime(date_str,'%Y-%m-%d')
    if df_price.index.tz is not None: d = d.replace(tzinfo=df_price.index.tz)
    w = df_price.loc[:d].tail(120)
    if len(w)<30: return 'NEUTRAL'
    try:
        k = kc.confirm_signal(ticker, {'direction':'LONG','conviction':0.7,'sl_pct':0.007,'tp_pct':0.02}, df=w)
        return k.get('status')
    except: return 'NEUTRAL'

inst = ac.INSTRUMENTS['ES']
sym = inst.data_symbol or 'ES=F'
data = yf.Ticker(sym).history(start='2010-01-01')[['Open','High','Low','Close','Volume']].copy()
data.columns=['open','high','low','close','volume']
df_price = data.sort_index()

# load existing cache
recs = json.load(open(CACHE))
have_dates = set((r['ticker'], r['date']) for r in recs)

added = 0
for start in ['2010-01-01','2015-01-01','2020-01-01']:
    br = persona_backtest_flow(ticker='ES', yahoo_start=start, use_short_signals=True, verbose=False)
    if not br or not br.oos_trades: continue
    for t in br.oos_trades:
        ds = t.date
        if ('ES', ds) in have_dates: continue
        sig = generate_daily_signal('ES', date_str=ds)
        if not sig:
            rec = {'date':ds,'pnl':t.net_points,'fold':'unknown','moon':'neutral','kronos':'NEUTRAL','conviction':'mid','ticker':'ES'}
        else:
            rec = {'date':ds,'pnl':t.net_points,'fold':fold_cat(sig.get('match_type','unknown')),
                   'moon':moon_cat(sig.get('moon_applies','void')),'kronos':kronos_for('ES',ds,df_price),
                   'conviction':conv_band(sig.get('conviction',0.5)),'ticker':'ES'}
        recs.append(rec); added += 1
        have_dates.add(('ES', ds))
        if added % 30 == 0:
            json.dump(recs, open(CACHE,'w'))
            print(f"  +{added} ES trades cached...", flush=True)

json.dump(recs, open(CACHE,'w'))
print(f"DONE: added {added} ES trades, cache now {len(recs)} total")

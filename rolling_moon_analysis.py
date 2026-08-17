#!/usr/bin/env python3
"""
ROLLING WALK-FORWARD + MOON REFINEMENT — many folds.
For each rolling fold, compute OOS trades AND their moon category,
then test whether the benefic-moon edge persists across ALL folds.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import binomtest
import astro_core_v2
from astro_configs import INSTRUMENTS
from pattern_engine_v3 import load_rectified, get_state
from astro_matraix_backtest import persona_backtest_flow

# Many rolling start points (more folds, overlapping windows)
STARTS = ["2012-01-01","2013-01-01","2014-01-01","2015-01-01","2016-01-01",
          "2017-01-01","2018-01-01","2019-01-01","2020-01-01","2021-01-01",
          "2022-01-01","2023-01-01"]

_charts = {}
def get_moon(ticker, date_str):
    if ticker not in _charts:
        inst = INSTRUMENTS[ticker]
        rect = load_rectified().get(ticker, {})
        utc_dt = datetime(inst.birth_year, inst.birth_month, inst.birth_day,
                          rect.get("hour",12), rect.get("min",0), rect.get("sec",0))
        local_dt = utc_dt + timedelta(hours=inst.birth_tz)
        _charts[ticker] = astro_core_v2.calculate_chart(local_dt.year, local_dt.month, local_dt.day,
            local_dt.hour, local_dt.minute, local_dt.second, inst.birth_lat, inst.birth_lon, inst.birth_tz)
    d = datetime.strptime(date_str, '%Y-%m-%d').replace(hour=17)
    st = get_state(_charts[ticker], d)
    moon = st.get("moon_applies", "void")
    return 'benefic' if moon in ("Jupiter","Venus") else ('malefic' if moon in ("Saturn","Mars") else 'neutral')

def run_ticker(ticker):
    print(f"\n{'='*70}")
    print(f"ROLLING WALK-FORWARD: {ticker} ({len(STARTS)} folds)")
    print(f"{'='*70}")
    all_pf, all_ben_wr, all_other_wr, n_ben, n_oth = [], [], [], [], []
    for start in STARTS:
        try:
            br = persona_backtest_flow(ticker=ticker, yahoo_start=start, use_short_signals=True, verbose=False)
            if not br or not br.out_of_sample or not br.oos_trades:
                continue
            oos = br.out_of_sample
            trades = br.oos_trades
            all_pf.append(oos.profit_factor)
            # classify by moon
            ben, oth = [], []
            for t in trades:
                try:
                    cat = get_moon(ticker, t.date)
                    (ben if cat=='benefic' else oth).append(t.net_points)
                except: pass
            if len(ben)>=5:
                all_ben_wr.append(sum(1 for p in ben if p>0)/len(ben))
                n_ben.append(len(ben))
            if len(oth)>=5:
                all_other_wr.append(sum(1 for p in oth if p>0)/len(oth))
                n_oth.append(len(oth))
        except Exception as e:
            print(f"  {start}: ERR {str(e)[:40]}")
    if all_pf:
        pf = np.array(all_pf)
        robust = sum(1 for p in pf if p>1.0)
        print(f"\n  BASE PF: median={np.median(pf):.2f}, robust(PF>1)={robust}/{len(pf)}")
    if all_ben_wr:
        bw = np.array(all_ben_wr); ow = np.array(all_other_wr)
        print(f"  BENEFIC WR: median={np.median(bw)*100:.0f}% across {len(all_ben_wr)} folds (avg n={np.mean(n_ben):.0f})")
        print(f"  OTHER  WR: median={np.median(ow)*100:.0f}% across {len(all_other_wr)} folds")
        print(f"  ΔWR = {np.median(bw)*100 - np.median(ow)*100:+.0f} pts")

def main():
    for t in ['GC','NQ','ES']:
        run_ticker(t)

if __name__ == '__main__':
    main()
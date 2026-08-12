#!/usr/bin/env python3
# pattern_engine_v2.py – Fixed: correct local time + max_hz bug
# Requires: astro_core_v2.py, rectified_times_v3.json

from datetime import datetime, timedelta, date
from collections import defaultdict
import math, json, random

from astro_core_v2 import (
    calculate_chart, SIGN_NAMES, fidaria, distributor,
    find_hllaj, bound_ruler
)

# ---------- Load rectified charts (UTC times) ----------
def load_rectified():
    try:
        with open("rectified_times_v3.json") as f:
            return json.load(f)
    except:
        print("rectified_times_v3.json not found – using demo times.")
        # fallback – these are UTC hours
        return {
            "NQ": {"hour": 22, "min": 8, "sec": 0, "score": 6615.0},
            "ES": {"hour": 23, "min": 16, "sec": 0, "score": 10564.0},
            "GC": {"hour": 2, "min": 40, "sec": 0, "score": 7437.0},
        }

# ---------- Demo data generator ----------
def make_demo_data(ticker, days=1500):
    px = {'NQ': 15000.0, 'ES': 5000.0, 'GC': 2000.0}.get(ticker, 1000.0)
    rng = random.Random(sum(ord(c) for c in ticker))
    dd, dlist = {}, []
    d = datetime(2010, 1, 1)
    price = px
    while len(dlist) < days:
        if d.weekday() < 5:
            r = rng.gauss(0.0003, 0.011)
            o = price
            c = max(1.0, o * (1 + r))
            dd[d.strftime('%Y-%m-%d')] = {
                'open': o,
                'high': max(o, c) * (1 + abs(rng.gauss(0, 0.004))),
                'low': min(o, c) * (1 - abs(rng.gauss(0, 0.004))),
                'close': c
            }
            dlist.append(d.strftime('%Y-%m-%d'))
            price = c
        d += timedelta(days=1)
    return dd, dlist

# ---------- Astrological state ----------
def get_state(chart, target_utc):
    sect = chart['sect']
    main, sub, _ = fidaria(chart['utc_time'], target_utc, sect)
    dist = distributor(chart, target_utc)

    age_years = (target_utc - chart['utc_time']).total_seconds() / 86400.0 / 365.25
    prof_sign = (chart['ascendant']['sign'] + int(age_years)) % 12
    house = (prof_sign - chart['ascendant']['sign'] + 12) % 12 + 1

    days_since_birth = (target_utc - chart['utc_time']).total_seconds() / 86400.0
    moon_phase = int(((days_since_birth % 29.53059) / 29.53059) * 8) % 8

    return {'main': main, 'sub': sub, 'dist': dist, 'house': house,
            'moon_phase': moon_phase, 'sect': sect}

# ---------- Pattern keys ----------
def state_key(state, horizon):
    return f"{state['main']}_{state['sub']}_{state['dist']}_H{state['house']}_MP{state['moon_phase']}_{horizon}d"

def build_patterns(chart, dd, dates, horizons=[3, 5, 7]):
    pats = defaultdict(list)
    for i in range(len(dates)-1):
        sd = dates[i]
        ed = dates[i+1]
        if sd not in dd or ed not in dd:
            continue
        # Signal date at noon EST -> UTC
        signal_utc = datetime.strptime(sd, '%Y-%m-%d').replace(hour=17)  # EST noon = 17:00 UTC
        st = get_state(chart, signal_utc)
        for hz in horizons:
            xi = i+1+hz
            if xi >= len(dates):
                continue
            xd = dates[xi]
            if xd not in dd:
                continue
            entry = dd[ed]['open']
            exit_p = dd[xd]['close']
            if entry <= 0:
                continue
            r = exit_p / entry - 1.0
            pats[state_key(st, hz)].append(r)
    return pats

# ---------- Pattern learning (fixed) ----------
def learn_patterns(pats, min_n=12, max_p=0.02, min_edge=0.52):
    learned = {}
    for key, rets in pats.items():
        n = len(rets)
        if n < min_n:
            continue
        mu = sum(rets) / n
        wr = sum(1 for r in rets if r > 0) / n
        edge = wr if mu > 0 else 1 - wr
        if edge < min_edge:
            continue
        sd = (sum((r-mu)**2 for r in rets) / (n-1))**0.5 if n>1 else 0
        if sd>0:
            pv = max(0.0, min(1.0, math.erfc(abs(mu/(sd/math.sqrt(n)))/math.sqrt(2))))
        else:
            pv = 0.0
        if pv <= max_p:
            # extract horizon from key (last _Xd)
            parts = key.split('_')
            hz = 7  # default
            if parts[-1].endswith('d'):
                try:
                    hz = int(parts[-1].rstrip('d'))
                except: pass
            score = edge * (-math.log(max(pv, 1e-12))) * min(n,300)/300 * (hz/7)
            learned[key] = {
                'key': key, 'direction': 'LONG' if mu>0 else 'SHORT',
                'win_rate': wr, 'avg_move': mu, 'p_value': pv,
                'n_samples': n, 'horizon': hz, 'score': score
            }
    return learned

# ---------- Main ----------
if __name__ == "__main__":
    print("="*60)
    print(" PATTERN ENGINE V2 — FIXED")
    print("="*60)

    rectified = load_rectified()
    ticker = "NQ"
    if ticker in rectified:
        t = rectified[ticker]
        # NQ birth date & location
        y, m, d = 1996, 10, 26
        lat, lon, tz = 41.8781, -87.6298, -5

        # Convert rectified UTC to local time
        utc_dt = datetime(y, m, d, t['hour'], t['min'], t['sec'])
        local_dt = utc_dt + timedelta(hours=tz)   # tz is -5, so local = UTC -5h

        chart = calculate_chart(local_dt.year, local_dt.month, local_dt.day,
                                local_dt.hour, local_dt.minute, local_dt.second,
                                lat, lon, tz)
        print(f"Rectified chart for {ticker}: Asc {chart['ascendant']['longitude']:.2f}° {SIGN_NAMES[chart['ascendant']['sign']]}, "
              f"MC {chart['midheaven']['longitude']:.2f}°, Sect {chart['sect']}")

        dd, dates = make_demo_data(ticker, days=1500)
        print(f"Demo data: {len(dates)} days ({dates[0]} to {dates[-1]})")

        pats = build_patterns(chart, dd, dates, horizons=[3,5,7])
        print(f"Total pattern keys: {len(pats)}")
        learned = learn_patterns(pats, min_n=12, max_p=0.02, min_edge=0.52)
        valid = sorted(learned.values(), key=lambda x: x['score'], reverse=True)
        print(f"Valid patterns: {len(valid)}")

        if valid:
            print("\nTop 10 patterns:")
            print(f"{'Pattern':<50} {'Dir':<6} {'WR%':<7} {'AvgMv':<9} {'N':<5} {'p':<10} {'Score':<7}")
            print("-"*95)
            for p in valid[:10]:
                print(f"{p['key']:<50} {p['direction']:<6} {p['win_rate']*100:6.1f}% {p['avg_move']*100:8.3f}% {p['n_samples']:<5} {p['p_value']:<10.2e} {p['score']:.2f}")
        else:
            print("No valid patterns (expected with random data).")
    else:
        print(f"No rectified chart for {ticker}.")
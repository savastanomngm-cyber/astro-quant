#!/usr/bin/env python3
"""
Event database for futures-contract rectification.

Per A Rectification Manual (Zoller, 3rd ed.) Ch.14, preferred events are
Martian, Saturnian, and Solar in nature:
  * MARS   = crashes, panics, liquidations, margin cascades, war/contagion
  * SATURN = structural troughs, cyclical lows, sovereign shocks, contractions
  * SUN    = peaks, bubble-tops, record highs, solar-cycle exuberance

The astro-planet label is assigned by EVENT SEMANTICS (not by which planet
happened to be in a Fidaria sub-period), because Stage III rectification times
events via the primary directions of *these three* planets to the angles.

This is the consolidated source: it merges the earlier event_db.EVENTS with the
richer date coverage of rectify_v3.ASSET_EVENTS (Black Monday 1987, 1990
recession, post-2022 events, etc.), with labels normalized to Mars/Saturn/Sun.

Each entry: (ticker, YYYY-MM-DD, planet, label)
"""

EVENTS = {
    ("GC", "1980-01-21", "Sun",    "Gold all-time high $850 (solar peak / euphoria)"),
    ("GC", "1980-03-27", "Mars",   "Hunt silver/gold collapse (margin calls, panic)"),
    ("GC", "1982-06-21", "Saturn", "Gold 20-year bear bottom ~$296 (structural trough)"),
    ("GC", "1999-08-25", "Saturn", "Gold $252 Brown Bottom — 20-yr cycle low (structural)"),
    ("GC", "2006-05-12", "Sun",    "Gold passes $700 first time since 1980 (solar peak)"),
    ("GC", "2008-03-17", "Mars",   "Gold $1030 high during Bear Stearns collapse (panic bid)"),
    ("GC", "2008-10-24", "Mars",   "Gold -20% during GFC liquidation (margin cascade)"),
    ("GC", "2011-09-06", "Sun",    "Gold all-time nominal high $1923 (solar euphoria)"),
    ("GC", "2013-04-15", "Saturn", "Gold -9% single day $1561→$1361 (structural break)"),
    ("GC", "2013-06-28", "Saturn", "Gold $1180 bear low after 2013 crash (structural)"),
    ("GC", "2015-12-03", "Saturn", "Gold $1046 cyclical low (structural trough)"),
    ("GC", "2020-03-16", "Mars",   "Gold leveraged liquidation in COVID panic (-$145/2d)"),
    ("GC", "2020-08-07", "Sun",    "Gold all-time high $2089 (COVID-era solar peak)"),
    ("GC", "2022-11-03", "Saturn", "Gold $1618 low (structural trough after rate hikes)"),
    ("GC", "2024-04-12", "Sun",    "Gold $2431 record high (solar peak)"),
    ("GC", "2025-04-22", "Saturn", "Gold $3500+ ATH (structural repricing / inflation)"),

    ("ES", "1987-10-19", "Mars",   "Black Monday -22% (martial liquidation)"),
    ("ES", "1990-07-16", "Saturn", "1990 recession bottom (structural trough)"),
    ("ES", "1997-10-27", "Mars",   "Asian contagion mini-crash -7% (panic)"),
    ("ES", "1998-08-31", "Mars",   "Russian default / LTCM — S&P -19% (martial contagion)"),
    ("ES", "2000-03-24", "Sun",    "Dot-com bubble peak S&P 1527 (solar top)"),
    ("ES", "2001-09-17", "Mars",   "9/11 reopening S&P -5% (war / martial)"),
    ("ES", "2002-07-23", "Saturn", "WorldCom bust — S&P 797 bear trough (structural)"),
    ("ES", "2007-10-09", "Sun",    "Pre-GFC all-time high S&P 1565 (solar peak)"),
    ("ES", "2008-09-29", "Mars",   "TARP rejected — S&P -8.8% single day (panic)"),
    ("ES", "2008-10-10", "Saturn", "GFC worst week — S&P freefall, VIX 89 (collapse)"),
    ("ES", "2009-03-09", "Saturn", "GFC absolute low S&P 666 'Haines Bottom' (trough)"),
    ("ES", "2010-05-06", "Mars",   "Flash Crash — S&P -9% in minutes (algo panic)"),
    ("ES", "2011-08-08", "Saturn", "US credit downgrade — S&P -6.7% (sovereign shock)"),
    ("ES", "2015-08-24", "Mars",   "China Black Monday — S&P -5.3% at open (contagion)"),
    ("ES", "2018-02-05", "Mars",   "Volmageddon — VIX ETN collapse, S&P -4.1% (martial vol)"),
    ("ES", "2018-12-24", "Saturn", "Christmas Eve Massacre — S&P -2.7% into bear (fear)"),
    ("ES", "2020-02-19", "Sun",    "COVID pre-crash peak S&P 3393 (solar top)"),
    ("ES", "2020-03-16", "Mars",   "COVID crash — S&P -12% single day (martial pandemic)"),
    ("ES", "2020-03-23", "Saturn", "COVID crash low S&P 2237 (structural trough)"),
    ("ES", "2022-01-03", "Sun",    "2022 peak S&P 4808 before tech/rate crash (solar top)"),
    ("ES", "2022-10-12", "Saturn", "2022 bear low S&P 3577 (structural trough)"),
    ("ES", "2023-10-27", "Mars",   "2023 correction low (martial pullback)"),
    ("ES", "2024-12-06", "Sun",    "Record high S&P 6090 (solar peak)"),

    ("NQ", "1998-08-31", "Mars",   "Russian default — Nasdaq -8.6% panic (contagion)"),
    ("NQ", "1999-03-10", "Sun",    "Nasdaq first passes 5000 (solar peak cycle)"),
    ("NQ", "2000-03-10", "Sun",    "Dot-com bubble high Nasdaq 5048 (solar euphoria top)"),
    ("NQ", "2001-09-17", "Mars",   "9/11 reopening — Nasdaq -6.8% (war / martial)"),
    ("NQ", "2002-10-09", "Saturn", "Nasdaq 1114 — -78% from peak (structural trough)"),
    ("NQ", "2007-10-31", "Sun",    "Pre-GFC Nasdaq high 2239 (solar cycle peak)"),
    ("NQ", "2008-09-29", "Mars",   "TARP rejected — Nasdaq -9.1% (panic liquidation)"),
    ("NQ", "2008-11-20", "Saturn", "GFC Nasdaq low 1018 (structural trough)"),
    ("NQ", "2009-03-09", "Saturn", "GFC Nasdaq low 1043 (structural trough)"),
    ("NQ", "2010-05-06", "Mars",   "Flash Crash — Nasdaq -9% in minutes (algo panic)"),
    ("NQ", "2011-08-08", "Saturn", "US downgrade — Nasdaq -6.9% (structural shock)"),
    ("NQ", "2011-11-25", "Saturn", "Euro crisis low (structural trough)"),
    ("NQ", "2014-04-04", "Mars",   "Momentum crash low (martial liquidation)"),
    ("NQ", "2018-12-24", "Mars",   "Christmas Eve massacre — Nasdaq -2.2% (martial fear)"),
    ("NQ", "2020-02-19", "Sun",    "COVID pre-crash peak Nasdaq 9738 (solar top)"),
    ("NQ", "2020-03-16", "Mars",   "COVID crash — Nasdaq -12.3% (martial liquidation)"),
    ("NQ", "2020-03-23", "Saturn", "COVID Nasdaq low 6945 (structural trough)"),
    ("NQ", "2021-11-19", "Sun",    "Nasdaq peak 16764 before 2022 crash (solar top)"),
    ("NQ", "2022-10-13", "Saturn", "2022 bear low Nasdaq 10717 (structural trough)"),
    ("NQ", "2023-10-26", "Mars",   "2023 correction low (martial pullback)"),
    ("NQ", "2024-02-22", "Sun",    "AI rally record Nasdaq (solar peak)"),
}


def get_events(ticker):
    """Return sorted list of (date_str, planet, label) for a ticker."""
    return sorted([(ds, pl, lb) for (tk, ds, pl, lb) in EVENTS if tk == ticker])


def all_tickers():
    return sorted(set(tk for (tk, _, _, _) in EVENTS))


if __name__ == "__main__":
    for tk in all_tickers():
        es = get_events(tk)
        print(f"\n{tk}: {len(es)} events")
        for ds, pl, lb in es:
            print(f"  {ds} [{pl}] {lb}")

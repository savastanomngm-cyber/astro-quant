#!/usr/bin/env python3
"""Major Martian/Saturnian/Solar events for futures contract rectification.

Per A Rectification Manual Ch 14: "preferred events for data collection are those
marked by Mars and Saturn ... martial and legal disputes, burglaries, accidents,
surgeries, illness, death, criminal activity... events of notoriety."

For futures contracts, the analog is: CRASHES, PANICS, LIQUIDATIONS, STRUCTURAL
BREAKS — the Martian (war/violence) and Saturnian (collapse/contraction) events
in the contract's history. Solar events = peaks/bubble-tops (exuberance reversed).

Format: dictionary keyed by (ticker, event_date:YYYY-MM-DD, astro_planet, label).
"""

EVENTS = {
    # ── GC (Gold, COMEX futures born 1974-12-31) ────────────────────
    ("GC", "1980-01-21", "Sun",   "Gold all-time high $850 (peak, solar hubris)"),
    ("GC", "1980-03-27", "Mars",  "Hunt silver/gold collapse (margin calls, panic, martial liquidation)"),
    ("GC", "1982-06-21", "Saturn","Gold 20-year bear bottom ~$296 (structural trough)"),
    ("GC", "1999-08-25", "Saturn","Gold $252 — 20-year cycle low (Brown Bottom, structural)"),
    ("GC", "2006-05-12", "Sun",   "Gold passes $700 for first time since 1980 (solar peak cycle)"),
    ("GC", "2008-03-17", "Mars",  "Gold $1030 all-time high during Bear Stearns collapse (panic bid)"),
    ("GC", "2008-10-24", "Mars",  "Gold crashes 20% during GFC liquidation (margin-call cascade)"),
    ("GC", "2011-09-06", "Sun",   "Gold all-time nominal high $1923 (solar peak, euphoria)"),
    ("GC", "2013-04-15", "Saturn","Gold crashes 9% in single day ($1561→$1361, structural break)"),
    ("GC", "2013-06-28", "Saturn","Gold $1180 — bear market low after 2013 crash (structural trough)"),
    ("GC", "2020-03-16", "Mars",  "Gold leveraged liquidation in COVID panic (-$145 in 2 days)"),
    ("GC", "2020-08-07", "Sun",   "Gold all-time high $2089 (COVID-era peak)"),

    # ── ES (S&P 500 E-mini, born 1997-09-09) ─────────────────────────
    ("ES", "1998-08-31", "Mars",  "Russian default / LTCM collapse (S&P drops 19%, martial contagion)"),
    ("ES", "2000-03-24", "Sun",   "Dot-com bubble peak (S&P 1527, solar exuberance top)"),
    ("ES", "2001-09-17", "Mars",  "9/11 reopening — S&P -5% (war, martial event)"),
    ("ES", "2002-07-23", "Saturn","WorldCom bankruptcy, S&P 797 bear trough (structural break)"),
    ("ES", "2007-10-09", "Sun",   "Pre-GFC all-time high S&P 1565 (solar peak)"),
    ("ES", "2008-09-29", "Mars",  "TARP rejected — S&P -8.8% single day (panic, martial liquidation)"),
    ("ES", "2008-10-10", "Saturn","GFC worst week — S&P freefall, VIX 89 (structural collapse)"),
    ("ES", "2009-03-09", "Saturn","GFC absolute low S&P 666 (structural trough, 'Haines Bottom')"),
    ("ES", "2010-05-06", "Mars",  "Flash Crash — S&P drops 9% in minutes (algorithmic panic)"),
    ("ES", "2011-08-08", "Saturn","US credit downgrade S&P — S&P -6.7% (structural sovereign shock)"),
    ("ES", "2015-08-24", "Mars",  "China Black Monday — S&P down 5.3% at open (contagion panic)"),
    ("ES", "2018-02-05", "Mars",  "Volmageddon — VIX ETN collapse, S&P -4.1% (martial vol event)"),
    ("ES", "2018-12-24", "Saturn","Christmas Eve Massacre — S&P -2.7% into bear (structural fear)"),
    ("ES", "2020-02-19", "Sun",   "COVID pre-crash peak S&P 3393 (solar top before pandemic plunge)"),
    ("ES", "2020-03-16", "Mars",  "COVID crash — S&P -12% single day (martial pandemic liquidation)"),
    ("ES", "2020-03-23", "Saturn","COVID crash low S&P 2237 (structural trough)"),
    ("ES", "2022-01-03", "Sun",   "2022 peak S&P 4808 before tech/rate crash (solar top)"),
    ("ES", "2022-10-12", "Saturn","2022 bear low S&P 3577 (structural trough after rate hikes)"),

    # ── NQ (Nasdaq-100 E-mini, born 1996-10-26) ───────────────────────
    ("NQ", "1998-08-31", "Mars",  "Russian default — Nasdaq -8.6% panic (martial contagion)"),
    ("NQ", "2000-03-10", "Sun",   "Nasdaq all-time bubble high 5048 (solar euphoria peak)"),
    ("NQ", "2001-09-17", "Mars",  "9/11 reopening — Nasdaq -6.8% (war/martial)"),
    ("NQ", "2002-10-09", "Saturn","Nasdaq 1114 — 78% drawdown from peak (structural trough)"),
    ("NQ", "2007-10-31", "Sun",   "Pre-GFC Nasdaq high 2239 (solar cycle peak)"),
    ("NQ", "2008-09-29", "Mars",  "TARP rejected — Nasdaq -9.1% (panic liquidation)"),
    ("NQ", "2009-03-09", "Saturn","GFC Nasdaq low 1043 (structural trough)"),
    ("NQ", "2010-05-06", "Mars",  "Flash Crash — Nasdaq -9% in minutes (algorithmic panic)"),
    ("NQ", "2011-08-08", "Saturn","US downgrade — Nasdaq -6.9% (structural shock)"),
    ("NQ", "2018-12-24", "Saturn","Christmas Eve massacre — Nasdaq -2.2%, bear fear"),
    ("NQ", "2020-02-19", "Sun",   "COVID Pre-crash peak Nasdaq 9738 (solar top)"),
    ("NQ", "2020-03-16", "Mars",  "COVID crash — Nasdaq -12.3% (martial liquidation)"),
    ("NQ", "2020-03-23", "Saturn","COVID Nasdaq low 6945 (structural trough)"),
    ("NQ", "2021-11-19", "Sun",   "Nasdaq peak 16764 before 2022 crash (solar top)"),
    ("NQ", "2022-10-13", "Saturn","2022 bear low Nasdaq 10717 (structural trough after rate hikes)"),
}

def get_events(ticker):
    """Return sorted list of (date_str, planet, label) for a ticker."""
    return sorted([(ds, pl, lb) for (tk, ds, pl, lb) in EVENTS if tk == ticker])

def all_tickers():
    return sorted(set(tk for (tk,_,_,_) in EVENTS))

if __name__ == "__main__":
    for tk in all_tickers():
        es = get_events(tk)
        print(f"\n{tk}: {len(es)} events")
        for ds, pl, lb in es:
            print(f"  {ds} [{pl}] {lb}")

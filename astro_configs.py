"""
ASTRO CONFIGS — Centralized Typed Configuration
=================================================
QuantMind-style: BaseFlowCfg + per-flow types, discriminated-union inputs.
One source of truth for ALL parameters — no scattered dicts or magic numbers.

Design rules (from QuantMind):
  - Extend BaseFlowCfg; never use Dict[str, Any]
  - discriminated-union input types per flow
  - frozen=True, extra="forbid"
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field
from astro_knowledge import DataSourceKind


# ====================================================================
# CORE CONFIG — Applies across all flows
# ====================================================================

class AstroQuantConfig(BaseModel, frozen=True):
    """Global configuration. Single source of truth."""
    # Ticker universe
    tickers: list[str] = Field(default_factory=lambda: ["NQ", "ES", "GC"])
    micro_contracts: bool = False

    # Pattern learning thresholds
    min_samples: int = Field(default=12, ge=5)
    max_p_value: float = Field(default=0.02, ge=0.0, le=1.0)
    min_edge: float = Field(default=0.52, ge=0.0, le=1.0)

    # Rectification
    rectification_step_minutes: int = Field(default=4, ge=1, le=60)

    # Dynamic filters
    dynamic_filters_enabled: bool = True


# ====================================================================
# DATA SOURCE DEFINITIONS
# ====================================================================

class YahooSource(BaseModel, frozen=True, extra="forbid"):
    kind: Literal[DataSourceKind.YAHOO] = DataSourceKind.YAHOO
    symbol: str  # e.g. "NQ=F"
    start_date: str = "2010-01-01"


class CsvSource(BaseModel, frozen=True, extra="forbid"):
    kind: Literal[DataSourceKind.CSV] = DataSourceKind.CSV
    filename: str  # e.g. "CME_MINI_NQ1!, 60.csv"
    start_year: int = 2010


class RepoDailySource(BaseModel, frozen=True, extra="forbid"):
    kind: Literal[DataSourceKind.REPO_H1, DataSourceKind.REPO_M30] = (
        DataSourceKind.REPO_H1
    )
    timeframe: str  # "H1" or "M30"
    start_date: str = "2000-01-01"


DataSource = Union[YahooSource, CsvSource, RepoDailySource]


# Per-ticker data sources
TICKER_DATA_SOURCES: dict[str, list[tuple[str, DataSource]]] = {
    "NQ": [
        ("Daily Yahoo", YahooSource(symbol="NQ=F")),
        ("60m CSV", CsvSource(filename="CME_MINI_NQ1!, 60.csv")),
        ("30m CSV", CsvSource(filename="NQ_2024-2026_30m.csv")),
        ("Repo Daily (H1)", RepoDailySource(kind=DataSourceKind.REPO_H1, timeframe="H1")),
        ("Repo Daily (M30)", RepoDailySource(kind=DataSourceKind.REPO_M30, timeframe="M30")),
    ],
    "ES": [
        ("Daily Yahoo", YahooSource(symbol="ES=F")),
        ("60m CSV", CsvSource(filename="CME_MINI_ES1!, 60.csv")),
        ("30m CSV", CsvSource(filename="CME_MINI_ES1!, 30.csv")),
        ("Repo Daily (H1)", RepoDailySource(kind=DataSourceKind.REPO_H1, timeframe="H1")),
        ("Repo Daily (M30)", RepoDailySource(kind=DataSourceKind.REPO_M30, timeframe="M30")),
    ],
    "GC": [
        ("Daily Yahoo", YahooSource(symbol="GC=F")),
        ("60m CSV", CsvSource(filename="COMEX_GC1!, 60.csv")),
        ("30m CSV", CsvSource(filename="GC_2024-2026_30m.csv")),
        ("Repo Daily (H1)", RepoDailySource(kind=DataSourceKind.REPO_H1, timeframe="H1")),
        ("Repo Daily (M30)", RepoDailySource(kind=DataSourceKind.REPO_M30, timeframe="M30")),
    ],
    "ITA": [
        ("Daily Yahoo", YahooSource(symbol="ITA")),
    ],
    "PPA": [
        ("Daily Yahoo", YahooSource(symbol="PPA")),
    ],
    "AIQ": [
        ("Daily Yahoo", YahooSource(symbol="AIQ")),
    ],
    "SHLD": [
        ("Daily Yahoo", YahooSource(symbol="SHLD")),
    ],
    "GURU": [
        ("Daily Yahoo", YahooSource(symbol="GURU")),
    ],
    "ARKK": [
        ("Daily Yahoo", YahooSource(symbol="ARKK")),
    ],
    "SOXX": [
        ("Daily Yahoo", YahooSource(symbol="SOXX")),
    ],
    "BOTZ": [
        ("Daily Yahoo", YahooSource(symbol="BOTZ")),
    ],
    "CIBR": [
        ("Daily Yahoo", YahooSource(symbol="CIBR")),
    ],
    "QAI": [
        ("Daily Yahoo", YahooSource(symbol="QAI")),
    ],
}


# ====================================================================
# INSTRUMENT DEFINITIONS
# ====================================================================

class InstrumentDef(BaseModel, frozen=True, extra="forbid"):
    """Rectified chart + trading params for one instrument."""
    ticker: str
    data_symbol: str = ""  # Yahoo Finance symbol (empty=use ticker=F for futures)
    # Birth event
    birth_year: int
    birth_month: int
    birth_day: int
    birth_lat: float
    birth_lon: float
    birth_tz: float
    # Trading
    point_value: float
    default_sl: int
    default_tp: int
    default_hold: int


INSTRUMENTS: dict[str, InstrumentDef] = {
    "NQ": InstrumentDef(
        ticker="NQ",
        birth_year=1996, birth_month=10, birth_day=26,
        birth_lat=41.8781, birth_lon=-87.6298, birth_tz=-5,
        point_value=20.0, default_sl=200, default_tp=300, default_hold=5,
    ),
    "ES": InstrumentDef(
        ticker="ES",
        birth_year=1997, birth_month=9, birth_day=9,
        birth_lat=41.8781, birth_lon=-87.6298, birth_tz=-5,
        point_value=50.0, default_sl=100, default_tp=150, default_hold=10,
    ),
    "GC": InstrumentDef(
        ticker="GC",
        birth_year=1974, birth_month=12, birth_day=31,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-5,
        point_value=100.0, default_sl=50, default_tp=150, default_hold=7,
    ),
    # ── New ETF trackers ──
    "ITA": InstrumentDef(
        ticker="ITA", data_symbol="ITA",  # iShares US Aerospace & Defense
        birth_year=2006, birth_month=5, birth_day=5,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=5, default_tp=15, default_hold=10,
    ),
    "PPA": InstrumentDef(
        ticker="PPA", data_symbol="PPA",  # Invesco Aerospace & Defense
        birth_year=2005, birth_month=10, birth_day=26,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=5, default_tp=15, default_hold=10,
    ),
    "AIQ": InstrumentDef(
        ticker="AIQ", data_symbol="AIQ",  # Global X AI & Technology
        birth_year=2018, birth_month=5, birth_day=16,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=3, default_tp=10, default_hold=7,
    ),
    "SHLD": InstrumentDef(
        ticker="SHLD", data_symbol="SHLD",  # Global X Defense Tech
        birth_year=2023, birth_month=9, birth_day=14,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=3, default_tp=10, default_hold=7,
    ),
    "GURU": InstrumentDef(
        ticker="GURU", data_symbol="GURU",
        birth_year=2012, birth_month=6, birth_day=5,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=5, default_tp=12, default_hold=30,
    ),
    "ARKK": InstrumentDef(
        ticker="ARKK", data_symbol="ARKK",
        birth_year=2014, birth_month=10, birth_day=31,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=5, default_tp=12, default_hold=14,
    ),
    "SOXX": InstrumentDef(
        ticker="SOXX", data_symbol="SOXX",
        birth_year=2001, birth_month=7, birth_day=13,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=5, default_tp=15, default_hold=10,
    ),
    "BOTZ": InstrumentDef(
        ticker="BOTZ", data_symbol="BOTZ",
        birth_year=2016, birth_month=9, birth_day=13,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=3, default_tp=10, default_hold=7,
    ),
    "CIBR": InstrumentDef(
        ticker="CIBR", data_symbol="CIBR",
        birth_year=2015, birth_month=7, birth_day=7,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=3, default_tp=10, default_hold=7,
    ),
    "QAI": InstrumentDef(
        ticker="QAI", data_symbol="QAI",
        birth_year=2009, birth_month=3, birth_day=25,
        birth_lat=40.7128, birth_lon=-74.006, birth_tz=-4,
        point_value=1.0, default_sl=3, default_tp=8, default_hold=21,
    ),
}


# ====================================================================
# BACKTEST CONFIG
# ====================================================================

class BacktestCfg(BaseModel, frozen=True, extra="forbid"):
    """Configuration for a single backtest run."""
    ticker: str
    source: DataSource
    train_ratio: float = Field(default=0.6, ge=0.3, le=0.9)
    date_start: str = "2010-01-01"
    date_end: Optional[str] = None  # None = use all available data
    point_value: Optional[float] = None  # None = lookup from INSTRUMENTS
    transaction_cost_points: float = 0.5

    # Grid search
    sl_grid: list[float] = Field(default_factory=lambda: [25, 50, 75, 100, 150, 200])
    tp_grid: list[float] = Field(default_factory=lambda: [50, 75, 100, 150, 200, 300])
    hold_grid: list[int] = Field(default_factory=lambda: [3, 5, 7, 10])
    min_trades: int = Field(default=5, ge=3)

    # Pattern horizons
    horizons: list[int] = Field(default_factory=lambda: [3, 5, 7])


class MultiSourceBacktestCfg(BaseModel, frozen=True, extra="forbid"):
    """Run backtests across multiple sources for a single ticker."""
    ticker: str
    sources: list[DataSource]
    base_cfg: BacktestCfg = Field(
        default_factory=lambda: BacktestCfg(ticker="", source=YahooSource(symbol=""))
    )


class BatchBacktestCfg(BaseModel, frozen=True, extra="forbid"):
    """Run backtests across multiple tickers."""
    tickers: list[str]
    sources_per_ticker: Optional[dict[str, list[DataSource]]] = None  # per-ticker source lists
    base_cfg_template: BacktestCfg = Field(
        default_factory=lambda: BacktestCfg(ticker="", source=YahooSource(symbol=""))
    )
    max_concurrency: int = Field(default=3, ge=1)


# ====================================================================
# CAMPAIGN CONFIG
# ====================================================================

class CampaignCfg(BaseModel, frozen=True, extra="forbid"):
    """Configuration for generating a trading campaign."""
    ticker: str
    date_start: str
    date_end: str

    # Trade parameters (default from instrument)
    sl_points: int = 0   # 0 = use instrument default
    tp_points: int = 0
    hold_days: int = 0

    # Pattern source
    source: YahooSource = Field(default_factory=lambda: YahooSource(symbol=""))

    # Regime filters
    use_dynamic_filters: bool = True
    filter_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "moon_app": 0.30,
            "nodes": 0.25,
            "moiety": 0.25,
            "arcus_vitae": 0.20,
        }
    )
    bullish_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    bearish_threshold: float = Field(default=-0.15, ge=-1.0, le=0.0)


# ====================================================================
# RECTIFY CONFIG
# ====================================================================

class RectifyCfg(BaseModel, frozen=True, extra="forbid"):
    """Configuration for chart rectification."""
    ticker: str
    step_minutes: int = Field(default=4, ge=1, le=60)
    search_window_hours: int = Field(default=48, ge=1, le=168)


# ====================================================================
# FILTER CONFIG
# ====================================================================

class FilterCfg(BaseModel, frozen=True, extra="forbid"):
    """Dynamic filter parameters."""
    moon_orb: float = 8.0
    nodes_orb: float = 2.0

    # Moiety multipliers (1.0 = traditional values)
    saturn_moiety_mult: float = 1.0
    jupiter_moiety_mult: float = 1.0

    # Weighted combination
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "moon_app": 0.30,
            "nodes": 0.25,
            "moiety": 0.25,
            "arcus_vitae": 0.20,
        }
    )

    # Thresholds for regime classification
    bullish_threshold: float = 0.15
    bearish_threshold: float = -0.15


# ====================================================================
# STATIC CONVENIENCE
# ====================================================================

def get_all_yahoo_sources() -> dict[str, YahooSource]:
    """Convenience: get Yahoo sources for all instruments."""
    return {
        "NQ": YahooSource(symbol="NQ=F"),
        "ES": YahooSource(symbol="ES=F"),
        "GC": YahooSource(symbol="GC=F"),
    }


def get_default_campaign(ticker: str, start: str = "2026-08-10", end: str = "2026-08-28") -> CampaignCfg:
    inst = INSTRUMENTS[ticker]
    return CampaignCfg(
        ticker=ticker,
        date_start=start,
        date_end=end,
        sl_points=inst.default_sl,
        tp_points=inst.default_tp,
        hold_days=inst.default_hold,
        source=YahooSource(symbol=f"{ticker}=F"),
    )
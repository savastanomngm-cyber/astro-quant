"""
ASTRO KNOWLEDGE — Typed Knowledge Shapes for Astro-Quant
============================================================
QuantMind-style Pydantic models replacing loose dicts.
All knowledge shapes carry provenance (SourceRef), are frozen,
and expose contracts the rest of the system depends on.

Shapes:
  - ChartSnapshot     (TreeKnowledge analog) — full rectified natal chart
  - PlanetPosition    (embedded type) — typed planet data
  - PatternCard        (FlattenKnowledge analog) — learned pattern result
  - RegimeCard         (FlattenKnowledge analog) — daily regime assessment
  - BacktestResult     (aggregate) — full backtest output with provenance
  - BatchBacktestResult (aggregate) — multi-source/multi-ticker fan-out

Design rules (from QuantMind AGENTS.md):
  - Pydantic at boundaries, frozen=True, extra="forbid"
  - All BaseKnowledge subclasses require `as_of: datetime`
  - Typed SourceRef provenance — no bare strings
  - Subclasses MUST override `embedding_text()` if relevant
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ====================================================================
# PROVENANCE
# ====================================================================

class DataSourceKind(str, Enum):
    YAHOO = "yahoo"
    CSV = "csv"
    REPO_H1 = "repo_h1"
    REPO_M30 = "repo_m30"


class SourceRef(BaseModel, frozen=True):
    """Provenance marker for any astro knowledge artifact."""
    kind: DataSourceKind
    symbol: str  # e.g. "NQ=F", "ES=F", "GC=F"
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    file_path: Optional[str] = None  # for CSV / repo sources

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.symbol}"


class ChartProvenance(BaseModel, frozen=True):
    """How this chart was rectified."""
    method: Literal["event_based_v3", "manual", "unknown", "persona_matraix_v1"] = "event_based_v3"
    event_count: int = 0
    total_error_days: float = 0.0
    rectified_utc: Optional[datetime] = None


# ====================================================================
# PLANET POSITION (embedded type)
# ====================================================================

class PlanetPosition(BaseModel, frozen=True, extra="forbid"):
    """Typed planetary position data — replaces dicts in chart['planets']."""
    name: str
    longitude: float = Field(ge=0.0, lt=360.0)
    latitude: float = Field(ge=-90.0, le=90.0, default=0.0)
    speed: float = Field(default=0.0)  # °/day
    sign_index: int = Field(ge=0, le=11)
    degree_in_sign: float = Field(ge=0.0, le=30.0)
    is_retrograde: bool = False

    @property
    def sign_name(self) -> str:
        from astro_core_v2 import SIGN_NAMES
        return SIGN_NAMES[self.sign_index]


class AnglePosition(BaseModel, frozen=True, extra="forbid"):
    """Typed angle (ASC/MC) position."""
    longitude: float = Field(ge=0.0, lt=360.0)
    sign_index: int = Field(ge=0, le=11)
    degree_in_sign: float = Field(ge=0.0, le=30.0)

    @property
    def sign_name(self) -> str:
        from astro_core_v2 import SIGN_NAMES
        return SIGN_NAMES[self.sign_index]


# ====================================================================
# CHART SNAPSHOT (TreeKnowledge analog)
# ====================================================================

class ChartSnapshot(BaseModel, frozen=True, extra="forbid"):
    """
    Complete natal chart for a financial instrument.
    This is the root knowledge artifact — everything else derives from it.

    TreeKnowledge analog: hierarchical (planets → positions), carries
    full structural information.
    """
    ticker: str = Field(min_length=1, max_length=5)
    as_of: datetime  # event date (e.g. instrument first trade)
    latitude: float
    longitude: float
    timezone: float

    ascendant: AnglePosition
    midheaven: AnglePosition
    sect: Literal["Diurnal", "Nocturnal"]

    planets: dict[str, PlanetPosition]  # keyed by planet name

    # Derived: Hllaj / Kadukhadah (computed at chart creation)
    hllaj: str  # e.g. "ASC", "Sun", "Moon"
    kadukhadah: str  # e.g. "Saturn", "Mars"

    # Optional: Arabic Parts
    part_of_fortune: Optional[float] = None
    part_of_spirit: Optional[float] = None

    # Provenance
    source: ChartProvenance = Field(default_factory=ChartProvenance)

    def embedding_text(self) -> str:
        """Contract for downstream store layers."""
        planet_lines = ", ".join(
            f"{p.name}@{p.sign_name}{p.degree_in_sign:.2f}"
            for p in self.planets.values()
        )
        return (
            f"{self.ticker} chart: ASC={self.ascendant.sign_name}{self.ascendant.degree_in_sign:.2f}, "
            f"MC={self.midheaven.sign_name}{self.midheaven.degree_in_sign:.2f}, "
            f"sect={self.sect}, hllaj={self.hllaj}, kadukhadah={self.kadukhadah}. "
            f"Planets: {planet_lines}"
        )


# ====================================================================
# PATTERN CARD (FlattenKnowledge analog)
# ====================================================================

class PatternCard(BaseModel, frozen=True, extra="forbid"):
    """
    A learned astro-quant pattern — one row from the pattern engine.
    FlattenKnowledge analog: an atomic card from a batch of learned patterns.

    Carries full statistical profile and provenance.
    """
    as_of: datetime  # when this pattern was computed
    state_key: str
    direction: Literal["LONG", "SHORT"]
    horizon: int = Field(ge=1, le=30)  # days
    n_samples: int = Field(ge=0)
    win_rate: float = Field(ge=0.0, le=1.0)
    avg_move: float  # average percentage move
    std_move: float = Field(ge=0.0)  # standard deviation
    profit_factor: float = Field(ge=0.0)
    p_value: float = Field(ge=0.0, le=1.0)
    score: float  # composite ranking score
    source: SourceRef

    def embedding_text(self) -> str:
        """Text representation for vector search over pattern space."""
        return (
            f"Pattern {self.state_key}: {self.direction}, "
            f"horizon={self.horizon}d, n={self.n_samples}, "
            f"WR={self.win_rate:.2%}, PF={self.profit_factor:.2f}, "
            f"avg_move={self.avg_move:.4f}"
        )


# ====================================================================
# REGIME CARD (FlattenKnowledge analog)
# ====================================================================

class RegimeCard(BaseModel, frozen=True, extra="forbid"):
    """
    Daily regime assessment from dynamic filters.
    One card per trading day per ticker.
    """
    as_of: datetime  # assessment date
    ticker: str

    # Per-filter scores (default 0.0 = not computed)
    moon_application_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    moon_application_details: dict = Field(default_factory=dict)

    nodes_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    nodes_details: dict = Field(default_factory=dict)

    moiety_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    moiety_details: dict = Field(default_factory=dict)

    arcus_vitae_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    arcus_vitae_details: dict = Field(default_factory=dict)

    # Combined
    combined_score: float = Field(ge=-1.0, le=1.0)
    regime: Literal["BULLISH", "BEARISH", "NEUTRAL"]

    # Effect on signal
    base_direction: Optional[Literal["LONG", "SHORT"]] = None
    modulated_direction: Optional[Literal["LONG", "SHORT", "FLAT"]] = None
    pattern_key: Optional[str] = None

    def embedding_text(self) -> str:
        return (
            f"Regime {self.as_of.date()} {self.ticker}: {self.regime} "
            f"(moon={self.moon_application_score:+.2f}, "
            f"nodes={self.nodes_score:+.2f}, "
            f"moiety={self.moiety_score:+.2f}, "
            f"arcus={self.arcus_vitae_score:+.2f})"
        )


# ====================================================================
# BACKTEST RESULT (aggregate)
# ====================================================================

class TradeRecord(BaseModel, frozen=True, extra="forbid"):
    """A single trade in a backtest."""
    date: str  # YYYY-MM-DD
    direction: Literal["LONG", "SHORT", "FLAT"]
    gross_points: float
    net_points: float


class TradeStats(BaseModel, frozen=True, extra="forbid"):
    """Aggregate stats for a set of trades."""
    n_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    total_points: float = 0.0
    total_dollars: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0


class BacktestResult(BaseModel, frozen=True, extra="forbid"):
    """
    Full backtest output with provenance.
    The main artifact produced by backtest_flow.
    """
    as_of: datetime  # when this backtest ran
    ticker: str
    source: SourceRef
    chart_provenance: ChartProvenance

    # Parameters
    train_ratio: float = Field(ge=0.3, le=0.9)
    sl_points: float = Field(default=1.0, gt=0)
    tp_points: float = Field(default=1.0, gt=0)
    hold_days: int = Field(default=1, ge=1)

    # Pattern engine
    patterns_found: int = 0
    patterns_valid: int = 0

    # Results
    validation: TradeStats = Field(default_factory=TradeStats)
    out_of_sample: TradeStats = Field(default_factory=TradeStats)

    # Optional: regime filter info
    filter_cfg: Optional[dict] = None
    regime_flat_ratio: Optional[float] = None  # % of signals filtered to FLAT

    # Raw trades (for detailed analysis)
    val_trades: list[TradeRecord] = Field(default_factory=list)
    oos_trades: list[TradeRecord] = Field(default_factory=list)

    def embedding_text(self) -> str:
        return (
            f"Backtest {self.ticker} via {self.source}: "
            f"OOS PF={self.out_of_sample.profit_factor:.2f}, "
            f"WR={self.out_of_sample.win_rate:.1%}, "
            f"Net=${self.out_of_sample.total_dollars:,.0f}"
        )

    @property
    def is_profitable_oos(self) -> bool:
        return self.out_of_sample.profit_factor > 1.0


class BatchBacktestResult(BaseModel, frozen=True, extra="forbid"):
    """
    Aggregated results from a batch run over multiple tickers/sources.
    """
    as_of: datetime
    results: list[BacktestResult]
    total_patterns: int = 0
    profitable_oos_count: int = 0

    def model_post_init(self, __context):
        self.total_patterns = sum(r.patterns_valid for r in self.results)
        self.profitable_oos_count = sum(1 for r in self.results if r.is_profitable_oos)


# ====================================================================
# HELPER: Convert raw chart dict → ChartSnapshot
# ====================================================================

def chart_to_snapshot(
    ticker: str,
    chart_dict: dict,
    birth_utc: datetime,
    tz_offset: float,
    lat: float,
    lon: float,
    event_error_days: float = 0.0,
) -> ChartSnapshot:
    """
    Convert a calculate_chart() dict (from astro_core_v2) into a typed ChartSnapshot.

    This is the bridge between the legacy dict-based system and the new typed system.
    """
    from astro_core_v2 import SIGN_NAMES, find_hllaj, part_of_fortune, part_of_spirit

    # Planets
    planets = {}
    for name, data in chart_dict["planets"].items():
        planets[name] = PlanetPosition(
            name=name,
            longitude=data["longitude"],
            latitude=data.get("latitude", 0.0),
            speed=data.get("speed", 0.0),
            sign_index=data["sign"],
            degree_in_sign=data["degree_in_sign"],
            is_retrograde=data.get("is_retrograde", False),
        )

    # Angles
    asc_data = chart_dict["ascendant"]
    mc_data = chart_dict["midheaven"]

    # Hllaj
    h_info = find_hllaj(chart_dict)

    # Arabic Parts
    try:
        pof = part_of_fortune(chart_dict)
    except Exception:
        pof = None
    try:
        pos = part_of_spirit(chart_dict)
    except Exception:
        pos = None

    return ChartSnapshot(
        ticker=ticker,
        as_of=birth_utc,
        latitude=lat,
        longitude=lon,
        timezone=tz_offset,
        ascendant=AnglePosition(
            longitude=asc_data["longitude"],
            sign_index=asc_data["sign"],
            degree_in_sign=asc_data["degree_in_sign"],
        ),
        midheaven=AnglePosition(
            longitude=mc_data["longitude"],
            sign_index=mc_data["sign"],
            degree_in_sign=mc_data["degree_in_sign"],
        ),
        sect=chart_dict["sect"],
        planets=planets,
        hllaj=h_info["hllaj"],
        kadukhadah=h_info["kadukhadah"],
        part_of_fortune=pof,
        part_of_spirit=pos,
        source=ChartProvenance(
            method="event_based_v3",
            total_error_days=event_error_days,
        ),
    )
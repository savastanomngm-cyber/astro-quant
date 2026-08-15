"""
ASTRO PERSONAS V2 — TraderPersona (MatrAIx-Style)
====================================================
Upgraded from PlanetaryPersona (10 dims) to TraderPersona (51 dims).
Each persona is a full MatrAIx-compatible trader profile combining:
  1. Astro-derived base traits (from fidaria+distributor+house+moon)
  2. MatrAIx 51-dimension personality profile
  3. Derived trading parameters (numerical, computed from traits)
  4. Historical performance memory (from pattern data)

Architecture:
  - TraderPersona dataclass — full 51-dimension profile
  - TraderPersona.generate_from_astro_state() — astro → trait mapping
  - TraderPersona.derive_parameters() — traits → numerical trading params
  - TraderPersona.to_system_prompt() — LLM conditioning (MatrAIx-style)
  - generate_trader_personas_from_learned() — batch generation
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal

from astro_knowledge import ChartSnapshot, PatternCard
from trader_persona_schema import (
    ALL_DIMENSIONS, DIMENSION_DERIVATIONS, ASTRO_TRAIT_MAP,
    DEFAULT_TRAITS, TOTAL_DIMENSIONS, validate_traits,
)


# ====================================================================
# MALEFICS / BENEFICS / PLANET CLASSIFICATION
# ====================================================================

MALEFICS = {"Mars", "Saturn"}
BENEFICS = {"Venus", "Jupiter"}

def _classify_planet(name: str) -> str:
    if name in MALEFICS: return "malefic"
    if name in BENEFICS: return "benefic"
    return "neutral"

def _is_angular(house: int) -> bool:
    return house in (1, 4, 7, 10)

MOON_SPEED_MAP = {
    "MP0": "fast", "MP1": "fast", "MP2": "fast",
    "MP3": "slow", "MP4": "slow",
    "MP5": "slow", "MP6": "fast", "MP7": "fast",
}


# ====================================================================
# TRADER PERSONA
# ====================================================================

@dataclass
class TraderPersona:
    """
    Full 51-dimension trader personality profile — MatrAIx-compatible.

    This is the MatrAIx OasisAgentProfile equivalent for trading.
    Each persona can be conditioned into an LLM system prompt
    to make the LLM trade according to this personality.
    """

    # Identity
    persona_id: str
    ticker: str
    as_of: datetime = field(default_factory=datetime.now)

    # Astro state source
    fidaria_main: str = ""
    fidaria_sub: str = ""
    distributor: str = ""
    moon_phase: str = ""
    house: int = 1

    # === 51-DIMENSION TRAIT PROFILE (MatrAIx-compatible) ===
    # Risk & Decision (4)
    risk_tolerance: str = "balanced"
    financial_risk_tolerance: str = "average"
    max_drawdown_tolerance_pct: str = "15%"
    position_sizing_style: str = "fixed_fractional"

    # Decision-Making (4)
    decision_style: str = "analytical"
    need_for_closure: str = "average"
    entry_trigger_style: str = "signal_plus_confirmation"
    exit_trigger_style: str = "strict_sl_tp"

    # Personality: Big Five (10)
    assertiveness: str = "average"
    anxiety: str = "average"
    open_mindedness: str = "average"
    self_discipline: str = "average"
    excitement_seeking: str = "average"
    trust: str = "average"
    emotional_volatility: str = "average"
    achievement_striving: str = "average"
    cautiousness: str = "average"
    intellectual_curiosity: str = "average"

    # Cognitive Style (12)
    patience: str = "moderate"
    ambiguity_tolerance: str = "moderate"
    optimism: str = "moderate"
    decision_speed: str = "balanced"
    confidence_calibration: str = "well_calibrated"
    numeracy_comfort: str = "moderate"
    detail_orientation: str = "moderate"
    skepticism: str = "moderate"
    big_picture_vs_detail: str = "both"
    risk_framing: str = "balanced"
    emotional_expressiveness: str = "moderate"
    perfectionism: str = "moderate"

    # Preferences (8)
    novelty_vs_familiarity: str = "balanced"
    speed_vs_accuracy: str = "balanced"
    quality_vs_quantity: str = "balanced"
    plan_vs_spontaneous: str = "balanced"
    stability_vs_change: str = "balanced"
    logic_vs_intuition: str = "balanced"
    lead_vs_follow: str = "situational"
    routine_vs_variety: str = "balanced"

    # Values & Motivation (7)
    schwartz_achievement: str = "average"
    schwartz_power: str = "average"
    schwartz_security: str = "average"
    schwartz_stimulation: str = "average"
    schwartz_hedonism: str = "average"
    schwartz_self_direction: str = "average"
    schwartz_conformity: str = "average"

    # Lifestyle (4)
    investment_style: str = "active_trader"
    frugality: str = "balanced"
    goal_setting: str = "weekly"
    screen_time: str = "moderate"

    # AI Adoption (2)
    ai_usage_frequency: str = "weekly"
    ai_trust: str = "trusts_after_verify"

    # === DERIVED TRADING PARAMETERS (computed from traits) ===
    position_size_pct: float = 0.10
    max_hold_days: int = 10
    stop_tightness: float = 0.08
    stop_tightness_mult: float = 1.0
    panic_exit_prob: float = 0.10
    hold_mult: float = 1.0
    early_exit_prob: float = 0.10
    bull_bias: float = 0.5
    short_prob: float = 0.20
    conviction_mult: float = 1.0
    error_rate: float = 0.05
    trade_freq_mult: float = 1.0
    impulse_trade_prob: float = 0.05
    overtrade_mult: float = 1.0
    boredom_exit_prob: float = 0.10
    rule_adherence: float = 0.75
    revenge_trade_prob: float = 0.10
    signal_accept_threshold: float = 0.6
    contrarian_prob: float = 0.20
    regime_reactivity: float = 0.8
    tilt_prob: float = 0.10
    systematic_weight: float = 0.50
    override_prob: float = 0.15
    profit_target_mult: float = 1.0
    effort_level: float = 0.7
    close_early_mult: float = 1.0
    reenter_prob: float = 0.10

    # === HISTORICAL MEMORY ===
    n_samples: int = 0
    historical_win_rate: float = 0.0
    historical_pf: float = 0.0
    historical_avg_move: float = 0.0
    pattern_direction: str = "LONG"
    pattern_score: float = 0.0

    # === SOURCE ===
    source_pattern: Optional[PatternCard] = None
    generation_method: str = "rule_based"

    # ==================================================================
    # FACTORY METHODS
    # ==================================================================

    @classmethod
    def generate_from_astro_state(
        cls,
        state_key: str,
        ticker: str,
        fidaria_main: str,
        fidaria_sub: str,
        distributor: str,
        moon_phase: str,
        house: int,
        pattern: Optional[PatternCard] = None,
    ) -> "TraderPersona":
        """
        Generate a TraderPersona from astro state using ASTRO_TRAIT_MAP.

        This is the primary factory — equivalent to MiroFish's
        generate_profile_from_entity().
        """
        planet_class = _classify_planet(fidaria_main)
        angularity = "angular" if _is_angular(house) else "cadent"
        moon_speed = MOON_SPEED_MAP.get(moon_phase, "fast")

        key = (planet_class, angularity, moon_speed)
        traits = ASTRO_TRAIT_MAP.get(key, DEFAULT_TRAITS.copy())

        # Start with defaults, override from astro map
        profile = DEFAULT_TRAITS.copy()
        profile.update(traits)

        # Create persona with all traits
        persona = cls(
            persona_id=state_key,
            ticker=ticker,
            fidaria_main=fidaria_main,
            fidaria_sub=fidaria_sub,
            distributor=distributor,
            moon_phase=moon_phase,
            house=house,
            **profile,
        )

        # Derive numerical parameters
        persona._derive_parameters()

        # Embed historical memory
        if pattern:
            persona.source_pattern = pattern
            persona.n_samples = pattern.n_samples
            persona.historical_win_rate = pattern.win_rate
            persona.historical_pf = pattern.profit_factor
            persona.historical_avg_move = pattern.avg_move
            persona.pattern_direction = pattern.direction
            persona.pattern_score = pattern.score

        return persona

    @classmethod
    def generate_with_llm(
        cls,
        state_key: str,
        ticker: str,
        chart_snapshot: ChartSnapshot,
        fidaria_main: str,
        fidaria_sub: str,
        distributor: str,
        moon_phase: str,
        house: int,
        pattern: Optional[PatternCard] = None,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> "TraderPersona":
        """
        LLM-powered persona generation (MatrAIx-style agent conditioning).
        Falls back to rule-based if no API key or on failure.
        Uses env vars: OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL (or Deepseek equivalents).
        """
        import os as _os
        
        # Use env vars if not explicitly provided
        llm_api_key = llm_api_key or _os.environ.get('OPENAI_API_KEY')
        llm_base_url = llm_base_url or _os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        llm_model = llm_model or _os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
        
        if not llm_api_key:
            return cls.generate_from_astro_state(
                state_key, ticker, fidaria_main, fidaria_sub,
                distributor, moon_phase, house, pattern,
            )

        # Build base persona first
        persona = cls.generate_from_astro_state(
            state_key, ticker, fidaria_main, fidaria_sub,
            distributor, moon_phase, house, pattern,
        )

        # LLM refines selected dimensions
        try:
            import json as _json
            from openai import OpenAI

            prompt = persona._build_llm_refinement_prompt(chart_snapshot)

            client = OpenAI(api_key=llm_api_key, base_url=llm_base_url)
            response = client.chat.completions.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": "You are an expert trading psychologist and astrological market analyst. Respond in JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=1200,
            )
            result = _json.loads(response.choices[0].message.content)

            # Merge LLM-refined traits (only update valid dimensions)
            for dim_id, value in result.get("traits", {}).items():
                if dim_id in ALL_DIMENSIONS and value in ALL_DIMENSIONS[dim_id]["values"]:
                    setattr(persona, dim_id, value)

            # Re-derive parameters with refined traits
            persona._derive_parameters()
            persona.generation_method = "llm_refined"

        except Exception:
            pass  # fall back to rule-based

        return persona

    # ==================================================================
    # DERIVATION
    # ==================================================================

    def _derive_parameters(self):
        """Compute numerical trading parameters from trait values."""
        for dim_id, value_map in DIMENSION_DERIVATIONS.items():
            current_value = getattr(self, dim_id, None)
            if current_value and current_value in value_map:
                params = value_map[current_value]
                for param, val in params.items():
                    if hasattr(self, param):
                        setattr(self, param, val)

    # ==================================================================
    # TRAIT ACCESS
    # ==================================================================

    def get_trait(self, dim_id: str) -> str:
        return getattr(self, dim_id, DEFAULT_TRAITS.get(dim_id, "unknown"))

    def to_trait_dict(self) -> dict[str, str]:
        """Full 51-dimension trait profile as dict — MatrAIx-compatible."""
        return {
            dim_id: self.get_trait(dim_id)
            for dim_id in ALL_DIMENSIONS
        }

    def validate(self) -> list[str]:
        return validate_traits(self.to_trait_dict())

    # ====================================================================
    # SYSTEM PROMPT (MatrAIx-style agent conditioning)
    # ====================================================================

    def to_system_prompt(self) -> str:
        """
        Generate an LLM system prompt that conditions the model
        to trade according to this persona's profile.

        MatrAIx analog: persona YAML → injected into agent prompt as context.
        """
        lines = [
            f"You are a financial trader with the following personality profile:",
            f"",
            f"IDENTITY: Trader {self.persona_id[:40]} on {self.ticker}",
            f"ASTRO STATE: {self.fidaria_main}-{self.fidaria_sub} fidaria, "
            f"{self.distributor} distributor, House {self.house}, {self.moon_phase}",
            f"",
            f"RISK PROFILE:",
            f"  Risk tolerance: {self.risk_tolerance}",
            f"  Max drawdown tolerance: {self.max_drawdown_tolerance_pct}",
            f"  Position sizing: {self.position_sizing_style} ({self.position_size_pct:.0%} per trade)",
            f"  Stop-loss tightness: {self.stop_tightness:.0%}",
            f"",
            f"DECISION-MAKING:",
            f"  Style: {self.decision_style}",
            f"  Entry: {self.entry_trigger_style}",
            f"  Exit: {self.exit_trigger_style}",
            f"  Need for closure: {self.need_for_closure}",
            f"",
            f"PERSONALITY (Big Five):",
            f"  Assertiveness: {self.assertiveness}",
            f"  Anxiety: {self.anxiety}",
            f"  Open-mindedness: {self.open_mindedness}",
            f"  Self-discipline: {self.self_discipline} (rule adherence: {self.rule_adherence:.0%})",
            f"  Excitement-seeking: {self.excitement_seeking}",
            f"  Emotional volatility: {self.emotional_volatility}",
            f"",
            f"COGNITIVE STYLE:",
            f"  Patience: {self.patience} (hold multiplier: {self.hold_mult:.1f}x)",
            f"  Optimism: {self.optimism} (bull bias: {self.bull_bias:.0%})",
            f"  Skepticism: {self.skepticism}",
            f"  Decision speed: {self.decision_speed}",
            f"  Confidence: {self.confidence_calibration}",
            f"  Numeracy: {self.numeracy_comfort}",
            f"  Detail orientation: {self.detail_orientation}",
            f"",
            f"TRADING BEHAVIOR:",
            f"  Systematic vs discretionary: {self.systematic_weight:.0%} systematic",
            f"  Max hold: {self.max_hold_days} days",
            f"  Impulse trade probability: {self.impulse_trade_prob:.0%}",
            f"  Panic exit probability: {self.panic_exit_prob:.0%}",
            f"  Overtrade tendency: {self.overtrade_mult:.1f}x",
            f"  Revenge trade probability: {self.revenge_trade_prob:.0%}",
            f"  Contrarian probability: {self.contrarian_prob:.0%}",
            f"  Signal acceptance threshold: {self.signal_accept_threshold:.0%}",
            f"",
            f"HISTORICAL TRACK RECORD:",
        ]

        if self.n_samples > 0:
            lines += [
                f"  Samples: {self.n_samples}",
                f"  Win rate: {self.historical_win_rate:.0%}",
                f"  Profit factor: {self.historical_pf:.2f}",
                f"  Avg move: {self.historical_avg_move:+.3%}",
                f"  Direction: {self.pattern_direction}",
                f"  Score: {self.pattern_score:.2f}",
            ]
        else:
            lines.append("  No historical data available.")

        lines += [
            f"",
            f"VALUES: Achievement={self.schwartz_achievement}, "
            f"Security={self.schwartz_security}, Stimulation={self.schwartz_stimulation}",
            f"",
            f"When making trading decisions, stay in character. Your risk tolerance, "
            f"patience level, and decision style should consistently influence "
            f"every trade you evaluate.",
        ]

        return "\n".join(lines)

    def trading_bio(self) -> str:
        """Short 1-line description."""
        return (
            f"{self.fidaria_main}-{self.fidaria_sub} H{self.house} {self.moon_phase} | "
            f"{self.decision_speed} {self.risk_tolerance} "
            f"{'trader' if 'trader' in self.investment_style else self.investment_style}"
        )

    def _build_llm_refinement_prompt(self, chart: ChartSnapshot) -> str:
        """Build prompt for LLM-based trait refinement."""
        return f"""Refine the trading personality profile below based on the natal chart context.

CURRENT PROFILE:
{self.to_trait_dict()}

CHART CONTEXT:
  Ticker: {chart.ticker}
  ASC: {chart.ascendant.sign_name} {chart.ascendant.degree_in_sign:.1f}°
  Sect: {chart.sect}  Hllaj: {chart.hllaj}  Kadukhadah: {chart.kadukhadah}
  Planets: {', '.join(f'{p.name}@{p.sign_name}{p.degree_in_sign:.1f}' for p in chart.planets.values())}

Refine up to 8 traits that would MOST change based on the chart specifics.
Return JSON: {{"traits": {{"risk_tolerance": "risk_tolerant", "patience": "high", ...}}}}
Only include traits you want to CHANGE from the current profile.
Valid values per dimension must be from the predefined sets."""


# ====================================================================
# BATCH GENERATION
# ====================================================================

def generate_trader_personas_from_learned(
    learned: dict,
    ticker: str,
    chart_snapshot: Optional[ChartSnapshot] = None,
    use_llm: bool = False,
    llm_api_key: Optional[str] = None,
) -> list[TraderPersona]:
    """
    Convert all learned patterns into TraderPersona objects.

    MatrAIx analog: generate_profiles_from_entities() batch.
    Handles field name variations from pattern_engine_v2.
    """
    personas = []

    for state_key, pat_data in learned.items():
        # Normalize field names from pattern_engine_v2 (which may use different keys)
        direction = pat_data.get("direction", "LONG")
        horizon = pat_data.get("horizon", pat_data.get("h", 5))
        n_samples = pat_data.get("n_samples", pat_data.get("n", 0))
        win_rate = pat_data.get("win_rate", pat_data.get("wr", pat_data.get("edge", 0.0)))
        avg_move = pat_data.get("avg_move", pat_data.get("mean", pat_data.get("mv", 0.0)))
        std_move = pat_data.get("std_move", pat_data.get("std", 0.0))

        # Compute profit_factor from available fields if not present
        pf = pat_data.get("profit_factor", pat_data.get("pf", None))
        if pf is None:
            # PF = (wr * avg_win) / ((1-wr) * avg_loss)
            # Approximation: if avg_move > 0 and win_rate > 0.5, PF ≈ wr / (1-wr) * avg_move_ratio
            if win_rate > 0 and win_rate < 1.0 and avg_move > 0:
                # Rough PF estimate from WR and mean return
                pf = win_rate / max(0.01, 1.0 - win_rate) * (abs(avg_move) / max(0.001, abs(avg_move)))
            elif win_rate > 0 and win_rate < 1.0:
                pf = win_rate / max(0.01, 1.0 - win_rate) * 0.5  # conservative
            else:
                pf = 0.0

        p_value = pat_data.get("p_value", pat_data.get("p", 1.0))
        score = pat_data.get("score", pat_data.get("s", 0.0))
        parts = state_key.split("_")
        try:
            h_part = next((p for p in parts if p.startswith("H")), "H1")
            mp_part = next((p for p in parts if p.startswith("MP")), "MP0")
            house = int(h_part[1:])
            moon_phase = mp_part
            fid_main = parts[0] if len(parts) > 0 else "?"
            fid_sub = parts[1] if len(parts) > 1 else "?"
            dist = parts[2] if len(parts) > 2 else "?"
        except (ValueError, IndexError):
            house = 1; moon_phase = "MP0"
            fid_main = fid_sub = dist = "?"

        from astro_knowledge import SourceRef, DataSourceKind
        pattern = PatternCard(
            as_of=datetime.now(),
            state_key=state_key,
            direction=direction,
            horizon=horizon,
            n_samples=n_samples,
            win_rate=win_rate,
            avg_move=avg_move,
            std_move=std_move,
            profit_factor=pf,
            p_value=p_value,
            score=score,
            source=SourceRef(kind=DataSourceKind.YAHOO, symbol=f"{ticker}=F"),
        ) if n_samples > 0 else None

        if use_llm and chart_snapshot and llm_api_key:
            persona = TraderPersona.generate_with_llm(
                state_key, ticker, chart_snapshot,
                fid_main, fid_sub, dist, moon_phase, house,
                pattern, llm_api_key,
            )
        else:
            persona = TraderPersona.generate_from_astro_state(
                state_key, ticker,
                fid_main, fid_sub, dist, moon_phase, house,
                pattern,
            )

        personas.append(persona)

    return personas


# ====================================================================
# SELF-TEST
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(" TRADER PERSONAS V2 — MatrAIx-Style Self-Test")
    print("=" * 60)

    # Test persona generation from astro state
    print("\n--- Malefic, Angular, Fast Moon (breakout hunter) ---")
    p1 = TraderPersona.generate_from_astro_state(
        "Mars_Saturn_Mercury_H1_MP2_7d", "NQ",
        "Mars", "Saturn", "Mercury", "MP2", 1,
    )
    print(f"  Risk: {p1.risk_tolerance} | Excite: {p1.excitement_seeking}")
    print(f"  Position: {p1.position_size_pct:.0%} | Stop: {p1.stop_tightness:.0%}")
    print(f"  Conviction mult: {p1.conviction_mult} | Error rate: {p1.error_rate:.0%}")
    print(f"  Panic exit: {p1.panic_exit_prob:.0%} | Revenge: {p1.revenge_trade_prob:.0%}")

    print("\n--- Benefic, Cadent, Slow Moon (defensive holder) ---")
    p2 = TraderPersona.generate_from_astro_state(
        "Venus_Jupiter_Sun_H12_MP5_7d", "ES",
        "Venus", "Jupiter", "Sun", "MP5", 12,
    )
    print(f"  Risk: {p2.risk_tolerance} | Excite: {p2.excitement_seeking}")
    print(f"  Position: {p2.position_size_pct:.0%} | Max hold: {p2.max_hold_days}d")
    print(f"  Systematic: {p2.systematic_weight:.0%} | Rule adherence: {p2.rule_adherence:.0%}")
    print(f"  Decision speed: {p2.decision_speed} | Bull bias: {p2.bull_bias:.0%}")

    print("\n--- With Pattern Memory ---")
    from astro_knowledge import PatternCard, SourceRef, DataSourceKind
    pat = PatternCard(
        as_of=datetime.now(), state_key="Test_Key", direction="LONG",
        horizon=5, n_samples=45, win_rate=0.62, avg_move=0.012,
        std_move=0.025, profit_factor=1.8, p_value=0.003, score=2.5,
        source=SourceRef(kind=DataSourceKind.YAHOO, symbol="NQ=F"),
    )
    p3 = TraderPersona.generate_from_astro_state(
        "Jupiter_Moon_Mars_H4_MP3_5d", "NQ",
        "Jupiter", "Moon", "Mars", "MP3", 4, pat,
    )
    print(f"  WR: {p3.historical_win_rate:.0%}  PF: {p3.historical_pf:.2f}")
    print(f"  Bio: {p3.trading_bio()}")
    
    # System prompt excerpt
    prompt = p3.to_system_prompt()
    print(f"\n  System prompt ({len(prompt)} chars) — first 300:")
    print(f"  {prompt[:300]}...")

    # Validate
    errors = p3.validate()
    print(f"\n  Validation: {'PASS' if not errors else 'FAIL — ' + str(errors)}")

    # Test batch generation
    print("\n--- Batch Generation ---")
    mock_learned = {
        "Mars_Saturn_Mercury_H1_MP2_7d": {
            "direction": "LONG", "horizon": 7, "n_samples": 20, "win_rate": 0.55,
            "avg_move": 0.01, "std_move": 0.03, "profit_factor": 1.4,
            "p_value": 0.01, "score": 0.30,
        },
        "Venus_Jupiter_Venus_H4_MP3_7d": {
            "direction": "LONG", "horizon": 7, "n_samples": 19, "win_rate": 0.895,
            "avg_move": 0.02, "std_move": 0.03, "profit_factor": 3.2,
            "p_value": 0.0003, "score": 0.59,
        },
    }
    personas = generate_trader_personas_from_learned(mock_learned, "NQ")
    print(f"  Generated {len(personas)} personas from {len(mock_learned)} patterns")
    for p in personas:
        print(f"    [{p.persona_id[:30]}] {p.trading_bio()}")
        print(f"      Risk={p.risk_tolerance} Stop={p.stop_tightness:.0%} MaxHold={p.max_hold_days}d")

    print("\n" + "=" * 60)
    print(" SELF-TEST COMPLETE")
    print("=" * 60)

"""
TRADER PERSONA SCHEMA — MatrAIx-Adapted Trading Dimensions
=============================================================
50 dimensions adapted from MatrAIx's 1,290-dimension persona schema,
specifically curated for financial trading personas.

Architecture (from MatrAIx):
  - Each dimension has a categorical value set (discrete, mutually exclusive)
  - Dimensions are orthogonal — one value per dimension per persona
  - Covers: Risk, Decision-Making, Personality (Big Five), Cognitive Style,
    Values, Behavior, Lifestyle, AI Adoption (trader-tool usage)
  - DIMENSION_DERIVATIONS map categorical values → numerical trading parameters

The schema is used by:
  1. astro_personas.TraderPersona — to define each persona's trait profile
  2. astro_simulation.MarketSimulation — to derive trading behavior from traits
  3. LLM conditioning — to inject persona profile into system prompts
"""

from __future__ import annotations
from typing import Literal

# ====================================================================
# DIMENSION DEFINITIONS — 50 dimensions across 8 categories
# ====================================================================

RISK_DIMENSIONS = {
    "risk_tolerance": {
        "label": "Risk Tolerance",
        "values": ["risk_averse", "cautious", "balanced", "risk_tolerant", "risk_seeking"],
        "category": "Risk & Decision",
        "source": "MatrAIx risk_tolerance",
    },
    "financial_risk_tolerance": {
        "label": "Financial Risk Tolerance (DOSPERT)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Risk & Decision",
        "source": "MatrAIx dospert_financial_risk_tolerance",
    },
    "max_drawdown_tolerance_pct": {
        "label": "Max Drawdown Tolerance",
        "values": ["5%", "10%", "15%", "25%", "40%", "no_limit"],
        "category": "Risk & Decision",
        "source": "Derived from risk_tolerance × bfi2_anxiety",
    },
    "position_sizing_style": {
        "label": "Position Sizing Style",
        "values": ["fixed_fractional", "kelly_criterion", "volatility_adjusted", "martingale", "intuition_based"],
        "category": "Risk & Decision",
        "source": "Derived from decision_style × numeracy_comfort",
    },
}

DECISION_DIMENSIONS = {
    "decision_style": {
        "label": "Decision Style",
        "values": ["analytical", "intuitive", "consensus_driven", "directive", "deliberative"],
        "category": "Decision-Making",
        "source": "MatrAIx decision_style",
    },
    "need_for_closure": {
        "label": "Need for Closure",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Decision-Making",
        "source": "MatrAIx need_for_closure",
    },
    "entry_trigger_style": {
        "label": "Entry Trigger Style",
        "values": ["signal_only", "signal_plus_confirmation", "signal_plus_confluence", "discretionary_override", "gut_feel"],
        "category": "Decision-Making",
        "source": "Derived from decision_style × plan_vs_spontaneous",
    },
    "exit_trigger_style": {
        "label": "Exit Trigger Style",
        "values": ["strict_sl_tp", "trailing_stop", "time_based", "condition_change", "discretionary"],
        "category": "Decision-Making",
        "source": "Derived from need_for_closure × patience",
    },
}

PERSONALITY_DIMENSIONS = {
    "assertiveness": {
        "label": "Assertiveness (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_assertiveness",
    },
    "anxiety": {
        "label": "Anxiety (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_anxiety",
    },
    "open_mindedness": {
        "label": "Open-Mindedness (BFI-2 domain)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_domain_open_mindedness",
    },
    "self_discipline": {
        "label": "Self-Discipline (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_self_discipline",
    },
    "excitement_seeking": {
        "label": "Excitement-Seeking (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_excitement_seeking",
    },
    "trust": {
        "label": "Trust (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_trust",
    },
    "emotional_volatility": {
        "label": "Emotional Volatility (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_emotional_volatility",
    },
    "achievement_striving": {
        "label": "Achievement-Striving (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_achievement_striving",
    },
    "cautiousness": {
        "label": "Cautiousness (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_cautiousness",
    },
    "intellectual_curiosity": {
        "label": "Intellectual Curiosity (BFI-2)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Personality: Big Five",
        "source": "MatrAIx bfi2_facet_intellectual_curiosity",
    },
}

COGNITIVE_DIMENSIONS = {
    "patience": {
        "label": "Patience",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_patience",
    },
    "ambiguity_tolerance": {
        "label": "Ambiguity Tolerance",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_ambiguity_tolerance",
    },
    "optimism": {
        "label": "Optimism",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_optimism",
    },
    "decision_speed": {
        "label": "Decision Speed",
        "values": ["snap_decisions", "quick", "balanced", "deliberate", "agonizes"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_decision_speed",
    },
    "confidence_calibration": {
        "label": "Confidence Calibration",
        "values": ["overconfident", "confident", "well_calibrated", "cautious", "underconfident"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_confidence_calibration",
    },
    "numeracy_comfort": {
        "label": "Numeracy Comfort",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_numeracy_comfort",
    },
    "detail_orientation": {
        "label": "Detail Orientation",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_detail_orientation",
    },
    "skepticism": {
        "label": "Skepticism",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_skepticism",
    },
    "big_picture_vs_detail": {
        "label": "Big Picture vs Detail",
        "values": ["big_picture_only", "big_picture", "both", "detail", "detail_obsessed"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_big_picture_vs_detail",
    },
    "risk_framing": {
        "label": "Risk Framing",
        "values": ["opportunity_focused", "balanced", "threat_focused"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_risk_framing",
    },
    "emotional_expressiveness": {
        "label": "Emotional Expressiveness",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_emotional_expressiveness",
    },
    "perfectionism": {
        "label": "Perfectionism",
        "values": ["very_low", "low", "moderate", "high", "very_high"],
        "category": "Cognitive Style",
        "source": "MatrAIx cog_perfectionism",
    },
}

PREFERENCE_DIMENSIONS = {
    "novelty_vs_familiarity": {
        "label": "Novelty vs Familiarity",
        "values": ["always_novel", "novelty_leaning", "balanced", "comfort_leaning", "always_familiar"],
        "category": "Preferences",
        "source": "MatrAIx pref_novelty_vs_familiarity",
    },
    "speed_vs_accuracy": {
        "label": "Speed vs Accuracy",
        "values": ["speed_first", "speed_leaning", "balanced", "accuracy_leaning", "accuracy_first"],
        "category": "Preferences",
        "source": "MatrAIx pref_speed_vs_accuracy",
    },
    "quality_vs_quantity": {
        "label": "Quality vs Quantity (trade selectivity)",
        "values": ["quality_first", "quality_leaning", "balanced", "quantity_leaning", "quantity_first"],
        "category": "Preferences",
        "source": "MatrAIx pref_quality_vs_quantity",
    },
    "plan_vs_spontaneous": {
        "label": "Planned vs Spontaneous",
        "values": ["highly_planned", "planned", "balanced", "spontaneous", "highly_spontaneous"],
        "category": "Preferences",
        "source": "MatrAIx pref_plan_vs_spontaneous",
    },
    "stability_vs_change": {
        "label": "Stability vs Change",
        "values": ["craves_stability", "stability_leaning", "balanced", "change_leaning", "craves_change"],
        "category": "Preferences",
        "source": "MatrAIx pref_stability_vs_change",
    },
    "logic_vs_intuition": {
        "label": "Logic vs Intuition",
        "values": ["pure_logic", "logic_leaning", "balanced", "intuition_leaning", "pure_intuition"],
        "category": "Preferences",
        "source": "MatrAIx pref_logic_vs_intuition",
    },
    "lead_vs_follow": {
        "label": "Lead vs Follow (contrarian vs herd)",
        "values": ["always_leads", "leans_lead", "situational", "leans_support", "prefers_follow"],
        "category": "Preferences",
        "source": "MatrAIx pref_lead_vs_follow",
    },
    "routine_vs_variety": {
        "label": "Routine vs Variety (strategy consistency)",
        "values": ["craves_routine", "routine_leaning", "balanced", "variety_leaning", "craves_variety"],
        "category": "Preferences",
        "source": "MatrAIx pref_routine_vs_variety",
    },
}

VALUES_DIMENSIONS = {
    "schwartz_achievement": {
        "label": "Achievement Value",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Values & Motivation",
        "source": "MatrAIx schwartz_value_achievement",
    },
    "schwartz_power": {
        "label": "Power Value",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Values & Motivation",
        "source": "MatrAIx schwartz_value_power",
    },
    "schwartz_security": {
        "label": "Security Value",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Values & Motivation",
        "source": "MatrAIx schwartz_value_security",
    },
    "schwartz_stimulation": {
        "label": "Stimulation Value",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Values & Motivation",
        "source": "MatrAIx schwartz_value_stimulation",
    },
    "schwartz_hedonism": {
        "label": "Hedonism Value (trading for thrill)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Values & Motivation",
        "source": "MatrAIx schwartz_value_hedonism",
    },
    "schwartz_self_direction": {
        "label": "Self-Direction Value (independent thinking)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Values & Motivation",
        "source": "MatrAIx schwartz_value_self_direction",
    },
    "schwartz_conformity": {
        "label": "Conformity Value (herd behavior)",
        "values": ["very_low", "low", "average", "high", "very_high"],
        "category": "Values & Motivation",
        "source": "MatrAIx schwartz_value_conformity",
    },
}

LIFESTYLE_DIMENSIONS = {
    "investment_style": {
        "label": "Investment Style",
        "values": ["index_investor", "active_trader", "crypto_heavy", "real_estate", "cash_saver", "none"],
        "category": "Lifestyle",
        "source": "MatrAIx lstyle_investment_style",
    },
    "frugality": {
        "label": "Frugality (profit reinvestment)",
        "values": ["frugal_saver", "balanced", "spender", "splurger"],
        "category": "Lifestyle",
        "source": "MatrAIx lstyle_frugality",
    },
    "goal_setting": {
        "label": "Goal Setting Habit",
        "values": ["daily", "weekly", "monthly", "rarely", "never"],
        "category": "Lifestyle",
        "source": "MatrAIx habit_goal_setting",
    },
    "screen_time": {
        "label": "Screen Time (market monitoring)",
        "values": ["constant", "high", "moderate", "low", "minimal"],
        "category": "Lifestyle",
        "source": "MatrAIx lstyle_screen_time",
    },
}

AI_ADOPTION_DIMENSIONS = {
    "ai_usage_frequency": {
        "label": "AI Tool Usage (trading)",
        "values": ["daily", "weekly", "monthly", "tried_not_active", "never_used", "actively_avoids"],
        "category": "AI Adoption",
        "source": "MatrAIx coding_ai_usage_frequency",
    },
    "ai_trust": {
        "label": "AI Output Trust",
        "values": ["strongly_trusts", "trusts_after_verify", "neutral", "distrusts_until_proven", "does_not_trust"],
        "category": "AI Adoption",
        "source": "MatrAIx coding_ai_output_trust",
    },
}

# ====================================================================
# ALL DIMENSIONS — flat dict for iteration
# ====================================================================

ALL_DIMENSIONS = {}
ALL_DIMENSIONS.update(RISK_DIMENSIONS)
ALL_DIMENSIONS.update(DECISION_DIMENSIONS)
ALL_DIMENSIONS.update(PERSONALITY_DIMENSIONS)
ALL_DIMENSIONS.update(COGNITIVE_DIMENSIONS)
ALL_DIMENSIONS.update(PREFERENCE_DIMENSIONS)
ALL_DIMENSIONS.update(VALUES_DIMENSIONS)
ALL_DIMENSIONS.update(LIFESTYLE_DIMENSIONS)
ALL_DIMENSIONS.update(AI_ADOPTION_DIMENSIONS)

TOTAL_DIMENSIONS = len(ALL_DIMENSIONS)

# ====================================================================
# DIMENSION → NUMERICAL DERIVATION MAP
# ====================================================================
# Maps each dimension value to a numerical trading parameter.
# Used by TraderPersona._derive_parameters() and MarketSimulation.

DIMENSION_DERIVATIONS = {
    # --- Risk → position sizing ---
    "risk_tolerance": {
        "risk_averse":     {"position_size_pct": 0.02, "max_hold_days": 3, "stop_tightness": 0.03},
        "cautious":         {"position_size_pct": 0.05, "max_hold_days": 5, "stop_tightness": 0.05},
        "balanced":         {"position_size_pct": 0.10, "max_hold_days": 10, "stop_tightness": 0.08},
        "risk_tolerant":    {"position_size_pct": 0.20, "max_hold_days": 20, "stop_tightness": 0.12},
        "risk_seeking":     {"position_size_pct": 0.35, "max_hold_days": 60, "stop_tightness": 0.20},
    },

    # --- Anxiety → stop-loss behavior ---
    "anxiety": {
        "very_low":  {"stop_tightness_mult": 0.6, "panic_exit_prob": 0.02},
        "low":       {"stop_tightness_mult": 0.8, "panic_exit_prob": 0.05},
        "average":   {"stop_tightness_mult": 1.0, "panic_exit_prob": 0.10},
        "high":      {"stop_tightness_mult": 1.3, "panic_exit_prob": 0.20},
        "very_high": {"stop_tightness_mult": 1.6, "panic_exit_prob": 0.35},
    },

    # --- Patience → hold duration ---
    "patience": {
        "very_low":  {"hold_mult": 0.3, "early_exit_prob": 0.40},
        "low":       {"hold_mult": 0.6, "early_exit_prob": 0.25},
        "moderate":  {"hold_mult": 1.0, "early_exit_prob": 0.10},
        "high":      {"hold_mult": 1.5, "early_exit_prob": 0.05},
        "very_high": {"hold_mult": 2.5, "early_exit_prob": 0.01},
    },

    # --- Optimism → directional bias ---
    "optimism": {
        "very_low":  {"bull_bias": 0.3, "short_prob": 0.50},
        "low":       {"bull_bias": 0.4, "short_prob": 0.35},
        "moderate":  {"bull_bias": 0.5, "short_prob": 0.20},
        "high":      {"bull_bias": 0.6, "short_prob": 0.10},
        "very_high": {"bull_bias": 0.7, "short_prob": 0.05},
    },

    # --- Confidence calibration → conviction scaling ---
    "confidence_calibration": {
        "overconfident":   {"conviction_mult": 1.4, "error_rate": 0.30},
        "confident":        {"conviction_mult": 1.2, "error_rate": 0.15},
        "well_calibrated":  {"conviction_mult": 1.0, "error_rate": 0.05},
        "cautious":         {"conviction_mult": 0.8, "error_rate": 0.08},
        "underconfident":   {"conviction_mult": 0.6, "error_rate": 0.03},
    },

    # --- Decision speed → trade frequency ---
    "decision_speed": {
        "snap_decisions":  {"trade_freq_mult": 2.0, "impulse_trade_prob": 0.30},
        "quick":           {"trade_freq_mult": 1.5, "impulse_trade_prob": 0.15},
        "balanced":        {"trade_freq_mult": 1.0, "impulse_trade_prob": 0.05},
        "deliberate":      {"trade_freq_mult": 0.6, "impulse_trade_prob": 0.02},
        "agonizes":        {"trade_freq_mult": 0.3, "impulse_trade_prob": 0.00},
    },

    # --- Excitement seeking → overtrading ---
    "excitement_seeking": {
        "very_low":  {"overtrade_mult": 0.5, "boredom_exit_prob": 0.01},
        "low":       {"overtrade_mult": 0.7, "boredom_exit_prob": 0.03},
        "average":   {"overtrade_mult": 1.0, "boredom_exit_prob": 0.05},
        "high":      {"overtrade_mult": 1.4, "boredom_exit_prob": 0.10},
        "very_high": {"overtrade_mult": 2.0, "boredom_exit_prob": 0.18},
    },

    # --- Self-discipline → rule following ---
    "self_discipline": {
        "very_low":  {"rule_adherence": 0.30, "revenge_trade_prob": 0.40},
        "low":       {"rule_adherence": 0.55, "revenge_trade_prob": 0.25},
        "average":   {"rule_adherence": 0.75, "revenge_trade_prob": 0.10},
        "high":      {"rule_adherence": 0.90, "revenge_trade_prob": 0.03},
        "very_high": {"rule_adherence": 0.98, "revenge_trade_prob": 0.01},
    },

    # --- Skepticism → signal filtering ---
    "skepticism": {
        "very_low":  {"signal_accept_threshold": 0.2, "contrarian_prob": 0.02},
        "low":       {"signal_accept_threshold": 0.4, "contrarian_prob": 0.05},
        "moderate":  {"signal_accept_threshold": 0.6, "contrarian_prob": 0.10},
        "high":      {"signal_accept_threshold": 0.8, "contrarian_prob": 0.18},
        "very_high": {"signal_accept_threshold": 0.9, "contrarian_prob": 0.25},
    },

    # --- Emotional volatility → regime reactivity ---
    "emotional_volatility": {
        "very_low":  {"regime_reactivity": 0.2, "tilt_prob": 0.01},
        "low":       {"regime_reactivity": 0.5, "tilt_prob": 0.05},
        "average":   {"regime_reactivity": 0.8, "tilt_prob": 0.10},
        "high":      {"regime_reactivity": 1.2, "tilt_prob": 0.20},
        "very_high": {"regime_reactivity": 1.6, "tilt_prob": 0.35},
    },

    # --- Plan vs spontaneous → systematic vs discretionary ---
    "plan_vs_spontaneous": {
        "highly_planned":     {"systematic_weight": 0.95, "override_prob": 0.02},
        "planned":            {"systematic_weight": 0.75, "override_prob": 0.08},
        "balanced":           {"systematic_weight": 0.50, "override_prob": 0.15},
        "spontaneous":        {"systematic_weight": 0.25, "override_prob": 0.30},
        "highly_spontaneous": {"systematic_weight": 0.05, "override_prob": 0.50},
    },

    # --- Achievement striving → profit motivation ---
    "achievement_striving": {
        "very_low":  {"profit_target_mult": 0.5, "effort_level": 0.3},
        "low":       {"profit_target_mult": 0.7, "effort_level": 0.5},
        "average":   {"profit_target_mult": 1.0, "effort_level": 0.7},
        "high":      {"profit_target_mult": 1.3, "effort_level": 0.9},
        "very_high": {"profit_target_mult": 1.6, "effort_level": 1.0},
    },

    # --- Need for closure → hold duration precision ---
    "need_for_closure": {
        "very_low":  {"close_early_mult": 0.5, "reenter_prob": 0.40},
        "low":       {"close_early_mult": 0.7, "reenter_prob": 0.25},
        "average":   {"close_early_mult": 1.0, "reenter_prob": 0.10},
        "high":      {"close_early_mult": 1.3, "reenter_prob": 0.05},
        "very_high": {"close_early_mult": 1.6, "reenter_prob": 0.01},
    },
}

# ====================================================================
# ASTRO STATE → PERSONALITY TRAIT MAPPING
# ====================================================================
# Maps fidaria ruler planet type (malefic/benefic/neutral) and
# house angularity to personality dimension values.
# Used by TraderPersona.generate_from_astro_state()

ASTRO_TRAIT_MAP = {
    # Key: (planet_class, angularity, moon_speed)
    ("malefic", "angular", "fast"): {
        "risk_tolerance": "risk_seeking",
        "excitement_seeking": "very_high",
        "assertiveness": "very_high",
        "anxiety": "low",
        "patience": "very_low",
        "decision_speed": "snap_decisions",
        "confidence_calibration": "overconfident",
        "self_discipline": "low",
        "emotional_volatility": "high",
        "plan_vs_spontaneous": "spontaneous",
        "novelty_vs_familiarity": "always_novel",
        "optimism": "high",
        "stability_vs_change": "craves_change",
        "schwartz_stimulation": "very_high",
        "schwartz_security": "low",
        "skepticism": "low",
        "lead_vs_follow": "always_leads",
    },
    ("malefic", "angular", "slow"): {
        "risk_tolerance": "risk_tolerant",
        "excitement_seeking": "high",
        "assertiveness": "high",
        "anxiety": "average",
        "patience": "low",
        "decision_speed": "quick",
        "confidence_calibration": "confident",
        "self_discipline": "average",
        "emotional_volatility": "average",
        "plan_vs_spontaneous": "balanced",
        "novelty_vs_familiarity": "novelty_leaning",
        "optimism": "moderate",
        "stability_vs_change": "change_leaning",
        "schwartz_stimulation": "high",
        "schwartz_security": "average",
        "skepticism": "moderate",
        "lead_vs_follow": "leans_lead",
    },
    ("malefic", "cadent", "fast"): {
        "risk_tolerance": "balanced",
        "excitement_seeking": "average",
        "assertiveness": "average",
        "anxiety": "high",
        "patience": "moderate",
        "decision_speed": "balanced",
        "confidence_calibration": "well_calibrated",
        "self_discipline": "average",
        "emotional_volatility": "high",
        "plan_vs_spontaneous": "balanced",
        "novelty_vs_familiarity": "balanced",
        "optimism": "low",
        "stability_vs_change": "balanced",
        "schwartz_stimulation": "average",
        "schwartz_security": "high",
        "skepticism": "high",
        "lead_vs_follow": "situational",
    },
    ("malefic", "cadent", "slow"): {
        "risk_tolerance": "cautious",
        "excitement_seeking": "low",
        "assertiveness": "low",
        "anxiety": "very_high",
        "patience": "high",
        "decision_speed": "deliberate",
        "confidence_calibration": "cautious",
        "self_discipline": "high",
        "emotional_volatility": "very_high",
        "plan_vs_spontaneous": "planned",
        "novelty_vs_familiarity": "comfort_leaning",
        "optimism": "very_low",
        "stability_vs_change": "stability_leaning",
        "schwartz_stimulation": "low",
        "schwartz_security": "very_high",
        "skepticism": "very_high",
        "lead_vs_follow": "leans_support",
    },

    ("benefic", "angular", "fast"): {
        "risk_tolerance": "risk_tolerant",
        "excitement_seeking": "high",
        "assertiveness": "high",
        "anxiety": "very_low",
        "patience": "moderate",
        "decision_speed": "quick",
        "confidence_calibration": "confident",
        "self_discipline": "average",
        "emotional_volatility": "low",
        "plan_vs_spontaneous": "balanced",
        "novelty_vs_familiarity": "novelty_leaning",
        "optimism": "very_high",
        "stability_vs_change": "balanced",
        "schwartz_stimulation": "high",
        "schwartz_security": "average",
        "skepticism": "low",
        "lead_vs_follow": "leans_lead",
    },
    ("benefic", "angular", "slow"): {
        "risk_tolerance": "balanced",
        "excitement_seeking": "average",
        "assertiveness": "average",
        "anxiety": "very_low",
        "patience": "high",
        "decision_speed": "balanced",
        "confidence_calibration": "well_calibrated",
        "self_discipline": "high",
        "emotional_volatility": "very_low",
        "plan_vs_spontaneous": "planned",
        "novelty_vs_familiarity": "balanced",
        "optimism": "high",
        "stability_vs_change": "balanced",
        "schwartz_stimulation": "average",
        "schwartz_security": "average",
        "skepticism": "moderate",
        "lead_vs_follow": "situational",
    },
    ("benefic", "cadent", "fast"): {
        "risk_tolerance": "cautious",
        "excitement_seeking": "low",
        "assertiveness": "low",
        "anxiety": "average",
        "patience": "moderate",
        "decision_speed": "balanced",
        "confidence_calibration": "cautious",
        "self_discipline": "average",
        "emotional_volatility": "average",
        "plan_vs_spontaneous": "balanced",
        "novelty_vs_familiarity": "balanced",
        "optimism": "moderate",
        "stability_vs_change": "balanced",
        "schwartz_stimulation": "low",
        "schwartz_security": "high",
        "skepticism": "moderate",
        "lead_vs_follow": "situational",
    },
    ("benefic", "cadent", "slow"): {
        "risk_tolerance": "risk_averse",
        "excitement_seeking": "very_low",
        "assertiveness": "very_low",
        "anxiety": "average",
        "patience": "very_high",
        "decision_speed": "agonizes",
        "confidence_calibration": "underconfident",
        "self_discipline": "very_high",
        "emotional_volatility": "low",
        "plan_vs_spontaneous": "highly_planned",
        "novelty_vs_familiarity": "always_familiar",
        "optimism": "low",
        "stability_vs_change": "craves_stability",
        "schwartz_stimulation": "very_low",
        "schwartz_security": "very_high",
        "skepticism": "high",
        "lead_vs_follow": "prefers_follow",
    },

    ("neutral", "angular", "fast"): {
        "risk_tolerance": "balanced",
        "excitement_seeking": "average",
        "assertiveness": "average",
        "anxiety": "low",
        "patience": "moderate",
        "decision_speed": "balanced",
        "confidence_calibration": "well_calibrated",
        "self_discipline": "average",
        "emotional_volatility": "low",
        "plan_vs_spontaneous": "balanced",
        "novelty_vs_familiarity": "balanced",
        "optimism": "moderate",
        "stability_vs_change": "balanced",
        "schwartz_stimulation": "average",
        "schwartz_security": "average",
        "skepticism": "moderate",
        "lead_vs_follow": "situational",
    },
    ("neutral", "angular", "slow"): {
        "risk_tolerance": "cautious",
        "excitement_seeking": "low",
        "assertiveness": "average",
        "anxiety": "average",
        "patience": "high",
        "decision_speed": "deliberate",
        "confidence_calibration": "well_calibrated",
        "self_discipline": "high",
        "emotional_volatility": "average",
        "plan_vs_spontaneous": "planned",
        "novelty_vs_familiarity": "balanced",
        "optimism": "moderate",
        "stability_vs_change": "balanced",
        "schwartz_stimulation": "low",
        "schwartz_security": "high",
        "skepticism": "moderate",
        "lead_vs_follow": "situational",
    },
    ("neutral", "cadent", "fast"): {
        "risk_tolerance": "cautious",
        "excitement_seeking": "low",
        "assertiveness": "low",
        "anxiety": "high",
        "patience": "low",
        "decision_speed": "quick",
        "confidence_calibration": "cautious",
        "self_discipline": "low",
        "emotional_volatility": "high",
        "plan_vs_spontaneous": "spontaneous",
        "novelty_vs_familiarity": "balanced",
        "optimism": "low",
        "stability_vs_change": "balanced",
        "schwartz_stimulation": "average",
        "schwartz_security": "average",
        "skepticism": "high",
        "lead_vs_follow": "leans_support",
    },
    ("neutral", "cadent", "slow"): {
        "risk_tolerance": "risk_averse",
        "excitement_seeking": "very_low",
        "assertiveness": "low",
        "anxiety": "high",
        "patience": "very_high",
        "decision_speed": "agonizes",
        "confidence_calibration": "underconfident",
        "self_discipline": "average",
        "emotional_volatility": "average",
        "plan_vs_spontaneous": "planned",
        "novelty_vs_familiarity": "comfort_leaning",
        "optimism": "low",
        "stability_vs_change": "stability_leaning",
        "schwartz_stimulation": "very_low",
        "schwartz_security": "very_high",
        "skepticism": "high",
        "lead_vs_follow": "prefers_follow",
    },
}

# Default traits when no mapping matches
DEFAULT_TRAITS = {
    "risk_tolerance": "balanced",
    "financial_risk_tolerance": "average",
    "excitement_seeking": "average",
    "assertiveness": "average",
    "anxiety": "average",
    "patience": "moderate",
    "decision_speed": "balanced",
    "confidence_calibration": "well_calibrated",
    "self_discipline": "average",
    "emotional_volatility": "average",
    "plan_vs_spontaneous": "balanced",
    "novelty_vs_familiarity": "balanced",
    "optimism": "moderate",
    "stability_vs_change": "balanced",
    "schwartz_stimulation": "average",
    "schwartz_security": "average",
    "skepticism": "moderate",
    "lead_vs_follow": "situational",
    "open_mindedness": "average",
    "trust": "average",
    "achievement_striving": "average",
    "cautiousness": "average",
    "intellectual_curiosity": "average",
    "need_for_closure": "average",
    "ambiguity_tolerance": "moderate",
    "numeracy_comfort": "moderate",
    "detail_orientation": "moderate",
    "big_picture_vs_detail": "both",
    "risk_framing": "balanced",
    "emotional_expressiveness": "moderate",
    "perfectionism": "moderate",
    "speed_vs_accuracy": "balanced",
    "quality_vs_quantity": "balanced",
    "logic_vs_intuition": "balanced",
    "routine_vs_variety": "balanced",
    "schwartz_achievement": "average",
    "schwartz_power": "average",
    "schwartz_hedonism": "average",
    "schwartz_self_direction": "average",
    "schwartz_conformity": "average",
    "investment_style": "active_trader",
    "frugality": "balanced",
    "goal_setting": "weekly",
    "screen_time": "moderate",
    "max_drawdown_tolerance_pct": "15%",
    "position_sizing_style": "fixed_fractional",
    "entry_trigger_style": "signal_plus_confirmation",
    "exit_trigger_style": "strict_sl_tp",
    "decision_style": "analytical",
    "ai_usage_frequency": "weekly",
    "ai_trust": "trusts_after_verify",
}

# ====================================================================
# CONVENIENCE
# ====================================================================

def get_all_dimension_ids() -> list[str]:
    return list(ALL_DIMENSIONS.keys())

def get_dimension_values(dim_id: str) -> list[str]:
    dim = ALL_DIMENSIONS.get(dim_id)
    return dim["values"] if dim else []

def get_category(dim_id: str) -> str:
    dim = ALL_DIMENSIONS.get(dim_id)
    return dim["category"] if dim else "Unknown"

def validate_traits(traits: dict[str, str]) -> list[str]:
    """Validate that all trait values are valid for their dimensions."""
    errors = []
    for dim_id, value in traits.items():
        valid = get_dimension_values(dim_id)
        if not valid:
            errors.append(f"Unknown dimension: {dim_id}")
        elif value not in valid:
            errors.append(f"Invalid value '{value}' for {dim_id}. Valid: {valid}")
    return errors


# ====================================================================
# SELF-TEST
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(f" TRADER PERSONA SCHEMA — {TOTAL_DIMENSIONS} dimensions")
    print("=" * 60)

    categories = {}
    for dim_id, dim in ALL_DIMENSIONS.items():
        cat = dim["category"]
        categories.setdefault(cat, []).append(dim_id)

    for cat, dims in sorted(categories.items()):
        print(f"\n  {cat}: {len(dims)} dimensions")
        for d in dims[:3]:
            print(f"    - {d}: {ALL_DIMENSIONS[d]['values']}")

    print(f"\n  DIMENSION_DERIVATIONS has {len(DIMENSION_DERIVATIONS)} derivation maps")
    print(f"  ASTRO_TRAIT_MAP has {len(ASTRO_TRAIT_MAP)} astro→trait profiles")
    print(f"  DEFAULT_TRAITS has {len(DEFAULT_TRAITS)} defaults")

    # Validate all default traits
    errors = validate_traits(DEFAULT_TRAITS)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
    else:
        print(f"\n  All {len(DEFAULT_TRAITS)} default trait values are valid.")

    print("\n" + "=" * 60)

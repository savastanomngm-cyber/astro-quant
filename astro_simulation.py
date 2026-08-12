"""
ASTRO SIMULATION V2 — TraderPersona-Driven Market Micro-Simulation
====================================================================
Upgraded from basic PlanetaryPersona voting to full TraderPersona-driven
simulation with dimension-derived behaviors (MatrAIx-style).

Each TraderPersona's 51-dimension profile determines:
  - When it votes (activation probability from screen_time × trade_freq)
  - What it votes (bull_bias, pattern_direction, contrarian_prob)
  - How strongly (conviction_mult × systematic_weight × effort_level)
  - Whether it exits early (early_exit_prob, panic_exit_prob)
  - Whether it revenge-trades (revenge_trade_prob after loss)
  - Whether it overrides signals (override_prob × systematic_weight)

This is the OASIS simulation equivalent: agent behaviors emerge from
persona dimensions rather than being hardcoded.
"""

from __future__ import annotations
import random
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Literal

from astro_personas import TraderPersona


# ====================================================================
# SIMULATION CONFIG
# ====================================================================

@dataclass
class SimulationConfig:
    max_agents_per_round: int = 5
    base_agents_min: int = 2
    base_agents_max: int = 7
    total_rounds: int = 50
    minutes_per_round: int = 1440
    base_volatility: float = 0.008
    sentiment_multiplier: float = 2.0
    noise_std: float = 0.003
    peak_house_multiplier: float = 1.5
    off_peak_multiplier: float = 0.5
    bullish_threshold: float = 0.15
    bearish_threshold: float = -0.15
    initial_price: float = 100.0
    random_seed: Optional[int] = None

    # New: TraderPersona-specific
    enable_behavioral_dynamics: bool = True  # panic exits, revenge trades, etc.
    enable_overtrading: bool = True          # boredom exits, impulse trades
    enable_contrarian_switches: bool = True   # skepticism-driven flips
    enable_emotion_volatility: bool = True    # regime reactivity, tilt


# ====================================================================
# SIMULATION RECORDS
# ====================================================================

@dataclass
class BarRecord:
    bar_index: int
    simulated_time: datetime
    active_personas: list[str] = field(default_factory=list)
    long_votes: int = 0
    short_votes: int = 0
    flat_votes: int = 0
    net_sentiment: float = 0.0
    open_price: float = 0.0
    close_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    return_pct: float = 0.0
    regime: str = "NEUTRAL"
    vote_details: list[dict] = field(default_factory=list)
    # New: behavioral events
    panic_exits: int = 0
    revenge_trades: int = 0
    impulse_trades: int = 0
    contrarian_flips: int = 0
    early_exits: int = 0


@dataclass
class SimulationResult:
    config: SimulationConfig
    ticker: str
    start_time: datetime
    end_time: datetime
    bars: list[BarRecord] = field(default_factory=list)
    total_rounds: int = 0
    bullish_rounds: int = 0
    bearish_rounds: int = 0
    neutral_rounds: int = 0
    final_price: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    volatility_pct: float = 0.0
    total_personas: int = 0
    personas_activated: set = field(default_factory=set)
    sentiment_price_correlation: float = 0.0
    # New: behavioral stats
    total_panic_exits: int = 0
    total_revenge_trades: int = 0
    total_impulse_trades: int = 0
    total_contrarian_flips: int = 0
    total_early_exits: int = 0


# ====================================================================
# MARKET SIMULATION ENGINE
# ====================================================================

class MarketSimulation:
    """MatrAIx-style multi-persona market simulation."""

    def __init__(
        self,
        config: SimulationConfig,
        personas: dict[str, TraderPersona],
        ticker: str = "NQ",
        actual_prices: Optional[list[float]] = None,
    ):
        self.cfg = config
        self.personas = personas
        self.ticker = ticker
        self.actual_prices = actual_prices

        if config.random_seed is not None:
            random.seed(config.random_seed)

        # Track persona state across rounds (for revenge trading, tilt)
        self._persona_state: dict[str, dict] = {}
        for pid in personas:
            self._persona_state[pid] = {
                "last_trade_result": None,  # "win" or "loss"
                "consecutive_losses": 0,
                "current_drawdown_pct": 0.0,
                "boredom_counter": 0,
                "rounds_since_last_trade": 0,
            }

    def run(self) -> SimulationResult:
        result = SimulationResult(
            config=self.cfg, ticker=self.ticker,
            start_time=datetime.now(), end_time=datetime.now(),
            total_personas=len(self.personas),
        )
        price = self.cfg.initial_price
        prices = [price]

        for round_num in range(self.cfg.total_rounds):
            simulated_minutes = round_num * self.cfg.minutes_per_round
            simulated_hour = (simulated_minutes // 60) % 24
            simulated_day = simulated_minutes // (60 * 24) + 1
            sim_time = datetime(2026, 1, 1) + timedelta(days=simulated_day - 1)

            # ACTIVATION — driven by screen_time + trade_freq
            active = self._activate_agents(simulated_hour)

            # VOTING — driven by persona dimensions
            votes, events = self._collect_votes(active, price, round_num)

            # AGGREGATE
            net_sentiment = self._aggregate_sentiment(votes)
            regime = "BULLISH" if net_sentiment >= self.cfg.bullish_threshold else \
                      "BEARISH" if net_sentiment <= self.cfg.bearish_threshold else "NEUTRAL"

            # PRICE
            price_change = self._sentiment_to_price(net_sentiment, price)
            new_price = price * (1.0 + price_change)
            intraday_range = abs(price_change) * 1.5 + self.cfg.noise_std * random.random()
            open_p, close_p = price, new_price
            high_p = max(open_p, close_p) + intraday_range * random.random()
            low_p = min(open_p, close_p) - intraday_range * random.random()

            # UPDATE PERSONA STATE after price is known
            round_went_up = price_change > 0
            for v in votes:
                pid = v["persona_id"]
                st = self._persona_state[pid]
                direction = v["direction"]
                if direction == "FLAT":
                    st["last_trade_result"] = None
                elif (direction == "LONG" and round_went_up) or (direction == "SHORT" and not round_went_up):
                    st["last_trade_result"] = "win"
                    st["consecutive_losses"] = 0
                else:
                    st["last_trade_result"] = "loss"
                    st["consecutive_losses"] = st.get("consecutive_losses", 0) + 1

            bar = BarRecord(
                bar_index=round_num, simulated_time=sim_time,
                active_personas=[p.persona_id for p in active],
                long_votes=sum(1 for v in votes if v["direction"] == "LONG"),
                short_votes=sum(1 for v in votes if v["direction"] == "SHORT"),
                flat_votes=sum(1 for v in votes if v["direction"] == "FLAT"),
                net_sentiment=net_sentiment,
                open_price=round(open_p, 4), close_price=round(close_p, 4),
                high_price=round(high_p, 4), low_price=round(low_p, 4),
                return_pct=round(price_change * 100, 4), regime=regime,
                vote_details=votes,
                panic_exits=events["panic"], revenge_trades=events["revenge"],
                impulse_trades=events["impulse"], contrarian_flips=events["contrarian"],
                early_exits=events["early"],
            )

            result.bars.append(bar)
            prices.append(close_p)
            price = close_p

            if regime == "BULLISH": result.bullish_rounds += 1
            elif regime == "BEARISH": result.bearish_rounds += 1
            else: result.neutral_rounds += 1

            result.total_panic_exits += events["panic"]
            result.total_revenge_trades += events["revenge"]
            result.total_impulse_trades += events["impulse"]
            result.total_contrarian_flips += events["contrarian"]
            result.total_early_exits += events["early"]

            for p in active:
                result.personas_activated.add(p.persona_id)

        # Aggregate stats
        result.end_time = datetime.now()
        result.total_rounds = len(result.bars)
        result.final_price = price
        result.total_return_pct = (price / self.cfg.initial_price - 1.0) * 100
        peak = self.cfg.initial_price
        mdd = 0.0
        for p in prices:
            peak = max(peak, p)
            dd = (p / peak - 1.0) * 100
            mdd = min(mdd, dd)
        result.max_drawdown_pct = mdd
        returns = [b.return_pct for b in result.bars]
        if returns:
            avg_ret = sum(returns) / len(returns)
            var = sum((r - avg_ret)**2 for r in returns) / len(returns)
            result.volatility_pct = math.sqrt(var)

        return result

    # ----- Agent Activation -----

    def _activate_agents(self, simulated_hour: int) -> list[TraderPersona]:
        candidates = []
        for pid, p in self.personas.items():
            state = self._persona_state[pid]
            state["rounds_since_last_trade"] += 1

            # Base activation probability from screen_time + trade_freq
            screen_map = {"constant": 0.95, "high": 0.80, "moderate": 0.50, "low": 0.25, "minimal": 0.10}
            base_p = screen_map.get(p.screen_time, 0.50)

            # Trade frequency multiplier
            base_p *= p.trade_freq_mult

            # Effort level
            base_p *= (0.5 + 0.5 * p.effort_level)

            # Boredom: if many rounds since last trade + high excitement seeking
            if self.cfg.enable_overtrading and state["rounds_since_last_trade"] > 5:
                boredom_bonus = min(0.3, state["rounds_since_last_trade"] * p.boredom_exit_prob)
                base_p = min(1.0, base_p + boredom_bonus)

            # Impulse trade: excitement-seeking drives random activation
            if self.cfg.enable_overtrading and random.random() < p.impulse_trade_prob:
                base_p = max(base_p, 0.8)

            if random.random() < base_p:
                candidates.append(p)

        # Select top by conviction
        candidates.sort(key=lambda x: x.conviction_mult * x.effort_level, reverse=True)
        target = min(
            random.randint(self.cfg.base_agents_min, self.cfg.base_agents_max),
            self.cfg.max_agents_per_round,
        )
        return candidates[:max(1, target)]

    # ----- Voting -----

    def _collect_votes(
        self, active: list[TraderPersona], price: float, round_num: int
    ) -> tuple[list[dict], dict]:
        votes = []
        events = {"panic": 0, "revenge": 0, "impulse": 0, "contrarian": 0, "early": 0}

        for p in active:
            state = self._persona_state[p.persona_id]
            direction = p.pattern_direction  # base from pattern
            conviction = p.conviction_mult
            risk = 5  # default

            # --- Behavioral dynamics ---

            # 1. Signal acceptance: skeptic personas ignore weak signals
            if self.cfg.enable_behavioral_dynamics:
                signal_strength = p.pattern_score / max(1.0, max(
                    x.pattern_score for x in self.personas.values()
                ))
                if signal_strength < p.signal_accept_threshold:
                    direction = "FLAT"

            # 2. Contrarian switch: skeptic + lead personality flips
            if self.cfg.enable_contrarian_switches and random.random() < p.contrarian_prob:
                direction = "SHORT" if direction == "LONG" else "LONG"
                events["contrarian"] += 1

            # 3. Revenge trade: after loss, low self-discipline doubles down
            if self.cfg.enable_behavioral_dynamics:
                if state["last_trade_result"] == "loss" and random.random() < p.revenge_trade_prob:
                    direction = "SHORT" if direction == "LONG" else "LONG"  # flip
                    conviction *= 1.5  # revenge trades are high conviction
                    events["revenge"] += 1

            # 4. Panic exit: high anxiety → FLAT after a loss
            if self.cfg.enable_behavioral_dynamics:
                if state["last_trade_result"] == "loss" and random.random() < p.panic_exit_prob:
                    direction = "FLAT"
                    events["panic"] += 1

            # 5. Early exit (boredom): high excitement-seeking exits winning trades
            if self.cfg.enable_overtrading:
                if random.random() < p.boredom_exit_prob:
                    direction = "FLAT"
                    events["early"] += 1

            # 6. Emotional volatility → tilt: consecutive losses amplify
            if self.cfg.enable_emotion_volatility and state["consecutive_losses"] >= 2:
                if random.random() < p.tilt_prob:
                    state["consecutive_losses"] = 0  # reset tilt
                    direction = random.choice(["LONG", "SHORT"])
                    conviction = 2.0
                    events["impulse"] += 1

            # 7. Systematic weight: override probability
            if self.cfg.enable_behavioral_dynamics:
                if random.random() < p.override_prob * (1.0 - p.systematic_weight):
                    direction = random.choice(["LONG", "SHORT", "FLAT"])

            # Apply conviction × effort
            weight = conviction * (0.5 + 0.5 * p.effort_level)

            # Risk level from risk_tolerance
            risk_map = {"risk_averse": 2, "cautious": 3, "balanced": 5, "risk_tolerant": 7, "risk_seeking": 9}
            risk = risk_map.get(p.risk_tolerance, 5)

            votes.append({
                "persona_id": p.persona_id,
                "direction": direction,
                "conviction": weight,
                "risk_level": risk,
                "traits": {
                    "risk": p.risk_tolerance,
                    "patience": p.patience,
                    "discipline": p.self_discipline,
                    "skepticism": p.skepticism,
                },
            })

            # Mark active — full state update happens after price is computed
            state["rounds_since_last_trade"] = 0

        return votes, events

    def _aggregate_sentiment(self, votes: list[dict]) -> float:
        if not votes: return 0.0
        tw, ws = 0.0, 0.0
        for v in votes:
            w = v["conviction"] * (v["risk_level"] / 10.0 + 0.5)
            tw += w
            if v["direction"] == "LONG": ws += w
            elif v["direction"] == "SHORT": ws -= w
        return ws / tw if tw > 0 else 0.0

    def _sentiment_to_price(self, ns: float, cp: float) -> float:
        d = ns * self.cfg.sentiment_multiplier * self.cfg.base_volatility
        return d + random.gauss(0, self.cfg.noise_std)


# ====================================================================
# COMPARISON + SELF-TEST
# ====================================================================

def compare_simulation_to_actual(sim: SimulationResult, returns: list[float]) -> dict:
    sr = [b.return_pct for b in sim.bars]
    n = min(len(sr), len(returns)); sr = sr[:n]; ar = returns[:n]
    if n < 3: return {"error": "not enough data"}
    same = sum(1 for s, a in zip(sr, ar) if (s>0 and a>0) or (s<0 and a<0))
    da = same / n
    mae = sum(abs(s-a) for s,a in zip(sr,ar)) / n
    ms, ma = sum(sr)/n, sum(ar)/n
    cov = sum((sr[i]-ms)*(ar[i]-ma) for i in range(n))/n
    ss, sa = math.sqrt(sum((s-ms)**2 for s in sr)/n), math.sqrt(sum((a-ma)**2 for a in ar)/n)
    corr = cov/(ss*sa) if ss>0 and sa>0 else 0.0
    return {"n":n,"directional_accuracy":round(da,4),"mae":round(mae,4),
            "correlation":round(corr,4),"sim_total_return":round(sum(sr),2),
            "actual_total_return":round(sum(ar),2)}


if __name__ == "__main__":
    print("=" * 60)
    print(" ASTRO SIMULATION V2 — TraderPersona Self-Test")
    print("=" * 60)

    from astro_personas import TraderPersona, generate_trader_personas_from_learned

    mock = {
        "Mars_Saturn_Mercury_H1_MP2_7d": {"direction":"SHORT","horizon":7,"n_samples":20,"win_rate":0.55,"avg_move":-0.008,"std_move":0.035,"profit_factor":1.4,"p_value":0.01,"score":0.30},
        "Venus_Jupiter_Venus_H4_MP3_7d": {"direction":"LONG","horizon":7,"n_samples":19,"win_rate":0.895,"avg_move":0.02,"std_move":0.03,"profit_factor":3.2,"p_value":0.0003,"score":0.59},
        "Mercury_Mercury_Venus_H7_MP1_7d": {"direction":"LONG","horizon":7,"n_samples":31,"win_rate":0.903,"avg_move":0.021,"std_move":0.04,"profit_factor":4.5,"p_value":0.0001,"score":2.07},
        "Mercury_Sun_Jupiter_H6_MP5_7d": {"direction":"LONG","horizon":7,"n_samples":33,"win_rate":0.727,"avg_move":0.0127,"std_move":0.03,"profit_factor":1.8,"p_value":0.002,"score":0.48},
        "Mercury_Jupiter_Mercury_H2_MP4_7d": {"direction":"SHORT","horizon":7,"n_samples":25,"win_rate":0.32,"avg_move":-0.0315,"std_move":0.05,"profit_factor":0.7,"p_value":0.12,"score":0.51},
        "Saturn_Mars_Moon_H7_MP7_3d": {"direction":"SHORT","horizon":3,"n_samples":15,"win_rate":0.60,"avg_move":-0.015,"std_move":0.04,"profit_factor":1.5,"p_value":0.03,"score":0.25},
    }
    personas_list = generate_trader_personas_from_learned(mock, "NQ")
    personas = {p.persona_id: p for p in personas_list}
    print(f"\n{len(personas)} personas generated:")

    # Show dimension spread
    from collections import Counter
    risks = Counter(p.risk_tolerance for p in personas.values())
    speeds = Counter(p.decision_speed for p in personas.values())
    stops = Counter(f"{p.stop_tightness:.0%}" for p in personas.values())
    print(f"  Risk spread: {dict(risks)}")
    print(f"  Decision speed: {dict(speeds)}")
    print(f"  Stop tightness: {dict(stops)}")

    # Run simulation
    cfg = SimulationConfig(total_rounds=30, base_agents_min=2, base_agents_max=5,
                           random_seed=42, enable_behavioral_dynamics=True,
                           enable_contrarian_switches=True, enable_overtrading=True,
                           enable_emotion_volatility=True)
    sim = MarketSimulation(cfg, personas, "NQ")
    result = sim.run()

    print(f"\nSimulation: {result.total_rounds} rounds")
    print(f"  Price: $100 → ${result.final_price:.2f} ({result.total_return_pct:+.2f}%)")
    print(f"  Regimes: {result.bullish_rounds}B/{result.bearish_rounds}Be/{result.neutral_rounds}N")
    print(f"  Behavioral events: panic={result.total_panic_exits} revenge={result.total_revenge_trades}")
    print(f"    impulse={result.total_impulse_trades} contrarian={result.total_contrarian_flips} early={result.total_early_exits}")

    print(f"\nFirst 8 bars:")
    print(f"{'Bar':>4} {'L':>3} {'S':>3} {'Sent':>7} {'Regime':<10} {'Ret%':>7} {'Events'}")
    print(f"{'-'*55}")
    for b in result.bars[:8]:
        ev = []
        if b.panic_exits: ev.append(f"panic:{b.panic_exits}")
        if b.revenge_trades: ev.append(f"rvng:{b.revenge_trades}")
        if b.contrarian_flips: ev.append(f"cntr:{b.contrarian_flips}")
        print(f"{b.bar_index:>4} {b.long_votes:>3} {b.short_votes:>3} {b.net_sentiment:>+7.3f} {b.regime:<10} {b.return_pct:>+7.2f} {','.join(ev) if ev else '—'}")

    print("\n" + "=" * 60)

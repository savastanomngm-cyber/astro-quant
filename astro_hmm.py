#!/usr/bin/env python3
"""
ASTRO-HMM — Hidden Markov Model for Market Regime Detection
=============================================================
Maps HMM theory (Jurafsky & Martin ch.A) onto astro-quant's
persona pipeline: astro states → hidden regimes → trading signals.

CORE INSIGHT:
  - Hidden states = market regimes (Bull, Bear, Range, Chop)
  - Observations = persona signal outcomes (win/loss, magnitude)
  - Transitions = probability of regime change between consecutive days
  - Emissions = probability of a signal outcome given a regime

ALGORITHMS (from the textbook):
  - Forward: P(signal_sequence | regime_model) — likelihood
  - Viterbi: most likely regime sequence given signal history
  - Baum-Welch: learn regime transition/emission probabilities from data

USE CASES:
  1. Regime detection: "Given recent signals, are we in bull/bear/range?"
  2. Signal filtering: "Reject LONG signals when HMM says bear regime"
  3. Transition forecasting: "What regime is most likely tomorrow?"
  4. Pattern validation: "How likely is this pattern sequence under normal conditions?"

No external deps beyond numpy. No PyTorch, no GPU.
"""

from __future__ import annotations
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

# ====================================================================
# REGIME DEFINITIONS
# ====================================================================

# Hidden states (market regimes)
REGIMES = ["BULL", "BEAR", "RANGE", "CHOP"]
N_REGIMES = len(REGIMES)
REGIME_INDEX = {r: i for i, r in enumerate(REGIMES)}

# Observation vocabulary: signal outcomes
OBSERVATIONS = [
    "LONG_WIN_BIG",     # LONG signal, win > 2%
    "LONG_WIN_SMALL",   # LONG signal, win 0-2%
    "LONG_LOSS_SMALL",  # LONG signal, loss 0-2%
    "LONG_LOSS_BIG",    # LONG signal, loss > 2%
    "SHORT_WIN_BIG",
    "SHORT_WIN_SMALL",
    "SHORT_LOSS_SMALL",
    "SHORT_LOSS_BIG",
    "NO_SIGNAL",
]
N_OBS = len(OBSERVATIONS)
OBS_INDEX = {o: i for i, o in enumerate(OBSERVATIONS)}


@dataclass
class HMMParams:
    """Full HMM parameter set λ = (π, A, B)."""
    pi: np.ndarray          # [N] initial state distribution
    A: np.ndarray           # [N x N] transition matrix A[i][j] = P(state_j | state_i)
    B: np.ndarray           # [N x M] emission matrix B[i][k] = P(obs_k | state_i)

    def __repr__(self):
        return (
            f"HMMParams(N={self.pi.shape[0]}, M={self.B.shape[1]}, "
            f"pi_sum={self.pi.sum():.4f}, A_rowsums_ok={np.allclose(self.A.sum(axis=1), 1.0)}, "
            f"B_rowsums_ok={np.allclose(self.B.sum(axis=1), 1.0)})"
        )


# ====================================================================
# DEFAULT PARAMETERS (sensible priors for trading)
# ====================================================================

def default_hmm_params() -> HMMParams:
    """
    Default HMM parameters with trading-domain priors.

    Transition matrix reflects market reality:
      - Bull/Bear regimes persist (self-transition ~0.7)
      - Range is sticky but resolves to Bull or Bear
      - Chop is temporary — resolves quickly

    Emission matrix reflects persona signal quality by regime:
      - Bull: LONG wins common, SHORT losses common
      - Bear: SHORT wins common, LONG losses common
      - Range: mixed outcomes, more small wins/losses
      - Chop: random outcomes, high loss rate
    """
    # Initial state: assume we start in a bull market (conservative)
    pi = np.array([0.35, 0.20, 0.30, 0.15])

    # Transition matrix
    #           BULL  BEAR  RANGE  CHOP
    A = np.array([
        [0.70, 0.05, 0.20, 0.05],  # BULL → mostly stays BULL or goes to RANGE
        [0.05, 0.70, 0.20, 0.05],  # BEAR → mostly stays BEAR or goes to RANGE
        [0.25, 0.25, 0.40, 0.10],  # RANGE → resolves to BULL/BEAR or stays
        [0.20, 0.20, 0.30, 0.30],  # CHOP → resolves or persists briefly
    ])

    # Emission matrix: P(signal_outcome | regime)
    #           BIG_W  SM_W  SM_L  BIG_L  (LONG, then SHORT, then NO_SIG)
    B = np.array([
        # BULL: LONG wins frequent, SHORT losses frequent
        [0.15, 0.30, 0.10, 0.02,  0.01, 0.01, 0.15, 0.10, 0.16],
        # BEAR: SHORT wins frequent, LONG losses frequent
        [0.02, 0.10, 0.30, 0.15,  0.10, 0.15, 0.01, 0.01, 0.16],
        # RANGE: mixed, more small outcomes
        [0.05, 0.15, 0.15, 0.05,  0.05, 0.15, 0.15, 0.05, 0.20],
        # CHOP: high noise, high loss rate
        [0.03, 0.08, 0.18, 0.18,  0.03, 0.08, 0.18, 0.18, 0.06],
    ])

    return HMMParams(pi=pi, A=A, B=B)


# ====================================================================
# HELPER: CONVERT PERSONA SIGNAL TO OBSERVATION
# ====================================================================

def signal_to_observation(direction: str, win: bool, pct_change: float) -> str:
    """
    Convert a persona signal result into an HMM observation token.

    Args:
        direction: "LONG" or "SHORT"
        win: True if trade was profitable
        pct_change: absolute percentage return

    Returns:
        Observation string like "LONG_WIN_BIG" or "SHORT_LOSS_SMALL"
    """
    if direction not in ("LONG", "SHORT"):
        return "NO_SIGNAL"

    size = "BIG" if abs(pct_change) > 0.02 else "SMALL"
    outcome = "WIN" if win else "LOSS"
    return f"{direction}_{outcome}_{size}"


def observation_index(direction: str, win: bool, pct_change: float) -> int:
    """Convert signal to observation index (faster, no string lookup)."""
    return OBS_INDEX.get(signal_to_observation(direction, win, pct_change), OBS_INDEX["NO_SIGNAL"])


# ====================================================================
# ALGORITHM 1: FORWARD (Likelihood)
# ====================================================================

def forward(params: HMMParams, observations: list[int]) -> tuple[np.ndarray, float]:
    """
    Forward algorithm: compute P(O | λ).

    Returns:
        alpha: [T x N] forward trellis
        likelihood: float = P(O | λ)
    """
    T = len(observations)
    N = len(params.pi)
    alpha = np.zeros((T, N))

    # Initialization: α₁(j) = πⱼ · bⱼ(o₁)
    obs0 = observations[0]
    for j in range(N):
        alpha[0, j] = params.pi[j] * params.B[j, obs0]

    # Recursion: αₜ(j) = Σᵢ αₜ₋₁(i) · aᵢⱼ · bⱼ(oₜ)
    for t in range(1, T):
        obs_t = observations[t]
        for j in range(N):
            alpha[t, j] = sum(
                alpha[t - 1, i] * params.A[i, j] * params.B[j, obs_t]
                for i in range(N)
            )

    # Termination: P(O|λ) = Σᵢ α_T(i)
    likelihood = alpha[T - 1].sum()
    return alpha, likelihood


# ====================================================================
# ALGORITHM 2: VITERBI (Decoding — Best Regime Sequence)
# ====================================================================

def viterbi(params: HMMParams, observations: list[int]) -> tuple[list[int], float]:
    """
    Viterbi algorithm: find most probable regime sequence.

    Returns:
        best_path: list of state indices [T]
        best_prob: float = max P(Q, O | λ)
    """
    T = len(observations)
    N = len(params.pi)
    v = np.zeros((T, N))
    backpointer = np.zeros((T, N), dtype=int)

    # Initialization: v₁(j) = πⱼ · bⱼ(o₁)
    obs0 = observations[0]
    for j in range(N):
        v[0, j] = params.pi[j] * params.B[j, obs0]
        backpointer[0, j] = 0

    # Recursion
    for t in range(1, T):
        obs_t = observations[t]
        for j in range(N):
            probs = np.array([
                v[t - 1, i] * params.A[i, j] * params.B[j, obs_t]
                for i in range(N)
            ])
            v[t, j] = probs.max()
            backpointer[t, j] = probs.argmax()

    # Termination
    best_prob = v[T - 1].max()
    best_last_state = v[T - 1].argmax()

    # Backtrace
    path = [best_last_state]
    for t in range(T - 1, 0, -1):
        path.append(backpointer[t, path[-1]])
    path.reverse()

    return path, best_prob


# ====================================================================
# ALGORITHM 3: BAUM-WELCH (Learning from unlabeled data)
# ====================================================================

def baum_welch(
    observations: list[int],
    n_regimes: int = 4,
    n_iterations: int = 50,
    epsilon: float = 1e-4,
    verbose: bool = False,
) -> HMMParams:
    """
    Baum-Welch (Forward-Backward) algorithm: learn HMM parameters.

    Returns:
        Trained HMMParams
    """
    observations = np.array(observations, dtype=int)
    T = len(observations)
    N = n_regimes
    M = N_OBS

    # Initialize with sensible priors
    params = default_hmm_params()

    for iteration in range(n_iterations):
        # ---- E-step: compute γ and ξ ----
        # Forward pass
        alpha = np.zeros((T, N))
        alpha[0] = params.pi * params.B[:, observations[0]]
        for t in range(1, T):
            for j in range(N):
                alpha[t, j] = sum(alpha[t-1, i] * params.A[i, j] * params.B[j, observations[t]]
                                  for i in range(N))

        # Backward pass
        beta = np.zeros((T, N))
        beta[T-1] = 1.0
        for t in range(T-2, -1, -1):
            for i in range(N):
                beta[t, i] = sum(params.A[i, j] * params.B[j, observations[t+1]] * beta[t+1, j]
                                 for j in range(N))

        # Likelihood
        P_O = alpha[T-1].sum()
        if P_O < 1e-300:
            P_O = 1e-300

        # γ_t(j) = P(q_t = j | O)
        gamma = np.zeros((T, N))
        for t in range(T):
            gamma[t] = (alpha[t] * beta[t]) / P_O

        # ξ_t(i,j) = P(q_t = i, q_{t+1} = j | O)
        xi = np.zeros((T-1, N, N))
        for t in range(T-1):
            for i in range(N):
                for j in range(N):
                    xi[t, i, j] = (
                        alpha[t, i] * params.A[i, j] *
                        params.B[j, observations[t+1]] * beta[t+1, j]
                    ) / P_O

        # ---- M-step: update parameters ----
        new_A = np.zeros_like(params.A)
        new_B = np.zeros_like(params.B)
        new_pi = gamma[0].copy()

        # Update A
        for i in range(N):
            denom = gamma[:-1, i].sum()
            if denom > 0:
                for j in range(N):
                    new_A[i, j] = xi[:, i, j].sum() / denom

        # Update B
        for j in range(N):
            denom = gamma[:, j].sum()
            if denom > 0:
                for k in range(M):
                    mask = (observations == k)
                    new_B[j, k] = gamma[mask, j].sum() / denom

        # Sanity: ensure rows sum to 1
        for i in range(N):
            if new_A[i].sum() < 1e-9:
                new_A[i] = params.A[i]
            else:
                new_A[i] /= new_A[i].sum()
            if new_B[i].sum() < 1e-9:
                new_B[i] = params.B[i]
            else:
                new_B[i] /= new_B[i].sum()

        # Check convergence
        delta_A = np.abs(new_A - params.A).max()
        delta_B = np.abs(new_B - params.B).max()

        params = HMMParams(pi=new_pi, A=new_A, B=new_B)

        if verbose and iteration % 10 == 0:
            print(f"  Iter {iteration}: δA={delta_A:.6f} δB={delta_B:.6f} P(O)={P_O:.4f}")

        if delta_A < epsilon and delta_B < epsilon:
            if verbose:
                print(f"  Converged at iteration {iteration}")
            break

    return params


# ====================================================================
# HIGH-LEVEL API: TRAIN ON PERSONA BACKTEST RESULTS
# ====================================================================

def train_from_persona_trades(
    ticker: str,
    persona_result,
    n_regimes: int = 4,
    n_iterations: int = 50,
    verbose: bool = True,
) -> HMMParams:
    """
    Train HMM from actual persona backtest trade outcomes.

    Args:
        ticker: "NQ", "ES", "GC"
        persona_result: output from persona_backtest_flow
        n_regimes: number of hidden regimes to discover
        n_iterations: Baum-Welch iterations

    Returns:
        Trained HMMParams
    """
    # Convert trades to observation sequence
    obs_seq = []
    for trade in persona_result.oos_trades:
        direction = trade.direction
        net = trade.net_points
        gross = trade.gross_points
        win = net > 0
        pct = abs(gross) / 100.0  # rough pct from points
        obs_seq.append(observation_index(direction, win, min(pct, 0.05)))

    if len(obs_seq) < 20:
        if verbose:
            print(f"  Not enough trades ({len(obs_seq)}) for HMM training — using defaults")
        return default_hmm_params()

    if verbose:
        print(f"  Training HMM on {len(obs_seq)} trades for {ticker}...")

    params = baum_welch(obs_seq, n_regimes=n_regimes, n_iterations=n_iterations, verbose=verbose)

    if verbose:
        print(f"  Learned transitions:\n{params.A}")
        print(f"  Regime distribution:")
        for i, r in enumerate(REGIMES):
            print(f"    {r}: π={params.pi[i]:.3f}, self-trans={params.A[i][i]:.3f}")

    return params


def predict_regime(
    params: HMMParams,
    recent_observations: list[int],
    n_forward: int = 1,
) -> dict:
    """
    Predict the current and next regime given recent observations.

    Returns:
        {
            "current_regime": str,
            "current_prob": float,
            "next_regime": str,
            "next_prob": float,
            "regime_probs": [float x N],
            "recommendation": str,
        }
    """
    if len(recent_observations) < 3:
        # Not enough data — use prior
        best_idx = params.pi.argmax()
        return {
            "current_regime": REGIMES[best_idx],
            "current_prob": float(params.pi[best_idx]),
            "next_regime": REGIMES[best_idx],
            "next_prob": float(params.pi[best_idx]),
            "regime_probs": params.pi.tolist(),
            "recommendation": "Insufficient data — using prior. Normal trading.",
        }

    # 1. Viterbi to find current regime
    path, _ = viterbi(params, recent_observations)
    current_idx = path[-1]
    current_regime = REGIMES[current_idx]

    # 2. Compute state probabilities via forward + smoothing
    alpha, likelihood = forward(params, recent_observations)
    if likelihood > 0:
        regime_probs = alpha[-1] / alpha[-1].sum()
    else:
        regime_probs = params.pi

    # 3. Predict next regime: max prob from transition row
    next_probs = params.A[current_idx]
    next_idx = next_probs.argmax()
    next_regime = REGIMES[next_idx]

    # 4. Recommendation
    recs = {
        "BULL": f"Bull regime — prioritize LONG signals, full position sizing",
        "BEAR": f"Bear regime — prioritize SHORT signals, reduce LONG exposure",
        "RANGE": f"Range regime — reduce conviction, tighten stops, expect reversals",
        "CHOP": f"Chop regime — SIT OUT. High noise, random outcomes expected",
    }

    return {
        "current_regime": current_regime,
        "current_prob": float(regime_probs[current_idx]),
        "next_regime": next_regime,
        "next_prob": float(next_probs.max()),
        "regime_probs": regime_probs.tolist(),
        "regime_labels": REGIMES,
        "recommendation": recs.get(current_regime, "Unknown regime"),
    }


def filter_signal_by_regime(
    signal: dict,
    params: HMMParams,
    recent_observations: list[int],
) -> dict:
    """
    Adjust a persona signal based on current HMM regime.

    Returns copy of signal with regime-adjusted conviction and position.
    """
    regime_info = predict_regime(params, recent_observations)
    regime = regime_info["current_regime"]
    signal = dict(signal)  # copy

    # Regime-specific adjustments
    adjustments = {
        "BULL": {"long_mult": 1.2, "short_mult": 0.5, "position_mult": 1.0},
        "BEAR": {"long_mult": 0.5, "short_mult": 1.2, "position_mult": 1.0},
        "RANGE": {"long_mult": 0.8, "short_mult": 0.8, "position_mult": 0.7},
        "CHOP": {"long_mult": 0.3, "short_mult": 0.3, "position_mult": 0.3},
    }

    adj = adjustments.get(regime, adjustments["RANGE"])
    direction = signal.get("direction", "LONG")
    mult = adj["long_mult"] if direction == "LONG" else adj["short_mult"]

    original_conv = float(signal.get("conviction", 1.0))
    signal["conviction"] = round(original_conv * mult, 2)
    signal["hmm_regime"] = regime
    signal["hmm_regime_prob"] = regime_info["current_prob"]
    signal["hmm_recommendation"] = regime_info["recommendation"]
    signal["position_pct"] = f"{max(1, int(float(signal.get('position_pct', '10%').rstrip('%')) * adj['position_mult']))}%"

    return signal


# ====================================================================
# PERSISTENCE
# ====================================================================

def save_hmm_params(params: HMMParams, ticker: str, path: str | None = None):
    """Save HMM parameters to JSON."""
    if path is None:
        path = os.path.expanduser(f"~/.astro-quant/hmm_{ticker}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "ticker": ticker,
        "pi": params.pi.tolist(),
        "A": params.A.tolist(),
        "B": params.B.tolist(),
        "regime_labels": REGIMES,
        "obs_labels": OBSERVATIONS,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_hmm_params(ticker: str, path: str | None = None) -> HMMParams | None:
    """Load HMM parameters from JSON."""
    if path is None:
        path = os.path.expanduser(f"~/.astro-quant/hmm_{ticker}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return HMMParams(
        pi=np.array(data["pi"]),
        A=np.array(data["A"]),
        B=np.array(data["B"]),
    )


# ====================================================================
# SELF-TEST
# ====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(" ASTRO-HMM — Self-Test")
    print("=" * 60)

    params = default_hmm_params()
    print(f"\n  Default params: {params}")

    # Simulate a sequence of persona trade outcomes
    np.random.seed(42)
    obs_seq = []
    descriptions = []
    state = 0  # start in BULL

    # Generate 50 days of observations following the HMM
    for day in range(50):
        # Transition
        state = np.random.choice(N_REGIMES, p=params.A[state])
        # Emit observation
        obs = np.random.choice(N_OBS, p=params.B[state])
        obs_seq.append(obs)
        descriptions.append(f"Day {day+1}: {REGIMES[state]} → {OBSERVATIONS[obs]}")

    print(f"\n  Simulated 50-trade sequence")
    for d in descriptions[:5]:
        print(f"    {d}")
    print(f"    ... ({len(obs_seq)} total)")

    # Test Forward
    alpha, likelihood = forward(params, obs_seq)
    print(f"\n  Forward: P(O|λ) = {likelihood:.8f}")

    # Test Viterbi
    path, prob = viterbi(params, obs_seq)
    regime_seq = [REGIMES[i] for i in path]
    print(f"  Viterbi: best path prob = {prob:.8f}")
    print(f"    First 10 regimes: {' → '.join(regime_seq[:10])}")

    # Test Baum-Welch (learn from observations)
    print(f"\n  Baum-Welch: learning HMM from observations...")
    learned = baum_welch(obs_seq, n_regimes=4, n_iterations=30, verbose=False)
    print(f"  Learned: {learned}")

    # Test regime prediction
    recent = obs_seq[-10:]  # last 10 observations
    regime_info = predict_regime(params, recent)
    print(f"\n  Current regime: {regime_info['current_regime']} (p={regime_info['current_prob']:.3f})")
    print(f"  Next regime: {regime_info['next_regime']} (p={regime_info['next_prob']:.3f})")
    print(f"  Recommendation: {regime_info['recommendation']}")

    # Test signal filtering
    mock_signal = {
        "direction": "LONG",
        "conviction": 1.0,
        "sl_pct": "5%",
        "tp_pct": "15%",
        "position_pct": "10%",
        "hold_days": 5,
    }
    filtered = filter_signal_by_regime(mock_signal, params, recent)
    print(f"\n  Signal filtering:")
    print(f"    Before: {mock_signal['direction']} conv={mock_signal['conviction']} pos={mock_signal['position_pct']}")
    print(f"    After:  {filtered['direction']} conv={filtered['conviction']} pos={filtered['position_pct']}")
    print(f"    Regime: {filtered.get('hmm_regime', '?')} | {filtered.get('hmm_recommendation', '?')}")

    # Persistence test
    save_hmm_params(params, "NQ")
    loaded = load_hmm_params("NQ")
    print(f"\n  Save/Load: {'✓ OK' if loaded else '✗ FAILED'}")

    print("\n" + "=" * 60)
    print(" SELF-TEST COMPLETE")
    print("=" * 60)
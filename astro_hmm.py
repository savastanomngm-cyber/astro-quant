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

REGIMES = ["BULL", "BEAR", "RANGE", "CHOP"]
N_REGIMES = len(REGIMES)
REGIME_INDEX = {r: i for i, r in enumerate(REGIMES)}

OBSERVATIONS = [
    "LONG_WIN_BIG",
    "LONG_WIN_SMALL",
    "LONG_LOSS_SMALL",
    "LONG_LOSS_BIG",
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
    pi: np.ndarray
    A: np.ndarray
    B: np.ndarray

    def __repr__(self):
        return (
            f"HMMParams(N={self.pi.shape[0]}, M={self.B.shape[1]}, "
            f"pi_sum={self.pi.sum():.4f}, A_rowsums_ok={np.allclose(self.A.sum(axis=1), 1.0)}, "
            f"B_rowsums_ok={np.allclose(self.B.sum(axis=1), 1.0)})"
        )


def default_hmm_params() -> HMMParams:
    pi = np.array([0.35, 0.20, 0.30, 0.15])
    A = np.array([
        [0.70, 0.05, 0.20, 0.05],
        [0.05, 0.70, 0.20, 0.05],
        [0.25, 0.25, 0.40, 0.10],
        [0.20, 0.20, 0.30, 0.30],
    ])
    B = np.array([
        [0.15, 0.30, 0.10, 0.02,  0.01, 0.01, 0.15, 0.10, 0.16],
        [0.02, 0.10, 0.30, 0.15,  0.10, 0.15, 0.01, 0.01, 0.16],
        [0.05, 0.15, 0.15, 0.05,  0.05, 0.15, 0.15, 0.05, 0.20],
        [0.03, 0.08, 0.18, 0.18,  0.03, 0.08, 0.18, 0.18, 0.06],
    ])
    return HMMParams(pi=pi, A=A, B=B)


def signal_to_observation(direction: str, win: bool, pct_change: float) -> str:
    if direction not in ("LONG", "SHORT"): return "NO_SIGNAL"
    size = "BIG" if abs(pct_change) > 0.02 else "SMALL"
    outcome = "WIN" if win else "LOSS"
    return f"{direction}_{outcome}_{size}"


def observation_index(direction: str, win: bool, pct_change: float) -> int:
    return OBS_INDEX.get(signal_to_observation(direction, win, pct_change), OBS_INDEX["NO_SIGNAL"])


def forward(params: HMMParams, observations: list[int]) -> tuple[np.ndarray, float]:
    T = len(observations)
    N = len(params.pi)
    alpha = np.zeros((T, N))
    obs0 = observations[0]
    for j in range(N):
        alpha[0, j] = params.pi[j] * params.B[j, obs0]
    for t in range(1, T):
        obs_t = observations[t]
        for j in range(N):
            alpha[t, j] = sum(alpha[t-1, i] * params.A[i, j] * params.B[j, obs_t] for i in range(N))
    likelihood = alpha[T-1].sum()
    return alpha, likelihood


def viterbi(params: HMMParams, observations: list[int]) -> tuple[list[int], float]:
    T = len(observations)
    N = len(params.pi)
    v = np.zeros((T, N))
    backpointer = np.zeros((T, N), dtype=int)
    obs0 = observations[0]
    for j in range(N):
        v[0, j] = params.pi[j] * params.B[j, obs0]
        backpointer[0, j] = 0
    for t in range(1, T):
        obs_t = observations[t]
        for j in range(N):
            probs = np.array([v[t-1, i] * params.A[i, j] * params.B[j, obs_t] for i in range(N)])
            v[t, j] = probs.max()
            backpointer[t, j] = probs.argmax()
    best_prob = v[T-1].max()
    best_last_state = v[T-1].argmax()
    path = [best_last_state]
    for t in range(T-1, 0, -1):
        path.append(backpointer[t, path[-1]])
    path.reverse()
    return path, best_prob


def baum_welch(observations, n_regimes=4, n_iterations=50, epsilon=1e-4, verbose=False) -> HMMParams:
    observations = np.array(observations, dtype=int)
    T = len(observations)
    N = n_regimes
    M = N_OBS
    params = default_hmm_params()
    for iteration in range(n_iterations):
        alpha = np.zeros((T, N))
        alpha[0] = params.pi * params.B[:, observations[0]]
        for t in range(1, T):
            for j in range(N):
                alpha[t, j] = sum(alpha[t-1, i] * params.A[i, j] * params.B[j, observations[t]] for i in range(N))
        beta = np.zeros((T, N))
        beta[T-1] = 1.0
        for t in range(T-2, -1, -1):
            for i in range(N):
                beta[t, i] = sum(params.A[i, j] * params.B[j, observations[t+1]] * beta[t+1, j] for j in range(N))
        P_O = max(alpha[T-1].sum(), 1e-300)
        gamma = np.zeros((T, N))
        for t in range(T):
            gamma[t] = (alpha[t] * beta[t]) / P_O
        xi = np.zeros((T-1, N, N))
        for t in range(T-1):
            for i in range(N):
                for j in range(N):
                    xi[t, i, j] = (alpha[t, i] * params.A[i, j] * params.B[j, observations[t+1]] * beta[t+1, j]) / P_O
        new_A = np.zeros_like(params.A)
        new_B = np.zeros_like(params.B)
        new_pi = gamma[0].copy()
        for i in range(N):
            denom = gamma[:-1, i].sum()
            if denom > 0:
                for j in range(N):
                    new_A[i, j] = xi[:, i, j].sum() / denom
        for j in range(N):
            denom = gamma[:, j].sum()
            if denom > 0:
                for k in range(M):
                    mask = (observations == k)
                    new_B[j, k] = gamma[mask, j].sum() / denom
        for i in range(N):
            new_A[i] = new_A[i] / new_A[i].sum() if new_A[i].sum() > 1e-9 else params.A[i]
            new_B[i] = new_B[i] / new_B[i].sum() if new_B[i].sum() > 1e-9 else params.B[i]
        delta_A = np.abs(new_A - params.A).max()
        delta_B = np.abs(new_B - params.B).max()
        params = HMMParams(pi=new_pi, A=new_A, B=new_B)
        if delta_A < epsilon and delta_B < epsilon:
            break
    return params


def train_from_persona_trades(ticker, persona_result, n_regimes=4, n_iterations=50, verbose=True) -> HMMParams:
    obs_seq = []
    for trade in persona_result.oos_trades:
        direction = trade.direction
        net = trade.net_points
        gross = trade.gross_points
        win = net > 0
        pct = abs(gross) / 100.0
        obs_seq.append(observation_index(direction, win, min(pct, 0.05)))
    if len(obs_seq) < 20:
        if verbose:
            print(f"  Not enough trades ({len(obs_seq)}) for HMM training — using defaults")
        return default_hmm_params()
    if verbose:
        print(f"  Training HMM on {len(obs_seq)} trades for {ticker}...")
    params = baum_welch(obs_seq, n_regimes=n_regimes, n_iterations=n_iterations, verbose=verbose)
    if verbose:
        for i, r in enumerate(REGIMES):
            print(f"    {r}: π={params.pi[i]:.3f}, self-trans={params.A[i][i]:.3f}")
    return params


def predict_regime(params: HMMParams, recent_observations: list[int], n_forward: int = 1) -> dict:
    if len(recent_observations) < 3:
        best_idx = params.pi.argmax()
        return {
            "current_regime": REGIMES[best_idx],
            "current_prob": float(params.pi[best_idx]),
            "next_regime": REGIMES[best_idx],
            "next_prob": float(params.pi[best_idx]),
            "regime_probs": params.pi.tolist(),
            "recommendation": "Insufficient data — using prior. Normal trading.",
        }

    # Compute state probabilities via forward (filtering distribution).
    # We use THIS as the single source of truth for both the "current
    # regime" label and its probability, so the label and the % always
    # agree (the previous code mixed Viterbi's hard path with forward's
    # probabilities, which could label BULL while showing RANGE=100%).
    alpha, likelihood = forward(params, recent_observations)
    if likelihood > 0:
        regime_probs = alpha[-1] / alpha[-1].sum()
    else:
        regime_probs = params.pi

    current_idx = int(np.argmax(regime_probs))
    current_regime = REGIMES[current_idx]

    # Predict next regime: max prob from transition row
    next_probs = params.A[current_idx]
    next_idx = next_probs.argmax()
    next_regime = REGIMES[next_idx]
    recs = {
        "BULL": "Bull regime — prioritize LONG signals, full position sizing",
        "BEAR": "Bear regime — prioritize SHORT signals, reduce LONG exposure",
        "RANGE": "Range regime — reduce conviction, tighten stops, expect reversals",
        "CHOP": "Chop regime — SIT OUT. High noise, random outcomes expected",
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


def filter_signal_by_regime(signal, params, recent_observations) -> dict:
    regime_info = predict_regime(params, recent_observations)
    regime = regime_info["current_regime"]
    signal = dict(signal)
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
    return signal


def save_hmm_params(params, ticker, path=None):
    if path is None:
        path = os.path.expanduser(f"~/.astro-quant/hmm_{ticker}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"ticker": ticker, "pi": params.pi.tolist(), "A": params.A.tolist(),
            "B": params.B.tolist(), "regime_labels": REGIMES, "obs_labels": OBSERVATIONS}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_hmm_params(ticker, path=None) -> HMMParams | None:
    if path is None:
        path = os.path.expanduser(f"~/.astro-quant/hmm_{ticker}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return HMMParams(pi=np.array(data["pi"]), A=np.array(data["A"]), B=np.array(data["B"]))


if __name__ == "__main__":
    print("=" * 60)
    print(" ASTRO-HMM — Self-Test")
    print("=" * 60)
    params = default_hmm_params()
    np.random.seed(42)
    obs_seq = []
    state = 0
    for day in range(50):
        state = np.random.choice(N_REGIMES, p=params.A[state])
        obs = np.random.choice(N_OBS, p=params.B[state])
        obs_seq.append(obs)
    alpha, likelihood = forward(params, obs_seq)
    path, prob = viterbi(params, obs_seq)
    regime_seq = [REGIMES[i] for i in path]
    print(f"  Forward P(O|λ) = {likelihood:.8f}")
    print(f"  Viterbi: best path prob = {prob:.8f}")
    print(f"  First 10: {' → '.join(regime_seq[:10])}")
    recent = obs_seq[-10:]
    regime_info = predict_regime(params, recent)
    print(f"  Current: {regime_info['current_regime']} (p={regime_info['current_prob']:.3f})")
    save_hmm_params(params, "NQ")
    loaded = load_hmm_params("NQ")
    print(f"  Save/Load: {'✓' if loaded else '✗'}")
"""
ASTRO MIND / MEMORY — Filesystem-Backed Run Archive
=====================================================
QuantMind mind/memory/ MVP: persist every backtest, campaign, and
rectification result to disk as timestamped JSON artifacts.

Features:
  - archive_run(result) — save a BacktestResult to <memory_dir>/runs/
  - list_runs(ticker=None, source=None) — filterable listing
  - load_run(run_id) — retrieve a past run
  - compare_runs(run_ids) — side-by-side comparison of multiple runs
  - recent_summary(n) — latest N runs summary card

Design (from QuantMind PR6):
  - Filesystem only (no embedding store yet — that's PR7)
  - Each run is a self-contained JSON file
  - Metadata index in <memory_dir>/index.json for fast listing
  - Trajectory archive at <memory_dir>/runs/YYYY-MM-DD/<run_id>.json
"""

from __future__ import annotations
import json
import os
import uuid
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional, Literal

from astro_knowledge import BacktestResult, BatchBacktestResult, RegimeCard


# ====================================================================
# MEMORY BACKEND (Protocol-compatible — no base class needed)
# ====================================================================

DEFAULT_MEMORY_DIR = os.path.expanduser("~/.astro-quant/memory")


@dataclass
class RunIndex:
    """Lightweight metadata index for fast listing."""
    run_id: str
    ticker: str
    source_kind: str
    source_symbol: str
    run_type: Literal["backtest", "campaign", "rectify", "batch"]
    as_of: str  # ISO timestamp
    oos_pf: float = 0.0
    oos_wr: float = 0.0
    oos_net: float = 0.0
    patterns: int = 0
    file_path: str = ""


class Memory:
    """
    Filesystem-backed memory for Astro-Quant runs.

    Usage:
        mem = Memory("~/.astro-quant/memory")
        run_id = mem.archive_run(backtest_result)
        previous = mem.load_run(run_id)
        summary = mem.list_runs(ticker="NQ")
    """

    def __init__(self, memory_dir: str = DEFAULT_MEMORY_DIR):
        self.memory_dir = os.path.expanduser(memory_dir)
        self.runs_dir = os.path.join(self.memory_dir, "runs")
        self.index_path = os.path.join(self.memory_dir, "index.json")
        os.makedirs(self.runs_dir, exist_ok=True)

        # Load or init index
        self._index: dict[str, RunIndex] = {}
        self._load_index()

    # ----- Persistence -----

    def _load_index(self) -> None:
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r") as f:
                    raw = json.load(f)
                self._index = {
                    rid: RunIndex(**data) for rid, data in raw.items()
                }
            except Exception:
                self._index = {}

    def _save_index(self) -> None:
        raw = {rid: r.__dict__ for rid, r in self._index.items()}
        with open(self.index_path, "w") as f:
            json.dump(raw, f, indent=2, default=str)

    # ----- Archive -----

    def archive_run(
        self,
        result: BacktestResult | BatchBacktestResult | RegimeCard,
        run_type: str | None = None,
    ) -> str:
        """Save a result to disk and update the index. Returns run_id."""
        run_id = str(uuid.uuid4())[:8]
        today = date.today().isoformat()

        # Determine run type
        if run_type is None:
            if isinstance(result, BatchBacktestResult):
                run_type = "batch"
            elif isinstance(result, RegimeCard):
                run_type = "campaign"
            else:
                run_type = "backtest"

        # Create date folder
        day_dir = os.path.join(self.runs_dir, today)
        os.makedirs(day_dir, exist_ok=True)

        filepath = os.path.join(day_dir, f"{run_id}.json")

        # Serialize
        # Use .model_dump() since these are Pydantic frozen models
        data = result.model_dump()

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

        # Update index
        if isinstance(result, BacktestResult):
            idx = RunIndex(
                run_id=run_id,
                ticker=result.ticker,
                source_kind=result.source.kind.value,
                source_symbol=result.source.symbol,
                run_type=run_type,
                as_of=result.as_of.isoformat(),
                oos_pf=result.out_of_sample.profit_factor,
                oos_wr=result.out_of_sample.win_rate,
                oos_net=result.out_of_sample.total_dollars,
                patterns=result.patterns_valid,
                file_path=filepath,
            )
        elif isinstance(result, BatchBacktestResult):
            # Use first result for metadata
            first = result.results[0] if result.results else None
            idx = RunIndex(
                run_id=run_id,
                ticker=",".join(r.ticker for r in result.results),
                source_kind="batch",
                source_symbol="multi",
                run_type=run_type,
                as_of=result.as_of.isoformat(),
                oos_pf=sum(
                    r.out_of_sample.profit_factor for r in result.results
                ) / max(1, len(result.results)),
                oos_wr=result.profitable_oos_count / max(1, len(result.results)),
                oos_net=sum(
                    r.out_of_sample.total_dollars for r in result.results
                ),
                patterns=result.total_patterns,
                file_path=filepath,
            )
        else:
            # RegimeCard
            idx = RunIndex(
                run_id=run_id,
                ticker=result.ticker,
                source_kind="regime",
                source_symbol=result.ticker,
                run_type=run_type,
                as_of=result.as_of.isoformat(),
                file_path=filepath,
            )
        self._index[run_id] = idx
        self._save_index()

        return run_id

    # ----- Retrieval -----

    def load_run(self, run_id: str) -> dict | None:
        """Load a previously archived run as raw dict."""
        idx = self._index.get(run_id)
        if not idx:
            return None
        if not os.path.exists(idx.file_path):
            return None
        with open(idx.file_path, "r") as f:
            return json.load(f)

    def list_runs(
        self,
        ticker: str | None = None,
        run_type: str | None = None,
        source_kind: str | None = None,
        limit: int = 20,
    ) -> list[RunIndex]:
        """Filter and list archived runs."""
        results = list(self._index.values())
        if ticker:
            results = [r for r in results if ticker in r.ticker]
        if run_type:
            results = [r for r in results if r.run_type == run_type]
        if source_kind:
            results = [r for r in results if r.source_kind == source_kind]

        # Sort by as_of descending (newest first)
        results.sort(key=lambda r: r.as_of, reverse=True)
        return results[:limit]

    # ----- Comparison -----

    def compare_runs(self, run_ids: list[str]) -> list[dict]:
        """
        Side-by-side comparison of multiple runs.
        Returns a list of dicts with key metrics aligned.
        """
        results = []
        for rid in run_ids:
            idx = self._index.get(rid)
            if not idx:
                continue
            data = self.load_run(rid)
            if not data:
                continue
            results.append({
                "run_id": rid,
                "ticker": idx.ticker,
                "source": idx.source_kind,
                "date": idx.as_of[:10],
                "oos_pf": idx.oos_pf,
                "oos_wr": idx.oos_wr,
                "oos_net": idx.oos_net,
                "patterns": idx.patterns,
                "full": data,
            })
        return results

    def recent_summary(self, n: int = 10) -> list[dict]:
        """Quick summary of the latest N runs."""
        recent = self.list_runs(limit=n)
        return [
            {
                "run_id": r.run_id,
                "date": r.as_of[:10],
                "ticker": r.ticker,
                "type": r.run_type,
                "source": r.source_kind,
                "oos_pf": r.oos_pf,
                "oos_net": r.oos_net,
            }
            for r in recent
        ]

    # ----- Stats -----

    def stats(self) -> dict:
        """Aggregated stats across all archived runs."""
        runs = list(self._index.values())
        backtests = [r for r in runs if r.run_type == "backtest"]
        profitable = [r for r in backtests if r.oos_pf > 1.0]
        return {
            "total_runs": len(runs),
            "backtest_runs": len(backtests),
            "profitable_oos_count": len(profitable),
            "profitable_oos_pct": (
                len(profitable) / max(1, len(backtests)) * 100
            ),
            "best_pf": max((r.oos_pf for r in backtests), default=0),
            "total_net_dollars": sum(r.oos_net for r in backtests),
            "per_ticker": {
                ticker: len([r for r in backtests if r.ticker == ticker])
                for ticker in sorted({r.ticker for r in backtests})
            },
        }

    def reset(self) -> None:
        """Clear all memory (destructive)."""
        self._index = {}
        self._save_index()
        import shutil
        if os.path.exists(self.runs_dir):
            shutil.rmtree(self.runs_dir)
        os.makedirs(self.runs_dir, exist_ok=True)


# ====================================================================
# SELF-TEST
# ====================================================================

if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print(" ASTRO MIND / MEMORY — SELF-TEST")
    print("=" * 60)

    # Create a test memory in a temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = Memory(os.path.join(tmpdir, "memory"))

        # Create a mock backtest result
        from astro_knowledge import (
            BacktestResult, TradeStats, SourceRef, ChartProvenance,
            DataSourceKind,
        )

        result = BacktestResult(
            as_of=datetime.now(),
            ticker="NQ",
            source=SourceRef(kind=DataSourceKind.YAHOO, symbol="NQ=F"),
            chart_provenance=ChartProvenance(),
            train_ratio=0.6,
            sl_points=200,
            tp_points=300,
            hold_days=5,
            patterns_found=150,
            patterns_valid=45,
            validation=TradeStats(
                n_trades=139,
                win_rate=0.496,
                profit_factor=1.38,
                total_dollars=101_515,
            ),
            out_of_sample=TradeStats(
                n_trades=93,
                win_rate=0.505,
                profit_factor=1.18,
                total_dollars=54_805,
            ),
        )

        # Archive it
        rid = mem.archive_run(result)
        print(f"Archived: {rid}")

        # Archive another
        result2 = result.model_copy(update={
            "as_of": datetime.now(),
            "ticker": "GC",
            "out_of_sample": TradeStats(
                n_trades=75,
                win_rate=0.44,
                profit_factor=2.07,
                total_dollars=123_930,
            ),
        })
        rid2 = mem.archive_run(result2)
        print(f"Archived: {rid2}")

        # List
        print("\nRecent runs:")
        for s in mem.recent_summary():
            print(f"  {s['run_id']}: {s['ticker']} PF={s['oos_pf']:.2f} Net=${s['oos_net']:,.0f}")

        # Stats
        print("\nMemory stats:")
        print(f"  {mem.stats()}")

        # Load
        loaded = mem.load_run(rid)
        print(f"\nLoaded run {rid}: ticker={loaded['ticker']}, OOS PF={loaded['out_of_sample']['profit_factor']}")

    print("\n" + "=" * 60)
    print(" SELF-TEST COMPLETE")
    print("=" * 60)

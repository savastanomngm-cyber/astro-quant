#!/usr/bin/env python3
"""
RUNBOOK: Daily Backtest
========================
QuantMind-style: 5 lines of Python, not a CLI command.

Usage:
    python3 runbooks/daily_backtest.py

This runbook:
  1. Loads the rectified chart for all tickers
  2. Runs backtest_flow on Yahoo daily data
  3. Archives results to memory (~/.astro-quant/memory)
  4. Prints a summary table
"""

import asyncio
import sys
import os

# Add parent to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from astro_configs import (
    BacktestCfg, YahooSource, INSTRUMENTS,
)
from astro_flows import backtest_flow, batch_run
from astro_mind import Memory


async def main():
    memory = Memory()

    # Build inputs for all tickers with Yahoo daily
    inputs = []
    for ticker in ["GC", "NQ", "ES"]:
        symbol = f"{ticker}=F"
        cfg = BacktestCfg(
            ticker=ticker,
            source=YahooSource(symbol=symbol),
            train_ratio=0.6,
            date_start="2010-01-01",
        )
        inputs.append({"cfg": cfg})

    print(f"Running backtests for {len(inputs)} tickers...")
    batch = await batch_run(backtest_flow, inputs, max_concurrency=2)

    print(f"\nResults: {batch.succeeded}/{batch.total} succeeded")
    if batch.errors:
        for err in batch.errors:
            print(f"  ERROR: {err}")

    # Archive + print summary
    for result in batch.results:
        if result is None:
            continue
        rid = memory.archive_run(result)
        print(
            f"  {result.ticker:4s} | "
            f"OOS PF: {result.out_of_sample.profit_factor:.2f} | "
            f"Net: ${result.out_of_sample.total_dollars:>10,.0f} | "
            f"WR: {result.out_of_sample.win_rate:.1%}  "
            f"[{rid}]"
        )

    print(f"\nArchived to: {memory.memory_dir}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

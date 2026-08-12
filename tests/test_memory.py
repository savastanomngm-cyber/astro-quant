"""
Tests for astro_mind/memory.py — filesystem-backed run archive.
"""

import os
import tempfile
import unittest
from datetime import datetime

from astro_knowledge import (
    BacktestResult, TradeStats, SourceRef, ChartProvenance, DataSourceKind,
)
from astro_mind import Memory


class TestMemory(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mem = Memory(os.path.join(self.tmpdir, "memory"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_result(self, ticker="NQ", oos_pf=1.18, oos_net=54805) -> BacktestResult:
        return BacktestResult(
            as_of=datetime.now(),
            ticker=ticker,
            source=SourceRef(kind=DataSourceKind.YAHOO, symbol=f"{ticker}=F"),
            chart_provenance=ChartProvenance(),
            train_ratio=0.6,
            sl_points=200, tp_points=300, hold_days=5,
            patterns_found=150, patterns_valid=45,
            validation=TradeStats(n_trades=139),
            out_of_sample=TradeStats(
                n_trades=93, win_rate=0.505,
                profit_factor=oos_pf, total_dollars=oos_net,
            ),
        )

    def test_archive_and_load(self):
        result = self._make_result()
        rid = self.mem.archive_run(result)

        loaded = self.mem.load_run(rid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["ticker"], "NQ")
        self.assertEqual(loaded["out_of_sample"]["profit_factor"], 1.18)

    def test_list_runs(self):
        r1 = self.mem.archive_run(self._make_result("NQ", 1.18, 54805))
        r2 = self.mem.archive_run(self._make_result("ES", 1.10, 18400))
        r3 = self.mem.archive_run(self._make_result("GC", 2.07, 123930))

        all_runs = self.mem.list_runs()
        self.assertEqual(len(all_runs), 3)

        nq_only = self.mem.list_runs(ticker="NQ")
        self.assertEqual(len(nq_only), 1)

    def test_compare_runs(self):
        r1 = self.mem.archive_run(self._make_result("NQ", 1.18))
        r2 = self.mem.archive_run(self._make_result("GC", 2.07))

        comp = self.mem.compare_runs([r1, r2])
        self.assertEqual(len(comp), 2)
        profit_factors = {c["ticker"]: c["oos_pf"] for c in comp}
        self.assertEqual(profit_factors["NQ"], 1.18)
        self.assertEqual(profit_factors["GC"], 2.07)

    def test_recent_summary(self):
        for i in range(5):
            self.mem.archive_run(self._make_result(ticker=f"T{i}"))

        summary = self.mem.recent_summary(n=3)
        self.assertEqual(len(summary), 3)

    def test_stats(self):
        self.mem.archive_run(self._make_result("NQ", 1.18))
        self.mem.archive_run(self._make_result("ES", 0.90))  # unprofitable
        self.mem.archive_run(self._make_result("GC", 2.07))

        stats = self.mem.stats()
        self.assertEqual(stats["backtest_runs"], 3)
        self.assertEqual(stats["profitable_oos_count"], 2)

    def test_reset(self):
        self.mem.archive_run(self._make_result())
        self.assertEqual(len(self.mem.list_runs()), 1)

        self.mem.reset()
        self.assertEqual(len(self.mem.list_runs()), 0)


if __name__ == "__main__":
    unittest.main()

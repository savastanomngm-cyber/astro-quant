"""
Tests for astro_configs — centralized typed configuration.
"""

import unittest

from astro_configs import (
    AstroQuantConfig, BacktestCfg, CampaignCfg, RectifyCfg, FilterCfg,
    YahooSource, CsvSource, RepoDailySource, InstrumentDef,
    INSTRUMENTS, TICKER_DATA_SOURCES,
)


class TestYahooSource(unittest.TestCase):

    def test_defaults(self):
        src = YahooSource(symbol="NQ=F")
        self.assertEqual(src.symbol, "NQ=F")
        self.assertEqual(src.start_date, "2010-01-01")


class TestBacktestCfg(unittest.TestCase):

    def test_defaults(self):
        cfg = BacktestCfg(
            ticker="GC",
            source=YahooSource(symbol="GC=F"),
        )
        self.assertEqual(cfg.train_ratio, 0.6)
        self.assertGreater(len(cfg.sl_grid), 0)
        self.assertIn(3, cfg.horizons)


class TestCampaignCfg(unittest.TestCase):

    def test_filter_weights(self):
        cfg = CampaignCfg(
            ticker="NQ",
            date_start="2026-08-10",
            date_end="2026-08-28",
        )
        self.assertIn("moon_app", cfg.filter_weights)
        self.assertEqual(sum(cfg.filter_weights.values()), 1.0)


class TestInstrumentDef(unittest.TestCase):

    def test_all_instruments(self):
        for ticker in ["NQ", "ES", "GC"]:
            inst = INSTRUMENTS[ticker]
            self.assertEqual(inst.ticker, ticker)
            self.assertGreater(inst.point_value, 0)
            self.assertGreater(inst.default_sl, 0)

    def test_data_sources_per_ticker(self):
        for ticker in ["NQ", "ES", "GC"]:
            sources = TICKER_DATA_SOURCES[ticker]
            self.assertGreaterEqual(len(sources), 3)
            # Each entry has a label + source
            for label, src in sources:
                self.assertIsInstance(label, str)
                self.assertTrue(len(label) > 0)


if __name__ == "__main__":
    unittest.main()

"""
Tests for astro_knowledge — typed knowledge shapes.
"""

import unittest
from datetime import datetime
from unittest import mock

# Mock astro_core_v2 before importing astro_knowledge (for sign_name property)
import sys
sys.modules["astro_core_v2"] = mock.MagicMock()

# Patch SIGN_NAMES
mock_astro = sys.modules["astro_core_v2"]
mock_astro.SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

from astro_knowledge import (
    PlanetPosition, AnglePosition, ChartSnapshot, ChartProvenance,
    PatternCard, RegimeCard, TradeStats, TradeRecord, BacktestResult,
    SourceRef, DataSourceKind,
)


class TestPlanetPosition(unittest.TestCase):

    def test_valid_planet(self):
        p = PlanetPosition(
            name="Moon", longitude=45.5, latitude=2.3, speed=13.2,
            sign_index=1, degree_in_sign=15.5, is_retrograde=False,
        )
        self.assertEqual(p.name, "Moon")
        self.assertEqual(p.sign_index, 1)
        self.assertFalse(p.is_retrograde)

    def test_rejects_out_of_range_longitude(self):
        with self.assertRaises(Exception):
            PlanetPosition(name="Sun", longitude=400.0, sign_index=0,
                          degree_in_sign=0.0)

    def test_sign_name(self):
        p = PlanetPosition(name="Mars", longitude=28.0, sign_index=0,
                          degree_in_sign=28.0)
        self.assertEqual(p.sign_name, "Aries")


class TestChartSnapshot(unittest.TestCase):

    def test_minimal_snapshot(self):
        snap = ChartSnapshot(
            ticker="NQ",
            as_of=datetime(1996, 10, 26, 20, 45),
            latitude=41.8781, longitude=-87.6298, timezone=-5,
            ascendant=AnglePosition(longitude=87.4, sign_index=2, degree_in_sign=27.4),
            midheaven=AnglePosition(longitude=332.35, sign_index=10, degree_in_sign=2.35),
            sect="Nocturnal",
            planets={
                "Sun": PlanetPosition(name="Sun", longitude=214.5, sign_index=7,
                                      degree_in_sign=4.5),
                "Moon": PlanetPosition(name="Moon", longitude=150.2, sign_index=4,
                                       degree_in_sign=0.2),
            },
            hllaj="ASC", kadukhadah="Mercury",
        )
        self.assertEqual(snap.ticker, "NQ")
        self.assertEqual(snap.sect, "Nocturnal")
        self.assertEqual(snap.hllaj, "ASC")

    def test_embedding_text(self):
        snap = ChartSnapshot(
            ticker="ES",
            as_of=datetime(1997, 9, 9, 12, 0),
            latitude=41.8781, longitude=-87.6298, timezone=-5,
            ascendant=AnglePosition(longitude=326.56, sign_index=10, degree_in_sign=26.56),
            midheaven=AnglePosition(longitude=245.0, sign_index=8, degree_in_sign=5.0),
            sect="Diurnal",
            planets={
                "Sun": PlanetPosition(name="Sun", longitude=167.0, sign_index=5,
                                      degree_in_sign=17.0),
            },
            hllaj="Sun", kadukhadah="Venus",
        )
        text = snap.embedding_text()
        self.assertIn("ES", text)
        self.assertIn("Diurnal", text)


class TestPatternCard(unittest.TestCase):

    def test_valid_card(self):
        card = PatternCard(
            as_of=datetime.now(),
            state_key="Fid_Sun_Moon_Dist_Mars_H1_LP3",
            direction="LONG",
            horizon=5,
            n_samples=45,
            win_rate=0.62,
            avg_move=0.012,
            std_move=0.025,
            profit_factor=1.8,
            p_value=0.003,
            score=2.5,
            source=SourceRef(kind=DataSourceKind.YAHOO, symbol="NQ=F"),
        )
        self.assertEqual(card.direction, "LONG")
        self.assertEqual(card.horizon, 5)
        self.assertGreater(card.profit_factor, 1.0)

    def test_embedding_text(self):
        card = PatternCard(
            as_of=datetime.now(),
            state_key="TEST_KEY",
            direction="SHORT",
            horizon=3,
            n_samples=20,
            win_rate=0.55,
            avg_move=-0.008,
            std_move=0.03,
            profit_factor=1.2,
            p_value=0.01,
            score=1.0,
            source=SourceRef(kind=DataSourceKind.YAHOO, symbol="GC=F"),
        )
        text = card.embedding_text()
        self.assertIn("SHORT", text)
        self.assertIn("horizon=3d", text)


class TestRegimeCard(unittest.TestCase):

    def test_bullish_regime(self):
        card = RegimeCard(
            as_of=datetime.now(),
            ticker="NQ",
            moon_application_score=0.3,
            regime="BULLISH",
            combined_score=0.25,
            base_direction="LONG",
            modulated_direction="LONG",
        )
        self.assertEqual(card.regime, "BULLISH")
        self.assertEqual(card.modulated_direction, "LONG")

    def test_bearish_flattens_long(self):
        card = RegimeCard(
            as_of=datetime.now(),
            ticker="ES",
            regime="BEARISH",
            combined_score=-0.3,
            base_direction="LONG",
            modulated_direction="FLAT",
        )
        self.assertEqual(card.modulated_direction, "FLAT")


class TestBacktestResult(unittest.TestCase):

    def test_profitable(self):
        result = BacktestResult(
            as_of=datetime.now(),
            ticker="GC",
            source=SourceRef(kind=DataSourceKind.YAHOO, symbol="GC=F"),
            chart_provenance=ChartProvenance(),
            train_ratio=0.6,
            sl_points=50, tp_points=150, hold_days=7,
            patterns_found=200, patterns_valid=80,
            validation=TradeStats(),
            out_of_sample=TradeStats(
                n_trades=75, win_rate=0.44, profit_factor=2.07,
                total_dollars=123_930,
            ),
        )
        self.assertTrue(result.is_profitable_oos)

    def test_unprofitable(self):
        result = BacktestResult(
            as_of=datetime.now(),
            ticker="NQ",
            source=SourceRef(kind=DataSourceKind.CSV, symbol="60m"),
            chart_provenance=ChartProvenance(),
            train_ratio=0.6,
            sl_points=50, tp_points=300, hold_days=10,
            patterns_found=100, patterns_valid=30,
            validation=TradeStats(),
            out_of_sample=TradeStats(profit_factor=0.66),
        )
        self.assertFalse(result.is_profitable_oos)


if __name__ == "__main__":
    unittest.main()

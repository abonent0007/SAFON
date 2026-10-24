# -*- coding: utf-8 -*-
"""Тесты кросс-категорийного анализа и walk-forward бэктеста."""
import os
import tempfile
import unittest

from core.cross_category import CrossCategoryAnalyzer
from core.database import SafonDatabase
from core.predictor import PredictionEngine


class TestCrossCategory(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.mkdtemp(prefix="safon_cc_")
        self.db = SafonDatabase(db_path=os.path.join(tmpdir, "test.db"))
        assert self.db.conn is not None

    def tearDown(self):
        self.db.close()

    def test_finds_known_chain(self):
        for year in (1900, 1925, 1950, 1975, 2000):
            self.db.add_event(title=f"Война {year}", year=year, category="война",
                              location="Европа")
        for year in (1902, 1927, 1952, 1977, 2002):
            self.db.add_event(title=f"Эпидемия {year}", year=year, category="эпидемия",
                              location="Европа")
        rules = CrossCategoryAnalyzer(self.db).analyze(max_delay=10)
        war_to_epi = [r for r in rules
                      if r["trigger_category"] == "война"
                      and r["result_category"] == "эпидемия"
                      and r["delay_years"] == 2]
        self.assertTrue(war_to_epi, f"цепочка война→эпидемия (2 года) не найдена: {rules}")
        self.assertGreater(war_to_epi[0]["lift"], 1.5)

    def test_rules_saved_and_loaded(self):
        for year in (1900, 1925, 1950, 1975, 2000):
            self.db.add_event(title=f"Война {year}", year=year, category="война",
                              location="Европа")
        for year in (1902, 1927, 1952, 1977, 2002):
            self.db.add_event(title=f"Эпидемия {year}", year=year, category="эпидемия",
                              location="Европа")
        analyzer = CrossCategoryAnalyzer(self.db)
        rules = analyzer.analyze(max_delay=10)
        analyzer.save_rules(rules)
        stored = self.db.conn.execute("SELECT COUNT(*) FROM cross_category_rules").fetchone()[0]
        self.assertEqual(stored, len(rules))


class TestBacktest(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.mkdtemp(prefix="safon_bt_")
        self.db = SafonDatabase(db_path=os.path.join(tmpdir, "test.db"))
        assert self.db.conn is not None
        for year in range(1800, 2021, 25):
            self.db.add_event(title=f"Война {year}", year=year, category="война",
                              location="Ближний Восток", magnitude=0.7, importance_score=0.8)
        self.engine = PredictionEngine(self.db, analyzer=None)

    def tearDown(self):
        self.db.close()

    def test_walk_forward_metrics(self):
        res = self.engine.run_backtest(from_year=1900)
        self.assertGreater(res["total_checks"], 0)
        self.assertIn("война", res["by_category"])
        for key in ("total_accuracy", "year_hit_rate", "location_hit_rate", "brier_score"):
            self.assertIn(key, res)
        self.assertTrue(0.0 <= res["brier_score"] <= 1.0)
        d = res["by_category"]["война"]
        self.assertIn("lift", d)
        self.assertGreater(d["lift"], 1.0, "на идеально периодичных данных lift > 1")
        statuses = {r[0] for r in self.db.conn.execute(
            "SELECT DISTINCT status FROM backtest_results")}
        self.assertTrue(statuses.issubset({"confirmed", "partial", "missed"}))

    def test_backtest_rows_saved(self):
        self.engine.run_backtest(from_year=1900)
        n = self.db.conn.execute("SELECT COUNT(*) FROM backtest_results").fetchone()[0]
        self.assertGreater(n, 0)
        lifts = [r[0] for r in self.db.conn.execute(
            "SELECT DISTINCT lift FROM backtest_results")]
        self.assertTrue(all(l is not None for l in lifts))


if __name__ == "__main__":
    unittest.main()

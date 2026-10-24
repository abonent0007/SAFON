# -*- coding: utf-8 -*-
"""Тесты ядра предсказаний: детерминизм, границы вероятностей, очистка устаревших прогнозов."""
import os
import tempfile
import unittest
from datetime import datetime

from core.database import SafonDatabase
from core.predictor import PredictionEngine


def seed_events(db):
    """Синтетика: три категории с разной плотностью и периодичностью."""
    for i, year in enumerate(range(1850, 2021, 25)):
        db.add_event(title=f"Война {year}", year=year, category="война",
                     location="Ближний Восток", magnitude=0.7, importance_score=0.8)
    for i, year in enumerate(range(1860, 2021, 10)):
        db.add_event(title=f"Наводнение {year}", year=year, category="наводнение",
                     location="Китай", magnitude=0.6, importance_score=0.7)
    for i, year in enumerate(range(1900, 2021, 4)):
        db.add_event(title=f"Пожар {year}", year=year, category="пожар",
                     location="США", magnitude=0.5, importance_score=0.6)


class TestPredictor(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.mkdtemp(prefix="safon_pred_")
        self.db = SafonDatabase(db_path=os.path.join(tmpdir, "test.db"))
        assert self.db.conn is not None
        seed_events(self.db)
        self.engine = PredictionEngine(self.db, analyzer=None)

    def tearDown(self):
        self.db.close()

    def _generate(self):
        return self.engine.generate_predictions(horizon=80, use_astrometry=False,
                                                use_ai=False, use_ensemble=True)

    def test_generate_returns_valid_predictions(self):
        preds = self._generate()
        self.assertGreater(len(preds), 0)
        required = {"category", "year", "month", "location", "probability",
                    "importance", "description", "reasoning"}
        for p in preds:
            self.assertTrue(required.issubset(p.keys()))
            self.assertLessEqual(0.05, p["probability"])
            self.assertLessEqual(p["probability"], 0.95)
            self.assertTrue(1 <= p["month"] <= 12)
            self.assertIn("ансамбль методик", p["reasoning"])

    def test_determinism(self):
        first = self._generate()
        second = self._generate()
        key = lambda ps: sorted((p["category"], p["year"], p["location"], round(p["probability"], 6))
                                for p in ps)
        self.assertEqual(key(first), key(second), "прогнозы должны быть воспроизводимы (без random)")

    def test_stale_predictions_cleaned(self):
        now = datetime.now().year
        self.db.conn.execute(
            "INSERT INTO predictions (category, predicted_year, location, probability, made_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("война", now + 10, "Никарагуа", 0.99))
        self.db.conn.commit()
        before = self.db.conn.execute(
            "SELECT COUNT(*) FROM predictions WHERE location = 'Никарагуа'").fetchone()[0]
        self.assertEqual(before, 1)
        self._generate()
        after = self.db.conn.execute(
            "SELECT COUNT(*) FROM predictions WHERE location = 'Никарагуа'").fetchone()[0]
        self.assertEqual(after, 0, "устаревший прогноз в активном окне должен быть удалён")

    def test_calibrate_bounds_and_monotonic(self):
        c = self.engine._calibrate
        self.assertEqual(c(0.5), 0.5)
        self.assertGreater(c(0.6), 0.6)
        self.assertLess(c(0.4), 0.5)
        self.assertEqual(c(-1.0), 0.05)
        self.assertEqual(c(2.0), 0.95)
        seq = [c(x / 100) for x in range(0, 101)]
        self.assertEqual(seq, sorted(seq), "калибровка должна быть монотонной")

    def test_month_deterministic(self):
        m1 = self.engine._predict_month_seasonal("пожар")
        m2 = self.engine._predict_month_seasonal("пожар")
        self.assertEqual(m1, m2)
        self.assertTrue(1 <= m1 <= 12)

    def test_accuracy_loaded_from_backtest(self):
        # пустая таблица → нейтральное значение
        acc = self.engine._category_accuracy()
        self.assertIsInstance(acc, dict)


if __name__ == "__main__":
    unittest.main()

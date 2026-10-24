# -*- coding: utf-8 -*-
"""Тесты БД: дедупликация, координаты из конфига, миграции, загрузка сида."""
import os
import tempfile
import unittest

from core.database import SafonDatabase


def make_db():
    tmpdir = tempfile.mkdtemp(prefix="safon_test_")
    db = SafonDatabase(db_path=os.path.join(tmpdir, "test.db"))
    assert db.conn is not None
    return db


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = make_db()

    def tearDown(self):
        self.db.close()

    def test_add_event_and_dedup(self):
        eid = self.db.add_event(title="Тестовое событие", year=2000, category="война",
                                location="Япония", description="desc")
        self.assertIsNotNone(eid)
        dup = self.db.add_event(title="Тестовое событие", year=2000, category="война",
                                location="Япония")
        self.assertIsNone(dup, "повторная вставка должна отсекаться хэшем")

    def test_get_coords_from_config(self):
        self.assertEqual(self.db._get_coords("Япония"), (36.0, 138.0))
        # ключ содержится в строке локации
        self.assertEqual(self.db._get_coords("Япония (море)"), (36.0, 138.0))
        # строка локации содержится в ключе
        self.assertEqual(self.db._get_coords("Ближний"), (28.0, 45.0))
        self.assertEqual(self.db._get_coords("Атлантида"), (30.0, 0.0))

    def test_migrations_applied(self):
        cols_bt = [r[1] for r in self.db.conn.execute("PRAGMA table_info(backtest_results)")]
        self.assertIn("lift", cols_bt)
        cols_pred = [r[1] for r in self.db.conn.execute("PRAGMA table_info(predictions)")]
        self.assertIn("ai_enhanced", cols_pred)

    def test_seed_events_loader(self):
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        self.db.load_historical_data()
        count = self.db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual(count, 677, "сид должен загрузить 677 стартовых событий")
        # идемпотентность: повторная загрузка не создаёт дублей
        self.db.load_historical_data()
        count2 = self.db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertEqual(count2, 677)


if __name__ == "__main__":
    unittest.main()

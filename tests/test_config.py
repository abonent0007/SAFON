# -*- coding: utf-8 -*-
"""Тесты конфиг-модуля: загрузка, авто-перезагрузка, полнота данных."""
import os
import unittest

from core.config import (CONFIG_PATH, get_categories, get_cycles,
                         get_descriptions, get_enrichment_templates,
                         get_locations, get_seasonal_months, get_config)


class TestConfig(unittest.TestCase):
    def test_config_file_exists(self):
        self.assertTrue(os.path.exists(CONFIG_PATH), "config/safon_config.json должен существовать")

    def test_categories_complete(self):
        cats = get_categories()
        self.assertGreaterEqual(len(cats), 11)
        self.assertIn("война", cats)
        self.assertEqual(cats["война"]["color"], "#ff0000")
        self.assertIn("shape", cats["война"])
        self.assertIn("icon", cats["война"])

    def test_locations_coords(self):
        locs = get_locations()
        self.assertGreater(len(locs), 100)
        self.assertEqual(locs["Япония"], {"lat": 36.0, "lng": 138.0})

    def test_cycles_and_descriptions(self):
        cycles = get_cycles()
        self.assertEqual(len(cycles), 11)
        for cat, data in cycles.items():
            self.assertIn("period", data)
            self.assertIn("base_confidence", data)
            self.assertTrue(data["locations"], cat)
        self.assertEqual(len(get_descriptions()), 11)

    def test_seasonal_and_contexts(self):
        seasonal = get_seasonal_months()
        self.assertTrue(all(isinstance(v, list) and v for v in seasonal.values()))
        ctx = get_config()["current_contexts"]
        self.assertTrue(all("{year}" in v for v in ctx.values()),
                        "все контексты должны содержать плейсхолдер {year}")

    def test_enrichment_templates(self):
        tpl = get_enrichment_templates()
        self.assertIn("wiki_queries", tpl)
        self.assertIn("ddg_templates", tpl)
        self.assertEqual(len(tpl["wiki_queries"]), 11)

    def test_force_reload(self):
        cfg = get_config(force=True)
        self.assertIsInstance(cfg, dict)
        self.assertIn("categories", cfg)


if __name__ == "__main__":
    unittest.main()

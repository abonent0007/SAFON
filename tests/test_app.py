# -*- coding: utf-8 -*-
"""Smoke-тесты Flask-приложения: маршруты, валидация параметров, оффлайн-режим."""
import os
import tempfile
import unittest
from unittest import mock

from core.database import SafonDatabase
from core.predictor import PredictionEngine


class TestAppEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmpdir = tempfile.mkdtemp(prefix="safon_app_")
        cls.db_path = os.path.join(tmpdir, "test.db")

        cls.env_patch = mock.patch.dict(os.environ, {
            'DEEPSEEK_MODE': 'api', 'DEEPSEEK_API_KEY': 'test-key',
            'SMTP_USERNAME': 'test@example.com', 'SMTP_PASSWORD': 'x',
            'NOTIFICATION_EMAIL': '',
        })
        cls.env_patch.start()

        import web.app as web_app

        cls.patches = [
            mock.patch.object(web_app, 'SafonDatabase', lambda: SafonDatabase(db_path=cls.db_path)),
            mock.patch.object(SafonDatabase, 'load_historical_data', lambda self: None),
            mock.patch.object(web_app, 'AstrometryModule', mock.MagicMock()),
            mock.patch.object(PredictionEngine, 'generate_predictions', return_value=[]),
        ]
        analyzer_patch = mock.patch.object(web_app, 'UltimateSemanticAnalyzer')
        cls.analyzer_cls = analyzer_patch.start()
        cls.analyzer_cls.return_value.get_status.return_value = {
            'available': False, 'mode': 'api', 'model': 'deepseek-flash'}
        cls.patches.append(analyzer_patch)

        for p in cls.patches:
            p.start()
        cls.app = web_app.create_app()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        cls.env_patch.stop()

    def test_index_ok(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_config_endpoint(self):
        resp = self.client.get('/api/config')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['categories'], "categories должны приходить с сервера")
        self.assertIn('threshold', data)
        self.assertIn('horizon', data)

    def test_predictions_endpoint(self):
        resp = self.client.get('/api/predictions')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('predictions', data)

    def test_historical_valid_and_invalid(self):
        self.assertEqual(self.client.get('/api/historical?years=5').status_code, 200)
        self.assertEqual(self.client.get('/api/historical?years=abc').status_code, 400)

    def test_send_email_validation(self):
        resp = self.client.post('/api/send-email', json={})
        self.assertEqual(resp.status_code, 400, "без получателя — 400")
        resp = self.client.post('/api/send-email', json={'email': 'not-an-email'})
        self.assertEqual(resp.status_code, 400, "некорректный email — 400")

    def test_ai_analyze_requires_title(self):
        resp = self.client.post('/api/ai/analyze', json={})
        self.assertEqual(resp.status_code, 400)

    def test_enrich_validation(self):
        resp = self.client.post('/api/enrich', json={'workers': 999})
        self.assertEqual(resp.status_code, 400)

    def test_backtest_validation(self):
        resp = self.client.post('/api/backtest', json={'from_year': 'zzz'})
        self.assertEqual(resp.status_code, 400)

    def test_backtest_runs(self):
        resp = self.client.post('/api/backtest', json={'from_year': 2000})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('year_hit_rate', data)
        self.assertIn('brier_score', data)

    def test_regenerate_ok(self):
        resp = self.client.post('/api/regenerate', json={})
        self.assertEqual(resp.status_code, 200)

    def test_astrometry_status_ok(self):
        resp = self.client.get('/api/astrometry/status')
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()

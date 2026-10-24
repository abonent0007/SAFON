# -*- coding: utf-8 -*-
"""Тесты email-нотификатора: возврат ошибок вместо тихого провала (без сети)."""
import unittest

from core.email_notifier import EmailNotifier


class TestEmailNotifier(unittest.TestCase):
    def test_no_predictions(self):
        notifier = EmailNotifier('smtp.local', 587, 'user', 'pass')
        ok, msg = notifier.send_important_predictions('a@b.co', [])
        self.assertFalse(ok)
        self.assertIn('Нет предсказаний', msg)

    def test_missing_credentials(self):
        notifier = EmailNotifier('smtp.local', 587, '', '')
        ok, msg = notifier.send_important_predictions(
            'a@b.co', [{'category': 'война', 'probability': 0.8}])
        self.assertFalse(ok)
        self.assertIn('SMTP', msg)

    def test_connection_error_is_reported(self):
        notifier = EmailNotifier('127.0.0.1', 1, 'user', 'pass')
        ok, msg = notifier.send_important_predictions(
            'a@b.co', [{'category': 'война', 'probability': 0.8,
                        'predicted_year': 2030, 'location': 'Европа'}])
        self.assertFalse(ok)
        self.assertTrue(msg, "текст ошибки должен возвращаться наружу")


if __name__ == "__main__":
    unittest.main()

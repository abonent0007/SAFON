"""
Модуль работы с базой данных SQLite
Хранит события, предсказания и исторические данные
"""

import sqlite3
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Tuple

from .config import get_locations


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))



class SafonDatabase:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path="data/safon.db"):
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()
        self._migrate_db()

    def _migrate_db(self):
        """Добавляет недостающие колонки и таблицы без удаления существующих данных"""
        # Колонки
        migrations = [
            ("predictions", "ai_enhanced", "BOOLEAN DEFAULT 0"),
            ("backtest_results", "lift", "REAL"),
        ]
        for table, column, col_type in migrations:
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                self.conn.commit()
            except Exception:
                pass

        # Новые таблицы (CREATE TABLE IF NOT EXISTS — безопасно)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                predicted_year INTEGER,
                location TEXT,
                probability REAL,
                actual_event_id INTEGER,
                actual_year INTEGER,
                actual_location TEXT,
                status TEXT,
                deviation_years INTEGER,
                lift REAL,
                created_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cycle_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                old_period REAL,
                new_period REAL,
                reason TEXT,
                backtest_accuracy_before REAL,
                backtest_accuracy_after REAL,
                adjusted_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_category_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_category TEXT,
                result_category TEXT,
                delay_years INTEGER,
                lift REAL,
                confidence REAL,
                sample_size INTEGER,
                discovered_at TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS location_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT,
                location TEXT
            )
        """)
        self.conn.commit()
    
    def _connect(self):
        """Устанавливает соединение с БД"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
    
    def _create_tables(self):
        """Создаёт все необходимые таблицы"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                year INTEGER,
                month INTEGER,
                day INTEGER,
                location TEXT,
                lat REAL,
                lng REAL,
                category TEXT,
                subcategory TEXT,
                magnitude REAL,
                importance_score REAL,
                source TEXT,
                source_confidence REAL,
                causes TEXT,
                effects TEXT,
                causal_delay INTEGER,
                created_at TIMESTAMP,
                hash TEXT UNIQUE
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                predicted_year INTEGER,
                predicted_month INTEGER,
                location TEXT,
                lat REAL,
                lng REAL,
                probability REAL,
                importance_score REAL,
                description TEXT,
                reasoning TEXT,
                cause_event_id INTEGER,
                made_at TIMESTAMP,
                email_sent BOOLEAN DEFAULT 0,
                astrometry_used BOOLEAN DEFAULT 0,
                ai_enhanced BOOLEAN DEFAULT 0
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id INTEGER,
                sent_at TIMESTAMP,
                recipient TEXT,
                status TEXT
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS astrometry_correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                planet_pair TEXT,
                aspect_type TEXT,
                event_category TEXT,
                phase_low REAL,
                phase_high REAL,
                probability REAL,
                lift REAL,
                confidence REAL,
                sample_size INTEGER,
                discovered_at TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    def _get_coords(self, location: str) -> Tuple[float, float]:
        """Возвращает координаты для локации"""
        location_lower = location.lower()
        for loc, coords in get_locations().items():
            if loc.lower() in location_lower or location_lower in loc.lower():
                return coords["lat"], coords["lng"]
        return 30.0, 0.0
    
    def add_event(self, **kwargs):
        """Добавляет событие в БД с дедупликацией"""
        lat, lng = self._get_coords(kwargs.get('location', 'глобально'))
        
        event_hash = hashlib.md5(
            f"{kwargs.get('title')}|{kwargs.get('year')}|{kwargs.get('category')}".encode()
        ).hexdigest()
        
        # Проверка на существование
        cursor = self.conn.execute("SELECT id FROM events WHERE hash = ?", (event_hash,))
        if cursor.fetchone():
            return None
        
        cursor = self.conn.execute("""
            INSERT INTO events (
                title, description, year, month, day, location, lat, lng,
                category, subcategory, magnitude, importance_score, source,
                source_confidence, causes, effects, causal_delay, created_at, hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kwargs.get('title'), kwargs.get('description', '')[:500],
            kwargs.get('year'), kwargs.get('month', 1), kwargs.get('day', 1),
            kwargs.get('location', 'глобально'), lat, lng,
            kwargs.get('category'), kwargs.get('subcategory', ''),
            kwargs.get('magnitude', 0.5), kwargs.get('importance_score', 0.5),
            kwargs.get('source', 'unknown'), kwargs.get('source_confidence', 0.7),
            json.dumps(kwargs.get('causes', [])), json.dumps(kwargs.get('effects', [])),
            kwargs.get('causal_delay', 2), datetime.now(), event_hash
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def save_prediction(self, prediction: Dict) -> int:
        """Сохраняет предсказание в БД с дедупликацией"""
        lat, lng = self._get_coords(prediction.get('location', 'глобально'))
        category = prediction['category']
        year = prediction['year']
        location = prediction.get('location', 'глобально')

        # Проверка: существует ли предсказание с таким же ключом
        existing = self.conn.execute(
            "SELECT id FROM predictions WHERE category=? AND predicted_year=? AND location=?",
            (category, year, location)
        ).fetchone()

        if existing:
            # Обновить существующее
            self.conn.execute("""
                UPDATE predictions SET
                    probability=?, importance_score=?, description=?, reasoning=?,
                    made_at=?, astrometry_used=?, ai_enhanced=?
                WHERE id=?
            """, (
                prediction['probability'], prediction.get('importance', prediction['probability']),
                prediction.get('description', ''), prediction.get('reasoning', ''),
                datetime.now(),
                prediction.get('astrometry_used', False),
                prediction.get('ai_enhanced', False),
                existing[0]
            ))
            return existing[0]

        cursor = self.conn.execute("""
            INSERT INTO predictions (
                category, predicted_year, predicted_month, location, lat, lng,
                probability, importance_score, description, reasoning, cause_event_id, made_at, astrometry_used, ai_enhanced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            category, year, prediction.get('month', 6),
            location, lat, lng,
            prediction['probability'], prediction.get('importance', prediction['probability']),
            prediction.get('description', ''), prediction.get('reasoning', ''),
            prediction.get('cause_event_id'), datetime.now(),
            prediction.get('astrometry_used', False),
            prediction.get('ai_enhanced', False)
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_active_predictions(self) -> List[Dict]:
        """Получает все активные предсказания (с 5 лет назад)"""
        cursor = self.conn.execute("""
            SELECT * FROM predictions 
            WHERE predicted_year >= ? 
            ORDER BY probability DESC, predicted_year ASC
        """, (datetime.now().year - 5,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_important_predictions(self, threshold: float = 0.75) -> List[Dict]:
        """Получает важные предсказания — включая валидационные (с 5 лет назад)"""
        cursor = self.conn.execute("""
            SELECT * FROM predictions 
            WHERE predicted_year >= ? AND probability >= ?
            ORDER BY probability DESC
            LIMIT 10
        """, (datetime.now().year - 5, threshold))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_events(self) -> List[Dict]:
        """Получает все события из БД"""
        cursor = self.conn.execute("SELECT * FROM events ORDER BY year")
        columns = [desc[0] for desc in cursor.description]
        events = []
        for row in cursor.fetchall():
            event = dict(zip(columns, row))
            if event.get('causes'):
                event['causes'] = json.loads(event['causes']) if isinstance(event['causes'], str) else event['causes']
            if event.get('effects'):
                event['effects'] = json.loads(event['effects']) if isinstance(event['effects'], str) else event['effects']
            events.append(event)
        return events
    
    def mark_email_sent(self, prediction_id: int, recipient: str, status: str):
        """Отмечает, что письмо отправлено"""
        self.conn.execute("""
            INSERT INTO email_log (prediction_id, sent_at, recipient, status)
            VALUES (?, ?, ?, ?)
        """, (prediction_id, datetime.now(), recipient, status))
        self.conn.execute("""
            UPDATE predictions SET email_sent = 1 WHERE id = ?
        """, (prediction_id,))
        self.conn.commit()
    
    def get_astrometry_correlations(self) -> List[Dict]:
        """Получает сохранённые астрометрические корреляции"""
        cursor = self.conn.execute("""
            SELECT * FROM astrometry_correlations 
            ORDER BY lift DESC, confidence DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def save_astrometry_correlation(self, correlation: Dict):
        """Сохраняет астрометрическую корреляцию"""
        self.conn.execute("""
            INSERT INTO astrometry_correlations 
            (planet_pair, aspect_type, event_category, phase_low, phase_high,
             probability, lift, confidence, sample_size, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            correlation['planet_pair'], correlation['aspect_type'], correlation['event_category'],
            correlation['phase_low'], correlation['phase_high'], correlation['probability'],
            correlation['lift'], correlation['confidence'], correlation['sample_size'],
            datetime.now()
        ))
        self.conn.commit()
    
    def load_historical_data(self):
        """Загружает стартовый набор исторических событий из config/seed_events.json.
        Дедупликация на уровне add_event — повторные запуски безопасны."""
        seed_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'seed_events.json',
        )
        if not os.path.exists(seed_path):
            _safe_print(f"⚠️ Стартовый набор не найден: {seed_path}")
            return
        with open(seed_path, encoding='utf-8') as f:
            seed_events = json.load(f)
        added = 0
        for e in seed_events:
            event_id = self.add_event(
                title=e.get('title'),
                description=e.get('description', ''),
                year=e.get('year'),
                month=e.get('month', 1),
                day=e.get('day', 1),
                location=e.get('location', 'глобально'),
                category=e.get('category'),
                subcategory=e.get('subcategory', ''),
                magnitude=e.get('magnitude', 0.5),
                importance_score=e.get('importance_score', 0.5),
                source=e.get('source', 'historical'),
                source_confidence=e.get('source_confidence', 0.7),
                causes=e.get('causes', []),
                effects=e.get('effects', []),
                causal_delay=e.get('causal_delay', 2),
            )
            if event_id:
                added += 1
        _safe_print(f"📚 Историческая база: добавлено {added} из {len(seed_events)} стартовых событий")

    def close(self):
        """Закрывает соединение с БД"""
        if self.conn:
            self.conn.close()
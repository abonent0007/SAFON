"""
Модуль генерации предсказаний с DeepSeek V4 Pro и астрометрией
"""

import random
import threading
from datetime import datetime
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .database import EVENT_CATEGORIES
from .astrometry import AstrometryModule, AstroPredictionEnhancer


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class PredictionEngine:
    """Генератор предсказаний с поддержкой DeepSeek и астрометрии"""
    
    def __init__(self, db, analyzer=None):
        self.db = db
        self.analyzer = analyzer  # DeepSeek анализатор
        self.astro = AstrometryModule()
        self.astro_enhancer = AstroPredictionEnhancer(self.astro)
        
        self.cycles = {
            "землетрясение": {"period": 8, "base_confidence": 0.65,
                              "locations": ["Япония", "Индонезия", "Китай", "США", "Турция", "Чили", "Италия", "Мексика"]},
            "цунами": {"period": 12, "base_confidence": 0.60,
                       "locations": ["Индонезия", "Япония", "Тихоокеанское побережье", "Чили"]},
            "наводнение": {"period": 7, "base_confidence": 0.70,
                          "locations": ["Китай", "Индия", "Пакистан", "Европа", "Бангладеш"]},
            "пожар": {"period": 5, "base_confidence": 0.68,
                     "locations": ["США", "Австралия", "Европа", "Россия", "Канада", "Турция"]},
            "ураган": {"period": 4, "base_confidence": 0.72,
                      "locations": ["США", "Карибы", "Юго-Восточная Азия", "Филиппины", "Багамы"]},
            "экономический кризис": {"period": 11, "base_confidence": 0.75,
                                     "locations": ["США", "Китай", "Европа", "глобально", "Юго-Восточная Азия"]},
            "война": {"period": 25, "base_confidence": 0.70,
                     "locations": ["Ближний Восток", "Восточная Европа", "Юго-Восточная Азия", "Африка"]},
            "эпидемия": {"period": 40, "base_confidence": 0.68,
                        "locations": ["глобально", "Китай", "Индия", "Африка"]},
            "революция": {"period": 30, "base_confidence": 0.65,
                         "locations": ["Ближний Восток", "Европа", "Африка", "Юго-Восточная Азия"]},
            "засуха": {"period": 12, "base_confidence": 0.62,
                      "locations": ["Африка", "Индия", "США", "Австралия"]},
            "экологическая катастрофа": {"period": 8, "base_confidence": 0.60,
                                        "locations": ["США", "Россия", "Китай", "Индия", "Европа"]},
        }
        
        self.descriptions = {
            "землетрясение": "Вероятно сильное землетрясение магнитудой 7.0-8.5 в сейсмоактивной зоне",
            "цунами": "Риск возникновения разрушительного цунами после подводного землетрясения",
            "наводнение": "Катастрофическое наводнение в результате аномальных осадков",
            "пожар": "Масштабные лесные пожары в засушливый сезон",
            "ураган": "Мощный ураган (4-5 категория) с ветрами до 250 км/ч",
            "экономический кризис": "Глобальный финансовый кризис на фоне пузырей на рынках",
            "война": "Военный конфликт из-за территориальных или ресурсных споров",
            "эпидемия": "Вспышка нового вируса с пандемическим потенциалом",
            "революция": "Массовые протесты и политический кризис с возможной сменой власти",
            "засуха": "Длительная засуха с риском неурожая и голода в регионе",
            "экологическая катастрофа": "Техногенная авария или природный катаклизм с экологическими последствиями",
        }
    
    def analyze_astrometry_correlations(self):
        """Запускает автоматический поиск корреляций"""
        _safe_print("\n🔭 АВТОМАТИЧЕСКИЙ ПОИСК ПЛАНЕТАРНЫХ КОРРЕЛЯЦИЙ...")
        events = self.db.get_all_events()
        if len(events) < 10:
            _safe_print("⚠️ Недостаточно исторических данных")
            return []
        
        correlations = self.astro.analyze_historical_correlations(events)
        
        self.db.conn.execute("DELETE FROM astrometry_correlations")
        for c in correlations:
            self.db.save_astrometry_correlation({
                'planet_pair': c.planet_pair,
                'aspect_type': c.aspect_type,
                'event_category': c.event_category,
                'phase_low': c.phase_range[0],
                'phase_high': c.phase_range[1],
                'probability': c.probability,
                'lift': c.lift,
                'confidence': c.confidence,
                'sample_size': c.sample_size
            })
        
        _safe_print(f"✅ Найдено {len(correlations)} корреляций")
        return correlations
    
    def generate_predictions(self, horizon: int = 80, use_astrometry: bool = True, use_ai: bool = True) -> List[Dict]:
        """Генерирует предсказания с использованием DeepSeek AI"""
        _safe_print("\n🔮 ГЕНЕРАЦИЯ ПРЕДСКАЗАНИЙ")
        _safe_print("=" * 60)
        _safe_print(f"📡 Астрометрический модуль: {'ВКЛЮЧЁН' if use_astrometry else 'ВЫКЛЮЧЁН'}")
        _safe_print(f"🧠 DeepSeek V4 Pro AI: {'ВКЛЮЧЁН' if use_ai else 'ВЫКЛЮЧЁН'}")
        
        if use_astrometry:
            self.analyze_astrometry_correlations()
        
        predictions = []
        current_year = datetime.now().year
        
        for category, data in self.cycles.items():
            cursor = self.db.conn.execute("""
                SELECT year FROM events WHERE category = ? 
                ORDER BY year DESC LIMIT 1
            """, (category,))
            
            last_event = cursor.fetchone()
            if not last_event:
                continue
            
            last_year = last_event[0]
            
            for cycle_num in range(1, int(horizon / data["period"]) + 1):
                base_year = last_year + int(data["period"] * cycle_num)
                
                if base_year > current_year and base_year <= current_year + horizon:
                    if use_astrometry:
                        predicted_year = self.astro_enhancer.find_best_prediction_year(
                            base_year, data["period"], category, search_range=3
                        )
                    else:
                        predicted_year = base_year
                    
                    for location in data["locations"]:
                        time_decay = 1.0 - (cycle_num - 1) * 0.03
                        base_prob = data["base_confidence"] * random.uniform(0.85, 1.15) * time_decay
                        base_prob = min(0.9, max(0.2, base_prob))
                        
                        if use_astrometry:
                            final_prob = self.astro_enhancer.adjust_prediction_probability(
                                base_prob, predicted_year, category
                            )
                        else:
                            final_prob = base_prob
                        
                        if final_prob >= 0.25:
                            reasoning = self._generate_reasoning(
                                category, last_year, data["period"], 
                                predicted_year, final_prob, use_astrometry
                            )
                            
                            prediction = {
                                "category": category,
                                "year": predicted_year,
                                "month": self._predict_month(category),
                                "location": location,
                                "probability": final_prob,
                                "importance": final_prob * EVENT_CATEGORIES.get(category, {}).get("importance", 0.8),
                                "description": self.descriptions.get(category, "Значительное событие"),
                                "reasoning": reasoning,
                                "icon": EVENT_CATEGORIES.get(category, {}).get("icon", "📌"),
                                "color": EVENT_CATEGORIES.get(category, {}).get("color", "#888888"),
                                "astrometry_used": use_astrometry
                            }
                            
                            # Улучшаем описание через DeepSeek AI
                            if use_ai and self.analyzer:
                                prediction = self.analyzer.enhance_prediction(prediction)
                            
                            predictions.append(prediction)
        
        # Дедупликация
        unique = {}
        for p in predictions:
            key = f"{p['category']}_{p['year']}_{p['location']}"
            if key not in unique or unique[key]['probability'] < p['probability']:
                unique[key] = p
        
        predictions = list(unique.values())
        predictions.sort(key=lambda x: (x['year'], -x['probability']))

        # AI-улучшение ТОЛЬКО для важных предсказаний (вероятность >= 75%) — многопоточно
        if use_ai and self.analyzer:
            ai_available = self.analyzer.get_status().get('available', False)
            if ai_available:
                important = [p for p in predictions if p['probability'] >= 0.75]
                _safe_print(f"\n🧠 AI-улучшение {len(important)} важных предсказаний (параллельно)...")
                lock = threading.Lock()

                def enhance_one(pred):
                    return self.analyzer.enhance_prediction(pred)

                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(enhance_one, pred) for pred in important[:10]]
                    for i, future in enumerate(as_completed(futures)):
                        try:
                            enhanced = future.result()
                            if enhanced.get('ai_enhanced'):
                                with lock:
                                    _safe_print(f"   ✅ {enhanced['category']} {enhanced['year']} ({enhanced['location']})")
                        except Exception as e:
                            _safe_print(f"   ⚠️ AI ошибка: {e}")

        # Сохраняем ВСЕ предсказания в БД (не только top 50)
        _safe_print(f"\n💾 Сохранение {len(predictions)} предсказаний в БД...")
        for pred in predictions:
            self.db.save_prediction(pred)
        self.db.conn.commit()
        _safe_print(f"✅ Сохранено {len(predictions)} предсказаний")
        
        _safe_print(f"\n✅ Сгенерировано {len(predictions)} предсказаний")
        
        if use_astrometry and self.astro.correlations:
            _safe_print("\n📊 АСТРОМЕТРИЧЕСКАЯ СТАТИСТИКА:")
            _safe_print(f"   Найдено корреляций: {len(self.astro.correlations)}")
        
        return predictions
    
    def _generate_reasoning(self, category: str, last_year: int, period: float,
                            predicted_year: int, probability: float,
                            use_astrometry: bool) -> str:
        events = self.db.get_all_events()
        cat_events = sorted(
            [(e['year'], e.get('title', '')) for e in events if e['category'] == category],
            key=lambda x: x[0]
        )

        # Последние 3 события для контекста
        recent = cat_events[-3:] if len(cat_events) >= 3 else cat_events
        recent_str = "; ".join([f"{y} г. — {t}" for y, t in recent])

        interval = int(predicted_year - last_year)
        base = (
            f"Цикл {int(period)} лет: исторический анализ {len(cat_events)} событий категории «{category}». "
            f"Последние: {recent_str}. "
            f"Следующее ожидается через {interval} лет после {last_year} года — в {predicted_year}. "
            f"Статистическая вероятность {probability:.0%}."
        )

        if use_astrometry and self.astro.correlations:
            active = self.astro.get_active_correlations(predicted_year)
            if active:
                astro_text = ". Планетарный фактор: " + ". ".join(
                    [f"{a['planets']} {a['aspect']} (boost {a['probability_boost']})" for a in active[:2]]
                )
                return base + astro_text
        return base
    
    def _predict_month(self, category: str) -> int:
        seasonal = {
            "землетрясение": [1, 2, 3, 11, 12],
            "цунами": [1, 2, 3, 11, 12],
            "наводнение": [6, 7, 8, 9],
            "пожар": [7, 8, 9],
            "ураган": [8, 9, 10],
            "экономический кризис": [9, 10],
            "война": [3, 4, 5, 6],
            "эпидемия": [1, 2, 11, 12],
            "революция": [3, 4, 5, 10],
            "засуха": [6, 7, 8],
            "экологическая катастрофа": [5, 6, 7, 8],
        }
        return random.choice(seasonal.get(category, [6, 7]))
    
    def get_astrometry_status(self) -> Dict:
        return {
            "enabled": True,
            "correlations_found": len(self.astro.correlations) if self.astro.correlations else len(self.db.get_astrometry_correlations()),
            "skyfield_available": self.astro.skyfield_available
        }
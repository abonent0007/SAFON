"""
Модуль генерации предсказаний: ансамбль методик
(циклы + спектральный анализ + астрометрия + причинные цепочки + калибровка по бэктесту)
"""

import copy
import math
import threading
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .astrometry import AstrometryModule, AstroPredictionEnhancer
from .config import (get_categories, get_cycles, get_descriptions,
                     get_seasonal_months)
from .cross_category import CrossCategoryAnalyzer
from .spectral_analyzer import SpectralAnalyzer


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class PredictionEngine:
    """Генератор предсказаний: ансамбль методик с объяснимым обоснованием"""

    ENSEMBLE_WEIGHTS = {
        "cycle": 0.40,
        "spectral": 0.25,
        "astro": 0.15,
        "chain": 0.10,
        "backtest": 0.10,
    }
    AGREEMENT_BONUS = 0.02
    HIGH_GAIN = 4.0

    def __init__(self, db, analyzer=None):
        self.db = db
        self.analyzer = analyzer  # DeepSeek анализатор
        self.astro = AstrometryModule()
        self.astro_enhancer = AstroPredictionEnhancer(self.astro)
        self._chain_rules = None
        self._accuracy_cache = None

        self.cycles = self._load_cycles()
        self.descriptions = get_descriptions()

    def _load_cycles(self) -> Dict:
        """Циклы из конфига (config/safon_config.json) + сохранённые автокоррекции из БД.
        Применяется последняя запись cycle_adjustments на категорию — корректировки
        больше не теряются между запусками."""
        cycles = copy.deepcopy(get_cycles())
        if self.db is not None:
            try:
                rows = self.db.conn.execute(
                    "SELECT category, new_period FROM cycle_adjustments "
                    "WHERE id IN (SELECT MAX(id) FROM cycle_adjustments GROUP BY category)"
                ).fetchall()
                for r in rows:
                    if r["category"] in cycles:
                        cycles[r["category"]]["period"] = r["new_period"]
            except Exception:
                pass
        return cycles

    # ========== ИСТОЧНИКИ ДАННЫХ ДЛЯ АНСАМБЛЯ ==========

    def _load_chain_rules(self) -> List[Dict]:
        """Правила причинных цепочек из БД (кэш в памяти)"""
        if self._chain_rules is None:
            rows = self.db.conn.execute("SELECT * FROM cross_category_rules").fetchall()
            self._chain_rules = [dict(r) for r in rows]
        return self._chain_rules

    def _category_accuracy(self) -> Dict:
        """Историческая точность и lift категорий из walk-forward бэктеста (кэш)"""
        if self._accuracy_cache is None:
            rows = self.db.conn.execute("""
                SELECT category, COUNT(*) AS total,
                       SUM(CASE WHEN status IN ('confirmed','partial') THEN 1 ELSE 0 END) AS hits,
                       AVG(lift) AS lift
                FROM backtest_results GROUP BY category
            """).fetchall()
            self._accuracy_cache = {
                r['category']: {'hits': r['hits'] or 0, 'total': r['total'], 'lift': r['lift']}
                for r in rows
            }
        return self._accuracy_cache

    # ========== МЕТОДИКИ АНСАМБЛЯ ==========

    def _calibrate(self, score: float) -> float:
        """Растяжка верхнего хвоста индекса согласия: сильное согласие методик
        даёт заметную вероятность. Нижняя половина (слабые/нейтральные сигналы)
        не искажается — порог 0.25 сохраняет прежний смысл."""
        if score > 0.5:
            score = 0.5 + (score - 0.5) * self.HIGH_GAIN
        return min(0.95, max(0.05, score))

    def _recency_factor(self, cat_events: List[Dict], predicted_year: int) -> float:
        """Методика «взвешенные циклы»: свежие и сильные события весомее (0.9..1.1)"""
        recent = sorted(cat_events, key=lambda e: e['year'])[-10:]
        weights = [
            1.0 / (1 + 0.03 * (predicted_year - e['year'])) * ((e.get('magnitude') or 0.5) + 0.5)
            for e in recent
        ]
        avg = sum(weights) / len(weights) if weights else 1.0
        return 0.9 + 0.1 * avg

    def _spectral_support(self, spectral: List, last_year: int, predicted_year: int) -> float:
        """Методика «спектральный анализ»: насколько скрытые периоды поддерживают год (0..1)"""
        if not spectral:
            return 0.5
        best = 0.0
        for period, conf, _count in spectral[:3]:
            if period <= 0:
                continue
            k = max(1, round((predicted_year - last_year) / period))
            anchor = last_year + period * k
            alignment = math.exp(-abs(anchor - predicted_year) / 1.5)
            best = max(best, alignment * conf)
        return max(0.0, min(1.0, best))

    def _chain_boost(self, category: str, predicted_year: int, events: List[Dict]):
        """Методика «причинные цепочки»: буст по правилам A→B через N лет (0..0.15)"""
        boost = 0.0
        notes = []
        rules = [r for r in self._load_chain_rules() if r.get('result_category') == category]
        if not rules:
            return 0.0, notes
        triggers = {}
        for e in events:
            triggers.setdefault(e['category'], []).append(e['year'])
        for rule in rules:
            for ty in triggers.get(rule.get('trigger_category'), []):
                if abs((predicted_year - ty) - (rule.get('delay_years') or 0)) <= 1:
                    boost += min(0.05, (rule.get('lift') or 1.0) * 0.02)
                    notes.append("%s→%s через %s лет (lift %.1fx)" % (
                        rule['trigger_category'], category,
                        rule.get('delay_years'), rule.get('lift') or 1.0))
                    break
            if len(notes) >= 3:
                break
        return min(0.15, boost), notes[:3]

    def _build_reasoning(self, category: str, cat_events: List[Dict], last_year: int,
                         period: float, predicted_year: int, probability: float,
                         spectral: List, spectral_support: float, astro_notes: List,
                         chain_notes: List, acc_info, use_ensemble: bool,
                         raw_index: Optional[float] = None) -> str:
        """Собирает объяснение: вклад каждой методики ансамбля"""
        recent = sorted(cat_events, key=lambda e: e['year'])[-3:]
        recent_str = "; ".join(f"{e['year']} — {e.get('title', '')[:70]}" for e in recent)
        parts = [
            f"Цикл {int(period)} лет: {len(cat_events)} событий в истории, последние: {recent_str}",
            f"Следующее ожидается в {predicted_year} (через {int(predicted_year - last_year)} лет после {last_year})",
        ]
        if spectral:
            p0 = spectral[0]
            parts.append(
                f"Спектральная проверка: скрытый период {p0[0]} лет "
                f"(уверенность {p0[1]:.2f}), согласие с прогнозом {spectral_support:.2f}"
            )
        if astro_notes:
            parts.append("Планетарные факторы: " + "; ".join(
                f"{a['planets']} {a['aspect']} (буст {a['probability_boost']})" for a in astro_notes))
        if chain_notes:
            parts.append("Причинные цепочки: " + "; ".join(chain_notes))
        if acc_info:
            parts.append(
                f"Walk-forward: точность {acc_info[0]:.0%}, lift {acc_info[1]:.2f}x к случайному году")
        label = "ансамбль методик" if use_ensemble else "базовый цикл"
        if raw_index is not None and abs(raw_index - probability) > 0.005:
            parts.append(
                f"Итоговая вероятность ({label}): {probability:.0%} "
                f"(индекс согласия методик {raw_index:.2f})")
        else:
            parts.append(f"Итоговая вероятность ({label}): {probability:.0%}")
        return ". ".join(parts) + "."

    # ========== ГЕНЕРАЦИЯ ==========

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

    def generate_predictions(self, horizon: int = 80, use_astrometry: bool = True,
                             use_ai: bool = True, use_ensemble: bool = True) -> List[Dict]:
        """Генерирует предсказания ансамблем методик с объяснением вклада каждой"""
        _safe_print("\n🔮 ГЕНЕРАЦИЯ ПРЕДСКАЗАНИЙ (ансамбль методик)")
        _safe_print("=" * 60)
        _safe_print(f"📡 Астрометрический модуль: {'ВКЛЮЧЁН' if use_astrometry else 'ВЫКЛЮЧЁН'}")
        _safe_print(f"🧠 DeepSeek AI: {'ВКЛЮЧЁН' if use_ai else 'ВЫКЛЮЧЁН'}")
        _safe_print(f"🧮 Ансамбль методик: {'ВКЛЮЧЁН' if use_ensemble else 'ВЫКЛЮЧЁН'}")

        events = self.db.get_all_events()
        self._chain_rules = None
        self._accuracy_cache = None
        # Авто-обновление из конфига при изменении данных на диске
        self.cycles = self._load_cycles()
        self.descriptions = get_descriptions()
        categories = get_categories()

        if use_ensemble:
            chain_analyzer = CrossCategoryAnalyzer(self.db)
            rules = chain_analyzer.analyze(max_delay=15)
            chain_analyzer.save_rules(rules)
            self._chain_rules = rules
            _safe_print(f"🔗 Причинно-следственных правил найдено: {len(rules)}")

        if use_astrometry:
            self.analyze_astrometry_correlations()

        accuracy = self._category_accuracy()

        predictions = []
        current_year = datetime.now().year
        start_year = current_year - 5  # начинаем за 5 лет до сейчас — валидация точности

        for category, data in self.cycles.items():
            cat_events = [e for e in events if e['category'] == category]
            if not cat_events:
                continue

            last_year = max(e['year'] for e in cat_events)
            years_sorted = sorted(e['year'] for e in cat_events)
            spectral = SpectralAnalyzer.find_periods(years_sorted) if use_ensemble else []
            acc = accuracy.get(category)
            acc_rate = round(acc['hits'] / acc['total'], 2) if acc and acc['total'] >= 8 else None
            if acc and acc['total'] >= 8 and acc.get('lift'):
                s_backtest_cat = max(0.2, min(1.0, acc['lift'] * 0.5))
                acc_info = (acc_rate, round(acc['lift'], 2))
            else:
                s_backtest_cat = 0.5
                acc_info = None
            month = self._predict_month_seasonal(category, cat_events)

            for cycle_num in range(1, int(horizon / data["period"]) + 1):
                base_year = last_year + int(data["period"] * cycle_num)
                if not (base_year > start_year and base_year <= current_year + horizon):
                    continue

                if use_astrometry:
                    predicted_year = self.astro_enhancer.find_best_prediction_year(
                        base_year, data["period"], category, search_range=3
                    )
                else:
                    predicted_year = base_year

                for location in data["locations"]:
                    time_decay = 1.0 - (cycle_num - 1) * 0.03
                    s_cycle = max(0.2, min(0.9, data["base_confidence"] * time_decay
                                          * self._recency_factor(cat_events, predicted_year)))
                    s_spectral = self._spectral_support(spectral, last_year, predicted_year) if use_ensemble else 0.5
                    s_astro = self.astro_enhancer.astro.calculate_event_probability(
                        predicted_year, category) if use_astrometry else 0.3
                    s_chain, chain_notes = (
                        self._chain_boost(category, predicted_year, events) if use_ensemble else (0.0, [])
                    )
                    s_backtest = s_backtest_cat

                    if use_ensemble:
                        w = self.ENSEMBLE_WEIGHTS
                        final_prob = (w["cycle"] * s_cycle + w["spectral"] * s_spectral
                                      + w["astro"] * s_astro + w["chain"] * s_chain
                                      + w["backtest"] * s_backtest)
                        supporters = sum(1 for s in (s_spectral, s_astro, s_chain) if s >= 0.5)
                        final_prob += self.AGREEMENT_BONUS * max(0, supporters - 1)
                        raw_index = min(0.95, max(0.05, final_prob))
                        final_prob = self._calibrate(raw_index)
                    else:
                        raw_index = max(0.2, min(0.9, s_cycle))
                        final_prob = raw_index

                    if final_prob < 0.25:
                        continue

                    astro_notes = []
                    if use_astrometry and s_astro > 0.5:
                        astro_notes = self.astro.get_active_correlations(predicted_year)[:2]

                    reasoning = self._build_reasoning(
                        category, cat_events, last_year, data["period"], predicted_year,
                        final_prob, spectral, s_spectral, astro_notes, chain_notes,
                        acc_info, use_ensemble, raw_index=raw_index
                    )

                    predictions.append({
                        "category": category,
                        "year": predicted_year,
                        "month": month,
                        "location": location,
                        "probability": final_prob,
                        "importance": final_prob * categories.get(category, {}).get("importance", 0.8),
                        "description": self.descriptions.get(category, "Значительное событие"),
                        "reasoning": reasoning,
                        "icon": categories.get(category, {}).get("icon", "📌"),
                        "color": categories.get(category, {}).get("color", "#888888"),
                        "astrometry_used": use_astrometry
                    })

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
            analyzer = self.analyzer
            ai_available = analyzer.get_status().get('available', False)
            if ai_available:
                important = [p for p in predictions if p['probability'] >= 0.75]
                _safe_print(f"\n🧠 AI-улучшение {len(important)} важных предсказаний (параллельно)...")
                lock = threading.Lock()

                def enhance_one(pred):
                    return analyzer.enhance_prediction(pred)

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

        # Сохраняем ВСЕ предсказания в БД
        _safe_print(f"\n💾 Сохранение {len(predictions)} предсказаний в БД...")
        # Логический пробел: активное окно пересоздаётся целиком, чтобы прогнозы
        # старых якорей циклов не накапливались как «актуальные».
        self.db.conn.execute("DELETE FROM predictions WHERE predicted_year >= ?", (start_year,))
        self.db.conn.commit()
        for pred in predictions:
            self.db.save_prediction(pred)
        self.db.conn.commit()
        _safe_print(f"✅ Сохранено {len(predictions)} предсказаний")

        if use_astrometry and self.astro.correlations:
            _safe_print(f"\n📊 Астрометрических корреляций: {len(self.astro.correlations)}")

        return predictions

    # ========== МЕСЯЦ (СЕЗОННАЯ ДЕКОМПОЗИЦИЯ) ==========

    def _predict_month(self, category: str) -> int:
        """Детерминированный fallback месяца по типичным сезонам категории"""
        seasonal = get_seasonal_months()
        months = seasonal.get(category, [6, 7])
        return months[len(months) // 2]

    def _predict_month_seasonal(self, category: str, events: Optional[List[Dict]] = None) -> int:
        """Предсказывает месяц на основе реального распределения событий в БД"""
        source = events if events is not None else self.db.get_all_events()
        months = [e.get('month', 6) for e in source if e['category'] == category and e.get('month')]
        if len(months) < 5:
            return self._predict_month(category)
        from collections import Counter
        mc = Counter(months)
        return mc.most_common(1)[0][0]

    def get_astrometry_status(self) -> Dict:
        return {
            "enabled": True,
            "correlations_found": len(self.astro.correlations) if self.astro.correlations else len(self.db.get_astrometry_correlations()),
            "skyfield_available": self.astro.skyfield_available
        }

    # ========== БЭКТЕСТИНГ (WALK-FORWARD) ==========
    def run_backtest(self, from_year: int = 2000, to_year: Optional[int] = None) -> Dict:
        """Walk-forward бэктест: цикл проверяется на каждом историческом шаге.
        Метрики: точность года (±1), точность локации, Brier score (confirmed=1 / partial=0.5 / missed=0)."""
        if to_year is None:
            to_year = datetime.now().year - 1
        _safe_print(f"\n📊 WALK-FORWARD БЭКТЕСТ {from_year}-{to_year}...")

        all_events = self.db.get_all_events()
        results = []
        accuracy_by_category = {}
        total_checks = 0
        total_hits = 0
        total_year_hits = 0
        total_loc_hits = 0
        brier_sum = 0.0

        for category, data in self.cycles.items():
            cat_events = sorted(
                [e for e in all_events if e['category'] == category],
                key=lambda e: (e['year'], e['id'])
            )
            if len(cat_events) < 5:
                continue
            period = data["period"]
            locations = [loc.lower() for loc in data["locations"]]

            covered = set()
            for e in cat_events:
                for yy in (e['year'] - 1, e['year'], e['year'] + 1):
                    if from_year <= yy <= to_year:
                        covered.add(yy)
            span = to_year - from_year + 1 if to_year >= from_year else 0
            baseline_rate = len(covered) / span if span else 0.01
            baseline_rate = max(baseline_rate, 0.01)

            for i in range(3, len(cat_events)):
                last_year = cat_events[i - 1]['year']
                predicted_year = last_year + period
                if predicted_year < from_year or predicted_year > to_year:
                    continue

                match = None
                for r in cat_events[i:]:
                    if abs(r['year'] - predicted_year) <= 1:
                        match = r
                        break

                total_checks += 1
                probability = data["base_confidence"]
                status = 'missed'
                loc_ok = False
                if match:
                    total_year_hits += 1
                    rl = (match.get('location') or '').lower()
                    if rl:
                        loc_ok = any(loc in rl or rl in loc for loc in locations)
                    status = 'confirmed' if loc_ok else 'partial'
                    total_hits += 1
                    if loc_ok:
                        total_loc_hits += 1

                outcome = 1.0 if status == 'confirmed' else 0.5 if status == 'partial' else 0.0
                brier_sum += (probability - outcome) ** 2

                results.append({
                    'category': category,
                    'predicted_year': predicted_year,
                    'location': data["locations"][0],
                    'probability': probability,
                    'actual_event_id': match['id'] if match else None,
                    'actual_year': match['year'] if match else None,
                    'actual_location': match.get('location', '') if match else None,
                    'status': status,
                    'deviation_years': abs(match['year'] - predicted_year) if match else None,
                })

                d = accuracy_by_category.setdefault(category, {'hits': 0, 'total': 0})
                d['total'] += 1
                if status in ('confirmed', 'partial'):
                    d['hits'] += 1

            d = accuracy_by_category.get(category)
            if d and d['total']:
                d['lift'] = round((d['hits'] / d['total']) / baseline_rate, 2)

        # Сохраняем в БД (производные данные — пересчитываются заново)
        lift_lookup = {c: d.get('lift') for c, d in accuracy_by_category.items()}
        self.db.conn.execute("DELETE FROM backtest_results")
        for r in results:
            self.db.conn.execute("""
                INSERT INTO backtest_results
                (category, predicted_year, location, probability, actual_event_id, actual_year, actual_location, status, deviation_years, lift, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (r['category'], r['predicted_year'], r['location'], r['probability'],
                  r['actual_event_id'], r['actual_year'], r['actual_location'], r['status'], r['deviation_years'],
                  lift_lookup.get(r['category'])))
        self.db.conn.commit()

        for cat in accuracy_by_category:
            d = accuracy_by_category[cat]
            d['accuracy'] = round(d['hits'] / d['total'], 2) if d['total'] else 0

        overall = round(total_hits / total_checks, 2) if total_checks else 0
        year_rate = round(total_year_hits / total_checks, 2) if total_checks else 0
        loc_rate = round(total_loc_hits / total_checks, 2) if total_checks else 0
        brier = round(brier_sum / total_checks, 3) if total_checks else 0
        lifts = [d.get('lift') for d in accuracy_by_category.values() if d.get('lift')]
        avg_lift = round(sum(lifts) / len(lifts), 2) if lifts else 0
        _safe_print(
            f"   Год±1: {year_rate:.0%} | Локация: {loc_rate:.0%} | Общая: {overall:.0%}"
            f" ({total_hits}/{total_checks}) | Brier: {brier} | Средний lift: {avg_lift}x"
        )

        return {
            'total_accuracy': overall,
            'year_hit_rate': year_rate,
            'location_hit_rate': loc_rate,
            'brier_score': brier,
            'by_category': accuracy_by_category,
            'total_checks': total_checks,
            'total_hits': total_hits,
        }

    # ========== АВТОКОРРЕКЦИЯ ЦИКЛОВ ==========
    def auto_correct_cycles(self):
        """Корректирует периоды циклов на основе результатов бэктестинга"""
        cursor = self.db.conn.execute("""
            SELECT category, COUNT(*) as total,
                   SUM(CASE WHEN status='confirmed' OR status='partial' THEN 1 ELSE 0 END) as hits
            FROM backtest_results GROUP BY category
        """)
        stats = {r['category']: {'total': r['total'], 'hits': r['hits']} for r in [dict(row) for row in cursor.fetchall()]}

        adjustments = 0
        for category, data in self.cycles.items():
            if category not in stats or stats[category]['total'] < 5:
                continue
            accuracy = stats[category]['hits'] / stats[category]['total']
            if accuracy < 0.4 and stats[category]['total'] >= 8:
                old_period = data['period']
                events = [e['year'] for e in self.db.get_all_events() if e['category'] == category]
                if len(events) < 4:
                    continue

                periods = SpectralAnalyzer.find_periods(events)
                if periods and periods[0][0] != int(old_period):
                    new_period = float(periods[0][0])
                    self.db.conn.execute("""
                        INSERT INTO cycle_adjustments
                        (category, old_period, new_period, reason, backtest_accuracy_before, adjusted_at)
                        VALUES (?,?,?,?,?,datetime('now'))
                    """, (category, old_period, new_period, 'low_backtest_accuracy', accuracy))
                    self.db.conn.commit()
                    self.cycles[category]['period'] = new_period
                    _safe_print(f"   🔧 {category}: период {old_period}→{new_period} лет (точность была {accuracy:.0%})")
                    adjustments += 1
        return adjustments

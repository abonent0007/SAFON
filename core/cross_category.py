"""Кросс-категорийный анализ: цепочки событий A → B через N лет"""
from typing import List, Dict
from collections import defaultdict


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class CrossCategoryAnalyzer:
    """Ищет связи между категориями: после события A повышается ли вероятность B?"""

    def __init__(self, db):
        self.db = db

    def analyze(self, max_delay: int = 20) -> List[Dict]:
        events = self.db.get_all_events()
        by_category = defaultdict(list)
        for e in events:
            by_category[e['category']].append(e['year'])

        categories = list(by_category.keys())
        rules = []

        for trigger_cat in categories:
            trigger_years = set(by_category[trigger_cat])
            for result_cat in categories:
                if trigger_cat == result_cat:
                    continue
                result_years = by_category[result_cat]
                if len(result_years) < 5 or len(trigger_years) < 5:
                    continue

                result_set = set(result_years)
                max_result = max(result_years)
                baseline_rate = len(result_years) / (max_result - min(trigger_years) + 1) if trigger_years else 0
                baseline_rate = max(baseline_rate, 0.01)

                for delay in range(1, max_delay):
                    matches = 0
                    total_checks = 0
                    for ty in trigger_years:
                        test_year = ty + delay
                        if test_year <= max_result:
                            total_checks += 1
                            if (test_year - 1 in result_set
                                    or test_year in result_set
                                    or test_year + 1 in result_set):
                                matches += 1

                    if total_checks < 3:
                        continue

                    observed_rate = matches / total_checks if total_checks else 0
                    lift = observed_rate / baseline_rate if baseline_rate else 1.0

                    if lift > 1.5 and matches >= 2:
                        rules.append({
                            "trigger_category": trigger_cat,
                            "result_category": result_cat,
                            "delay_years": delay,
                            "lift": round(lift, 2),
                            "confidence": round(min(0.9, lift / 4 + matches / 10), 2),
                            "sample_size": total_checks,
                        })

        rules.sort(key=lambda r: -r['lift'])
        return rules[:50]

    def save_rules(self, rules: List[Dict]):
        self.db.conn.execute("DELETE FROM cross_category_rules")
        for r in rules:
            self.db.conn.execute("""
                INSERT INTO cross_category_rules
                (trigger_category, result_category, delay_years, lift, confidence, sample_size, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (r['trigger_category'], r['result_category'], r['delay_years'],
                  r['lift'], r['confidence'], r['sample_size']))
        self.db.conn.commit()

    def apply_to_prediction(self, prediction: Dict, context_events: List[Dict]) -> float:
        """Применяет кросс-категорийные правила к вероятности предсказания"""
        cursor = self.db.conn.execute("""
            SELECT * FROM cross_category_rules
            WHERE result_category = ?
        """, (prediction['category'],))
        rules = [dict(r) for r in cursor.fetchall()]

        boost = 0.0
        for rule in rules:
            trigger_years = [e['year'] for e in context_events if e['category'] == rule['trigger_category']]
            for ty in trigger_years:
                if abs((prediction['year'] - ty) - rule['delay_years']) <= 1:
                    boost += rule['lift'] * 0.03
        return min(0.15, boost)

"""Спектральный анализ временных рядов для поиска скрытых периодов"""
from typing import List, Dict, Tuple
from collections import Counter


class SpectralAnalyzer:
    """Поиск скрытых циклов через анализ интервалов"""

    @staticmethod
    def find_periods(years: List[int], min_period: int = 3, max_period: int = 120) -> List[Tuple[int, float, int]]:
        """Находит периоды по распределению интервалов между событиями.
        Возвращает: [(period, confidence, count), ...] отсортированные по confidence."""
        if len(years) < 3:
            return []
        years = sorted(years)
        diffs = [years[i + 1] - years[i] for i in range(len(years) - 1)]

        # Группируем близкие интервалы
        diff_counter = Counter(diffs)
        results = []
        seen = set()

        for diff, count in diff_counter.most_common():
            if count < 2 or diff < min_period or diff > max_period:
                continue
            if diff in seen:
                continue

            # Проверяем: является ли diff кратным более мелкого периода
            is_harmonic = False
            base_period = diff
            for d in range(min_period, diff // 2 + 1):
                if diff % d == 0 and d in diff_counter and diff_counter[d] >= count:
                    base_period = d
                    is_harmonic = True

            confidence = min(0.95, count / (len(years) / base_period + 1) * 2)
            results.append((base_period, round(confidence, 2), count))
            seen.add(diff)
            if is_harmonic:
                seen.add(base_period)

        results.sort(key=lambda x: (-x[1], -x[2]))
        return results[:5]

    @staticmethod
    def find_multi_scale_periods(years: List[int]) -> Dict[str, List[Tuple[int, float, int]]]:
        """Находит периоды на разных временных масштабах"""
        return {
            "short": SpectralAnalyzer.find_periods(years, 2, 15),
            "medium": SpectralAnalyzer.find_periods(years, 10, 50),
            "long": SpectralAnalyzer.find_periods(years, 30, 120),
        }

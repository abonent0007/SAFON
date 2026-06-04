"""
Модуль автоматического обогащения исторической базы через поиск в интернете
Источники: DuckDuckGo + Wikipedia API — бесплатно, без API-ключей
Асинхронный многопоточный режим для максимальной скорости
"""
import re
import time
import random
import json
import requests
import threading
from datetime import datetime
from typing import List, Dict, Optional
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class HistoryEnricher:
    """Автоматический поиск исторических событий по циклическим паттернам"""

    WIKI_SEARCH_QUERIES = {
        "землетрясение": ["{year} earthquake", "earthquakes in {year}"],
        "цунами": ["{year} tsunami", "tsunamis in {year}"],
        "наводнение": ["{year} flood", "floods in {year}"],
        "пожар": ["{year} wildfire", "great fire of {year}"],
        "ураган": ["{year} hurricane", "typhoon {year}"],
        "экономический кризис": ["{year} financial crisis", "panic of {year}"],
        "война": ["{year} war", "battle of {year}"],
        "эпидемия": ["{year} plague", "pandemic {year}"],
        "революция": ["{year} revolution", "revolt of {year}"],
        "засуха": ["{year} famine", "drought in {year}"],
        "экологическая катастрофа": ["{year} oil spill", "nuclear accident {year}"],
    }

    DDG_TEMPLATES = {
        "землетрясение": [
            "major earthquake {year} magnitude",
            "earthquake {year} history casualties",
        ],
        "цунами": ["tsunami {year} disaster", "tsunami {year} Indian Ocean Pacific"],
        "наводнение": ["major flood {year} disaster", "flood {year} casualties"],
        "пожар": ["great fire {year} disaster", "wildfire {year} acres burned"],
        "ураган": ["hurricane {year} category disaster", "typhoon {year} casualties"],
        "экономический кризис": ["financial crisis {year} recession", "stock market crash {year}"],
        "война": ["war {year} conflict invasion", "battle {year} war conquest"],
        "эпидемия": ["pandemic {year} plague outbreak", "plague epidemic {year}"],
        "революция": ["revolution {year} uprising", "rebellion {year} overthrow"],
        "засуха": ["drought {year} famine", "famine {year} starvation"],
        "экологическая катастрофа": ["environmental disaster {year}", "oil spill nuclear {year}"],
    }

    def __init__(self, db, deepseek_engine=None):
        self.db = db
        self.deepseek = deepseek_engine
        self.found_events = []

    def search_wikipedia(self, query: str, max_results: int = 5) -> List[Dict]:
        try:
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": max_results,
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            return data.get("query", {}).get("search", [])
        except Exception as e:
            _safe_print(f"   ⚠️ Wikipedia search: {e}")
            return []

    def get_wikipedia_extract(self, title: str) -> Optional[str]:
        try:
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "titles": title,
                "format": "json",
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                return page.get("extract", "")
            return None
        except Exception:
            return None

    def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            return results
        except ImportError:
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results))
                return results
            except ImportError:
                return []
        except Exception as e:
            _safe_print(f"   ⚠️ DDG: {e}")
            return []

    def detect_cycle_gaps(self, events: List[Dict], category: str) -> List[int]:
        years = sorted([e['year'] for e in events if e['category'] == category])
        if len(years) < 2:
            return []
        diffs = [years[i + 1] - years[i] for i in range(len(years) - 1)]
        if not diffs:
            return []

        diff_counter = Counter(diffs)
        most_common_diff, count = diff_counter.most_common(1)[0]
        if count < 2 or most_common_diff < 2:
            return []

        cycle_period = most_common_diff
        min_year = min(years)
        missing_years = []
        year = min_year
        while year <= datetime.now().year:
            if year not in years:
                if year >= 500:
                    missing_years.append(year)
            year += cycle_period
        return missing_years

    def _ai_parse_extract(self, text: str, category: str, target_year: int) -> Optional[Dict]:
        if not self.deepseek:
            return None
        system_prompt = (
            "You are a historical data extractor. Extract event information from Wikipedia text.\n"
            "Reply ONLY in JSON: "
            '{"title": "...", "location": "...", "year": 0000, "category": "...", '
            '"magnitude": 0.0-1.0, "found": true/false}\n'
            'If no relevant event found, return {"found": false}.'
        )
        prompt = (
            f"Find a {category} event in {target_year} from this text:\n"
            f"{text[:2000]}\n\n"
            f"If found, extract title, location, and rate magnitude 0-1."
        )
        try:
            response = self.deepseek.generate(prompt, system_prompt, max_tokens=300)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if data.get('found'):
                    data['year'] = target_year
                    data['category'] = category
                    data['source'] = 'wikipedia'
                    data['source_confidence'] = 0.85
                    return data
        except Exception:
            pass
        return None

    def enrich_from_wikipedia(self, category: str, gap_year: int) -> Optional[Dict]:
        queries = self.WIKI_SEARCH_QUERIES.get(category, [f"{category} {gap_year}"])
        for query_template in queries:
            query = query_template.format(year=gap_year)
            results = self.search_wikipedia(query, max_results=3)
            for result in results:
                title = result.get("title", "")
                if not title or "List of" in title or "Category:" in title:
                    continue
                extract = self.get_wikipedia_extract(title)
                if not extract or len(extract) < 50:
                    continue
                if str(gap_year) not in extract and str(gap_year - 1) not in extract:
                    continue

                parsed = self._ai_parse_extract(extract, category, gap_year)
                if parsed:
                    parsed['title'] = title
                    return parsed

                # Fallback: basic extraction without AI
                return {
                    'title': title,
                    'location': 'глобально',
                    'year': gap_year,
                    'category': category,
                    'magnitude': 0.5,
                    'importance_score': 0.5,
                    'source': 'wikipedia',
                    'source_confidence': 0.7,
                }
            time.sleep(0.5)
        return None

    def _store_event(self, data: Dict) -> bool:
        event_id = self.db.add_event(
            title=data.get('title', f'{data.get("category")} {data.get("year")}'),
            description=str(data.get('title', '')),
            year=data['year'],
            location=data.get('location', 'глобально'),
            category=data['category'],
            magnitude=data.get('magnitude', 0.5),
            importance_score=data.get('importance_score', 0.5),
            source=data.get('source', 'enrichment'),
            source_confidence=data.get('source_confidence', 0.5),
        )
        if event_id:
            self.found_events.append(data)
            _safe_print(f"      + {data['year']}: {data.get('title', str(data['year']))}")
            return True
        return False

    def enrich_category(self, category: str, max_searches: int = 20) -> int:
        events = self.db.get_all_events()
        gaps = self.detect_cycle_gaps(events, category)

        if not gaps:
            _safe_print(f"   {category}: недостаточно данных для циклов — поиск по десятилетиям...")
            cat_events = sorted([e['year'] for e in events if e['category'] == category])
            if cat_events:
                min_y, max_y = min(cat_events), max(cat_events)
                gaps = list(range(max(min_y, 500), min(max_y, 2020), random.randint(15, 25)))
            else:
                gaps = list(range(1500, 2020, 20))

        gaps = [g for g in gaps if 500 <= g <= 2020]
        _safe_print(f"   {category}: поиск по {min(max_searches, len(gaps))} из {len(gaps)} пробелов...")

        added = 0
        searched = 0
        for gap_year in sorted(gaps, reverse=True):
            if searched >= max_searches:
                break
            searched += 1

            # 1. Wikipedia first (more reliable)
            wiki_data = self.enrich_from_wikipedia(category, gap_year)
            if wiki_data:
                if self._store_event(wiki_data):
                    added += 1
                    time.sleep(random.uniform(2.0, 4.0))
                    continue

            # 2. DuckDuckGo fallback
            templates = self.DDG_TEMPLATES.get(category, [f"{category} {gap_year} history"])
            query = random.choice(templates).format(year=gap_year)
            results = self.search_duckduckgo(query, max_results=3)
            if results:
                combined = " ".join([r.get('body', '') or r.get('snippet', '') for r in results[:3]])[:2000]
                parsed = self._ai_parse_extract(combined, category, gap_year)
                if parsed:
                    parsed['source'] = 'duckduckgo'
                    parsed['source_confidence'] = 0.6
                    if self._store_event(parsed):
                        added += 1
                        continue
                else:
                    ddg_data = {
                        'title': f"{category.capitalize()} {gap_year}",
                        'location': 'глобально',
                        'year': gap_year,
                        'category': category,
                        'magnitude': 0.5,
                        'importance_score': 0.5,
                        'source': 'duckduckgo',
                        'source_confidence': 0.5,
                    }
                    if self._store_event(ddg_data):
                        added += 1

            time.sleep(random.uniform(2.0, 4.0))

        return added

    def enrich_all(self, max_per_category: int = 20, workers: int = 6) -> Dict:
        self.found_events = []
        _safe_print(f"\n🌐 АВТОМАТИЧЕСКОЕ ОБОГАЩЕНИЕ БАЗЫ (многопоточно: {workers} потоков)")
        _safe_print("=" * 60)
        _safe_print("Источники: Wikipedia API + DuckDuckGo\n")

        categories = list(self.WIKI_SEARCH_QUERIES.keys())
        total_added = 0
        summary = {}
        lock = threading.Lock()

        def enrich_one(category):
            added = self.enrich_category(category, max_searches=max_per_category)
            with lock:
                summary[category] = added
            return added

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(enrich_one, cat): cat for cat in categories}
            for future in as_completed(futures):
                cat = futures[future]
                try:
                    added = future.result()
                    with lock:
                        total_added += added
                except Exception as e:
                    _safe_print(f"   ⚠️ {cat}: ошибка потока — {e}")

        _safe_print(f"\n✅ Обогащение завершено. Добавлено {total_added} событий.")
        return {'total_added': total_added, 'by_category': summary, 'events': self.found_events}

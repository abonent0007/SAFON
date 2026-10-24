# -*- coding: utf-8 -*-
"""One-time bootstrap tool (уже выполнено): вынесение констант из кода в config/*.json.
После рефакторинга core.database больше не экспортирует LOCATION_COORDS/EVENT_CATEGORIES —
скрипт хранится как исторический артефакт миграции и повторно не запускается."""
import sys
import os
import json
import sqlite3
from datetime import datetime

getattr(sys.stdout, "reconfigure")(encoding="utf-8")
ROOT = r"C:\Users\User\Documents\SAFON"
sys.path.insert(0, ROOT)

from core.database import LOCATION_COORDS, EVENT_CATEGORIES  # noqa: E402
from core.predictor import PredictionEngine  # noqa: E402
from core.deepseek_engine import DeepSeekEngine  # noqa: E402
from core.history_enricher import HistoryEnricher  # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)

SHAPES = {
    "землетрясение": "polygon", "цунами": "wave", "наводнение": "drop",
    "пожар": "triangle", "ураган": "spiral", "экономический кризис": "diamond",
    "война": "hexagon", "эпидемия": "cross", "засуха": "square",
    "революция": "star", "экологическая катастрофа": "octagon",
}

SEASONAL = {
    "землетрясение": [1, 2, 3, 11, 12], "цунами": [1, 2, 3, 11, 12],
    "наводнение": [6, 7, 8, 9], "пожар": [7, 8, 9], "ураган": [8, 9, 10],
    "экономический кризис": [9, 10], "война": [3, 4, 5, 6],
    "эпидемия": [1, 2, 11, 12], "революция": [3, 4, 5, 10],
    "засуха": [6, 7, 8], "экологическая катастрофа": [5, 6, 7, 8],
}

# --- engine instance without db/network (api mode, no key => no checks) ---
eng = PredictionEngine(db=None, analyzer=None)
ds = DeepSeekEngine({"DEEPSEEK_MODE": "api", "DEEPSEEK_API_KEY": ""})

year_now = str(datetime.now().year)
current_contexts = {}
for cat in EVENT_CATEGORIES.keys():
    ctx = ds.get_current_context(cat)
    current_contexts[cat] = ctx.replace(year_now, "{year}")

categories = {}
for cat, meta in EVENT_CATEGORIES.items():
    categories[cat] = {
        "color": meta.get("color", "#00d4ff"),
        "icon": meta.get("icon", "📌"),
        "importance": meta.get("importance", 0.8),
        "shape": SHAPES.get(cat, "circle"),
    }

config = {
    "version": 1,
    "categories": categories,
    "locations": dict(LOCATION_COORDS),
    "cycles": json.loads(json.dumps(eng.cycles)),
    "descriptions": dict(eng.descriptions),
    "seasonal_months": SEASONAL,
    "current_contexts": current_contexts,
    "enrichment": {
        "wiki_queries": json.loads(json.dumps(HistoryEnricher.WIKI_SEARCH_QUERIES)),
        "ddg_templates": json.loads(json.dumps(HistoryEnricher.DDG_TEMPLATES)),
    },
}

cfg_path = os.path.join(CONFIG_DIR, "safon_config.json")
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=1)
print("CONFIG SAVED:", cfg_path)
print("  categories:", len(config["categories"]))
print("  locations:", len(config["locations"]))
print("  cycles:", len(config["cycles"]))
print("  descriptions:", len(config["descriptions"]))
print("  contexts:", len(config["current_contexts"]),
      "| with {year}:", sum(1 for v in current_contexts.values() if "{year}" in v))

# --- seed events (source='historical') ---
db = sqlite3.connect("file:%s?mode=ro" % os.path.join(ROOT, "data", "safon.db").replace("\\", "/"), uri=True)
db.row_factory = sqlite3.Row
rows = [dict(r) for r in db.execute(
    "SELECT title, description, year, month, day, location, category, subcategory, "
    "magnitude, importance_score, source, source_confidence, causes, effects, causal_delay "
    "FROM events WHERE source = 'historical' ORDER BY id")]
db.close()

seed = []
for r in rows:
    def _dec(v):
        try:
            return json.loads(v) if v else []
        except Exception:
            return []
    seed.append({
        "title": r["title"], "description": r["description"], "year": r["year"],
        "month": r["month"], "day": r["day"], "location": r["location"],
        "category": r["category"], "subcategory": r["subcategory"] or "",
        "magnitude": r["magnitude"], "importance_score": r["importance_score"],
        "source": r["source"], "source_confidence": r["source_confidence"],
        "causes": _dec(r["causes"]), "effects": _dec(r["effects"]),
        "causal_delay": r["causal_delay"],
    })

seed_path = os.path.join(CONFIG_DIR, "seed_events.json")
with open(seed_path, "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)
print("SEED SAVED:", seed_path, "| events:", len(seed))
print("DONE")

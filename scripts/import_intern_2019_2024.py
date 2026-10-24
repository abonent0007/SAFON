# -*- coding: utf-8 -*-
"""Append-only импорт батча InternLM (2019-2024, 76 событий) в data/safon.db.

Источник: сохранённый вывод браузера (tool-output файл).
Ничего не удаляется и не перезаписывается: только INSERT через SafonDatabase.add_event.
Дедупликация: точный hash (title|year|category) + схожесть названий (>=0.7) в той же категории/году.
"""
import sys
import os
import json
import hashlib
import sqlite3

getattr(sys.stdout, "reconfigure")(encoding="utf-8")
sys.path.insert(0, r"C:\Users\User\Documents\SAFON")

from difflib import SequenceMatcher  # noqa: E402
from core.database import SafonDatabase  # noqa: E402

SRC = r"C:\Users\User\.local\share\opencode\tool-output\tool_13a92c5e3001GmYcoSrc8ijBe2"
DB = r"C:\Users\User\Documents\SAFON\data\safon.db"
CLEAN = r"C:\Users\User\Documents\SAFON\data\import_intern_2019_2024.json"

# ---------- 1. Извлечение ----------
raw = open(SRC, encoding="utf-8", errors="replace").read()
marker = "### Result\n"
i = raw.find(marker) + len(marker)
obj, _ = json.JSONDecoder().raw_decode(raw, i)
events = json.loads(obj)
print("DECODED:", len(events))

# ---------- 2. Точечные правки (задокументированы в отчёте) ----------
EXCLUDE = {"Ураган Майорк"}  # выдуманное событие (такого урагана не существует)

DATE_FIX = {
    "Атака на нефтяные объекты Саудовской Аравии": (9, 14),  # реальная дата Абкайк/Хурайс
    "Наводнение в ЮАР": (4, 11),          # Квазулу-Натал, апрель 2022
    "Вспышка оспы обезьян": (7, 23),      # дата объявления ЧС ВОЗ
    "Ураган Айота": (11, 16),             # выход на сушу (не 04.11, как у Этты)
}

TEXT_FIX = [
    ("intervenir", "вмешаться"),
    ("覆盖了 ", "охватили "),
    ("影响了 ", "повлияла на "),
    ("оффензива", "наступление"),
    ("Огрон", "Орегон"),
    ("луизиану", "Луизиану"),
    ("КваЗулу-Натал", "Квазулу-Натал"),
]

patched, excluded = [], []
for ev in events:
    if ev["title"] in EXCLUDE:
        excluded.append(ev["title"])
        continue
    if ev["title"] in DATE_FIX:
        m, d = DATE_FIX[ev["title"]]
        print("DATEFIX: %s  %d-%02d -> %d-%02d" % (ev["title"], ev["month"], ev["day"], m, d))
        ev["month"], ev["day"] = m, d
    for a, b in TEXT_FIX:
        if a in ev.get("description", ""):
            ev["description"] = ev["description"].replace(a, b)
            print("TEXTFIX in:", ev["title"])
        for f in ("causes", "effects"):
            if isinstance(ev.get(f), list):
                ev[f] = [x.replace(a, b) if isinstance(x, str) else x for x in ev[f]]
    patched.append(ev)
print("PATCHED:", len(patched), "| EXCLUDED:", excluded)

with open(CLEAN, "w", encoding="utf-8") as f:
    json.dump(patched, f, ensure_ascii=False, indent=1)
print("SAVED CLEAN COPY:", CLEAN)

# ---------- 3. Дедупликация (только чтение) ----------
ro = sqlite3.connect("file:%s?mode=ro" % DB.replace("\\", "/"), uri=True)
ro.row_factory = sqlite3.Row
rows = [dict(r) for r in ro.execute("SELECT id,title,year,category,hash FROM events").fetchall()]
byhash = set(r["hash"] for r in rows)
bycy = {}
for r in rows:
    bycy.setdefault((r["category"], r["year"]), []).append(r)


def norm(s):
    return " ".join((s or "").casefold().split())


def dup_reason(ev):
    h = hashlib.md5(("%s|%s|%s" % (ev["title"], ev["year"], ev["category"])).encode()).hexdigest()
    if h in byhash:
        return "hash-exact"
    for r in bycy.get((ev["category"], ev["year"]), []):
        t1, t2 = norm(ev["title"]), norm(r["title"])
        if t1 == t2:
            return "id%d exact" % r["id"]
        if SequenceMatcher(None, t1, t2).ratio() >= 0.7:
            return "id%d sim" % r["id"]
    return None


to_add = []
for ev in patched:
    d = dup_reason(ev)
    if d:
        print("SKIP-DUP: %s | %s" % (ev["title"], d))
    else:
        to_add.append(ev)
print("TO_ADD:", len(to_add))
ro.close()

# ---------- 4. Append-only вставка ----------
db = SafonDatabase(db_path=DB)
assert db.conn is not None
before = db.conn.execute("SELECT COUNT(*) c FROM events").fetchone()[0]

added, failed = [], []
for ev in to_add:
    try:
        res = db.add_event(
            title=ev["title"],
            description=ev["description"],
            year=ev["year"],
            month=ev["month"],
            day=ev["day"],
            location=ev["location"],
            category=ev["category"],
            subcategory=ev.get("subcategory", ""),
            magnitude=ev.get("magnitude", 0.5),
            importance_score=ev.get("importance_score", 0.5),
            source=ev.get("source", "llm-import"),
            source_confidence=ev.get("source_confidence", 0.7),
            causes=ev.get("causes", []),
            effects=ev.get("effects", []),
            causal_delay=ev.get("causal_delay", 2),
        )
    except Exception as e:  # noqa: BLE001
        failed.append((ev["title"], str(e)))
        continue
    if res:
        added.append((res, ev["title"], "%d-%02d" % (ev["year"], ev["month"])))
    else:
        failed.append((ev["title"], "duplicate-hash"))

after = db.conn.execute("SELECT COUNT(*) c FROM events").fetchone()[0]
print("DB COUNT: %d -> %d | ADDED: %d | FAILED: %d" % (before, after, len(added), len(failed)))
if failed:
    for t, e in failed:
        print("  FAILED:", t, "|", e)

# ---------- 5. Проверка результата ----------
print("ANCHORS (max year per category after import):")
for r in db.conn.execute("SELECT category, MAX(year) m, COUNT(*) c FROM events GROUP BY category ORDER BY category"):
    print("  %-26s max=%s n=%d" % (r[0], r[1], r[2]))

print("LAST 5 INSERTED:")
for r in db.conn.execute("SELECT id,title,year,month,location,category FROM events ORDER BY id DESC LIMIT 5"):
    print("  #%s %s (%d-%02d, %s) [%s]" % (r[0], r[1], r[2], r[3], r[4], r[5]))

db.close()
print("DONE")

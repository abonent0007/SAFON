# -*- coding: utf-8 -*-
"""Remove stale (pre-today) predictions. Events table untouched. Predictions are derived data."""
import sys
from datetime import datetime

getattr(sys.stdout, "reconfigure")(encoding="utf-8")
sys.path.insert(0, r"C:\Users\User\Documents\SAFON")

from core.database import SafonDatabase  # noqa: E402

db = SafonDatabase(db_path=r"C:\Users\User\Documents\SAFON\data\safon.db")
assert db.conn is not None
ts = datetime.now().strftime("%Y-%m-%d 00:00:00")

before = db.conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
db.conn.execute("DELETE FROM predictions WHERE made_at < ?", (ts,))
db.conn.commit()
after = db.conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

active = db.conn.execute(
    "SELECT COUNT(*) FROM predictions WHERE predicted_year >= ?",
    (datetime.now().year - 5,),
).fetchone()[0]

total_events = db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
new_events = db.conn.execute("SELECT COUNT(*) FROM events WHERE id > 2696").fetchone()[0]

print("PREDICTIONS: %d -> %d (removed stale: %d) | active: %d" % (before, after, before - after, active))
print("EVENTS: total=%d | imported_today=%d" % (total_events, new_events))
print("SAMPLE NEW EVENTS:")
for r in db.conn.execute(
    "SELECT id, title, year, month, day, category, location, source_confidence "
    "FROM events WHERE id > 2696 ORDER BY id LIMIT 6"
):
    print("  #%d %d-%02d-%02d %s | %s | %s | conf=%s" % (r[0], r[2], r[3], r[4], r[1], r[5], r[6], r[7]))
db.close()
print("DONE")

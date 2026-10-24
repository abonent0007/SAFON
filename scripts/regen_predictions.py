# -*- coding: utf-8 -*-
"""Regenerate predictions with the multi-method ensemble.
Predictions are derived data: cleared and rebuilt from the current events DB."""
import sys

getattr(sys.stdout, "reconfigure")(encoding="utf-8")
sys.path.insert(0, r"C:\Users\User\Documents\SAFON")

from core.database import SafonDatabase  # noqa: E402
from core.predictor import PredictionEngine  # noqa: E402

db = SafonDatabase(db_path=r"C:\Users\User\Documents\SAFON\data\safon.db")
assert db.conn is not None

db.conn.execute("DELETE FROM predictions")
db.conn.commit()

eng = PredictionEngine(db, analyzer=None)
preds = eng.generate_predictions(horizon=80, use_astrometry=False, use_ai=False)

active = db.get_active_predictions()
imp = db.get_important_predictions(0.70)
print("GENERATED:", len(preds), "| ACTIVE:", len(active), "| IMPORTANT>=70%%:", len(imp))
print("SAMPLE (>=70%):")
for x in imp[:6]:
    print("  %.0f%% | %d-%02d | %s | %s" % (
        x["probability"] * 100, x["predicted_year"], x["predicted_month"] or 0,
        x["category"], x["location"]))
print("REASONING SAMPLE:")
for x in imp[:2]:
    print("  [%s %d] %s" % (x["category"], x["predicted_year"], (x["reasoning"] or "")[:420]))
db.close()
print("DONE")

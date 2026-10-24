# -*- coding: utf-8 -*-
"""Run the walk-forward backtest and print metrics (accuracy + Brier)."""
import sys

getattr(sys.stdout, "reconfigure")(encoding="utf-8")
sys.path.insert(0, r"C:\Users\User\Documents\SAFON")

from core.database import SafonDatabase  # noqa: E402
from core.predictor import PredictionEngine  # noqa: E402

db = SafonDatabase(db_path=r"C:\Users\User\Documents\SAFON\data\safon.db")
assert db.conn is not None

eng = PredictionEngine(db, analyzer=None)
res = eng.run_backtest(from_year=1990)

print("TOTAL: %.0f%% | YEAR+-1: %.0f%% | LOCATION: %.0f%% | BRIER: %s | CHECKS: %d" % (
    res["total_accuracy"] * 100, res["year_hit_rate"] * 100,
    res["location_hit_rate"] * 100, res["brier_score"], res["total_checks"]))
print("BY CATEGORY (accuracy | lift):")
for c, d in sorted(res["by_category"].items(), key=lambda x: -(x[1].get("lift") or 0)):
    print("  %-26s %5.0f%%  (%d/%d)  lift=%sx" % (
        c, d["accuracy"] * 100, d["hits"], d["total"], d.get("lift")))
db.close()
print("DONE")

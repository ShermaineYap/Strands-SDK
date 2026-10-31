"""Eval 1 - deterministic classification against real JPS thresholds.

Cases are hand-specified *positions relative to a threshold* (just below, exactly
at, just above) on every Kelantan station whose published thresholds are valid,
plus every data fault present in the live table captured 2026-11-01 00:45 MYT.
The expected label comes from the position, not from the classifier.

    python -m evals.eval_classify
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from jagasungai.classify import classify_station, thresholds_valid
from jagasungai.models import Band, DataQuality
from jagasungai.scenarios import BASE_TIME, base_stations

TAKEN = BASE_TIME + timedelta(minutes=5)


def cases() -> list[dict]:
    out = []
    stations = base_stations()
    valid = [s for s in stations if thresholds_valid(s)[0]]
    for s in valid[:8]:
        positions = [
            ("well below Waspada", s.waspada_m - 1.0, Band.NORMAL),
            ("1 cm below Waspada", s.waspada_m - 0.01, Band.NORMAL),
            ("exactly Waspada", s.waspada_m, Band.WASPADA),
            ("1 cm below Amaran", s.amaran_m - 0.01, Band.WASPADA),
            ("exactly Amaran", s.amaran_m, Band.AMARAN),
            ("1 cm below Bahaya", s.bahaya_m - 0.01, Band.AMARAN),
            ("exactly Bahaya", s.bahaya_m, Band.BAHAYA),
            ("1 m above Bahaya", s.bahaya_m + 1.0, Band.BAHAYA),
        ]
        for label, level, band in positions:
            r = s.model_copy(update={"level_m": round(level, 2)})
            out.append({"case": f"{s.station_id} {label}", "reading": r, "expect_band": band,
                        "expect_quality": DataQuality.OK})
    # every real data fault in the captured table
    for s in stations:
        ok, _ = thresholds_valid(s)
        if s.level_m is not None and s.level_m <= -9000:
            out.append({"case": f"{s.station_id} live sensor fault {s.level_m}", "reading": s,
                        "expect_band": Band.UNKNOWN, "expect_quality": DataQuality.SENSOR_FAULT})
        elif not ok:
            out.append({"case": f"{s.station_id} live placeholder thresholds", "reading": s,
                        "expect_band": Band.UNKNOWN, "expect_quality": DataQuality.NO_THRESHOLD})
    # synthetic faults
    good = valid[0]
    out.append({"case": "stale reading (3 h old)",
                "reading": good.model_copy(update={"observed_at": TAKEN - timedelta(hours=3)}),
                "expect_band": Band.UNKNOWN, "expect_quality": DataQuality.STALE})
    out.append({"case": "missing timestamp", "reading": good.model_copy(update={"observed_at": None}),
                "expect_band": Band.UNKNOWN, "expect_quality": DataQuality.STALE})
    out.append({"case": "blank level", "reading": good.model_copy(update={"level_m": None}),
                "expect_band": Band.UNKNOWN, "expect_quality": DataQuality.SENSOR_FAULT})
    out.append({"case": "thresholds out of order",
                "reading": good.model_copy(update={"amaran_m": good.waspada_m - 1}),
                "expect_band": Band.UNKNOWN, "expect_quality": DataQuality.NO_THRESHOLD})
    out.append({"case": "station missing from page", "reading": None,
                "expect_band": Band.UNKNOWN, "expect_quality": DataQuality.MISSING})
    return out


def run() -> dict:
    rows, passed = [], 0
    for c in cases():
        r = c["reading"]
        if r is not None and r.observed_at is not None and "stale" not in c["case"]:
            r = r.model_copy(update={"observed_at": BASE_TIME})
        st = classify_station(r, "X" if r is None else r.station_id, TAKEN)
        ok = st.band == c["expect_band"] and st.quality == c["expect_quality"]
        passed += ok
        rows.append({"case": c["case"], "expect": f"{c['expect_band'].name}/{c['expect_quality'].name}",
                     "got": f"{st.band.name}/{st.quality.name}", "pass": ok})
    return {"name": "classification", "passed": passed, "total": len(rows), "rows": rows}


if __name__ == "__main__":
    res = run()
    for r in res["rows"]:
        if not r["pass"]:
            print("FAIL", r)
    print(json.dumps({k: res[k] for k in ("name", "passed", "total")}))

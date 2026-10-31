"""Synthetic scenarios built on top of a real captured InfoBanjir table.

The base table (station IDs, names, thresholds, data faults) is the live
Kelantan page captured 2026-11-01 00:45 MYT. Only water levels and timestamps
are changed, so every scenario uses real JPS thresholds.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .models import Snapshot, StationReading
from .sources import infobanjir

ROOT = Path(__file__).resolve().parent.parent
BASE_WATER = ROOT / "fixtures/live/waterlevel_Kelantan_20261101T0045.html"
BASE_RAIN = ROOT / "fixtures/live/rainfall_Kelantan_20261101T0045.html"
BASE_TIME = datetime(2026, 11, 1, 0, 45)


def base_stations() -> list[StationReading]:
    return infobanjir.load_fixture_water(BASE_WATER)


def live_snapshot() -> Snapshot:
    """Exactly what InfoBanjir showed at capture time."""
    return Snapshot(
        taken_at=BASE_TIME + timedelta(minutes=5),
        state="Kelantan",
        stations=base_stations(),
        rain=infobanjir.load_fixture_rain(BASE_RAIN),
        source_urls=[infobanjir.WATER_URL.format(state="Kelantan")],
    )


def with_levels(levels: dict[str, float | None], at: datetime, stations: list[StationReading] | None = None,
                state: str = "Kelantan") -> Snapshot:
    """Copy the base table, set some levels, stamp every row with ``at``."""
    out = []
    for s in stations or base_stations():
        s = s.model_copy()
        s.observed_at = at
        if s.station_id in levels:
            s.level_m = levels[s.station_id]
        out.append(s)
    return Snapshot(taken_at=at + timedelta(minutes=5), state=state, stations=out)


def rising_galas(hours: int = 48, step_min: int = 15, start: datetime | None = None) -> list[Snapshot]:
    """48 h of 15-minute snapshots: Sg. Galas at Kg. Lembaga and Limau Kasturi rise
    through Waspada and Amaran into Bahaya, then fall. Smooth piecewise-linear profile."""
    start = start or datetime(2026, 11, 3, 0, 0)
    n = hours * 60 // step_min
    snaps = []
    # Kg. Lembaga thresholds 83.70 / 85.60 / 87.90; Limau Kasturi 56.00 / 60.00 / 61.00
    for i in range(n):
        t = i / (n - 1)
        # quiet for the first 30%, rise to a peak at 70%, recede after
        if t < 0.30:
            f = 0.0
        elif t < 0.70:
            f = (t - 0.30) / 0.40
        else:
            f = max(0.0, 1 - (t - 0.70) / 0.30)
        lembaga = round(82.97 + f * (88.20 - 82.97), 2)
        kasturi = round(54.14 + f * (61.30 - 54.14), 2)
        snaps.append(with_levels({"0730851WL(L)": lembaga, "5020401": kasturi},
                                 start + timedelta(minutes=i * step_min)))
    return snaps

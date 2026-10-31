"""Deterministic classification against official JPS thresholds.

No model is involved anywhere in this file. Its outputs are the only facts the
brief writer may state, and the verifier checks the brief against them.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .actions import FORBIDDEN_PHRASES
from .models import (
    Assessment,
    Band,
    DataQuality,
    MetWarning,
    RainReading,
    Snapshot,
    StationReading,
    StationState,
    Trigger,
)
from .profile import Profile

PLACEHOLDER_THRESHOLD_M = 300.0  # JPS fills missing thresholds with 310/315/320 m
SENTINEL_MAX = -9000.0  # JPS publishes -9999.00 for a faulty sensor
NAME_RE = re.compile(r"^[A-Za-z0-9 .,'()&/-]{3,60}$")


def safe_name(name: str, station_id: str) -> tuple[str, str]:
    """Scraped station names reach the model and the message, so they are untrusted.
    Anything unusual is replaced by the station ID."""
    low = name.lower()
    if not NAME_RE.match(name) or any(p in low for p in FORBIDDEN_PHRASES) or \
            any(w in low for w in ("ignore", "instruction", "abaikan", "arahan", "system", "prompt")):
        return station_id, "station name withheld (unexpected text)"
    return name, ""


def thresholds_valid(r: StationReading) -> tuple[bool, str]:
    t = [r.waspada_m, r.amaran_m, r.bahaya_m]
    if any(v is None for v in t):
        return False, "threshold missing"
    if any(v >= PLACEHOLDER_THRESHOLD_M for v in t):  # type: ignore[operator]
        return False, f"placeholder thresholds {t[0]:.2f}/{t[1]:.2f}/{t[2]:.2f} m"
    if not (t[0] < t[1] < t[2]):  # type: ignore[operator]
        return False, "thresholds not increasing"
    return True, ""


def band_for(level: float, r: StationReading) -> Band:
    if level >= r.bahaya_m:  # type: ignore[operator]
        return Band.BAHAYA
    if level >= r.amaran_m:  # type: ignore[operator]
        return Band.AMARAN
    if level >= r.waspada_m:  # type: ignore[operator]
        return Band.WASPADA
    return Band.NORMAL


def _threshold_for(band: Band, r: StationReading) -> float | None:
    return {Band.WASPADA: r.waspada_m, Band.AMARAN: r.amaran_m, Band.BAHAYA: r.bahaya_m}.get(band)


def classify_station(
    r: StationReading | None,
    station_id: str,
    taken_at: datetime,
    previous: StationReading | None = None,
    previous_band: Band | None = None,
    stale_after_minutes: int = 90,
) -> StationState:
    if r is None:
        return StationState(
            station_id=station_id,
            name=station_id,
            district="",
            observed_at=None,
            level_m=None,
            band=Band.UNKNOWN,
            previous_band=previous_band,
            quality=DataQuality.MISSING,
            quality_note="station not on the page",
        )

    name, name_note = safe_name(r.name, r.station_id)
    base = dict(
        station_id=r.station_id,
        name=name,
        district=r.district,
        observed_at=r.observed_at,
        previous_band=previous_band,
    )

    if r.level_m is None or r.level_m <= SENTINEL_MAX:
        return StationState(**base, level_m=None, band=Band.UNKNOWN, quality=DataQuality.SENSOR_FAULT,
                            quality_note=f"sensor fault (reported {r.level_m})")

    if r.observed_at is None or taken_at - r.observed_at > timedelta(minutes=stale_after_minutes):
        return StationState(**base, level_m=r.level_m, band=Band.UNKNOWN, quality=DataQuality.STALE,
                            quality_note=f"last reading {r.observed_at:%d/%m %H:%M}" if r.observed_at else "no timestamp")

    ok, why = thresholds_valid(r)
    if not ok:
        return StationState(**base, level_m=r.level_m, band=Band.UNKNOWN, quality=DataQuality.NO_THRESHOLD,
                            quality_note=why)

    band = band_for(r.level_m, r)
    thresholds = {"waspada": r.waspada_m, "amaran": r.amaran_m, "bahaya": r.bahaya_m}  # type: ignore[dict-item]
    next_band = Band(band + 1) if band < Band.BAHAYA else None
    to_next = round(_threshold_for(next_band, r) - r.level_m, 2) if next_band else None  # type: ignore[operator]

    rate = None
    if previous is not None and previous.level_m is not None and previous.level_m > SENTINEL_MAX \
            and previous.observed_at and r.observed_at and r.observed_at > previous.observed_at:
        hours = (r.observed_at - previous.observed_at).total_seconds() / 3600
        rate = round((r.level_m - previous.level_m) / hours, 2)

    return StationState(
        **base,
        level_m=r.level_m,
        band=band,
        quality=DataQuality.OK,
        quality_note=name_note,
        thresholds=thresholds,
        next_band=next_band,
        metres_to_next_band=to_next,
        rate_m_per_h=rate,
    )


def rain_warnings(warnings: list[MetWarning], keywords: list[str]) -> list[MetWarning]:
    kws = [k.lower() for k in keywords]
    return [
        w for w in warnings
        if w.mentions_area and any(k in f"{w.title_en} {w.title_ms}".lower() for k in kws)
    ]


def assess(
    snapshot: Snapshot,
    profile: Profile,
    previous: Snapshot | None = None,
    memory: dict | None = None,
) -> Assessment:
    """Classify every watched station and decide whether a brief is needed.

    ``memory`` is the per-community record kept between runs:
    ``{"last_bands": {station_id: int}, "last_sent_at": iso, "last_max_band": int}``.
    """
    memory = memory or {}
    last_bands = {k: Band(v) for k, v in (memory.get("last_bands") or {}).items()}
    by_id = {r.station_id: r for r in snapshot.stations}
    prev_by_id = {r.station_id: r for r in previous.stations} if previous else {}

    states = [
        classify_station(
            by_id.get(sid),
            sid,
            snapshot.taken_at,
            previous=prev_by_id.get(sid),
            previous_band=last_bands.get(sid),
            stale_after_minutes=profile.rules.stale_after_minutes,
        )
        for sid in profile.watch_ids
    ]
    known = [s for s in states if s.band != Band.UNKNOWN]
    max_band = max((s.band for s in known), default=Band.UNKNOWN)

    reasons: list[str] = []
    for s in states:
        if s.band_rose:
            reasons.append(f"band_rose:{s.station_id}:{s.previous_band.name}->{s.band.name}")  # type: ignore[union-attr]
        if (
            s.band != Band.UNKNOWN
            and s.rate_m_per_h is not None
            and s.metres_to_next_band is not None
            and s.rate_m_per_h >= profile.rules.fast_rise_m_per_h
            and s.metres_to_next_band <= profile.rules.near_next_band_m
        ):
            reasons.append(f"fast_rise:{s.station_id}:{s.rate_m_per_h}m/h:{s.metres_to_next_band}m_to_{s.next_band.name}")  # type: ignore[union-attr]

    if max_band >= Band.AMARAN:
        last_sent = memory.get("last_sent_at")
        due = True
        if last_sent:
            age = snapshot.taken_at - datetime.fromisoformat(last_sent)
            due = age >= timedelta(minutes=profile.rules.rebrief_after_minutes)
        if due:
            reasons.append(f"high_band:{max_band.name}")

    rw = rain_warnings(snapshot.warnings, profile.rules.rain_warning_keywords)
    if rw and not memory.get("rain_warning_sent_for") == (rw[0].issued.isoformat() if rw[0].issued else rw[0].title_en):
        reasons.append(f"met_rain_warning:{rw[0].title_en}")

    # Same rule the DispatchGuard enforces, applied upstream so the coordinator is never
    # asked to approve a brief that could not be sent: within an hour of the last brief,
    # only an escalation to a higher band triggers a new one.
    suppressed: list[str] = []
    last_sent = memory.get("last_sent_at")
    if reasons and last_sent:
        recent = snapshot.taken_at - datetime.fromisoformat(last_sent) < timedelta(minutes=60)
        escalation = max_band > Band(memory.get("last_max_band", -1))
        if recent and not escalation:
            suppressed, reasons = [f"suppressed:{r}" for r in reasons], []

    rain = {
        r.station_id: r.last_hour_mm
        for r in snapshot.rain
        if r.station_id in profile.rain_watch and r.last_hour_mm is not None
    }

    return Assessment(
        community_id=profile.id,
        community_name=profile.name,
        snapshot_time=snapshot.taken_at,
        states=states,
        max_band=max_band,
        trigger=Trigger(fired=bool(reasons), reasons=reasons or suppressed),
        shelter=profile.nearest_shelter(),
        warnings=rw,
        rain_last_hour_mm=rain,
    )


def memory_after_send(assessment: Assessment, sent_at: datetime, old: dict | None = None) -> dict:
    """The record written after a brief is dispatched."""
    mem = dict(old or {})
    mem["last_bands"] = {s.station_id: int(s.band) for s in assessment.states}
    mem["last_sent_at"] = sent_at.isoformat()
    mem["last_max_band"] = int(assessment.max_band)
    if assessment.warnings:
        w = assessment.warnings[0]
        mem["rain_warning_sent_for"] = w.issued.isoformat() if w.issued else w.title_en
    return mem


def memory_after_quiet_run(assessment: Assessment, old: dict | None = None) -> dict:
    """Bands are remembered every run so 'band rose' compares like with like."""
    mem = dict(old or {})
    mem["last_bands"] = {s.station_id: int(s.band) for s in assessment.states}
    return mem

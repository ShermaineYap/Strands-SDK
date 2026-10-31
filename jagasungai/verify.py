"""Deterministic grounding verifier.

Every number, time, station, band word and shelter name in a ``FloodBrief``
must trace back to the ``Assessment`` produced by code. Anything that does not
is returned to the writer as a precise error; after the retry budget is spent
the graph fails closed to a template brief built only from code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .actions import FORBIDDEN_PHRASES
from .models import Assessment, Band, FloodBrief, StationState

BAND_WORDS: dict[Band, set[str]] = {
    Band.NORMAL: {"normal"},
    Band.WASPADA: {"waspada", "alert"},
    Band.AMARAN: {"amaran", "warning"},
    Band.BAHAYA: {"bahaya", "danger"},
}
ALL_BAND_WORDS = set().union(*BAND_WORDS.values())
NO_DATA_MARKERS = (
    "tiada data", "data tidak", "tidak tersedia", "tidak boleh dipercayai", "rosak", "tiada bacaan",
    "no data", "unavailable", "not available", "fault", "unreliable", "no reading", "missing",
)
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")
RIVER_RE = re.compile(r"\b(?:Sg\.|Sungai)\s*([A-Z][a-zA-Z']+)")
MAX_HEADLINE_WORDS = 20
MAX_LINE_WORDS = 45


@dataclass
class VerifyResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def feedback(self) -> str:
        return "\n".join(f"- {e}" for e in self.errors)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def allowed_numbers(a: Assessment) -> set[float]:
    nums: set[float] = {999.0}  # emergency number may appear
    for s in a.states:
        for v in [s.level_m, s.metres_to_next_band, s.rate_m_per_h, *s.thresholds.values()]:
            if v is not None:
                nums.add(round(float(v), 2))
                nums.add(round(abs(float(v)), 2))
                nums.add(round(float(v), 1))
                nums.add(round(abs(float(v)), 1))
    for v in a.rain_last_hour_mm.values():
        nums.update({round(v, 2), round(v, 1), float(round(v))})
    if a.shelter and a.shelter.distance_km is not None:
        nums.update({round(a.shelter.distance_km, 1), float(round(a.shelter.distance_km))})
    return nums


def allowed_times(a: Assessment) -> set[str]:
    times = {a.snapshot_time.strftime("%H:%M")}
    for s in a.states:
        if s.observed_at:
            times.add(s.observed_at.strftime("%H:%M"))
    for w in a.warnings:
        for t in (w.issued, w.valid_to):
            if t:
                times.add(t.strftime("%H:%M"))
    return times


def allowed_rivers(a: Assessment) -> set[str]:
    rivers = set()
    for s in a.states:
        rivers.update(m.lower() for m in RIVER_RE.findall(s.name))
    return rivers


def _check_text(text: str, where: str, a: Assessment, nums: set[float], times: set[str],
                rivers: set[str], band_ok: set[str], errors: list[str]) -> None:
    low = _norm(text)
    for phrase in FORBIDDEN_PHRASES:
        if phrase in low:
            errors.append(f"{where}: forbidden phrase '{phrase}'")
    if "http" in low or "www." in low:
        errors.append(f"{where}: links are not allowed in model text")

    stripped = text
    for m in TIME_RE.finditer(text):
        hhmm = f"{int(m.group(1)):02d}:{m.group(2)}"
        if hhmm not in times:
            errors.append(f"{where}: time {m.group(0)} is not a reading time ({', '.join(sorted(times))})")
        stripped = stripped.replace(m.group(0), " ")

    ids = {s.station_id for s in a.states}
    for sid in ids:
        stripped = stripped.replace(sid, " ")

    for m in NUM_RE.finditer(stripped):
        val = float(m.group(0).replace(",", "."))
        if round(val, 2) not in nums and round(abs(val), 2) not in nums:
            errors.append(f"{where}: number {m.group(0)} does not appear in the readings")

    for r in RIVER_RE.findall(text):
        if r.lower() not in rivers:
            errors.append(f"{where}: river '{r}' is not one of the watched stations")

    used = _words(text) & ALL_BAND_WORDS
    bad = used - band_ok
    if bad:
        errors.append(f"{where}: band word(s) {sorted(bad)} not supported by the readings (allowed: {sorted(band_ok)})")


BAND_BY_WORD = {w: b for b, ws in BAND_WORDS.items() for w in ws}
# "tahap Amaran", "paras Bahaya", "Warning level", "at Danger": a claim about the CURRENT band.
CLAIM_RES = [
    re.compile(r"\b(?:tahap|paras|status)\s+(normal|waspada|amaran|bahaya)\b", re.I),
    re.compile(r"\b(normal|alert|warning|danger)\s+(?:level|band|status)\b", re.I),
    re.compile(r"\b(?:at|is|now|reached|reaches)\s+(normal|alert|warning|danger)\b", re.I),
]


def band_claims(text: str) -> set[Band]:
    out = set()
    for rx in CLAIM_RES:
        for m in rx.finditer(text):
            out.add(BAND_BY_WORD[m.group(1).lower()])
    return out


def _band_words_for(s: StationState) -> set[str]:
    ok: set[str] = set()
    for b in (s.band, s.previous_band, s.next_band):
        if b is not None and b in BAND_WORDS:
            ok |= BAND_WORDS[b]
    return ok


def verify(brief: FloodBrief, a: Assessment) -> VerifyResult:
    errors: list[str] = []
    nums, times, rivers = allowed_numbers(a), allowed_times(a), allowed_rivers(a)
    by_id = {s.station_id: s for s in a.states}

    # 1. coverage: exactly one line per watched station, no invented stations
    seen: list[str] = []
    for line in brief.stations:
        if line.station_id not in by_id:
            errors.append(f"station {line.station_id!r} is not a watched station ({', '.join(by_id)})")
        seen.append(line.station_id)
    for sid in by_id:
        if seen.count(sid) == 0:
            errors.append(f"station {sid} is missing; every watched station needs one line")
        elif seen.count(sid) > 1:
            errors.append(f"station {sid} appears {seen.count(sid)} times")

    # 2. per-station facts
    for line in brief.stations:
        s = by_id.get(line.station_id)
        if s is None:
            continue
        where = f"station {s.station_id}"
        if line.band != s.band.name:
            errors.append(f"{where}: band {line.band} but classifier says {s.band.name}")
        if s.band == Band.UNKNOWN:
            if line.level_m is not None:
                errors.append(f"{where}: level {line.level_m} given for a station with no usable reading (must be null)")
            for txt, lang in ((line.text_ms, "ms"), (line.text_en, "en")):
                if not any(m in txt.lower() for m in NO_DATA_MARKERS):
                    errors.append(f"{where} ({lang}): must say the data is unavailable, not describe a level")
            band_ok: set[str] = set()
        else:
            if line.level_m is None or s.level_m is None or abs(line.level_m - s.level_m) > 0.005:
                errors.append(f"{where}: level {line.level_m} but reading is {s.level_m}")
            band_ok = _band_words_for(s)
        for txt, lang in ((line.text_ms, "ms"), (line.text_en, "en")):
            wrong = {b for b in band_claims(txt) if b != s.band}
            if wrong:
                errors.append(f"{where} ({lang}): claims {sorted(b.name for b in wrong)} but the station is at {s.band.name}")
            if len(txt.split()) > MAX_LINE_WORDS:
                errors.append(f"{where} ({lang}): too long ({len(txt.split())} words)")
            _check_text(txt, f"{where} ({lang})", a, nums, times, rivers, band_ok, errors)

    # 3. headline and trend: may use band words of any known station
    any_ok: set[str] = set()
    for s in a.states:
        if s.band != Band.UNKNOWN:
            any_ok |= _band_words_for(s)
    if a.warnings:
        any_ok |= {"amaran", "warning"}
    for field_name in ("headline_ms", "headline_en", "trend_ms", "trend_en"):
        txt = getattr(brief, field_name)
        if field_name.startswith("headline") and len(txt.split()) > MAX_HEADLINE_WORDS:
            errors.append(f"{field_name}: too long ({len(txt.split())} words)")
        _check_text(txt, field_name, a, nums, times, rivers, any_ok, errors)

    # 4. headline must not overstate: no band word above the highest known band
    for field_name in ("headline_ms", "headline_en"):
        over = {b for b in band_claims(getattr(brief, field_name)) if b > a.max_band}
        if over:
            errors.append(f"{field_name}: claims {sorted(b.name for b in over)}; highest band is {a.max_band.name}")
    if a.max_band != Band.UNKNOWN:
        higher = set().union(*(BAND_WORDS[b] for b in BAND_WORDS if b > a.max_band)) if a.max_band < Band.BAHAYA else set()
        for field_name in ("headline_ms", "headline_en"):
            over = _words(getattr(brief, field_name)) & higher
            # "amaran"/"warning" may legitimately refer to a MET warning
            if a.warnings:
                over -= {"amaran", "warning"}
            if over:
                errors.append(f"{field_name}: overstates severity with {sorted(over)}; highest band is {a.max_band.name}")

    # 5. reading time
    if brief.reading_time.strip() != a.snapshot_time.strftime("%H:%M"):
        errors.append(f"reading_time {brief.reading_time!r} must be {a.snapshot_time:%H:%M}")

    return VerifyResult(ok=not errors, errors=errors)

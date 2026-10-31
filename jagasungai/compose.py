"""Template brief (fail-closed path) and final message composition.

``template_brief`` builds a FloodBrief from the Assessment with no model at
all. It is used when the writer exhausts its retries, when Bedrock is
unreachable, and as the offline demo writer. ``compose_message`` wraps any
verified brief with code-owned parts: actions, shelter, disclaimer, source.
"""

from __future__ import annotations

from .actions import DISCLAIMER_EN, DISCLAIMER_MS, actions_for
from .models import Assessment, Band, FloodBrief, StationLine, StationState

SOURCE_URL = "https://publicinfobanjir.water.gov.my/waterleveldata/{state}"


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def _line(s: StationState) -> StationLine:
    if s.band == Band.UNKNOWN:
        why_ms = {
            "SENSOR_FAULT": "sensor rosak",
            "NO_THRESHOLD": "tiada paras ambang sah",
            "STALE": "bacaan lama",
            "MISSING": "tiada dalam senarai",
        }[s.quality.name]
        why_en = {
            "SENSOR_FAULT": "sensor fault",
            "NO_THRESHOLD": "no valid thresholds",
            "STALE": "reading is old",
            "MISSING": "not listed",
        }[s.quality.name]
        return StationLine(
            station_id=s.station_id,
            level_m=None,
            band="UNKNOWN",
            text_ms=f"{s.name}: tiada data boleh dipercayai ({why_ms}).",
            text_en=f"{s.name}: no data ({why_en}).",
        )
    ms = f"{s.name}: {_fmt(s.level_m)} m, tahap {s.band.ms}."
    en = f"{s.name}: {_fmt(s.level_m)} m, {s.band.en} level."
    if s.next_band is not None and s.metres_to_next_band is not None:
        ms += f" {_fmt(s.metres_to_next_band)} m lagi ke {s.next_band.ms}."
        en += f" {_fmt(s.metres_to_next_band)} m below {s.next_band.en}."
    if s.rate_m_per_h is not None and s.rate_m_per_h > 0:
        ms += f" Naik {_fmt(s.rate_m_per_h)} m/jam."
        en += f" Rising {_fmt(s.rate_m_per_h)} m/h."
    return StationLine(station_id=s.station_id, level_m=s.level_m, band=s.band.name, text_ms=ms, text_en=en)


def template_brief(a: Assessment) -> FloodBrief:
    known = [s for s in a.states if s.band != Band.UNKNOWN]
    if known:
        top = max(known, key=lambda s: s.band)
        head_ms = f"{a.community_name}: paras tertinggi {top.band.ms} di {top.name}"
        head_en = f"{a.community_name}: highest level {top.band.en} at {top.name}"
    else:
        head_ms = f"{a.community_name}: tiada data tolok boleh dipercayai"
        head_en = f"{a.community_name}: no reliable gauge data"
    return FloodBrief(
        headline_ms=head_ms,
        headline_en=head_en,
        stations=[_line(s) for s in a.states],
        reading_time=a.snapshot_time.strftime("%H:%M"),
    )


def compose_message(brief: FloodBrief, a: Assessment, state: str, language: str = "ms",
                    writer: str = "model") -> str:
    """The exact text a coordinator receives. Code owns everything outside the brief."""
    ms = language != "en"
    lines = [
        f"*JagaSungai · {a.snapshot_time:%d/%m %H:%M}*",
        brief.headline_ms if ms else brief.headline_en,
        "",
    ]
    for st in brief.stations:
        lines.append("• " + (st.text_ms if ms else st.text_en))
    trend = brief.trend_ms if ms else brief.trend_en
    if trend:
        lines += ["", trend]
    lines += ["", "*Tindakan:*" if ms else "*Actions:*"]
    for i, (a_ms, a_en) in enumerate(actions_for(a.max_band), 1):
        lines.append(f"{i}. {a_ms if ms else a_en}")
    if a.shelter and a.max_band >= Band.WASPADA:
        lines += [
            "",
            (f"PPS terdekat (profil): {a.shelter.name}, ~{a.shelter.distance_km} km"
             if ms else f"Nearest relief centre (profile): {a.shelter.name}, ~{a.shelter.distance_km} km"),
        ]
    lines += [
        "",
        DISCLAIMER_MS if ms else DISCLAIMER_EN,
        SOURCE_URL.format(state=state),
    ]
    if writer == "template":
        lines.append("(format ringkas)" if ms else "(short format)")
    return "\n".join(lines)

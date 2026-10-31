"""Typed data shared by every node.

Everything the language model is allowed to talk about is represented here
first, by deterministic code. The model only ever sees these objects and must
return a ``FloodBrief`` that the verifier checks back against them.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field


class Band(IntEnum):
    """JPS flood threshold bands, ordered so comparisons mean 'more severe'.

    ``UNKNOWN`` is deliberately below ``NORMAL`` so that a broken gauge can
    never be mistaken for a rising one, and is never described as normal.
    """

    UNKNOWN = -1
    NORMAL = 0
    WASPADA = 1  # alert
    AMARAN = 2  # warning
    BAHAYA = 3  # danger

    @property
    def ms(self) -> str:
        return {-1: "TIADA DATA", 0: "Normal", 1: "Waspada", 2: "Amaran", 3: "Bahaya"}[self.value]

    @property
    def en(self) -> str:
        return {-1: "NO DATA", 0: "Normal", 1: "Alert", 2: "Warning", 3: "Danger"}[self.value]


BandName = Literal["UNKNOWN", "NORMAL", "WASPADA", "AMARAN", "BAHAYA"]


class DataQuality(IntEnum):
    OK = 0
    SENSOR_FAULT = 1  # e.g. JPS sentinel -9999
    NO_THRESHOLD = 2  # placeholder thresholds such as 310/315/320 m
    STALE = 3  # reading older than the freshness limit
    MISSING = 4  # station absent from the page


class StationReading(BaseModel):
    """One row of the Public InfoBanjir water-level table, unmodified."""

    station_id: str
    name: str
    district: str
    basin: str = ""
    sub_basin: str = ""
    observed_at: datetime | None
    level_m: float | None
    normal_m: float | None
    waspada_m: float | None
    amaran_m: float | None
    bahaya_m: float | None


class RainReading(BaseModel):
    station_id: str
    name: str
    district: str
    observed_at: datetime | None
    since_midnight_mm: float | None
    last_hour_mm: float | None
    daily_mm: list[float | None] = Field(default_factory=list)


class StationState(BaseModel):
    """Classifier output for one watched station. Produced only by code."""

    station_id: str
    name: str
    district: str
    observed_at: datetime | None
    level_m: float | None
    band: Band
    previous_band: Band | None = None
    quality: DataQuality
    quality_note: str = ""
    thresholds: dict[str, float] = Field(default_factory=dict)
    next_band: Band | None = None
    metres_to_next_band: float | None = None
    rate_m_per_h: float | None = None

    @property
    def band_rose(self) -> bool:
        return (
            self.previous_band is not None
            and self.band != Band.UNKNOWN
            and self.previous_band != Band.UNKNOWN
            and self.band > self.previous_band
        )


class MetWarning(BaseModel):
    issued: datetime | None
    title_en: str
    title_ms: str
    valid_to: datetime | None
    text_en: str
    mentions_area: bool = False


class Shelter(BaseModel):
    """A relief centre (PPS) candidate from the community profile."""

    name: str
    lat: float
    lon: float
    distance_km: float | None = None
    note: str = ""


class Snapshot(BaseModel):
    """What the agent knew at one polling instant."""

    taken_at: datetime
    state: str
    stations: list[StationReading]
    rain: list[RainReading] = Field(default_factory=list)
    warnings: list[MetWarning] = Field(default_factory=list)
    jkm_open_pps_in_state: int | None = None
    source_urls: list[str] = Field(default_factory=list)


class Trigger(BaseModel):
    fired: bool
    reasons: list[str] = Field(default_factory=list)


class Assessment(BaseModel):
    """Everything classify produces for one community. The writer's only input."""

    community_id: str
    community_name: str
    snapshot_time: datetime
    states: list[StationState]
    max_band: Band
    trigger: Trigger
    shelter: Shelter | None
    warnings: list[MetWarning] = Field(default_factory=list)
    rain_last_hour_mm: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------- LLM output


class StationLine(BaseModel):
    """One sentence about one gauge, in both languages."""

    station_id: str = Field(description="Exact ID Stesen from the input, e.g. 0730851WL(L)")
    level_m: float | None = Field(description="Exact level from the input, or null if no data")
    band: BandName = Field(description="Exact band from the input")
    text_ms: str = Field(description="One plain Bahasa Melayu sentence, max 30 words")
    text_en: str = Field(description="The same sentence in plain English, max 30 words")


class FloodBrief(BaseModel):
    """What the brief_writer agent must return. Actions are NOT included:
    they come from a fixed, reviewed library chosen by code."""

    headline_ms: str = Field(description="Max 15 words, Bahasa Melayu")
    headline_en: str = Field(description="Max 15 words, English")
    stations: list[StationLine]
    trend_ms: str = Field(default="", description="Optional one sentence on rainfall/trend in BM")
    trend_en: str = Field(default="", description="Optional one sentence on rainfall/trend in English")
    reading_time: str = Field(description="HH:MM of the snapshot, copied from input")

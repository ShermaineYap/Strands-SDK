"""Community profiles (YAML). A community is data, not code."""

from __future__ import annotations

import math
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .models import Shelter

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"


class Rules(BaseModel):
    fast_rise_m_per_h: float = 0.30
    near_next_band_m: float = 0.50
    rebrief_after_minutes: int = 180
    stale_after_minutes: int = 90
    rain_warning_keywords: list[str] = Field(default_factory=lambda: ["hujan", "rain"])


class WatchedStation(BaseModel):
    id: str
    role: str = "upstream"


class Coordinator(BaseModel):
    role: str
    language: str = "ms"
    allowlist_env: str = "JAGASUNGAI_ALLOWLIST"

    def allowlist(self) -> set[str]:
        raw = os.environ.get(self.allowlist_env, "")
        return {n.strip() for n in raw.split(",") if n.strip()}


class Profile(BaseModel):
    id: str
    name: str
    state: str
    area_terms: list[str]
    location: dict[str, float]
    coordinator: Coordinator
    watch: list[WatchedStation]
    rain_watch: list[str] = Field(default_factory=list)
    shelters: list[dict] = Field(default_factory=list)
    rules: Rules = Field(default_factory=Rules)

    @property
    def watch_ids(self) -> list[str]:
        return [w.id for w in self.watch]

    def nearest_shelter(self) -> Shelter | None:
        best: Shelter | None = None
        for s in self.shelters:
            d = haversine_km(self.location["lat"], self.location["lon"], s["lat"], s["lon"])
            cand = Shelter(name=s["name"], lat=s["lat"], lon=s["lon"], distance_km=round(d, 1), note=s.get("note", ""))
            if best is None or (cand.distance_km or 0) < (best.distance_km or 0):
                best = cand
        return best


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_profile(name_or_path: str) -> Profile:
    p = Path(name_or_path)
    if not p.exists():
        p = PROFILE_DIR / f"{name_or_path}.yaml"
    return Profile.model_validate(yaml.safe_load(p.read_text()))

"""MET Malaysia warnings via the data.gov.my Weather API (CC BY 4.0, no key)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import requests

from ..models import MetWarning

WARNING_URL = "https://api.data.gov.my/weather/warning"


def _dt(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_warnings(data: list[dict], area_terms: list[str]) -> list[MetWarning]:
    out = []
    terms = [t.lower() for t in area_terms]
    for w in data:
        issue = w.get("warning_issue") or {}
        text_en = w.get("text_en") or ""
        text_bm = w.get("text_bm") or ""
        hay = f"{text_en} {text_bm}".lower()
        out.append(
            MetWarning(
                issued=_dt(issue.get("issued")),
                title_en=issue.get("title_en") or w.get("heading_en") or "",
                title_ms=issue.get("title_bm") or w.get("heading_bm") or "",
                valid_to=_dt(w.get("valid_to")),
                text_en=text_en,
                mentions_area=any(t in hay for t in terms),
            )
        )
    return out


def fetch_warnings(area_terms: list[str]) -> tuple[list[MetWarning], str]:  # pragma: no cover - network
    r = requests.get(WARNING_URL, timeout=30)
    r.raise_for_status()
    return parse_warnings(r.json(), area_terms), WARNING_URL


def load_fixture(path: str | Path, area_terms: list[str]) -> list[MetWarning]:
    return parse_warnings(json.loads(Path(path).read_text()), area_terms)

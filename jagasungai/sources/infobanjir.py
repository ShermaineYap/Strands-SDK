"""Public InfoBanjir (JPS) water-level and rainfall tables.

The portal has no published API or terms for automated access, so this module:
  * fetches at most once per state page per polling cycle (15 min),
  * identifies itself with a descriptive User-Agent,
  * keeps the parser isolated so an official API can replace it in one place.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ..models import RainReading, StationReading

BASE = "https://publicinfobanjir.water.gov.my"
WATER_URL = BASE + "/waterleveldata/{state}"
RAIN_URL = BASE + "/rainfalldata/{state}"
USER_AGENT = "JagaSungai/0.1 (+https://github.com/ShermaineYap/Strands-SDK; flood-brief research agent)"

SENTINEL_MAX = -9000.0  # JPS publishes -9999.00 for a faulty sensor


def _num(text: str) -> float | None:
    text = text.strip().replace(",", "")
    if not text or text in {"-", "N/A", "NA"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _time(text: str) -> datetime | None:
    text = text.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _rows(html: str, min_cells: int) -> list[list[str]]:
    soup = BeautifulSoup(html, "lxml")
    out: list[list[str]] = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            if len(cells) >= min_cells and cells[0].strip().isdigit():
                out.append(cells)
    return out


def parse_water_levels(html: str) -> list[StationReading]:
    """Parse ``/waterleveldata/<State>``.

    Columns: Bil | ID Stesen | Nama Stesen | Daerah | Lembangan | Sub Lembangan |
    Kemaskini Terakhir | Aras Air (m) | Normal | Waspada | Amaran | Bahaya
    """
    readings = []
    for c in _rows(html, 12):
        readings.append(
            StationReading(
                station_id=c[1].strip(),
                name=c[2].strip(),
                district=c[3].strip(),
                basin=c[4].strip(),
                sub_basin=c[5].strip(),
                observed_at=_time(c[6]),
                level_m=_num(c[7]),
                normal_m=_num(c[8]),
                waspada_m=_num(c[9]),
                amaran_m=_num(c[10]),
                bahaya_m=_num(c[11]),
            )
        )
    return readings


def parse_rainfall(html: str) -> list[RainReading]:
    """Parse ``/rainfalldata/<State>``.

    Columns: Bil | ID | Nama | Daerah | Kemaskini | 6 x daily totals |
    since-midnight | last-hour
    """
    readings = []
    for c in _rows(html, 13):
        readings.append(
            RainReading(
                station_id=c[1].strip(),
                name=c[2].strip(),
                district=c[3].strip(),
                observed_at=_time(c[4]),
                daily_mm=[_num(x) for x in c[5:11]],
                since_midnight_mm=_num(c[11]),
                last_hour_mm=_num(c[12]),
            )
        )
    return readings


def fetch(url: str, timeout: float = 30.0, retries: int = 2) -> str:
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:  # pragma: no cover - network
            last = exc
    raise RuntimeError(f"InfoBanjir fetch failed for {url}: {last}")


def fetch_water_levels(state: str) -> tuple[list[StationReading], str]:
    url = WATER_URL.format(state=state)
    return parse_water_levels(fetch(url)), url


def fetch_rainfall(state: str) -> tuple[list[RainReading], str]:
    url = RAIN_URL.format(state=state)
    return parse_rainfall(fetch(url)), url


def load_fixture_water(path: str | Path) -> list[StationReading]:
    return parse_water_levels(Path(path).read_text(encoding="utf-8", errors="ignore"))


def load_fixture_rain(path: str | Path) -> list[RainReading]:
    return parse_rainfall(Path(path).read_text(encoding="utf-8", errors="ignore"))

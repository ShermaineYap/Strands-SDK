"""JKM InfoBencana: open relief-centre (PPS) counts by state and district.

The landing page renders a server-side summary table:
BENCANA | NEGERI | DAERAH | PPS | KELUARGA | MANGSA | KAPASITI
Individual PPS names and coordinates load client-side and are not used.
"""

from __future__ import annotations

from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://infobencanajkmv2.jkm.gov.my/landing/index.php?b=0&a=0"


def parse_open_pps(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for table in soup.find_all("table"):
        head = [th.get_text(" ", strip=True).upper() for th in table.find_all("th")]
        if "PPS" not in head or "NEGERI" not in head:
            continue
        for tr in table.find_all("tr"):
            c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(c) >= 7 and c[0].upper() != "JUMLAH":
                try:
                    rows.append(
                        {
                            "disaster": c[0],
                            "state": c[1],
                            "district": c[2],
                            "pps": int(c[3]),
                            "families": int(c[4]),
                            "victims": int(c[5]),
                            "capacity": c[6],
                        }
                    )
                except ValueError:
                    continue
        break
    return rows


def open_pps_in_state(rows: list[dict], state: str) -> int:
    return sum(r["pps"] for r in rows if r["state"].lower() == state.lower())


def fetch_open_pps() -> tuple[list[dict], str]:  # pragma: no cover - network
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    return parse_open_pps(r.text), URL


def load_fixture(path: str | Path) -> list[dict]:
    return parse_open_pps(Path(path).read_text(encoding="utf-8", errors="ignore"))

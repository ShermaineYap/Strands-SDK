"""Build a Snapshot from the live public sources."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Snapshot
from .profile import Profile
from .sources import infobanjir, jkm, met

MYT = timezone(timedelta(hours=8))


def now_myt() -> datetime:
    """Naive MYT wall-clock time, matching InfoBanjir timestamps."""
    return datetime.now(MYT).replace(tzinfo=None)


def live_snapshot(profile: Profile) -> Snapshot:
    stations, wurl = infobanjir.fetch_water_levels(profile.state)
    urls = [wurl]
    try:
        rain, rurl = infobanjir.fetch_rainfall(profile.state)
        urls.append(rurl)
    except RuntimeError:
        rain = []
    try:
        warnings, murl = met.fetch_warnings(profile.area_terms)
        urls.append(murl)
    except Exception:  # noqa: BLE001 - warnings are context, never block the cycle
        warnings = []
    try:
        rows, jurl = jkm.fetch_open_pps()
        open_pps = jkm.open_pps_in_state(rows, profile.state)
        urls.append(jurl)
    except Exception:  # noqa: BLE001
        open_pps = None
    return Snapshot(
        taken_at=now_myt(),
        state=profile.state,
        stations=stations,
        rain=rain,
        warnings=warnings,
        jkm_open_pps_in_state=open_pps,
        source_urls=urls,
    )

"""Save the raw InfoBanjir pages every 15 minutes, to build a real replay sequence.

    python scripts/capture.py --state Kelantan --minutes 15

Writes fixtures/captures/<state>/<YYYYmmddTHHMM>_{water,rain}.html. One request per
page per interval, with an identifying User-Agent.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jagasungai.live import now_myt  # noqa: E402
from jagasungai.sources import infobanjir  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="Kelantan")
    ap.add_argument("--minutes", type=int, default=15)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    out = Path(__file__).resolve().parent.parent / "fixtures" / "captures" / args.state
    out.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = now_myt().strftime("%Y%m%dT%H%M")
        for kind, url in (("water", infobanjir.WATER_URL), ("rain", infobanjir.RAIN_URL)):
            try:
                html = infobanjir.fetch(url.format(state=args.state))
                (out / f"{stamp}_{kind}.html").write_text(html)
                print(stamp, kind, "ok")
            except RuntimeError as exc:
                print(stamp, kind, "failed:", exc)
        if args.once:
            break
        time.sleep(args.minutes * 60)


if __name__ == "__main__":
    main()

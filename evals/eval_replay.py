"""Eval 4 - replay 48 hours of 15-minute cycles through the full graph.

The scenario (``scenarios.rising_galas``) keeps the real Kelantan station table
and real JPS thresholds and moves two Sg. Galas gauges smoothly from Normal
through Waspada and Amaran into Bahaya and back. A simulated coordinator replies
"YA" five minutes after each draft. We measure what a judge would ask:

* how many cycles called a model at all (cost), and how many stayed quiet
* for each band crossing: minutes from the first reading at that band to the
  draft, and to delivery
* whether every escalation reached the coordinator, and how many briefs were sent

By default the writer is the scripted model (offline, deterministic). With
``--bedrock`` it calls Amazon Nova through Bedrock and reports measured tokens/cost.

    python -m evals.eval_replay [--bedrock]
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import timedelta

from strands.session.file_session_manager import FileSessionManager

from jagasungai.classify import assess
from jagasungai.compose import template_brief
from jagasungai.graph import JagaSungaiGraph
from jagasungai.messenger import ConsoleMessenger
from jagasungai.models import Band
from jagasungai.profile import load_profile
from jagasungai.scenarios import rising_galas
from jagasungai.scripted_model import ScriptedModel
from jagasungai.store import FileStore

APPROVAL_DELAY = timedelta(minutes=5)


def run(bedrock: bool = False) -> dict:
    os.environ["JAGASUNGAI_ALLOWLIST"] = "+60100000001,+60100000002"
    root = tempfile.mkdtemp(prefix="replay-")
    p = load_profile("gua_musang")
    store, msg = FileStore(root), ConsoleMessenger(echo=False)
    snaps = rising_galas()
    clock = [snaps[0].taken_at]
    current = [snaps[0]]

    if bedrock:  # pragma: no cover - needs AWS
        from jagasungai.writer import make_model
        model = make_model()
    else:
        # A well-behaved "model": writes exactly the facts it is given (template wording).
        def script(prompt: str, n: int) -> dict:
            prev = store.get(f"memory/{p.id}.json") or {}
            from jagasungai.models import Snapshot
            prev_snap = Snapshot.model_validate(prev["previous_snapshot"]) if prev.get("previous_snapshot") else None
            a = assess(current[0], p, previous=prev_snap, memory=prev)
            return template_brief(a).model_dump()
        model = ScriptedModel(script)

    def mk():
        return JagaSungaiGraph(p, store, msg, lambda: current[0], model=model,
                               session_manager_factory=lambda s: FileSessionManager(session_id=s, storage_dir=root + "/s"),
                               clock=lambda: clock[0], approver="+60199999999")

    first_seen: dict[int, str] = {}
    drafted: dict[int, str] = {}
    delivered: dict[int, str] = {}
    cycles = quiet = drafts = sends = denied = 0
    model_calls = 0
    tokens_in = tokens_out = 0
    ms_per_cycle = []
    for snap in snaps:
        current[0], clock[0] = snap, snap.taken_at
        cycles += 1
        t0 = time.perf_counter()
        r = mk().run_cycle()
        ms_per_cycle.append((time.perf_counter() - t0) * 1000)
        band = Band[r["max_band"]] if r["max_band"] else Band.UNKNOWN
        if band >= Band.WASPADA:
            first_seen.setdefault(int(band), snap.taken_at.isoformat())
        if "quiet" in r["nodes"]:
            quiet += 1
            continue
        drafts += 1
        model_calls += r["attempts"] or 0
        tokens_in += (r["usage"] or {}).get("inputTokens", 0)
        tokens_out += (r["usage"] or {}).get("outputTokens", 0)
        drafted.setdefault(int(band), snap.taken_at.isoformat())
        if r["interrupted"]:
            clock[0] = snap.taken_at + APPROVAL_DELAY
            rr = mk().resume("YA")
            if rr.get("sent"):
                sends += 1
                delivered.setdefault(int(band), clock[0].isoformat())
            else:
                denied += 1

    from datetime import datetime as _dt
    crossings = []
    for b in (Band.WASPADA, Band.AMARAN, Band.BAHAYA):
        fs = first_seen.get(int(b))
        dr = drafted.get(int(b))
        dl = delivered.get(int(b))
        crossings.append({
            "band": b.name,
            "first_reading_at_band": fs,
            "minutes_to_draft": None if not (fs and dr) else (_dt.fromisoformat(dr) - _dt.fromisoformat(fs)).seconds // 60,
            "minutes_to_delivery": None if not (fs and dl) else (_dt.fromisoformat(dl) - _dt.fromisoformat(fs)).seconds // 60,
        })
    ms_sorted = sorted(ms_per_cycle)
    res = {
        "name": "replay_48h",
        "writer": "bedrock" if bedrock else "scripted",
        "cycles": cycles,
        "quiet_cycles_no_model_call": quiet,
        "drafts": drafts,
        "sent": sends,
        "approved_but_denied": denied,
        "model_calls": model_calls,
        "crossings": crossings,
        "every_escalation_delivered": all(c["minutes_to_delivery"] is not None for c in crossings),
        "graph_ms_median": round(ms_sorted[len(ms_sorted) // 2], 1),
        "graph_ms_p95": round(ms_sorted[int(len(ms_sorted) * 0.95)], 1),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }
    if bedrock:
        res["cost_usd_total"] = round((tokens_in * 0.30 + tokens_out * 2.50) / 1e6, 4)
        res["cost_usd_per_draft"] = round(res["cost_usd_total"] / max(drafts, 1), 5)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bedrock", action="store_true")
    print(json.dumps(run(ap.parse_args().bedrock), indent=1))

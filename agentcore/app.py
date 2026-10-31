"""Amazon Bedrock AgentCore Runtime entrypoint.

Payloads:
  {"action": "poll"}                                   one cycle for every profile in JAGASUNGAI_PROFILES
  {"action": "poll", "profiles": ["gua_musang"]}
  {"action": "reply", "from": "+6012...", "text": "YA"} coordinator reply -> resume the interrupted graph
  {"action": "status", "profile": "gua_musang"}        live readings, no model, no send

Environment (set on the runtime):
  JAGASUNGAI_BUCKET            S3 bucket for state, snapshots and Strands sessions
  JAGASUNGAI_PROFILES          comma list, default "gua_musang"
  JAGASUNGAI_APPROVERS         JSON {"+60...": "gua_musang"} coordinator number -> profile
  JAGASUNGAI_ALLOWLIST         comma list of broadcast recipients
  JAGASUNGAI_CHANNEL           whatsapp | telegram | console
  JAGASUNGAI_WA_PHONE_NUMBER_ID, JAGASUNGAI_WA_REGION
  JAGASUNGAI_MODEL_ID          default global.amazon.nova-2-lite-v1:0
  JAGASUNGAI_BEDROCK_REGION    default ap-southeast-1
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402

from jagasungai.classify import assess  # noqa: E402
from jagasungai.cli import _session_factory  # noqa: E402
from jagasungai.graph import JagaSungaiGraph  # noqa: E402
from jagasungai.live import live_snapshot, now_myt  # noqa: E402
from jagasungai.messenger import messenger_from_env  # noqa: E402
from jagasungai.profile import load_profile  # noqa: E402
from jagasungai.store import store_from_env  # noqa: E402
from jagasungai.writer import make_model  # noqa: E402

app = BedrockAgentCoreApp()


def _approver_for(profile_name: str) -> str | None:
    approvers = json.loads(os.environ.get("JAGASUNGAI_APPROVERS", "{}"))
    return next((num for num, prof in approvers.items() if prof == profile_name), None)


def _graph(profile_name: str, with_model: bool = True) -> JagaSungaiGraph:
    p = load_profile(profile_name)
    return JagaSungaiGraph(
        p, store_from_env(), messenger_from_env(), lambda: live_snapshot(p),
        model=make_model() if with_model else None,
        session_manager_factory=_session_factory(), clock=now_myt,
        approver=_approver_for(profile_name),
    )


@app.entrypoint
def invoke(payload: dict) -> dict:
    action = payload.get("action", "poll")
    if action == "poll":
        names = payload.get("profiles") or os.environ.get("JAGASUNGAI_PROFILES", "gua_musang").split(",")
        return {"results": {n: _graph(n.strip()).run_cycle() for n in names}}
    if action == "reply":
        sender = payload.get("from", "")
        approvers = json.loads(os.environ.get("JAGASUNGAI_APPROVERS", "{}"))
        profile_name = approvers.get(sender)
        if not profile_name:
            return {"status": "ignored", "reason": "sender is not a registered coordinator"}
        return _graph(profile_name, with_model=False).resume(payload.get("text", ""))
    if action == "status":
        p = load_profile(payload.get("profile", "gua_musang"))
        a = assess(live_snapshot(p), p)
        return a.model_dump(mode="json")
    return {"status": "error", "reason": f"unknown action {action!r}"}


if __name__ == "__main__":
    app.run()

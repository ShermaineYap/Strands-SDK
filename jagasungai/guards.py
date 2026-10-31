"""Hard boundaries, enforced as Strands hooks.

``DispatchGuard`` runs on ``BeforeToolCallEvent`` for the ``send_brief`` tool
and cancels the call unless every rule holds. It does not trust the caller,
the model, or the message: it re-reads the approval record and the send log
from the store. ``ApprovalGate`` runs on ``BeforeNodeCallEvent`` and raises a
graph interrupt before the dispatch node, which is persisted by the session
manager so the coordinator can answer minutes later from another process.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import BeforeNodeCallEvent, BeforeToolCallEvent

from .actions import DISCLAIMER_EN, DISCLAIMER_MS, FORBIDDEN_PHRASES
from .store import Store

APPROVE_WORDS = {"ya", "yes", "ok", "hantar", "send", "y"}
MAX_APPROVAL_AGE = timedelta(minutes=60)
MIN_INTERVAL = timedelta(minutes=60)
ALLOWED_LINK = "https://publicinfobanjir.water.gov.my/"
WHATSAPP_MAX = 4096


def is_approval(response: Any) -> bool:
    if isinstance(response, dict):
        response = response.get("text") or response.get("response") or ""
    return str(response).strip().lower().split(" ")[0] in APPROVE_WORDS if str(response).strip() else False


def check_dispatch(store: Store, now: datetime, community_id: str, recipient: str, text: str,
                   approval_id: str, allowlist: set[str]) -> str | None:
    """Return a denial reason, or None if the send may go ahead. Pure and testable."""
    if recipient not in allowlist:
        return f"recipient {recipient} is not on the community allowlist"

    pending = store.get(f"pending/{community_id}.json")
    if not pending or pending.get("approval_id") != approval_id:
        return "no matching draft awaiting approval"
    if pending.get("status") != "approved":
        return "draft has not been approved by the coordinator"
    approved_at = datetime.fromisoformat(pending["approved_at"])
    created_at = datetime.fromisoformat(pending["created_at"])
    if approved_at - created_at > MAX_APPROVAL_AGE:
        return "approval arrived more than 60 minutes after the draft; readings are stale"
    if text != pending.get("message"):
        return "text differs from the approved draft"

    log = store.get(f"dispatch/{community_id}.json") or {}
    last = log.get("last_batch_at")
    if last and log.get("last_approval_id") != approval_id:
        # Escalation (a higher band than the last brief) is never rate-limited.
        new_band = (pending.get("assessment") or {}).get("max_band", -1)
        escalation = new_band > log.get("last_max_band", -1)
        if not escalation and now - datetime.fromisoformat(last) < MIN_INTERVAL:
            return "rate limit: one brief per community per hour (no escalation)"
    if recipient in (log.get("sent_to_for", {}).get(approval_id, [])):
        return "already sent to this recipient"

    # The disclaimer is code-owned and itself says "not an official warning"; scan everything else.
    body = text.replace(DISCLAIMER_MS, " ").replace(DISCLAIMER_EN, " ")
    low = " ".join(body.lower().split())
    for phrase in FORBIDDEN_PHRASES:
        if phrase in low:
            return f"forbidden phrase '{phrase}'"
    if DISCLAIMER_MS not in text and DISCLAIMER_EN not in text:
        return "disclaimer missing"
    for token in text.split():
        if ("http://" in token or "https://" in token) and not token.startswith(ALLOWED_LINK):
            return f"unexpected link {token}"
    if len(text) > WHATSAPP_MAX:
        return "message too long"
    return None


class DispatchGuard(HookProvider):
    def __init__(self, store: Store, allowlist: Callable[[], set[str]],
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.store, self.allowlist, self.clock = store, allowlist, clock
        self.denials: list[str] = []

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before_tool)

    def before_tool(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] != "send_brief":
            return
        args = event.tool_use["input"]
        reason = check_dispatch(
            self.store, self.clock(), args.get("community_id", ""), args.get("recipient", ""),
            args.get("text", ""), args.get("approval_id", ""), self.allowlist(),
        )
        if reason:
            self.denials.append(reason)
            event.cancel_tool = f"DENIED: {reason}"


class ApprovalGate(HookProvider):
    """Interrupt the graph before ``dispatch`` and wait for the coordinator."""

    def __init__(self, store: Store, clock: Callable[[], datetime] = datetime.now) -> None:
        self.store, self.clock = store, clock

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeNodeCallEvent, self.before_node)

    def before_node(self, event: BeforeNodeCallEvent) -> None:
        if event.node_id != "dispatch":
            return
        ctx = (event.invocation_state or {}).get("ctx", {})
        reason = {
            "community_id": ctx.get("community_id"),
            "approval_id": ctx.get("approval_id"),
            "message": ctx.get("message"),
        }
        response = event.interrupt("coordinator_approval", reason=reason)
        community_id = ctx.get("community_id") or (event.invocation_state or {}).get("community_id")
        pending = self.store.get(f"pending/{community_id}.json") if community_id else None
        if is_approval(response) and pending:
            pending["status"] = "approved"
            pending["approved_at"] = self.clock().isoformat()
            self.store.put(f"pending/{community_id}.json", pending)
        else:
            if pending:
                pending["status"] = "rejected"
                self.store.put(f"pending/{community_id}.json", pending)
            event.cancel_node = "coordinator did not approve"

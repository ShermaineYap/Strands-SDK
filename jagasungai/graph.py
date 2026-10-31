"""The JagaSungai Strands graph.

    ingest -> classify --(trigger fired)--> write <-> verify --> finalize -> [approval interrupt] -> dispatch
                       \--(quiet)--------> quiet

* ingest, classify, verify, finalize, dispatch and quiet are deterministic custom nodes
  (``MultiAgentBase`` subclasses). Only ``write`` calls a language model.
* ``classify -> write`` is a conditional edge: on most 15-minute cycles nothing changes,
  the model is never called and the run costs nothing.
* ``verify -> write`` is a cycle with ``reset_on_revisit``: a rejected draft goes back with
  the exact errors, up to MAX_ATTEMPTS, then the graph fails closed to a template brief.
* ``ApprovalGate`` interrupts before ``dispatch``; the session manager persists the graph so
  the coordinator's reply (minutes later, another process) resumes it.
* ``dispatch`` calls the ``send_brief`` tool directly (no model) and ``DispatchGuard`` can
  still cancel each call.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Callable

from strands import Agent, tool
from strands.agent.agent_result import AgentResult
from strands.models.model import Model
from strands.multiagent import GraphBuilder
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.session.session_manager import SessionManager
from strands.telemetry.metrics import EventLoopMetrics

from .classify import assess, memory_after_quiet_run, memory_after_send
from .compose import compose_message, template_brief
from .guards import ApprovalGate, DispatchGuard
from .messenger import Messenger
from .models import Assessment, FloodBrief, Snapshot
from .profile import Profile
from .store import Store
from .verify import verify
from .writer import write_brief

MAX_ATTEMPTS = 3
NOVA_2_LITE_USD_PER_M = (0.30, 2.50)  # input, output; check current pricing before quoting


class FnNode(MultiAgentBase):
    """Run a deterministic Python function as a graph node.

    ``fn(task, ctx) -> str``; ``ctx`` is the shared ``invocation_state['ctx']`` dict.
    """

    def __init__(self, name: str, fn: Callable[[Any, dict], str]) -> None:
        super().__init__()
        self.name = self.id = name
        self.fn = fn

    async def invoke_async(self, task, invocation_state=None, **kwargs) -> MultiAgentResult:
        state = invocation_state if invocation_state is not None else {}
        ctx = state.setdefault("ctx", {})
        t0 = time.perf_counter()
        text = self.fn(task, ctx)
        ms = int((time.perf_counter() - t0) * 1000)
        ctx.setdefault("trace", []).append({"node": self.name, "ms": ms, "summary": text[:160]})
        result = AgentResult(
            stop_reason="end_turn",
            message={"role": "assistant", "content": [{"text": text}]},
            metrics=EventLoopMetrics(),
            state={},
        )
        return MultiAgentResult(
            status=Status.COMPLETED,
            results={self.name: NodeResult(result=result, status=Status.COMPLETED, execution_time=ms)},
            execution_time=ms,
        )


def make_send_tool(messenger: Messenger, store: Store, clock: Callable[[], datetime]):
    @tool
    def send_brief(community_id: str, recipient: str, text: str, approval_id: str) -> str:
        """Send an approved flood brief to one recipient. Guarded by DispatchGuard."""
        message_id = messenger.send(recipient, text)
        # Every successful send is logged here, so the guard sees it however the tool was called.
        log = store.get(f"dispatch/{community_id}.json") or {}
        if log.get("last_approval_id") != approval_id:
            pending = store.get(f"pending/{community_id}.json") or {}
            log["last_batch_at"] = clock().isoformat()
            log["last_approval_id"] = approval_id
            log["last_max_band"] = (pending.get("assessment") or {}).get("max_band", -1)
        log.setdefault("sent_to_for", {}).setdefault(approval_id, []).append(recipient)
        store.put(f"dispatch/{community_id}.json", log)
        return message_id

    return send_brief


class JagaSungaiGraph:
    """Build and run the graph for one community."""

    def __init__(
        self,
        profile: Profile,
        store: Store,
        messenger: Messenger,
        snapshot_source: Callable[[], Snapshot],
        model: Any | None = None,
        session_manager_factory: Callable[[str], SessionManager] | None = None,
        clock: Callable[[], datetime] = datetime.now,
        approver: str | None = None,
    ) -> None:
        self.profile, self.store, self.messenger = profile, store, messenger
        self.snapshot_source, self.model, self.clock = snapshot_source, model, clock
        self.session_manager_factory = session_manager_factory
        self.approver = approver
        self.guard = DispatchGuard(store, profile.coordinator.allowlist, clock)
        self.dispatcher = Agent(
            name="dispatcher",
            tools=[make_send_tool(messenger, store, clock)],
            hooks=[self.guard],
            callback_handler=None,
            record_direct_tool_call=False,
            model=_NoModel(),
        )

    # ------------------------------------------------------------------ nodes

    def _ingest(self, task, ctx) -> str:
        snap = self.snapshot_source()
        ctx["snapshot"] = snap
        key = f"snapshots/{snap.state}/{snap.taken_at:%Y%m%dT%H%M}.json"
        self.store.put(key, snap.model_dump(mode="json"))
        return f"snapshot {snap.taken_at:%Y-%m-%d %H:%M} {len(snap.stations)} stations"

    def _classify(self, task, ctx) -> str:
        snap: Snapshot = ctx["snapshot"]
        memory = self.store.get(f"memory/{self.profile.id}.json") or {}
        prev_raw = memory.get("previous_snapshot")
        previous = Snapshot.model_validate(prev_raw) if prev_raw else None
        a = assess(snap, self.profile, previous=previous, memory=memory)
        ctx["assessment"] = a
        ctx["memory"] = memory
        ctx["attempts"] = 0
        ctx["usage"] = {"inputTokens": 0, "outputTokens": 0}
        bands = ", ".join(f"{s.station_id}={s.band.name}" for s in a.states)
        return f"max={a.max_band.name} fired={a.trigger.fired} {a.trigger.reasons} | {bands}"

    def _quiet(self, task, ctx) -> str:
        a: Assessment = ctx["assessment"]
        mem = memory_after_quiet_run(a, ctx.get("memory"))
        mem["previous_snapshot"] = _slim(ctx["snapshot"], self.profile)
        self.store.put(f"memory/{self.profile.id}.json", mem)
        self._audit(ctx, "quiet", {"max_band": a.max_band.name})
        return "quiet: no brief needed, model not called"

    def _write(self, task, ctx) -> str:
        a: Assessment = ctx["assessment"]
        ctx["attempts"] = ctx.get("attempts", 0) + 1
        if self.model is None:
            ctx["brief"], ctx["writer"] = template_brief(a), "template"
            return "template writer (no model configured)"
        try:
            brief, usage = write_brief(self.model, a, ctx.get("feedback"))
        except Exception as exc:  # model unavailable or invalid output: fail closed
            ctx["brief"], ctx["writer"] = template_brief(a), "template"
            ctx["writer_error"] = f"{type(exc).__name__}: {exc}"[:300]
            ctx["attempts"] = MAX_ATTEMPTS
            return f"writer failed ({type(exc).__name__}); using template"
        for k in ("inputTokens", "outputTokens"):
            ctx["usage"][k] += int(usage.get(k, 0))
        ctx["brief"], ctx["writer"] = brief, "model"
        return f"draft {ctx['attempts']}: {brief.headline_ms}"

    def _verify(self, task, ctx) -> str:
        res = verify(ctx["brief"], ctx["assessment"])
        ctx["verify_ok"] = res.ok
        ctx["feedback"] = None if res.ok else res.feedback()
        ctx.setdefault("verifier_log", []).append({"attempt": ctx["attempts"], "ok": res.ok, "errors": res.errors})
        return "verified" if res.ok else f"rejected ({len(res.errors)} errors): " + "; ".join(res.errors[:3])

    def _finalize(self, task, ctx) -> str:
        a: Assessment = ctx["assessment"]
        brief: FloodBrief = ctx["brief"]
        if not ctx.get("verify_ok"):
            brief, ctx["writer"] = template_brief(a), "template"
            ctx["fail_closed"] = True
            # The template is built from the same facts and must itself verify. If even
            # that fails, nothing is drafted: the coordinator is told to check InfoBanjir.
            check = verify(brief, a)
            if not check.ok:
                ctx["blocked"] = check.errors
                self._audit(ctx, "blocked", {"errors": check.errors})
                if self.approver:
                    self.messenger.send(self.approver, "JagaSungai: semakan fakta gagal, tiada ringkasan dihantar. "
                                        "Sila semak https://publicinfobanjir.water.gov.my/ secara terus.")
                self.store.delete(f"pending/{self.profile.id}.json")
                return "blocked: template failed verification; nothing drafted"
        message = compose_message(brief, a, self.profile.state, self.profile.coordinator.language, ctx["writer"])
        approval_id = f"{self.profile.id}-{a.snapshot_time:%Y%m%dT%H%M}-{uuid.uuid4().hex[:8]}"
        ctx.update(message=message, approval_id=approval_id, community_id=self.profile.id)
        cost = (ctx["usage"]["inputTokens"] * NOVA_2_LITE_USD_PER_M[0]
                + ctx["usage"]["outputTokens"] * NOVA_2_LITE_USD_PER_M[1]) / 1e6
        ctx["cost_usd"] = round(cost, 5)
        self.store.put(f"pending/{self.profile.id}.json", {
            "approval_id": approval_id,
            "status": "awaiting",
            "created_at": self.clock().isoformat(),
            "message": message,
            "assessment": a.model_dump(mode="json"),
            "snapshot": _slim(ctx["snapshot"], self.profile),
            "writer": ctx["writer"],
            "attempts": ctx["attempts"],
        })
        self._audit(ctx, "draft", {"approval_id": approval_id, "writer": ctx["writer"],
                                   "attempts": ctx["attempts"], "cost_usd": ctx["cost_usd"]})
        if self.approver:
            self.messenger.send(self.approver, "DRAF untuk kelulusan / DRAFT for approval\n"
                                "Balas YA untuk hantar, TIDAK untuk batal.\n\n" + message)
        return json.dumps({"approval_id": approval_id, "writer": ctx["writer"], "attempts": ctx["attempts"]})

    def _dispatch(self, task, ctx) -> str:
        pending = self.store.get(f"pending/{self.profile.id}.json") or {}
        message, approval_id = pending.get("message", ""), pending.get("approval_id", "")
        sent, denied = [], []
        for recipient in sorted(self.profile.coordinator.allowlist()):
            res = self.dispatcher.tool.send_brief(
                community_id=self.profile.id, recipient=recipient, text=message, approval_id=approval_id)
            if res["status"] == "success":
                sent.append(recipient)
            else:
                denied.append(res["content"][0]["text"])
        if sent:
            a = Assessment.model_validate(pending["assessment"])
            mem = memory_after_send(a, self.clock(), self.store.get(f"memory/{self.profile.id}.json"))
            mem["previous_snapshot"] = pending.get("snapshot")
            self.store.put(f"memory/{self.profile.id}.json", mem)
            pending["status"] = "sent"
            self.store.put(f"pending/{self.profile.id}.json", pending)
        self._audit(ctx, "dispatch", {"approval_id": approval_id, "sent": len(sent), "denied": denied})
        ctx["sent"], ctx["denied"] = sent, denied
        return f"sent to {len(sent)}; denied {len(denied)}" + (f": {denied[0]}" if denied else "")

    # ------------------------------------------------------------------ build

    def build(self, session_id: str | None = None):
        b = GraphBuilder()
        for name, fn in [("ingest", self._ingest), ("classify", self._classify), ("quiet", self._quiet),
                         ("write", self._write), ("verify", self._verify), ("finalize", self._finalize),
                         ("dispatch", self._dispatch)]:
            b.add_node(FnNode(name, fn), name)
        b.add_edge("ingest", "classify")
        b.add_edge("classify", "write", condition=_ctx_cond(lambda c: c["assessment"].trigger.fired))
        b.add_edge("classify", "quiet", condition=_ctx_cond(lambda c: not c["assessment"].trigger.fired))
        b.add_edge("write", "verify")
        b.add_edge("verify", "write", condition=_ctx_cond(
            lambda c: not c.get("verify_ok") and c.get("attempts", 0) < MAX_ATTEMPTS))
        b.add_edge("verify", "finalize", condition=_ctx_cond(
            lambda c: c.get("verify_ok") or c.get("attempts", 0) >= MAX_ATTEMPTS))
        b.add_edge("finalize", "dispatch", condition=_ctx_cond(lambda c: not c.get("blocked")))
        b.set_entry_point("ingest")
        b.reset_on_revisit(True)
        b.set_max_node_executions(20)
        b.set_execution_timeout(300)
        b.set_graph_id("jagasungai")
        hooks = [ApprovalGate(self.store, self.clock)]
        b.set_hook_providers(hooks)
        if session_id and self.session_manager_factory:
            b.set_session_manager(self.session_manager_factory(session_id))
        return b.build()

    def run_cycle(self) -> dict:
        """One polling cycle. Returns a summary; may end in an approval interrupt."""
        session_id = f"{self.profile.id}-{self.clock():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        graph = self.build(session_id)
        state: dict = {"ctx": {}, "community_id": self.profile.id}
        result = graph("poll", invocation_state=state)
        ctx = state["ctx"]
        if result.interrupts:
            pending = self.store.get(f"pending/{self.profile.id}.json")
            pending.update(session_id=session_id, interrupt_id=result.interrupts[0].id)
            self.store.put(f"pending/{self.profile.id}.json", pending)
        return _summary(result, ctx, session_id)

    def resume(self, response: str) -> dict:
        """Resume the interrupted graph with the coordinator's reply."""
        pending = self.store.get(f"pending/{self.profile.id}.json")
        if not pending or pending.get("status") != "awaiting" or "session_id" not in pending:
            return {"status": "nothing_pending"}
        graph = self.build(pending["session_id"])
        state: dict = {"ctx": {}, "community_id": self.profile.id}
        try:
            result = graph([{"interruptResponse": {"interruptId": pending["interrupt_id"], "response": response}}],
                           invocation_state=state)
        except RuntimeError as exc:  # ApprovalGate cancelled the dispatch node
            self._audit(state["ctx"], "rejected", {"approval_id": pending.get("approval_id"), "reply": response[:40]})
            return {"status": "rejected", "session_id": pending["session_id"], "reason": str(exc),
                    "nodes": [], "sent": [], "denied": []}
        return _summary(result, state["ctx"], pending["session_id"])

    def _audit(self, ctx: dict, event: str, data: dict) -> None:
        self.store.append_line(f"audit/{self.profile.id}.jsonl", {
            "at": self.clock().isoformat(), "event": event, **data,
            "trace": [t["node"] for t in ctx.get("trace", [])],
        })


class _NoModel(Model):
    """The dispatcher agent never calls a model; tools are invoked directly by code."""

    def update_config(self, **model_config: Any) -> None:  # pragma: no cover
        pass

    def get_config(self) -> Any:  # pragma: no cover
        return {"model_id": "none"}

    async def structured_output(self, *args, **kwargs):  # pragma: no cover
        raise RuntimeError("dispatcher must not call a model")
        yield {}

    async def stream(self, *args, **kwargs):  # pragma: no cover
        raise RuntimeError("dispatcher must not call a model")
        yield {}


def _ctx_cond(fn: Callable[[dict], bool]):
    def condition(state, invocation_state=None) -> bool:
        ctx = (invocation_state or {}).get("ctx", {})
        try:
            return bool(fn(ctx))
        except KeyError:
            return False
    return condition


def _slim(snap: Snapshot, profile: Profile) -> dict:
    keep = set(profile.watch_ids)
    d = snap.model_dump(mode="json")
    d["stations"] = [s for s in d["stations"] if s["station_id"] in keep]
    d["rain"] = []
    return d


def _summary(result, ctx: dict, session_id: str) -> dict:
    a: Assessment | None = ctx.get("assessment")
    return {
        "status": result.status.value,
        "session_id": session_id,
        "interrupted": bool(result.interrupts),
        "nodes": [t["node"] for t in ctx.get("trace", [])],
        "max_band": a.max_band.name if a else None,
        "trigger": a.trigger.reasons if a else None,
        "writer": ctx.get("writer"),
        "attempts": ctx.get("attempts"),
        "fail_closed": ctx.get("fail_closed", False),
        "verifier_log": ctx.get("verifier_log", []),
        "message": ctx.get("message"),
        "cost_usd": ctx.get("cost_usd"),
        "usage": ctx.get("usage"),
        "sent": ctx.get("sent"),
        "denied": ctx.get("denied"),
    }

"""Command line.

  python -m jagasungai.cli status  --profile gua_musang          # live readings, no model, no send
  python -m jagasungai.cli cycle   --profile gua_musang [--model bedrock|template]
  python -m jagasungai.cli approve --profile gua_musang --reply YA
  python -m jagasungai.cli demo                                  # offline end-to-end on a replayed rise
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta

from strands.session.file_session_manager import FileSessionManager

from .classify import assess
from .compose import compose_message, template_brief
from .graph import JagaSungaiGraph
from .live import live_snapshot, now_myt
from .messenger import ConsoleMessenger, messenger_from_env
from .profile import load_profile
from .store import FileStore, store_from_env


def _session_factory():
    bucket = os.environ.get("JAGASUNGAI_BUCKET")
    if bucket:  # pragma: no cover - needs AWS
        from strands.session.s3_session_manager import S3SessionManager

        return lambda sid: S3SessionManager(session_id=sid, bucket=bucket, prefix="sessions/",
                                            region_name=os.environ.get("AWS_REGION"))
    root = os.environ.get("JAGASUNGAI_STATE_DIR", ".jagasungai")
    return lambda sid: FileSessionManager(session_id=sid, storage_dir=os.path.join(root, "sessions"))


def _model(kind: str):
    if kind == "bedrock":
        from .writer import make_model

        return make_model()
    return None


def cmd_status(args) -> None:
    p = load_profile(args.profile)
    snap = live_snapshot(p)
    a = assess(snap, p)
    print(f"{p.name} · {snap.taken_at:%Y-%m-%d %H:%M} MYT · trigger={a.trigger.fired} {a.trigger.reasons}")
    for s in a.states:
        lvl = "-" if s.level_m is None else f"{s.level_m:.2f}"
        print(f"  {s.station_id:14} {s.name[:40]:40} {lvl:>8} m  {s.band.name:8} {s.quality.name} {s.quality_note}")
    print("\n" + compose_message(template_brief(a), a, p.state, writer="template"))


def cmd_cycle(args) -> None:
    p = load_profile(args.profile)
    g = JagaSungaiGraph(p, store_from_env(), messenger_from_env(), lambda: live_snapshot(p),
                        model=_model(args.model), session_manager_factory=_session_factory(),
                        clock=now_myt, approver=os.environ.get("JAGASUNGAI_APPROVER"))
    print(json.dumps(g.run_cycle(), indent=1, ensure_ascii=False, default=str))


def cmd_approve(args) -> None:
    p = load_profile(args.profile)
    g = JagaSungaiGraph(p, store_from_env(), messenger_from_env(), lambda: live_snapshot(p),
                        session_manager_factory=_session_factory(), clock=now_myt)
    print(json.dumps(g.resume(args.reply), indent=1, ensure_ascii=False, default=str))


def cmd_demo(args) -> None:
    """Offline: replay a real-threshold rise through the full graph with the scripted writer."""
    import tempfile

    from .scenarios import with_levels

    os.environ.setdefault("JAGASUNGAI_ALLOWLIST", "+60100000001,+60100000002")
    root = tempfile.mkdtemp(prefix="jagasungai-demo-")
    store, msg = FileStore(root), ConsoleMessenger()
    p = load_profile("gua_musang")
    t = [now_myt().replace(second=0, microsecond=0)]
    snap = [with_levels({"0730851WL(L)": 86.10, "5020401": 57.20}, t[0])]
    def mk():
        return JagaSungaiGraph(
            p, store, msg, lambda: snap[0], model=None,
            session_manager_factory=lambda sid: FileSessionManager(session_id=sid, storage_dir=root + "/sessions"),
            clock=lambda: t[0], approver="+60199999999")
    r = mk().run_cycle()
    print(f"\n[cycle] nodes={r['nodes']} status={r['status']} trigger={r['trigger']}")
    t[0] += timedelta(minutes=4)
    r = mk().resume("YA")
    print(f"[approve] nodes={r['nodes']} sent={r['sent']} denied={r['denied']}")
    print(f"\nstate kept in {root}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="jagasungai")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--profile", default="gua_musang"); s.set_defaults(fn=cmd_status)
    c = sub.add_parser("cycle"); c.add_argument("--profile", default="gua_musang")
    c.add_argument("--model", choices=["bedrock", "template"], default="bedrock"); c.set_defaults(fn=cmd_cycle)
    a = sub.add_parser("approve"); a.add_argument("--profile", default="gua_musang")
    a.add_argument("--reply", default="YA"); a.set_defaults(fn=cmd_approve)
    d = sub.add_parser("demo"); d.set_defaults(fn=cmd_demo)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

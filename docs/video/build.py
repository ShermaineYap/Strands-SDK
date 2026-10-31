"""Build the silent, captioned demo video from real program output.

    python docs/video/build.py          # -> docs/video/jagasungai_demo.mp4

Frames are HTML pages rendered by Playwright (Chromium) at 1920x1080, then held
as stills with fades by ffmpeg, one file per scene, joined with the concat demuxer.
All on-screen data comes from docs/video/demo_run.json, results/eval_results.json and
the live fixtures. No music (the hackathon rules restrict third-party audio).
"""

from __future__ import annotations

import html
import json
import os
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "build"
W, H, FPS = 1920, 1080, 30

run = json.loads((HERE / "demo_run.json").read_text())
ev = json.loads((ROOT / "results" / "eval_results.json").read_text())

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1920px;height:1080px;background:#0f2430;color:#eaf2f6;font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;overflow:hidden;position:relative}
.wrap{position:absolute;left:110px;right:110px;top:90px;bottom:200px}
.kicker{font-size:28px;letter-spacing:.14em;text-transform:uppercase;color:#7fd3f0;font-weight:700;margin-bottom:22px}
h1{font-size:92px;line-height:1.05;font-weight:800;letter-spacing:-.01em}
h2{font-size:60px;line-height:1.12;font-weight:800;margin-bottom:34px}
p.lead{font-size:38px;line-height:1.4;color:#c7d8e1;max-width:1500px}
.cap{position:absolute;left:0;right:0;bottom:0;height:150px;background:rgba(5,14,20,.88);display:flex;align-items:center;padding:0 110px;font-size:36px;line-height:1.35;color:#fff;border-top:3px solid #2f8fb3}
.term{background:#071319;border:2px solid #24414f;border-radius:16px;padding:30px 36px;font-family:"DejaVu Sans Mono",Menlo,monospace;font-size:26px;line-height:1.5;color:#d6e6ee;white-space:pre-wrap}
.prompt{color:#7fd3f0}.ok{color:#5be08b}.bad{color:#ff7b6b}.warn{color:#ffc65c}.dim{color:#7f97a3}
table{border-collapse:collapse;width:100%;font-size:30px}
td,th{padding:14px 18px;border-bottom:1px solid #24414f;text-align:left}
th{color:#7fd3f0;font-size:24px;letter-spacing:.06em;text-transform:uppercase}
td.n{font-weight:800;color:#5be08b;white-space:nowrap}
.stat{display:inline-block;margin-right:70px;vertical-align:top}
.stat b{display:block;font-size:110px;font-weight:800;color:#fff;line-height:1}
.stat span{font-size:30px;color:#9fb8c4}
.pill{display:inline-block;padding:4px 14px;border-radius:999px;font-size:24px;font-weight:700}
.p-normal{background:#1e4d3a;color:#8ff0b8}.p-unk{background:#4b2a2a;color:#ffb3a8}.p-amaran{background:#5a3b10;color:#ffcf7a}
.nodes{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:34px}
.node{padding:16px 26px;border-radius:12px;border:3px solid #2f6f8f;background:#123445;font-size:30px;font-weight:700}
.node.llm{border-color:#c07a00;background:#3a2a0b}.node.on{box-shadow:0 0 0 4px rgba(127,211,240,.35)}
.node.rej{border-color:#ff7b6b;background:#3a1714}.node.pass{border-color:#5be08b;background:#103222}
.node.int{border-color:#ff7b6b;background:#2a1a1a}
.phone{position:absolute;right:150px;top:40px;width:600px;height:870px;border-radius:56px;background:#05090c;border:6px solid #7fd3f0;padding:26px}
.screen{width:100%;height:100%;border-radius:36px;background:#e7ddd3;overflow:hidden;padding:18px 16px;font-size:16.5px;line-height:1.3;color:#111}
.bub{background:#fff;border-radius:14px;padding:12px 14px;margin-bottom:12px;max-width:94%;white-space:pre-wrap;box-shadow:0 1px 1px rgba(0,0,0,.15)}
.bub.me{background:#d9fdd3;margin-left:auto;max-width:30%;font-weight:700;font-size:22px;text-align:center;padding:8px}
.side{position:absolute;left:110px;top:120px;width:1060px}
"""


def page(body: str, caption: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
            f"{body}<div class='cap'>{caption}</div></body></html>")


def esc(s: str) -> str:
    return html.escape(s)


def scenes() -> list[tuple[str, str, float]]:
    S: list[tuple[str, str, float]] = []
    S.append(("01_title", page(
        "<div class='wrap' style='top:250px'><div class='kicker'>Strands Agents · Climate resilience</div>"
        "<h1>JagaSungai</h1><p class='lead' style='margin-top:30px'>Verified flood briefs for communities that get cut off, "
        "from Malaysia's official river gauges to a coordinator's WhatsApp.</p></div>",
        "Gua Musang, Kelantan: about 10,000 Temiar Orang Asli. In December 2025, floods displaced more than 1,000 of them."), 8.0))

    S.append(("02_problem", page(
        "<div class='wrap'><div class='kicker'>The gap</div><h2>The data is public. The decision isn't.</h2>"
        "<div style='margin-top:40px'><div class='stat'><b>28</b><span>Kelantan river gauges</span></div>"
        "<div class='stat'><b>15 min</b><span>JPS update interval</span></div>"
        "<div class='stat'><b>4</b><span>official thresholds each</span></div></div>"
        "<p class='lead' style='margin-top:60px'>Normal · Waspada (Alert) · Amaran (Warning) · Bahaya (Danger). "
        "Someone with signal has to know which upstream gauge matters, read it correctly at 2 a.m., and turn it into instructions.</p></div>",
        "Public InfoBanjir publishes every gauge. A table of numbers is not a warning people can act on."), 11.0))

    rows = ""
    for s in run["live"]:
        lvl = "-9,999.00" if s["quality"] == "SENSOR_FAULT" else f"{s['level']:.2f}"
        pill = {"NORMAL": "p-normal"}.get(s["band"], "p-unk")
        label = s["band"] if s["band"] != "UNKNOWN" else ("SENSOR FAULT" if s["quality"] == "SENSOR_FAULT" else "NO VALID THRESHOLDS")
        note = s["note"] if s["band"] == "UNKNOWN" else f"{s['to_next']:.2f} m to Waspada"
        rows += f"<tr><td>{esc(s['id'])}</td><td>{esc(s['name'])}</td><td>{lvl} m</td><td><span class='pill {pill}'>{label}</span></td><td class='dim' style='font-size:24px'>{esc(note)}</td></tr>"
    S.append(("03_live", page(
        "<div class='wrap' style='top:70px'><div class='kicker'>Live · 1 Nov 2026 00:45 MYT</div>"
        "<h2>Gua Musang's four gauges, read by JagaSungai</h2>"
        f"<table><tr><th>Station</th><th>Name</th><th>Level</th><th>Band</th><th>Note</th></tr>{rows}</table></div>",
        "Tonight, two of the four gauges were unusable. JagaSungai says \"no reliable data\", never \"normal\"."), 13.0))

    S.append(("04_arch", "ARCH", 13.0))

    nodes = lambda states: "<div class='nodes'>" + "".join(  # noqa: E731
        f"<div class='node {c}'>{n}</div>" for n, c in states) + "</div>"
    errs = run["cycle"]["verifier_log"][0]["errors"]
    bad = run["draft_bad"]
    bad_line = next(l for l in bad["stations"] if l["station_id"] == "0730851WL(L)")
    S.append(("05_trigger", page(
        "<div class='wrap' style='top:70px'><div class='kicker'>Replay · Sg. Galas di Kg. Lembaga crosses Amaran (85.60 m)</div>"
        + nodes([("ingest", "on"), ("classify", "on"), ("write", "llm"), ("verify", ""), ("finalize", ""), ("approval", ""), ("dispatch", "")])
        + "<div class='term'><span class='prompt'>classify</span>  0730851WL(L)  86.10 m  <span class='warn'>AMARAN</span>  (was WASPADA)  1.80 m to BAHAYA\n"
        "<span class='prompt'>classify</span>  5020401       57.20 m  WASPADA\n"
        "<span class='prompt'>classify</span>  0730831WL     <span class='bad'>UNKNOWN</span>  placeholder thresholds 310.00/315.00/320.00 m\n"
        "<span class='prompt'>classify</span>  0731351WL     <span class='bad'>UNKNOWN</span>  sensor fault (reported -9999.0)\n\n"
        "<span class='ok'>trigger</span>   band_rose:0730851WL(L):WASPADA->AMARAN   ->  conditional edge to <b>write</b></div></div>",
        "Code classifies every gauge against its JPS thresholds. Only a crossing wakes the language model."), 9.0))

    S.append(("06_reject", page(
        "<div class='wrap' style='top:70px'><div class='kicker'>Draft 1 · Strands Agent · structured_output = FloodBrief</div>"
        + nodes([("ingest", ""), ("classify", ""), ("write", "llm on"), ("verify", "rej on"), ("finalize", ""), ("approval", ""), ("dispatch", "")])
        + "<div class='term'><span class='dim'>model draft:</span>\n"
        f"  \"{esc(bad_line['text_ms'])}\"\n  \"{esc(bad['trend_ms'])}\"\n\n"
        "<span class='bad'>verify  REJECTED</span>\n" + "\n".join(f"  <span class='bad'>✗</span> {esc(e)}" for e in errs)
        + "\n\n<span class='dim'>-> back to write with these exact errors (reset_on_revisit, max 3)</span></div></div>",
        "The model claimed Danger and told people they were safe to stay home. The verifier caught both."), 13.0))

    S.append(("07_pass", page(
        "<div class='wrap' style='top:70px'><div class='kicker'>Draft 2 · verified · graph interrupted for approval</div>"
        + nodes([("ingest", ""), ("classify", ""), ("write", "llm"), ("verify", "pass on"), ("finalize", "on"), ("approval", "int on"), ("dispatch", "")])
        + "<div class='term'><span class='ok'>verify  PASS</span>  every number, station, band word and time traced to a reading\n"
        "<span class='prompt'>finalize</span> + reviewed actions for AMARAN + nearest PPS from profile + disclaimer\n"
        "<span class='warn'>ApprovalGate</span>  BeforeNodeCallEvent -> event.interrupt(\"coordinator_approval\")\n"
        "<span class='dim'>graph state persisted by the session manager; this process can now exit</span>\n\n"
        f"nodes run: {esc(' -> '.join(run['cycle']['nodes']))}</div></div>",
        "The second draft passes. The graph pauses and persists, waiting for a human."), 10.0))

    msg = run["cycle"]["message"]
    S.append(("08_phone", page(
        "<div class='side'><div class='kicker'>Coordinator's phone</div><h2>Draft arrives in Bahasa Melayu</h2>"
        "<p class='lead'>Broken gauges say <i>tiada data</i>. Actions come from a reviewed library, not the model. "
        "It says plainly it is not an official warning.</p>"
        "<p class='lead' style='margin-top:30px'>Reply <b>YA</b> to send, <b>TIDAK</b> to drop.</p></div>"
        f"<div class='phone'><div class='screen'><div class='bub'>DRAF untuk kelulusan\n\n{esc(msg)}</div>"
        "<div class='bub me'>YA</div></div></div>",
        "The coordinator approves with one word. Their reply resumes the graph in another process."), 14.0))

    S.append(("09_sent", page(
        "<div class='wrap' style='top:70px'><div class='kicker'>Resume · dispatch · DispatchGuard (BeforeToolCallEvent)</div>"
        + nodes([("approval", "pass"), ("dispatch", "on")])
        + "<div class='term'>"
        f"<span class='ok'>sent</span>    {esc(', '.join(run['resume']['sent']))}   (community allowlist)\n\n"
        "<span class='dim'># anyone calling send_brief directly still goes through the hook:</span>\n"
        f"<span class='bad'>{esc(run['unlisted'])}</span>\n"
        "<span class='bad'>DENIED: text differs from the approved draft</span>\n"
        "<span class='bad'>DENIED: rate limit: one brief per community per hour (no escalation)</span>\n"
        "<span class='bad'>DENIED: approval arrived more than 60 minutes after the draft; readings are stale</span></div></div>",
        "Code calls the send tool. A Strands hook re-checks every send, whoever calls it."), 11.0))

    c, v, r, rp = ev["classification"], ev["verifier"]["part_a"], ev["redteam"], ev["replay"]
    vb = ev["verifier"]["part_b"]
    S.append(("10_evals", page(
        "<div class='wrap' style='top:60px'><div class='kicker'>Evals · python -m evals.run_all</div>"
        "<table>"
        f"<tr><td>Band classification on real JPS thresholds + every live data fault</td><td class='n'>{c['passed']}/{c['total']}</td></tr>"
        f"<tr><td>Injected hallucinations rejected by the verifier</td><td class='n'>{v['caught']}/{v['total']}</td></tr>"
        f"<tr><td>Correct paraphrases accepted (no over-blocking)</td><td class='n'>{v['controls_accepted']}/{v['controls_total']}</td></tr>"
        f"<tr><td>Always-bad model: graph fails closed to a verified template</td><td class='n'>{vb['fail_closed']}/{vb['total_each']}</td></tr>"
        f"<tr><td>Attacks on the send path blocked (incl. prompt injection)</td><td class='n'>{r['blocked']}/{r['total']}</td></tr>"
        f"<tr><td>48 h replay: cycles that never called a model</td><td class='n'>{rp['quiet_cycles_no_model_call']}/{rp['cycles']}</td></tr>"
        f"<tr><td>48 h replay: every escalation delivered (Waspada → Amaran → Bahaya)</td><td class='n'>yes · 5 min</td></tr>"
        "</table></div>",
        "Every number is reproducible offline in about 20 seconds. Each attack and error is listed in the repo."), 14.0))

    S.append(("11_learned", page(
        "<div class='wrap'><div class='kicker'>What the evals caught while building</div>"
        "<p class='lead' style='font-size:36px;line-height:1.55'>"
        "• My guard blocked my own disclaimer: \"Bukan <b>amaran rasmi</b>\".<br>"
        "• My first rate limit would have silenced an Amaran → Bahaya escalation.<br>"
        "• My first replay asked the coordinator to approve 18 briefs that could never be sent.<br>"
        "• \"tahap Bahaya\" slipped past the verifier because \"1.80 m to Bahaya\" was allowed.</p></div>",
        "Model decides how to say it. Code decides what is true, whether anything is sent, and to whom."), 12.0))

    S.append(("12_real", page(
        "<div class='wrap'><div class='kicker'>What is real</div>"
        "<p class='lead' style='font-size:34px;line-height:1.55'><b>Real:</b> JPS stations, thresholds and faults captured 1 Nov 2026; "
        "the Strands graph, interrupt, persistence and hooks; every eval number.<br><br>"
        "<b>Simulated:</b> coordinator and community personas, placeholder relief centres, the replayed rise. "
        "No agency has adopted this yet. Not an official warning.</p>"
        "<p class='lead' style='margin-top:50px;color:#7fd3f0;font-size:40px'>github.com/ShermaineYap/Strands-SDK</p></div>",
        "JagaSungai · Strands Agents SDK · Amazon Bedrock AgentCore · Apache-2.0"), 10.0))
    return S


def render() -> Path:
    OUT.mkdir(exist_ok=True)
    arch = (ROOT / "docs" / "architecture.png").resolve()
    files = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        for name, content, dur in scenes():
            jpg = OUT / f"{name}.jpg"
            if content == "ARCH":
                content = page(f"<div style='position:absolute;left:0;right:0;top:20px;bottom:150px;background:#fff;"
                               f"display:flex;align-items:center;justify-content:center'><img src='file://{arch}' "
                               f"style='max-width:1880px;max-height:900px'></div>",
                               "One model node out of seven. Graph, not Swarm: crossing, truth and sending are never the model's call.")
            src = OUT / f"{name}.html"
            src.write_text(content)
            pg.goto(f"file://{src}")
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(jpg), type="jpeg", quality=92)
            files.append((name, jpg, dur))
        b.close()

    parts = []
    for name, jpg, dur in files:
        tmp, final = OUT / f"{name}.tmp.mp4", OUT / f"{name}.mp4"
        fade_out = dur - 0.4
        vf = (f"format=yuv420p,loop=-1:1,trim=duration={dur},fade=t=in:st=0:d=0.4,"
              f"fade=t=out:st={fade_out}:d=0.4,setpts=PTS-STARTPTS")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(jpg), "-vf", vf,
                        "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        str(tmp)], check=True)
        os.replace(tmp, final)
        parts.append(final)
    lst = OUT / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    video_only = OUT / "video.tmp.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(video_only)], check=True)
    # silent stereo track: some platforms reject videos with no audio stream
    final = HERE / "jagasungai_demo.mp4"
    tmp = HERE / "jagasungai_demo.tmp.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_only), "-f", "lavfi", "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-shortest", str(tmp)], check=True)
    os.replace(tmp, final)
    return final


if __name__ == "__main__":
    print(render())

<!--
HOW TO USE THIS FILE
1. Builder Center → hackathon → "Your project" → Start your project.
2. Title and Description fields: copy from the two blocks below (limits: 255 / 512 characters).
3. Body: copy everything under "BODY STARTS HERE". Paste via a Markdown preview (e.g. GitHub's rendered view)
   so headings, tables and code blocks keep their formatting. Upload docs/architecture.png where marked.
4. Replace every ⟦…⟧ placeholder. Search for "⟦" before publishing; there must be none left.
5. Cover image: docs/cover.jpg (1200×675, no text). Repo link field: https://github.com/ShermaineYap/Strands-SDK
6. Tags (max 5): strands · amazon-bedrock · agentic-ai · generative-ai · plus a climate/sustainability tag if offered.
-->

**Title (≤255):**

JagaSungai: verified flood briefs for cut-off communities, built with Strands Agents

**Description (≤512):**

A Strands Agents graph that watches Malaysia's official JPS river gauges and, when a threshold is crossed, drafts a plain Bahasa Melayu/English brief for a flood coordinator in Gua Musang. It checks every number against the readings and only sends over WhatsApp after the coordinator replies YA. 33/33 injected hallucinations caught, 32/32 send-path attacks blocked, and 181 of 192 replay cycles needed no model call.

---

BODY STARTS HERE

## Demo and links

🎬 **Demo video (under 3 min):** ⟦YouTube URL⟧
💻 **Code (Apache-2.0):** https://github.com/ShermaineYap/Strands-SDK
📊 **Every eval, attack and injected error:** https://github.com/ShermaineYap/Strands-SDK/blob/main/results/EVALS.md

⟦Insert docs/architecture.png here⟧

> The model decides how to say it. Code decides what is true, whether anything is sent, and to whom.

## The problem, and who has it

I live in Kuala Lumpur, and every Northeast Monsoon the news from Kelantan looks the same: roads cut, villages isolated, people moved to relief centres (PPS) late at night. In Gua Musang, about 10,000 Temiar Orang Asli live in posts like Pos Bihai, Pos Belatim and Kuala Betis, and the road to them is the first thing to go. In December 2025, floods displaced more than 1,000 Orang Asli across five Gua Musang villages. Across Malaysia, the 2024–25 monsoon put 40,922 families into 633 relief centres.

What surprised me is that the data to warn these communities is already public. JPS updates every river gauge every 15 minutes on Public InfoBanjir, and each station has four official thresholds: **Normal, Waspada (Alert), Amaran (Warning), Bahaya (Danger)**. But that is a table of 28 Kelantan stations, not a decision. Someone with signal (a JAKOA officer, a Tok Batin, an NGO volunteer) has to know which upstream gauge matters, read it correctly at 2 a.m., and turn it into instructions people will trust.

When I scraped the live table on 1 November 2026, it also showed me how easy it is to read wrongly. **Two of the four gauges that matter for Gua Musang were unusable.** One reported `-9,999.00` (a sensor fault), and the other had placeholder thresholds of `310 / 315 / 320 m`. Six other Kelantan stations had the same placeholder problem (7 of 28 in total). A naive reader would either raise a false alarm or tell people a broken gauge is "normal".

## What the coordinator actually gets

When nothing has crossed a threshold, nothing happens: no message and no model call. When Sg. Galas at Kg. Lembaga crosses Amaran, the coordinator receives this draft:

```
*JagaSungai · 03/11 10:05*
Kuala Betis & pos-pos Orang Asli, Gua Musang: paras tertinggi Amaran di Sg. Galas di Kg. Lembaga (F1)

• Sg. Nenggiri di Bertam (F1): tiada data boleh dipercayai (tiada paras ambang sah).
• Sg. Galas di Limau Kasturi: 57.20 m, tahap Waspada. 2.80 m lagi ke Amaran.
• Sg. Galas di Kg. Pulai (F1): tiada data boleh dipercayai (sensor rosak).
• Sg. Galas di Kg. Lembaga (F1): 86.10 m, tahap Amaran. 1.80 m lagi ke Bahaya.

*Tindakan:*
1. Bersedia untuk berpindah. Bawa warga emas, OKU dan kanak-kanak ke tempat tinggi dahulu.
2. Jangan menyeberang sungai atau jalan yang dinaiki air.
3. Hubungi pegawai daerah / JKM untuk status PPS dan pengangkutan.

Ringkasan JagaSungai berdasarkan bacaan tolok JPS awam. Bukan amaran rasmi; ikut arahan pihak berkuasa.
```

They reply **YA** and it goes to the community list, or **TIDAK** and it is dropped. Three details matter:

* Broken gauges say "tiada data boleh dipercayai" (no reliable data) and never "normal".
* The actions are not written by the model. They come from a fixed library, chosen by the highest band, that an agency can review in advance.
* Every message says it is a summary of public readings and not an official warning.

## Social impact

| What | Result | Measured by |
|---|---|---|
| Band classification on real JPS thresholds, at every boundary, plus every live data fault | **77/77** | `evals/eval_classify.py` |
| Injected hallucinations stopped before reaching the coordinator | **33/33** | `evals/eval_verifier.py` |
| Correct paraphrases accepted (the checker doesn't just block everything) | **5/5** | `evals/eval_verifier.py` |
| Attacks on the send path blocked | **32/32** | `evals/eval_redteam.py` |
| 48 h replay: every escalation (Waspada → Amaran → Bahaya) delivered | **yes**, drafted in the same 15-min cycle, delivered 5 min later | `evals/eval_replay.py` |
| 48 h replay: cycles that needed no model call | **181 of 192** | `evals/eval_replay.py` |
| Nova 2 Lite, measured: first-draft pass rate / cost per brief | ⟦x/y⟧ / ⟦US$…⟧ | `scripts/smoke_bedrock.py`, `evals.run_all --bedrock` |

For the coordinator, this means a brief arrives in the same 15-minute cycle in which a gauge crosses a threshold. It names the real stations, it is in Bahasa Melayu, it carries reviewed actions, and it is honest about broken gauges. They are never asked to approve twice in an hour unless the river gets worse. In the 48-hour replay they approved 11 briefs, and all 11 were delivered.

Reach: a community is a YAML file listing its station IDs, so any of the 28 Kelantan gauges (and any state page on InfoBanjir) can be onboarded without code. The repo ships two: Gua Musang and Kuala Krai.

## Technical execution: how it uses Strands Agents

JagaSungai is a Strands **Graph** with seven nodes, and only one of them calls a model.

1. **ingest** (code) scrapes the InfoBanjir water-level and rainfall tables, MET warnings and JKM relief-centre counts.
2. **classify** (code) applies each station's four JPS thresholds and detects sensor faults, placeholder thresholds and stale readings. It decides whether anything is worth saying: a band rose, Amaran or above, a fast rise near the next band, or a MET rain warning for the area.
3. A **conditional edge** sends quiet cycles to a `quiet` node. No model is called, which was 181 of 192 cycles in the replay.
4. **write** is a Strands `Agent` on **Amazon Nova 2 Lite** with `structured_output_model=FloodBrief`. It receives only the classified facts as JSON and must return typed fields: station ID, level, band, and a sentence in BM and English.
5. **verify** (code) checks every number, time, river name, band word and station against the facts. It rejects false reassurance and any claim to be an official warning. A rejected draft goes **back to `write` with the exact errors** (a cycle with `reset_on_revisit`, at most three attempts). After that the graph **fails closed** to a template brief built only from code, and that template is verified too.
6. **finalize** (code) adds the reviewed actions, the nearest relief centre from the profile, and the disclaimer.
7. An **`ApprovalGate` hook on `BeforeNodeCallEvent` interrupts the graph** before `dispatch`. The interrupted graph is persisted with a **session manager** (`S3SessionManager` in production), and the coordinator's WhatsApp reply resumes it in a different process minutes later.
8. **dispatch** (code) calls the `send_brief` tool directly. A **`DispatchGuard` hook on `BeforeToolCallEvent`** re-checks every send against stored state: recipient on the allowlist, draft approved, text identical to what was approved, approval within 60 minutes, at most one brief an hour unless the river escalated, no forbidden phrases, disclaimer present. If any check fails, `cancel_tool` blocks the send.

**Why a Graph and not a Swarm?** In a Swarm, agents decide who acts next. The decisions that matter here are whether a threshold was crossed, whether a draft is true, and whether to send, and those should never be a model's call. So the flow is a developer-defined graph, and the model sits in one node.

**Why not voice?** The coordinators read Malay. Nova Sonic had no Malay voice and no Southeast Asian region when I built this, so text on WhatsApp was the more useful channel.

**Testing without a network.** I implemented the Strands `Model` interface as a deterministic `ScriptedModel`. The test suite drives the real agent loop, structured-output tool, graph cycles, interrupts and hooks offline. It can also inject deliberately wrong drafts to measure the verifier.

## How it is built on AWS

* **Amazon Bedrock**: Nova 2 Lite through the `global.` inference profile from ap-southeast-1
* **Amazon Bedrock AgentCore Runtime** (ap-southeast-1): `BedrockAgentCoreApp` entrypoint with `poll`, `reply` and `status` actions
* **AgentCore Observability**: OpenTelemetry traces of each graph run in CloudWatch ⟦insert trace screenshot⟧
* **Amazon EventBridge Scheduler → AWS Lambda**: `InvokeAgentRuntime` every 15 minutes (Asia/Kuala_Lumpur)
* **Amazon S3**: state, snapshots and Strands graph sessions
* **AWS End User Messaging Social**: WhatsApp out, with inbound replies via SNS → Lambda → `{"action": "reply"}` ⟦or: "Telegram during the hackathon while my WhatsApp Business Account was in review"⟧

## Originality: beyond the workshop

The workshop builds a customer-service agent: an agent loop with tools, then hooks, sessions, multi-agent patterns and an AgentCore deploy. I used every one of those building blocks, but inverted who is in charge:

* The LLM is **one node out of seven**. Ingest, classification, verification, composition and dispatch are code.
* The **verifier loop** sits inside the graph, with targeted feedback and a fail-closed path that is itself verified.
* **Human approval is a persisted graph interrupt**, not an `if` statement around the agent.
* **Hooks are policy, not logging.** The guard re-reads stored state on every send, so it holds even if someone calls the tool directly.
* It runs on **real, messy government data**, with a parser and fault detector written against live captures.

## Evals and red-teaming

All numbers are reproducible with `python -m evals.run_all` (about 20 seconds, offline) and listed case by case in `results/EVALS.md`.

* **Classification (77/77):** eight Kelantan stations with valid thresholds, each tested at 8 positions around its thresholds (1 cm below, exactly at, above), plus all 8 live data faults and 5 synthetic ones (stale, missing timestamp, blank level, thresholds out of order, station missing).
* **Verifier (33/33 caught, 5/5 controls accepted):** wrong levels, escalated or downgraded bands, an invented station, a broken gauge called normal, "selamat untuk tinggal", "no need to evacuate", "official warning", invented forecasts, rainfall and times, links, phone numbers, and a prompt-injection echo.
* **Verifier inside the real graph:** bad draft then good draft keeps the model text after one retry (33/33), and an always-bad model fails closed to the template after three attempts (33/33).
* **Red team (32/32 blocked):** unlisted and malformed numbers, no draft, an unapproved draft, TIDAK and ambiguous replies ("YA? tunggu" does not count), wrong approval ID, approval after 95 minutes, text altered after approval, a tampered stored draft, a stripped disclaimer, a duplicate recipient, a second brief within the hour, an over-long message, a prompt injection planted in a scraped station name, a model that obeys that injection, and a model that impersonates NADMA.

## What is real, and disclosures

* **Real:** JPS station IDs, thresholds and data faults (captured from Public InfoBanjir on 1 Nov 2026), the parsers, the live `status` command, the Strands graph, interrupt, persistence and hooks, and every eval number above.
* **Simulated:** the coordinator and community personas, the relief-centre entries (placeholders until replaced by the district JKM list), and the water levels in the replay (real thresholds, synthetic rise). **No JAKOA office, Tok Batin or NGO has adopted this yet.**
* **The evals use a deterministic stand-in model**, so they measure the guarantees the code makes whatever the model writes. Nova's own numbers are in the table row marked "measured".
* Public InfoBanjir has no published API or terms for automated access. I fetch each page at most once per 15 minutes with an identifying User-Agent, and the scraper can be replaced by an official API in one module.
* JagaSungai never tells anyone they are safe, never tells anyone not to evacuate, and does not replace JPS, MET, NADMA or district instructions.

## Challenges and what I learned

My own evals caught several of my mistakes, and these are the parts I am proudest of:

* **The guard blocked my first real message.** My disclaimer, "Bukan *amaran rasmi*", contains the forbidden phrase "amaran rasmi". The fix was to scan everything except the code-owned disclaimer, and it made me trust the guard more, not less.
* **My first rate limit was unsafe.** "One brief per hour" would have silenced an Amaran → Bahaya escalation 30 minutes after the last brief. Escalations now bypass it.
* **My first replay pestered the coordinator.** 18 of 32 drafts were approved and then blocked by the rate limit. The same rule now also runs upstream in `classify`, with the guard as the backstop: 11 drafts, 11 sent.
* **My verifier had a one-band blind spot.** A draft saying a station was at "tahap Bahaya" passed the band check, because "Bahaya" is legitimately mentioned in "1.80 m lagi ke Bahaya". The verifier now checks *claims* ("tahap X", "X level") against the station's real band. I found this while recording the demo video, and it is now three of the 33 eval cases.
* **Government data needs a fault detector before it needs an LLM.** A quarter of Kelantan's gauges (7 of 28) had placeholder thresholds the night I captured them, and one more reported -9,999.
* **Strands made the safety architecture cheap.** A custom node is a small class, a conditional edge is a lambda, and an approval step is one hook calling `event.interrupt()`, which the session manager persists for free.

## Path to adoption

The people who would run JagaSungai are not developers: a district JAKOA office, an NGO already working with Orang Asli communities, or a mosque or village committee with one person who keeps signal during floods. The design is aimed at them:

* **Onboarding a community is a YAML file**: station IDs from InfoBanjir, a coordinator number, the district's relief-centre list. No code changes.
* **Running cost scales with floods, not with time.** Quiet cycles make no model call (181 of 192 in the replay), so most of the year the cost is a scheduler, a few seconds of runtime per cycle, and S3.
* **Nothing is sent without a named human approving it**, which is what a disaster-response agency needs before putting its name near an automated message.
* **It runs in one AWS account.** A non-profit could host it on AWS Social Impact Credits, for one district or many.

## What's next

1. Swap the placeholder relief centres for the district JKM list and add Amazon Location Service routes.
2. Tamil and Mandarin through Amazon Translate, with the verifier re-run on the translation.
3. Coordinator voice notes through Amazon Transcribe `ms-MY` as typed field reports.
4. A pilot with one coordinator during the 2026–27 monsoon. If you work with a community in a flood-prone area, I would love to talk.

## Try it in five minutes

```bash
git clone https://github.com/ShermaineYap/Strands-SDK && cd Strands-SDK
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt pytest
python -m jagasungai.cli status   # live Gua Musang gauges right now
python -m jagasungai.cli demo     # a full rise → draft → approval → dispatch, offline
python -m evals.run_all           # every number in this article
```

*Data: JPS Public InfoBanjir; MET Malaysia via data.gov.my (CC BY 4.0); JKM InfoBencana. Flood statistics: Malaysiakini, Malay Mail (17 Dec 2025), ReliefWeb (FL-2024-000218-MYS). JagaSungai is independent and not affiliated with these agencies.*

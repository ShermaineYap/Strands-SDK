# Your submission checklist (only you can do these)

Deadline: **Wed 4 Nov 23:59 PST = Thu 5 Nov 15:59 MYT.** Treat **Thu 5 Nov 12:00 MYT** as the hard stop,
and aim to publish by **Wed 4 Nov evening MYT**. Builder Center locks publishing at the end time, and the
moderation scan must pass first.

## ⚠️ 0. Eligibility (do first)

The hackathon Terms exclude "individuals living in … Malaysia". Before investing more time, post on the
hackathon's **Discussion** tab:

> "Can a Malaysia-resident builder participate as a non-leader member of a team led by an eligible-country
> resident? Is there a required hashtag or tag for submissions?"

If the answer is no, everything below still gives you a complete, public portfolio piece. Do not misstate
your country of residence: it is verified against your profile and can disqualify even after winning.

## 1. Workshop (required, inside the window)

- [x] Builder Center → Build → Workshops → free sandbox → **Building AI Agents with Strands SDK: From Simple Loops to Multi-Agent Swarms**
- [x] Request the sandbox (one per week; **the quota reset today, Sun 1 Nov**). It lasts 8 hours from the "ready" email.
- [x] Finish **all** modules (done 1 Nov: Modules 1–7 executed; Module 4 patched for Strands 1.63; Module 5 deployed and invoked on AgentCore) (~2 h). Screenshot each completed module and your "Your Workshops" tab.
- [ ] While the sandbox is open (Bedrock enabled), you can also run `scripts/smoke_bedrock.py` there if your own account is not ready.

## 2. AWS (your own account), about 1–2 h

- [ ] Budget alarm (US$20). Bedrock model access for **Amazon Nova 2 Lite** in **ap-southeast-1**.
- [ ] `python scripts/smoke_bedrock.py`. Copy the output (pass/fail per attempt, tokens, cost).
- [ ] `python -m evals.run_all --bedrock`. Commit the updated `results/EVALS.md`.
- [ ] Deploy to AgentCore Runtime (`docs/DEPLOY.md` step 3). Run `agentcore invoke '{"action": "poll"}'` and **screenshot the Observability trace**.
- [ ] Optional: `sam deploy` for the 15-min scheduler (step 4). Optional: WhatsApp (step 5) or the Telegram fallback.

## 3. Fill the article placeholders (`docs/ARTICLE.md`, search for ⟦)

- [x] YouTube URL (https://youtu.be/aWROx7sH9GU)
- [ ] Nova first-draft pass rate and cost per brief (from step 2)
- [ ] Trace screenshot
- [x] WhatsApp status stated honestly (console channel in demo)
- [x] If you did **not** deploy to AgentCore, change "How it is built on AWS" to say the runtime entrypoint and
      templates are included but were run locally. Don't claim a deployment you didn't do.

## 4. Video

- [x] Upload `docs/video/jagasungai_demo.mp4` (2:18) as **Public** on YouTube, or record the narrated version in `docs/VIDEO_SCRIPT.md`.
- [x] Check it from a logged-out browser (oEmbed public).

## 5. Publish on Builder Center

- [x] Join the hackathon if you haven't yet → **Your project** → Start your project
- [x] Title and Description from `docs/ARTICLE.md` (limits 255 / 512)
- [x] Body: paste (external images are rejected by Builder Center; diagram is linked) from a rendered Markdown view; upload `docs/architecture.png` where marked
- [ ] Cover: `docs/cover.jpg` (1200×675, no text)
- [x] Repo link: https://github.com/ShermaineYap/Strands-SDK (make sure the repo is **public**)
- [x] Tags (max 5): strands, amazon-bedrock, agentic-ai, generative-ai, + a climate/sustainability tag if offered
- [ ] Preview → check every link → **Publish** (publishing = submitting)
- [ ] Open the published page logged out. Post the link on the Discussion tab.

## 6. Keep consistent

If any number changes after a Bedrock run, update it in **README.md, docs/ARTICLE.md and the video** together.
An AI judge compares all three against the repo.

# Demo video

**Ready now:** `docs/video/jagasungai_demo.mp4` (2:18, 1920×1080, silent with burnt-in captions, no music).
Every screen is built from real program output by `docs/video/build.py`. You can upload it as-is.

**Stronger:** once the agent is deployed, re-record two shots with the real thing (an AgentCore trace and
your phone) and add your voice. The judges' rubric rewards "showing the agent working", and a real trace
plus a real phone is the most convincing proof. Keep it under 2:50 so judges never hit the 3:00 limit.

## Rules for the upload

* YouTube, **Public** (not Unlisted), and open the link from a logged-out browser to check.
* No music and no third-party logos. Hide browser tabs and bookmarks bars with brand icons.
* Paste the link at the top of the article, in "Demo and links".

## Narrated version (≈ 2:45). Speak slowly; 140 words per minute is plenty.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:12 | Title card (`build/01_title.jpg`) | "This is JagaSungai. It watches Malaysia's official river gauges for communities that get cut off by floods, like the Temiar Orang Asli posts in Gua Musang, where floods displaced more than a thousand people last December." |
| 0:12–0:27 | Public InfoBanjir Kelantan page in the browser | "JPS publishes every gauge every 15 minutes, with four official thresholds. But it's a table of 28 stations. Someone has to know which gauge matters and read it right at 2 a.m." |
| 0:27–0:45 | Terminal: `python -m jagasungai.cli status` | "Here's JagaSungai reading Gua Musang's gauges live. Two of the four are broken tonight: one reports minus 9,999, one has placeholder thresholds. It says 'no reliable data', never 'normal'." |
| 0:45–1:00 | Architecture diagram | "It's a Strands graph with seven nodes. Only one calls a model, Amazon Nova. Code classifies, verifies and decides whether anything is sent. Hooks are the hard boundaries." |
| 1:00–1:30 | **AgentCore Observability trace** of a cycle with a rejected first draft (or `build/05`–`07`) | "When a gauge crosses Amaran, the writer agent drafts a brief as structured output. This first draft claimed Danger and said people were safe to stay home. The verifier caught both and sent it back. The second draft passes, and the graph pauses for a human." |
| 1:30–1:55 | **Your phone**: draft arrives, you reply YA, the brief arrives on the second phone | "The coordinator gets the draft in Bahasa Melayu, with reviewed actions and a clear 'not an official warning'. One word, YA, resumes the graph in another process and it's sent." |
| 1:55–2:10 | Terminal: a denied send (`build/09_sent.jpg`) | "Anything that calls the send tool goes through a Strands hook: allowlist, approved text only, approval freshness, rate limit, forbidden phrases." |
| 2:10–2:30 | `python -m evals.run_all` output (`build/10_evals.jpg`) | "33 of 33 injected hallucinations caught, 32 of 32 attacks blocked, and in a 48-hour replay, 181 of 192 cycles never called a model. Every escalation was delivered." |
| 2:30–2:45 | What-is-real card (`build/12_real.jpg`) | "The personas and shelters are simulated, and no agency uses this yet. It's not an official warning. The code is open source. Thanks for watching." |

## Recording tips

* OBS Studio (free): one scene for the screen and one for the phone (phone mirroring, or film it with a second phone).
* For the live run: deploy, then make a crossing happen on demand by temporarily lowering a threshold in
  a copy of the profile, or run `python -m jagasungai.cli demo` locally with `JAGASUNGAI_CHANNEL=telegram`
  to receive the message on your own phone.
- To rebuild the silent video after editing captions: `python docs/video/build.py` (needs Playwright + ffmpeg).

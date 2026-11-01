# Deploying JagaSungai to AWS

Everything in this repo runs offline (`python -m jagasungai.cli demo`, `pytest`, `python -m evals.run_all`).
This guide takes it to a deployed agent: Amazon Bedrock AgentCore Runtime in **ap-southeast-1 (Singapore)**,
polled every 15 minutes by EventBridge Scheduler, with WhatsApp through AWS End User Messaging Social.

> Honest status: the deployment files in this repo (`agentcore/app.py`, `lambdas/`, `infra/template.yaml`)
> were written and statically checked (imports, `cfn-lint`, payload parsing) but have not been deployed
> by the author yet. Steps 1–3 are the minimum for the hackathon demo; 4–5 add the scheduler and WhatsApp.

## 0. Prerequisites

* An AWS account (Free Tier is fine) with a budget alarm (e.g. US$20).
* Python 3.11+, Node 20+, `uv`, AWS CLI v2, configured credentials (`aws configure`).
* Bedrock model access in **ap-southeast-1** for **Amazon Nova 2 Lite**. From Malaysia/Singapore it is
  reached through the cross-region profile `global.amazon.nova-2-lite-v1:0`. Fallback:
  `apac.amazon.nova-pro-v1:0` (set `JAGASUNGAI_MODEL_ID`). Hackathon/workshop credits cover Nova only.

## 1. Smoke-test Bedrock locally (5 minutes)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
export AWS_REGION=ap-southeast-1
python scripts/smoke_bedrock.py            # one real Nova call -> FloodBrief -> verifier verdict, tokens, cost
python -m jagasungai.cli status            # live InfoBanjir readings for Gua Musang, no model
python -m jagasungai.cli cycle --model bedrock   # full graph locally with Nova, console "WhatsApp"
python -m jagasungai.cli approve --reply YA      # resume the interrupted graph
python -m evals.run_all --bedrock          # adds measured Nova tokens and cost to results/EVALS.md
```

Save the output of `smoke_bedrock.py` and `run_all --bedrock`; the article quotes them.

## 2. Create the state bucket

```bash
aws s3 mb s3://jagasungai-state-<your-suffix> --region ap-southeast-1
```

(Or deploy `infra/template.yaml` in step 4, which creates an encrypted private bucket for you.)

## 3. Deploy the agent to AgentCore Runtime

This follows the workshop's Module 5 flow (`create → add → copy code → uv → deploy`). The new CLI is on
npm (`@aws/agentcore`, Node 20+); remove the old `bedrock-agentcore-starter-toolkit` if installed.

```bash
sudo npm install -g @aws/agentcore
pip uninstall -y bedrock-agentcore-starter-toolkit

agentcore create                      # project name e.g. jagasungai; "What would you like to build?" -> Skip
cd jagasungai
agentcore add                         # agent -> Name JagaSungai -> Bring my own code -> default app/JagaSungai/
                                      # -> entrypoint main.py -> Direct Code Deploy -> Amazon Bedrock -> defaults
bash ../scripts/package_agentcore.sh app/JagaSungai   # copies main.py, jagasungai/, profiles/ and writes pyproject.toml
# set "region": "ap-southeast-1" in agentcore/aws-targets.json
agentcore deploy                      # zips to S3 (no container) and provisions via CloudFormation
agentcore invoke '{"action": "status"}'
agentcore invoke '{"action": "poll"}'
agentcore logs                        # runtime logs; traces via `agentcore traces` once Transaction Search is on
```

`agentcore deploy` builds from a `pyproject.toml` in the agent folder; a `requirements.txt` alone fails with
"Required project file not found". `agentcore dev` needs a local browser, so test with `invoke` on remote IDEs.
Enable CloudWatch **Transaction Search** once per account (CloudWatch → Application Signals → Transaction search)
to see spans on the GenAI Observability page.

Set these environment variables on the runtime (CLI config or console):

| Variable | Value |
|---|---|
| `JAGASUNGAI_BUCKET` | the bucket from step 2/4 |
| `JAGASUNGAI_PROFILES` | `gua_musang,kuala_krai` |
| `JAGASUNGAI_APPROVERS` | `{"+60XXXXXXXXX": "gua_musang"}` (coordinator number → profile) |
| `JAGASUNGAI_ALLOWLIST` | comma list of broadcast numbers (start with your own) |
| `JAGASUNGAI_CHANNEL` | `console` first, then `whatsapp` or `telegram` |
| `JAGASUNGAI_MODEL_ID` | `global.amazon.nova-2-lite-v1:0` |
| `JAGASUNGAI_BEDROCK_REGION` | `ap-southeast-1` |

The runtime role needs: `bedrock:InvokeModel*` on the Nova profile, `s3:GetObject/PutObject/DeleteObject/ListBucket`
on the bucket, and (for WhatsApp) `social-messaging:SendWhatsAppMessage`.

Observability: AgentCore Runtime emits OpenTelemetry traces for the Strands graph to CloudWatch
(GenAI Observability). Screenshot one trace showing `ingest → classify → write → verify → finalize` for the article.

## 4. Scheduler and inbound handler

```bash
sam build -t infra/template.yaml
sam deploy --guided --region ap-southeast-1 \
  --parameter-overrides AgentRuntimeArn=<runtime-arn> InboundTopicArn=<sns-topic-arn-or-empty>
```

This creates the encrypted state bucket, a Lambda invoked every 15 minutes (Asia/Kuala_Lumpur) that calls
`InvokeAgentRuntime` with `{"action": "poll"}` and a 33+ character session ID, and, if you pass an SNS
topic, a Lambda that forwards coordinator replies as `{"action": "reply"}`.

## 5. WhatsApp (optional, needs Meta approval)

1. In **AWS End User Messaging Social** (ap-southeast-1 or ap-southeast-5), link a WhatsApp Business Account
   and a phone number; note the `phone-number-id-...`.
2. Set an SNS topic for inbound events and pass it as `InboundTopicArn` in step 4.
3. Set `JAGASUNGAI_CHANNEL=whatsapp`, `JAGASUNGAI_WA_PHONE_NUMBER_ID`, `JAGASUNGAI_WA_REGION`.
4. WhatsApp only allows free-form text within 24 h of the recipient's last message. For a pilot, have each
   recipient message the number first; for production, register a Utility template for the brief.

If Meta approval does not arrive in time, set `JAGASUNGAI_CHANNEL=telegram` and `JAGASUNGAI_TELEGRAM_TOKEN`
(a bot from @BotFather); the graph, guards and approval flow are identical. Say so in the article.

## Costs

* Quiet cycles (no threshold crossed) make no model call: 181 of 192 cycles in the 48 h replay.
* A brief is one Nova 2 Lite call (two or three if the verifier rejects a draft). Measure it with
  `scripts/smoke_bedrock.py`; Nova 2 Lite list price used in the code is US$0.30 / US$2.50 per million
  input/output tokens; check current pricing before quoting.
* AgentCore Runtime bills per active vCPU-second and GB-second; a cycle runs for well under a second of compute
  plus network time.

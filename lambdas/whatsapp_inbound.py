"""Inbound WhatsApp (AWS End User Messaging Social -> SNS -> this Lambda).

Each SNS record carries ``whatsAppWebhookEntry``: the Meta webhook entry as a JSON
string. Text replies from a registered coordinator are forwarded to the AgentCore
runtime as ``{"action": "reply"}``, which resumes the interrupted Strands graph.
"""

from __future__ import annotations

import json
import os
import uuid

import boto3

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


def _messages(sns_message: dict):
    entry = sns_message.get("whatsAppWebhookEntry")
    if isinstance(entry, str):
        entry = json.loads(entry)
    for change in (entry or {}).get("changes", []):
        for m in change.get("value", {}).get("messages", []):
            if m.get("type") == "text":
                yield "+" + m["from"].lstrip("+"), m["text"]["body"]


def handler(event, context):
    handled = 0
    for record in event.get("Records", []):
        msg = json.loads(record["Sns"]["Message"])
        for sender, text in _messages(msg):
            session = f"jagasungai-reply-{uuid.uuid4().hex}-{uuid.uuid4().hex[:8]}"
            resp = client().invoke_agent_runtime(
                agentRuntimeArn=os.environ["AGENT_RUNTIME_ARN"],
                runtimeSessionId=session,
                payload=json.dumps({"action": "reply", "from": sender, "text": text}).encode(),
            )
            print(resp["response"].read().decode()[:1000])
            handled += 1
    return {"handled": handled}

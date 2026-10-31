"""EventBridge Scheduler target: every 15 minutes, invoke the AgentCore runtime with a poll."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import boto3

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


def handler(event, context):
    # runtimeSessionId must be at least 33 characters
    session = f"jagasungai-poll-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex}"
    resp = client().invoke_agent_runtime(
        agentRuntimeArn=os.environ["AGENT_RUNTIME_ARN"],
        runtimeSessionId=session,
        payload=json.dumps({"action": "poll"}).encode(),
    )
    body = resp["response"].read().decode()
    print(body[:2000])
    return {"statusCode": 200, "session": session}

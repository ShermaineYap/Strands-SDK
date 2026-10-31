"""A deterministic stand-in for Bedrock, used by tests, evals and offline demos.

It implements the Strands ``Model`` interface and answers every request by
calling the structured-output tool with a payload produced by a Python
function. This lets the test-suite drive the *real* Strands agent loop,
structured-output tool, retries and hooks without network access, and lets
evals inject deliberately wrong drafts to measure the verifier.

It is never used in production; ``writer.make_model`` returns a BedrockModel.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterable, Callable
from typing import Any

from strands.models.model import Model

Script = Callable[[str, int], dict]


class ScriptedModel(Model):
    def __init__(self, script: Script, tool_name: str = "FloodBrief") -> None:
        self.script = script
        self.tool_name = tool_name
        self.calls = 0
        self.prompts: list[str] = []
        self.config: dict[str, Any] = {"model_id": "scripted"}

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> Any:
        return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):  # pragma: no cover
        payload = self.script(json.dumps(prompt, default=str), self.calls)
        self.calls += 1
        yield {"output": output_model.model_validate(payload)}

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncIterable[dict]:
        # If the last message is a tool result, the structured output was accepted: end the turn.
        last = messages[-1] if messages else {}
        if any("toolResult" in c for c in last.get("content", [])):
            yield {"messageStart": {"role": "assistant"}}
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": "done"}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            yield {"metadata": {"usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
                                "metrics": {"latencyMs": 0}}}
            return

        prompt_text = json.dumps(messages, default=str)
        self.prompts.append(prompt_text)
        payload = self.script(prompt_text, self.calls)
        self.calls += 1
        names = [t.get("name") for t in (tool_specs or [])]
        name = self.tool_name if self.tool_name in names else (names[0] if names else self.tool_name)
        body = json.dumps(payload)
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"t{self.calls}", "name": name}}}}
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": body}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}
        # Token counts approximate a real call so cost reporting has something to show offline.
        yield {"metadata": {"usage": {"inputTokens": len(prompt_text) // 4, "outputTokens": len(body) // 4,
                                      "totalTokens": (len(prompt_text) + len(body)) // 4},
                            "metrics": {"latencyMs": 0}}}

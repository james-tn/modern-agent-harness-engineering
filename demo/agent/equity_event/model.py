"""Deterministic chat client shared by baseline and governed runs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, FunctionInvocationLayer, Message
from agent_framework.observability import ChatTelemetryLayer

from .analysis import build_analysis_script

BRIEF_MARKER = "EQUITY_EVENT_BRIEF::"


class ScriptedEquityClient(FunctionInvocationLayer, ChatTelemetryLayer, BaseChatClient):
    """Offline model substitute that emits a plan and executable Python."""

    OTEL_PROVIDER_NAME = "scripted"

    def __init__(self, *, model_id: str = "equity-analyst-v1", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.model_id = model_id
        self.call_count = 0

    async def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        del options, kwargs
        if stream:
            raise NotImplementedError("The deterministic demo client is non-streaming.")
        self.call_count += 1
        prompt = "\n".join(str(getattr(item, "text", "")) for item in messages)
        payload = _extract(prompt)
        script = build_analysis_script(
            payload["data"],
            mode=payload["mode"],
            corrections=payload.get("corrections", []),
        )
        proposal = {
            "model_id": self.model_id,
            "mode": payload["mode"],
            "plan": [
                "Classify the event request and load relevant skills.",
                "Retrieve public evidence and approved internal context.",
                "Align the event to a trading date and compute benchmark-adjusted impact.",
                "Generate and execute a self-contained Python/SVG briefing.",
                "Verify evidence, calculations, policy, chart integrity, and approval.",
            ],
            "script": script,
            "model_completion_claim": True,
        }
        return ChatResponse(
            messages=[Message(role="assistant", contents=[json.dumps(proposal)])],
            model=self.model_id,
            response_id=f"equity-response-{self.call_count:03d}",
        )


def _extract(prompt: str) -> dict[str, Any]:
    start = prompt.rfind(BRIEF_MARKER)
    if start < 0:
        raise ValueError("Equity-event brief marker not found.")
    raw = prompt[start + len(BRIEF_MARKER) :].strip()
    return json.loads(raw)


def prompt_for(data: dict[str, Any], *, mode: str, corrections: list[str]) -> str:
    return (
        "Create an executable equity-event analysis. Return only the requested structured proposal.\n"
        + BRIEF_MARKER
        + json.dumps({"mode": mode, "data": data, "corrections": corrections}, separators=(",", ":"))
    )

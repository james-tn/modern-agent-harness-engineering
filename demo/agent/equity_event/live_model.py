"""Token-authenticated Azure Responses client; MAF emits model/tool telemetry."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

from agent_framework import ChatResponse, Message
from agent_framework.openai import OpenAIChatClient
from azure.identity import AzureCliCredential

from .live_trace import LiveTrace

DEFAULT_DEPLOYMENT = "gpt-5.6-terra"


class LiveEquityClient(OpenAIChatClient):
    def __init__(
        self,
        trace: LiveTrace,
        *,
        endpoint: str | None = None,
        deployment: str = DEFAULT_DEPLOYMENT,
        max_model_requests: int = 40,
        max_tool_calls: int = 60,
    ) -> None:
        endpoint = endpoint if endpoint is not None else os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not endpoint.strip():
            raise ValueError("Set AZURE_OPENAI_ENDPOINT to your Azure model resource endpoint before a live run.")
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith((".cognitiveservices.azure.com", ".openai.azure.com"))
            or parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            raise ValueError("Use an HTTPS Azure model resource endpoint without credentials or query parameters.")
        if not deployment.strip():
            raise ValueError("A model deployment name is required.")
        self.trace = trace
        self.request_count = 0
        self.max_model_requests = max_model_requests
        self.credential = AzureCliCredential()
        super().__init__(
            model=deployment,
            azure_endpoint=endpoint,
            credential=self.credential,
            function_invocation_configuration={
                "max_iterations": max_model_requests,
                "max_function_calls": max_tool_calls,
                "max_duration_seconds": 540,
                "max_consecutive_errors_per_request": 3,
                "include_detailed_errors": True,
            },
        )

    async def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatResponse:
        if stream:
            raise ValueError("The audited demo uses non-streaming calls.")
        if self.request_count >= self.max_model_requests:
            self.trace.record("model_budget_exhausted", limit=self.max_model_requests)
            raise RuntimeError("The episode exhausted its model-request budget.")
        self.request_count += 1
        return await super()._inner_get_response(
            messages=messages, options=options, stream=False, **kwargs,
        )

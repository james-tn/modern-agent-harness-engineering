"""Domain source adapters: deterministic snapshots plus optional live preflight."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class PublicResearchAdapter:
    root: Path
    retrieval_log: list[dict[str, Any]] = field(default_factory=list)

    def search_event(self, ticker: str, query: str) -> tuple[dict[str, Any], dict[str, Any]]:
        public = _read(self.root / "public-sources.json")
        market = _read(self.root / "market-prices.json")
        if public["event"]["ticker"] != ticker or market["ticker"] != ticker:
            raise LookupError(f"No checked-in event snapshot for {ticker}.")
        self.retrieval_log.append(
            {
                "adapter": "public-research",
                "operation": "search_event",
                "query": query,
                "mode": "recorded-primary-source-snapshot",
                "result_source_ids": [source["source_id"] for source in public["sources"]]
                + [market["source_id"]],
            }
        )
        return public, market

    @staticmethod
    def probe_official_reference(reference: dict[str, Any], *, timeout_seconds: int = 12) -> dict[str, Any]:
        request = urllib.request.Request(
            reference["url"],
            headers={
                "User-Agent": "modern-agent-harness-equity-demo/1.0",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content = response.read(1_000_000)
            return {
                "title": reference["title"],
                "url": response.geturl(),
                "status": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "bytes_read": len(content),
                "retrieved_at": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "used_for_fictional_facts": False,
            }


@dataclass
class MockInternalApi:
    root: Path
    access_log: list[dict[str, Any]] = field(default_factory=list)

    ENDPOINTS = {
        "mock://portfolio/v1/exposure": "internal-portfolio.json",
        "mock://research/v1/thesis/ACX": "internal-thesis.json",
        "mock://research-policy/v3/equity-event": "internal-policy.json",
        "mock://research/v1/lessons": "lessons.json",
    }

    def get(self, endpoint: str) -> dict[str, Any]:
        name = self.ENDPOINTS.get(endpoint)
        if name is None:
            raise LookupError(f"Unknown mock internal API endpoint: {endpoint}")
        payload = _read(self.root / name)
        if payload.get("api") != endpoint:
            raise ValueError(f"Fixture endpoint mismatch: expected {endpoint}, found {payload.get('api')}")
        self.access_log.append(
            {
                "adapter": "mock-internal-api",
                "operation": "GET",
                "endpoint": endpoint,
                "source_id": payload["source_id"],
                "classification": payload["data_classification"],
            }
        )
        return payload


def retrieve_episode_bundle(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    public_adapter = PublicResearchAdapter(root)
    public, market = public_adapter.search_event(
        "ACX",
        "latest ACX earnings release, filing, and adjusted event-window prices",
    )
    internal = MockInternalApi(root)
    portfolio = internal.get("mock://portfolio/v1/exposure")
    thesis = internal.get("mock://research/v1/thesis/ACX")
    policy = internal.get("mock://research-policy/v3/equity-event")
    lessons = internal.get("mock://research/v1/lessons")
    bundle = {
        "public": public,
        "market": market,
        "portfolio": portfolio,
        "thesis": thesis,
        "policy": policy,
        "lessons": lessons,
    }
    return bundle, [*public_adapter.retrieval_log, *internal.access_log]

"""Typed episode input and provenance records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sources import retrieve_episode_bundle


@dataclass(frozen=True)
class Claim:
    claim_id: str
    source_id: str
    status: str
    text: str
    evidence: str
    integrity: str
    confidentiality: str

    def to_dict(self) -> dict[str, str]:
        return {
            "claim_id": self.claim_id,
            "source_id": self.source_id,
            "status": self.status,
            "text": self.text,
            "evidence": self.evidence,
            "integrity": self.integrity,
            "confidentiality": self.confidentiality,
        }


@dataclass
class EpisodeData:
    root: Path
    event: dict[str, Any]
    public_sources: list[dict[str, Any]]
    market: dict[str, Any]
    portfolio: dict[str, Any]
    policy: dict[str, Any]
    thesis: dict[str, Any]
    lessons: dict[str, Any]
    claims: list[Claim] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    retrieval_log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ticker(self) -> str:
        return str(self.event["ticker"])

    @property
    def event_id(self) -> str:
        return str(self.event["event_id"])

    def model_payload(self, *, governed: bool, admitted_claim_ids: set[str] | None = None) -> dict[str, Any]:
        claims = [c.to_dict() for c in self.claims]
        if governed and admitted_claim_ids is not None:
            claims = [c for c in claims if c["claim_id"] in admitted_claim_ids]

        position = dict(self.portfolio["positions"][0])
        if governed:
            position = {
                "ticker": position["ticker"],
                "exposure_band": position["exposure_band"],
                "confidentiality": {"exposure_band": "internal"},
            }

        return {
            "data_classification": "synthetic-illustrative",
            "event": self.event,
            "claims": claims,
            "market": self.market,
            "position": position,
            "policy": self.policy,
            "thesis": self.thesis,
            "prior_lessons": self.lessons["lessons"],
        }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_episode(root: Path) -> EpisodeData:
    root = Path(root)
    bundle, retrieval_log = retrieve_episode_bundle(root)
    public = bundle["public"]
    market = bundle["market"]
    portfolio = bundle["portfolio"]
    policy = bundle["policy"]
    thesis = bundle["thesis"]
    lessons = bundle["lessons"]

    claims: list[Claim] = []
    for source in public["sources"]:
        for raw in source.get("claims", []):
            claims.append(
                Claim(
                    source_id=source["source_id"],
                    integrity=source["integrity"],
                    confidentiality=source["confidentiality"],
                    **raw,
                )
            )
    for raw in thesis["thesis"]:
        claims.append(
            Claim(
                source_id=thesis["source_id"],
                integrity="trusted",
                confidentiality=thesis["confidentiality"],
                **raw,
            )
        )

    files = [
        "public-sources.json",
        "market-prices.json",
        "internal-portfolio.json",
        "internal-policy.json",
        "internal-thesis.json",
        "lessons.json",
    ]
    records = [
        {
            "source_id": _read(root / name).get("source_id", "src-public-bundle" if name == "public-sources.json" else name),
            "artifact": f"demo/sample-input/{name}",
            "content_sha256": _sha(root / name),
            "classification": "synthetic-illustrative",
        }
        for name in files
    ]
    return EpisodeData(
        root=root,
        event=public["event"],
        public_sources=public["sources"],
        market=market,
        portfolio=portfolio,
        policy=policy,
        thesis=thesis,
        lessons=lessons,
        claims=claims,
        source_records=records,
        retrieval_log=retrieval_log,
    )

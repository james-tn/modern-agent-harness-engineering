"""REMEMBER: durable evidence and lesson state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..domain import Claim, EpisodeData


@dataclass
class EvidenceLedger:
    episode_id: str
    claims: dict[str, Claim] = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    lesson_candidates: list[dict] = field(default_factory=list)

    def ingest(self, episode: EpisodeData) -> None:
        self.claims = {claim.claim_id: claim for claim in episode.claims}
        self.sources = list(episode.source_records)

    def add_lesson_candidate(self, candidate: dict) -> None:
        if not any(item["lesson_id"] == candidate["lesson_id"] for item in self.lesson_candidates):
            self.lesson_candidates.append(candidate)

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "sources": self.sources,
            "claims": [claim.to_dict() for claim in self.claims.values()],
            "lesson_candidates": self.lesson_candidates,
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

"""REMEMBER: durable episode, approval, retry, and learning state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PENDING = "pending"
RUNNING = "running"
VERIFIED = "verified"
APPROVED = "approved"
PUBLISHED = "published"
FAILED = "failed"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class RunState:
    idempotency_key: str
    status: str = PENDING
    trace_id: str = ""
    plan: list[str] = field(default_factory=list)
    todos: list[dict] = field(default_factory=list)
    selected_skills: list[str] = field(default_factory=list)
    verifier_version: str = ""
    approval_receipt: str | None = None
    retry_count: int = 0
    lesson_candidates: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def record(self, event: str, **detail) -> None:
        self.events.append({"at": now(), "event": event, **detail})

    def to_dict(self) -> dict:
        return {
            "run": {
                "idempotency_key": self.idempotency_key,
                "status": self.status,
                "trace_id": self.trace_id,
                "retry_count": self.retry_count,
            },
            "plan": self.plan,
            "todos": self.todos,
            "selected_skills": self.selected_skills,
            "verifier_version": self.verifier_version,
            "approval_receipt": self.approval_receipt,
            "lesson_candidates": self.lesson_candidates,
            "events": self.events,
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "RunState | None":
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        run = raw["run"]
        state = cls(
            idempotency_key=run["idempotency_key"],
            status=run["status"],
            trace_id=run["trace_id"],
            retry_count=run.get("retry_count", 0),
        )
        for name in ("plan", "todos", "selected_skills", "lesson_candidates", "events"):
            setattr(state, name, raw.get(name, []))
        state.verifier_version = raw.get("verifier_version", "")
        state.approval_receipt = raw.get("approval_receipt")
        return state


def open_or_resume(path: Path, key: str) -> tuple[RunState, bool]:
    existing = RunState.load(path)
    if existing and existing.idempotency_key == key:
        if existing.status == PUBLISHED:
            return existing, True
        existing.retry_count += 1
        existing.record("run_resumed", retry_count=existing.retry_count)
        return existing, False
    return RunState(idempotency_key=key), False

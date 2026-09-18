"""EVOLVE: trace attribution, candidate lesson, approval, and replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .verifier import PATCHED_VERSION


def build_diagnosis(trace_id: str) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "observed_failure": "An after-close announcement was analyzed on the calendar date instead of the next trading day.",
        "attribution": [
            {
                "category": "Verification",
                "confidence": 0.96,
                "reason": "The original verifier recomputed the selected date but did not verify timestamp-to-session alignment.",
            },
            {
                "category": "Governance",
                "confidence": 0.88,
                "reason": "The approved methodology existed, but admission did not require a machine-checkable event-date rule.",
            },
        ],
        "candidate_lesson": {
            "lesson_id": "lesson-after-close-event-date",
            "scope": "event-date-alignment",
            "status": "candidate",
            "rule": "For after-close events, require the next valid trading day and verify the mapping independently.",
            "proposed_skill": "event-date-alignment/SKILL.md",
            "proposed_verifier": PATCHED_VERSION,
            "auto_applied": False,
        },
    }


def review_and_promote(diagnosis: dict[str, Any], *, approved: bool, replay_passed: bool) -> dict[str, Any]:
    lesson = dict(diagnosis["candidate_lesson"])
    if approved and replay_passed:
        lesson.update(
            {
                "status": "approved",
                "reviewer": "demo-research-methodology-reviewer",
                "approval_receipt": "lesson-approval-acx-001",
                "regression_replay": "passed",
                "promoted_to": "lessons/approved/event-date-alignment",
            }
        )
    else:
        lesson.update(
            {
                "status": "candidate",
                "regression_replay": "passed" if replay_passed else "failed",
                "promotion_blocked": "reviewer approval and a passing replay are both required",
            }
        )
    return lesson


def write_diagnosis(diagnosis: dict[str, Any], path: Path) -> Path:
    path.write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")
    return path

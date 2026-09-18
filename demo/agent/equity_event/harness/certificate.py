"""Evidence certificate emitted only after verification and approval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .policy import PolicyDecision
from .verifier import VerificationReport


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_certificate(
    *,
    event_id: str,
    trace_id: str,
    sources: list[dict[str, Any]],
    policy: PolicyDecision,
    verification: VerificationReport,
    approval_receipt: str,
    analysis_path: Path,
    dashboard_path: Path,
    script_path: Path,
) -> dict[str, Any]:
    if not verification.passed:
        raise ValueError("Cannot certify an unverified analysis.")
    if not approval_receipt:
        raise ValueError("Cannot certify without a reviewer approval receipt.")
    return {
        "certificate_type": "equity-event-completion-certificate",
        "event_id": event_id,
        "trace_id": trace_id,
        "source_snapshots": sources,
        "policy": {
            "policy_id": "equity-event-research-standard",
            "version": policy.version,
            "decision": policy.decision,
        },
        "verifier": verification.to_dict(),
        "approval_receipt": approval_receipt,
        "artifacts": {
            "analysis_sha256": sha256_file(analysis_path),
            "dashboard_sha256": sha256_file(dashboard_path),
            "generated_script_sha256": sha256_file(script_path),
        },
    }


def write_certificate(certificate: dict[str, Any], path: Path) -> Path:
    path.write_text(json.dumps(certificate, indent=2), encoding="utf-8")
    return path

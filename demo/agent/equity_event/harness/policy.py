"""GOVERN: internal research-policy and information-flow admission."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import EpisodeData

POLICY_ID = "equity-event-research-standard"
SINK = "shared-research-briefing"


@dataclass
class PolicyDecision:
    version: str
    decision: str = "allow_after_approval"
    admitted_claim_ids: list[str] = field(default_factory=list)
    excluded_claim_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    forbidden_fields: list[str] = field(default_factory=list)
    approval_required: bool = True

    def to_dict(self) -> dict:
        return {
            "policy_id": POLICY_ID,
            "version": self.version,
            "sink": SINK,
            "decision": self.decision,
            "approval_required": self.approval_required,
            "admitted_claim_ids": self.admitted_claim_ids,
            "excluded_claim_ids": self.excluded_claim_ids,
            "forbidden_output_fields": self.forbidden_fields,
            "reasons": self.reasons,
        }


def admit(episode: EpisodeData) -> PolicyDecision:
    rules = episode.policy["rules"]
    decision = PolicyDecision(
        version=episode.policy["version"],
        forbidden_fields=list(rules["forbidden_output_fields"]),
        approval_required=bool(rules["human_approval_required"]),
    )
    for claim in episode.claims:
        if claim.integrity not in {"trusted", "untrusted"} or claim.confidentiality not in {
            "public",
            "internal",
            "internal_only",
        }:
            decision.excluded_claim_ids.append(claim.claim_id)
            decision.reasons.append(f"{claim.claim_id}: unknown label; fail closed.")
        elif claim.integrity == "untrusted":
            decision.excluded_claim_ids.append(claim.claim_id)
            decision.reasons.append(f"{claim.claim_id}: untrusted commentary cannot drive the shared briefing.")
        elif claim.confidentiality == "internal_only":
            decision.excluded_claim_ids.append(claim.claim_id)
            decision.reasons.append(f"{claim.claim_id}: internal-only content is excluded.")
        else:
            decision.admitted_claim_ids.append(claim.claim_id)
    return decision

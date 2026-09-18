"""Regression tests for the Equity Event Impact Analyst harness."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from equity_event.analysis import execute_analysis_script
from equity_event.domain import load_episode
from equity_event.harness.capabilities import ALWAYS_ON, discover_skills, select_skills
from equity_event.harness.diagnosis import build_diagnosis, review_and_promote
from equity_event.harness.policy import admit
from equity_event.harness.state import FAILED, PUBLISHED, RunState, open_or_resume
from equity_event.harness.verifier import BASE_VERSION, PATCHED_VERSION, verify
from equity_event.progress import EpisodeProgress
from equity_event.runs import DuplicateRun, run_baseline, run_governed

REPO = Path(__file__).resolve().parents[3]
SAMPLE_INPUT = REPO / "demo" / "sample-input"
SKILLS = REPO / "demo" / "agent" / "skills"


def approve_for_test(_dashboard: Path, _report) -> str:
    return "test-reviewer"


@pytest.fixture(scope="module")
def episode():
    return load_episode(SAMPLE_INPUT)


@pytest.fixture(scope="module")
def baseline(episode, tmp_path_factory):
    return asyncio.run(run_baseline(episode, SKILLS, tmp_path_factory.mktemp("run-a")))


@pytest.fixture(scope="module")
def governed(episode, tmp_path_factory):
    return asyncio.run(
        run_governed(
            episode,
            SKILLS,
            tmp_path_factory.mktemp("run-b"),
            idempotency_key="test:acx-2026-q2",
            approval_provider=approve_for_test,
        )
    )


def test_01_all_episode_inputs_load(episode):
    assert episode.event_id == "acx-2026-q2-earnings"
    assert len(episode.source_records) == 6
    assert len(episode.retrieval_log) == 5
    assert sum(item["adapter"] == "mock-internal-api" for item in episode.retrieval_log) == 4


def test_02_all_inputs_are_synthetic(episode):
    assert all(item["classification"] == "synthetic-illustrative" for item in episode.source_records)


def test_03_claims_preserve_source_status(episode):
    statuses = {claim.status for claim in episode.claims}
    assert {"reported_fact", "management_guidance", "risk_disclosure", "external_commentary"} <= statuses


def test_04_market_prices_are_adjusted(episode):
    assert episode.market["adjusted"] is True
    assert episode.market["benchmark"] == "CHIP"


def test_05_internal_fields_are_typed(episode):
    labels = episode.portfolio["positions"][0]["confidentiality"]
    assert labels["exposure_band"] == "internal"
    assert labels["shares"] == "internal_only"


def test_06_filesystem_skill_catalog_is_complete():
    skills = discover_skills(SKILLS)
    assert len(skills) == 11
    assert all(skill.path.joinpath("SKILL.md").exists() for skill in skills)


def test_07_selection_defers_capabilities(episode):
    selection = select_skills(
        "analyze an earnings event, research sources and internal policy, calculate benchmark-adjusted "
        "portfolio impact, render an HTML chart, and verify evidence",
        SKILLS,
    )
    assert selection.deferred
    assert len(selection.selected) < 11
    assert {"event-date-alignment", "portfolio-impact"} <= set(selection.selected)


def test_08_policy_and_verification_skills_are_always_on():
    selection = select_skills("make a chart", SKILLS)
    assert ALWAYS_ON <= set(selection.selected)


def test_09_low_confidence_widens_safely():
    selection = select_skills("perform a task", SKILLS)
    assert selection.widened
    assert ALWAYS_ON <= set(selection.selected)


def test_10_policy_excludes_untrusted_causal_commentary(episode):
    decision = admit(episode)
    assert "claim-causal-rumor" in decision.excluded_claim_ids
    assert "claim-causal-rumor" not in decision.admitted_claim_ids


def test_11_governed_payload_strips_exact_position_fields(episode):
    decision = admit(episode)
    payload = episode.model_payload(governed=True, admitted_claim_ids=set(decision.admitted_claim_ids))
    assert payload["position"] == {
        "ticker": "ACX",
        "exposure_band": "medium (2%-5%)",
        "confidentiality": {"exposure_band": "internal"},
    }


def test_12_policy_requires_human_approval(episode):
    decision = admit(episode)
    assert decision.approval_required
    assert decision.decision == "allow_after_approval"


def test_13_baseline_self_declares_completion(baseline):
    assert baseline.analysis["self_declared_complete"] is True


def test_14_baseline_uses_wrong_calendar_event_date(baseline):
    assert baseline.analysis["event_date"] == "2026-08-05"


def test_15_baseline_uses_raw_return(baseline):
    assert baseline.analysis["method"]["benchmark_adjusted"] is False
    assert baseline.analysis["returns"]["abnormal"] == baseline.analysis["returns"]["security"]


def test_16_baseline_leaks_restricted_position_details(baseline):
    text = baseline.dashboard
    assert "125000 shares" in text
    assert "cost basis $78.40" in text


def test_17_baseline_shadow_verifier_catches_seeded_failures(baseline):
    failed = {failure.code for failure in baseline.report.failures}
    assert {
        "approved_method",
        "claim_provenance",
        "restricted_data_excluded",
        "causal_claim_guard",
        "event_date_alignment",
    } <= failed


def test_18_governed_run_passes(governed):
    assert governed.report.passed
    assert governed.state and governed.state.status == PUBLISHED
    status = json.loads(Path(governed.outputs["progress_json"]).read_text(encoding="utf-8"))
    assert status["episode"]["status"] == "published"
    assert [step["id"] for step in status["steps"]] == [
        "plan",
        "select",
        "retrieve",
        "govern",
        "generate",
        "execute",
        "verify",
        "approve",
        "certify",
    ]
    assert all(step["status"] in {"passed", "approved", "certified"} for step in status["steps"])
    assert {item.replace("_", " ") for item in status["contracts"]} == {
        "formula contract",
        "business rules",
        "report contract",
    }
    progress_html = Path(governed.outputs["progress_html"]).read_text(encoding="utf-8")
    assert "Live domain harness control plane" in progress_html
    assert "Domain contracts engineered into the harness" in progress_html


def test_19_governed_run_uses_bounded_repair(governed):
    assert governed.iterations == 2
    assert governed.corrections == ["event_date_alignment"]
    status = json.loads(Path(governed.outputs["progress_json"]).read_text(encoding="utf-8"))
    assert [attempt["passed"] for attempt in status["verifier_attempts"]] == [False, True]
    assert status["verifier_attempts"][0]["failures"] == ["event_date_alignment"]
    assert len(status["verifier_attempts"][1]["checks"]) == 9


def test_20_governed_event_date_is_next_trading_day(governed):
    assert governed.analysis["event_date"] == "2026-08-06"


def test_21_governed_abnormal_return_is_recomputed(governed):
    expected = (110 / 101 - 1) - (103 / 100 - 1)
    assert governed.analysis["returns"]["abnormal"] == pytest.approx(expected)


def test_22_governed_output_has_evidence_ids(governed):
    assert {
        "src-ir-acx-q2",
        "src-filing-acx-q2",
        "src-internal-thesis",
        "src-market-snapshot",
        "src-internal-policy",
    } <= set(governed.analysis["evidence_ids"])


def test_23_certificate_hashes_match_artifacts(governed):
    artifacts = governed.certificate["artifacts"]
    assert artifacts["dashboard_sha256"] == hashlib.sha256(governed.execution.dashboard_path.read_bytes()).hexdigest()
    assert artifacts["analysis_sha256"] == hashlib.sha256(governed.execution.analysis_path.read_bytes()).hexdigest()
    assert artifacts["generated_script_sha256"] == hashlib.sha256(
        governed.execution.script_path.read_bytes()
    ).hexdigest()


def test_24_certificate_has_policy_verifier_and_approval(governed):
    certificate = governed.certificate
    assert certificate["policy"]["version"] == "3.2.0"
    assert certificate["verifier"]["passed"] is True
    assert certificate["approval_receipt"].startswith("approval-")
    approval = next(event for event in governed.state.events if event["event"] == "human_approval_recorded")
    assert approval["reviewer"] == "test-reviewer"


def test_25_published_idempotency_key_is_a_noop(episode, tmp_path):
    key = "test-idempotency"
    published_run = asyncio.run(
        run_governed(
            episode,
            SKILLS,
            tmp_path,
            idempotency_key=key,
            approval_provider=approve_for_test,
        )
    )
    progress_path = Path(published_run.outputs["progress_json"])
    published_progress = progress_path.read_bytes()
    with pytest.raises(DuplicateRun):
        asyncio.run(
            run_governed(
                episode,
                SKILLS,
                tmp_path,
                idempotency_key=key,
                approval_provider=approve_for_test,
            )
        )
    assert progress_path.read_bytes() == published_progress


def test_26_resume_increments_retry(episode, tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    RunState(idempotency_key="resume-key").save(path)
    resumed, published = open_or_resume(path, "resume-key")
    assert published is False
    assert resumed.retry_count == 1
    progress_dir = tmp_path / "failed-progress"
    progress = EpisodeProgress(progress_dir, event_id="test-event", trace_id="test-trace")
    progress.transition("plan", "running", "Starting.")
    EpisodeProgress.fail_existing(progress_dir, RuntimeError("seeded failure"))
    failed = json.loads((progress_dir / "episode-status.json").read_text(encoding="utf-8"))
    assert failed["episode"]["status"] == "failed"
    assert failed["steps"][0]["status"] == "failed"

    def fail_during_selection(event):
        if event["step_id"] == "select":
            raise RuntimeError("seeded status failure")

    governed_dir = tmp_path / "failed-run"
    with pytest.raises(RuntimeError, match="seeded status failure"):
        asyncio.run(
            run_governed(
                episode,
                SKILLS,
                governed_dir,
                idempotency_key="failed-run",
                status_sink=fail_during_selection,
            )
        )
    durable = json.loads((governed_dir / "runtime-state.json").read_text(encoding="utf-8"))
    assert durable["run"]["status"] == FAILED
    progress_state = json.loads((governed_dir / "episode-status.json").read_text(encoding="utf-8"))
    assert progress_state["episode"]["status"] == "failed"

    execution_dir = tmp_path / "missing-artifacts"
    execution_dir.mkdir()
    (execution_dir / "analysis.json").write_text('{"stale": true}', encoding="utf-8")
    (execution_dir / "dashboard.html").write_text("<p>stale</p>", encoding="utf-8")
    execution = execute_analysis_script("print('no artifacts')", execution_dir)
    assert execution.success is False
    assert not execution.analysis_path.exists()
    assert not execution.dashboard_path.exists()

    def fail_during_finalization(execution):
        raise RuntimeError("seeded finalization failure")

    monkeypatch.setattr("equity_event.runs._read_execution", fail_during_finalization)
    finalization_dir = tmp_path / "failed-finalization"
    with pytest.raises(RuntimeError, match="seeded finalization failure"):
        asyncio.run(
            run_governed(
                episode,
                SKILLS,
                finalization_dir,
                idempotency_key="failed-finalization",
                approval_provider=approve_for_test,
            )
        )
    durable = json.loads((finalization_dir / "runtime-state.json").read_text(encoding="utf-8"))
    assert durable["run"]["status"] == FAILED
    progress_state = json.loads((finalization_dir / "episode-status.json").read_text(encoding="utf-8"))
    assert progress_state["episode"]["status"] == "failed"


def test_27_scoped_verifier_patch_catches_event_date_rule(episode, baseline):
    base = verify(episode, baseline.execution, admit(episode), version=BASE_VERSION)
    patched = verify(episode, baseline.execution, admit(episode), version=PATCHED_VERSION)
    assert "event_date_alignment" not in {item.code for item in base.checks}
    assert "event_date_alignment" in {item.code for item in patched.failures}


def test_28_lesson_promotion_requires_review_and_replay():
    diagnosis = build_diagnosis("trace-test")
    blocked = review_and_promote(diagnosis, approved=False, replay_passed=True)
    promoted = review_and_promote(diagnosis, approved=True, replay_passed=True)
    assert blocked["status"] == "candidate"
    assert promoted["status"] == "approved"
    assert promoted["auto_applied"] is False
    assert json.loads(json.dumps(promoted))

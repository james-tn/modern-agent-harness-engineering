"""Same model, two episodes: context-only baseline and controlled harness."""

from __future__ import annotations

import asyncio
import hashlib
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent_framework import Agent, SkillsProvider, create_harness_agent

from .analysis import ExecutionResult, execute_analysis_script
from .domain import EpisodeData
from .harness.capabilities import Selection, all_skill_paths, select_skills
from .harness.certificate import build_certificate, write_certificate
from .harness.diagnosis import build_diagnosis, review_and_promote, write_diagnosis
from .harness.ledger import EvidenceLedger
from .harness.policy import PolicyDecision, admit
from .harness.state import APPROVED, FAILED, PUBLISHED, RUNNING, VERIFIED, RunState, open_or_resume
from .harness.verifier import PATCHED_VERSION, VerificationReport, save_report, verify
from .model import ScriptedEquityClient, prompt_for
from .progress import EpisodeProgress, StatusSink

MAX_ITERATIONS = 2

BASELINE_PROMPT = """You are an equity-event analyst. You have a large static prompt,
all domain skills, every source, and every tool. Analyze the event, calculate impact,
render a polished dashboard, and tell the user when you are done."""

GOVERNED_PROMPT = """You are an equity-event analyst operating inside a controlled
episode. Follow the plan, load only selected skills, write executable analysis code,
preserve source status and uncertainty, and propose completion. The runtime—not you—
admits completion after independent verification and human approval."""


class DuplicateRun(RuntimeError):
    """An idempotency key has already produced a published certificate."""


class CompletionDenied(RuntimeError):
    """The verifier denied completion after the bounded correction loop."""


class ApprovalRequired(RuntimeError):
    """The verified episode cannot certify without an explicit reviewer."""


ApprovalProvider = Callable[[Path, VerificationReport], str | None]


@dataclass
class RunResult:
    label: str
    analysis: dict[str, Any]
    dashboard: str
    execution: ExecutionResult
    report: VerificationReport
    iterations: int = 1
    selection: dict[str, Any] = field(default_factory=dict)
    policy_decision: dict[str, Any] = field(default_factory=dict)
    corrections: list[str] = field(default_factory=list)
    state: RunState | None = None
    certificate: dict[str, Any] | None = None
    outputs: dict[str, str] = field(default_factory=dict)


async def _ask(agent: Agent, message: str) -> dict[str, Any]:
    response = await agent.run(message, session=agent.create_session())
    return json.loads(response.text)


def _read_execution(execution: ExecutionResult) -> tuple[dict[str, Any], str]:
    analysis = json.loads(execution.analysis_path.read_text(encoding="utf-8"))
    dashboard = execution.dashboard_path.read_text(encoding="utf-8")
    return analysis, dashboard


def _write_json(path: Path, value: dict[str, Any]) -> str:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return str(path)


def _baseline_selection(skills_root: Path) -> dict[str, Any]:
    paths = all_skill_paths(skills_root)
    return {
        "selected_skills": [path.name for path in paths],
        "deferred_skills": [],
        "catalog_size": len(paths),
        "exposed_tools": "all tools",
        "selector_confidence": None,
        "widened_on_low_confidence": False,
    }


async def run_baseline(
    episode: EpisodeData,
    skills_root: Path,
    out_dir: Path,
) -> RunResult:
    """Run A: fluent output, no admission control, no correction, self-declared done."""

    out_dir.mkdir(parents=True, exist_ok=True)
    client = ScriptedEquityClient()
    provider = SkillsProvider.from_paths(
        all_skill_paths(skills_root),
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        agent = Agent(
            client=client,
            instructions=BASELINE_PROMPT,
            name="equity-baseline",
            context_providers=[provider],
        )
        proposal = await _ask(
            agent,
            prompt_for(episode.model_payload(governed=False), mode="baseline", corrections=[]),
        )
    execution = execute_analysis_script(proposal["script"], out_dir)
    policy = admit(episode)
    shadow = verify(episode, execution, policy)
    save_report(shadow, out_dir / "shadow-verification.json")
    analysis, dashboard = _read_execution(execution)
    outputs = {
        "analysis": str(execution.analysis_path),
        "dashboard": str(execution.dashboard_path),
        "generated_script": str(execution.script_path),
        "shadow_verification": str(out_dir / "shadow-verification.json"),
        "selection": _write_json(out_dir / "capability-selection.json", _baseline_selection(skills_root)),
    }
    return RunResult(
        label="Run A - context-engineered baseline",
        analysis=analysis,
        dashboard=dashboard,
        execution=execution,
        report=shadow,
        selection=_baseline_selection(skills_root),
        policy_decision={"applied": False},
        outputs=outputs,
    )


def _goal(episode: EpisodeData) -> str:
    return (
        f"Plan and analyze the {episode.event['event_type']} event for {episode.ticker}; "
        "research primary sources and internal policy, calculate benchmark-adjusted portfolio impact, "
        "write and run analysis code, render an interactive HTML/SVG briefing, and verify evidence."
    )


def _approval_receipt(trace_id: str, dashboard: Path, reviewer: str) -> str:
    raw = trace_id.encode("utf-8") + reviewer.encode("utf-8") + dashboard.read_bytes()
    return "approval-" + hashlib.sha256(raw).hexdigest()[:16]


async def _progress(
    tracker: EpisodeProgress,
    step_id: str,
    status: str,
    summary: str,
    *,
    evidence: dict[str, Any] | None = None,
    pace: float = 0,
) -> None:
    tracker.transition(step_id, status, summary, evidence=evidence)
    if pace > 0:
        await asyncio.sleep(pace)


async def run_governed(
    episode: EpisodeData,
    skills_root: Path,
    out_dir: Path,
    *,
    idempotency_key: str = "equity-event:acx-2026-q2",
    pace: float = 0,
    status_sink: StatusSink | None = None,
    open_progress: bool = False,
    approval_provider: ApprovalProvider | None = None,
) -> RunResult:
    try:
        return await _run_governed_impl(
            episode,
            skills_root,
            out_dir,
            idempotency_key=idempotency_key,
            pace=pace,
            status_sink=status_sink,
            open_progress=open_progress,
            approval_provider=approval_provider,
        )
    except (CompletionDenied, ApprovalRequired, DuplicateRun):
        raise
    except Exception as error:
        state_path = Path(out_dir) / "runtime-state.json"
        state = RunState.load(state_path)
        if state and state.status != PUBLISHED:
            state.status = FAILED
            state.record("episode_failed", error_type=type(error).__name__)
            state.save(state_path)
        EpisodeProgress.fail_existing(out_dir, error)
        raise


async def _run_governed_impl(
    episode: EpisodeData,
    skills_root: Path,
    out_dir: Path,
    *,
    idempotency_key: str = "equity-event:acx-2026-q2",
    pace: float = 0,
    status_sink: StatusSink | None = None,
    open_progress: bool = False,
    approval_provider: ApprovalProvider | None = None,
) -> RunResult:
    """Run B: JIT skills, durable state, policy, verification, repair, and proof."""

    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "runtime-state.json"
    state, duplicate = open_or_resume(state_path, idempotency_key)
    if duplicate:
        raise DuplicateRun(f"Already published: {idempotency_key}")

    trace_id = state.trace_id or "trace-" + hashlib.sha256(
        f"{episode.event_id}:{idempotency_key}".encode("utf-8")
    ).hexdigest()[:16]
    state.trace_id = trace_id
    progress = EpisodeProgress(
        out_dir,
        event_id=episode.event_id,
        trace_id=trace_id,
        sink=status_sink,
        open_browser=open_progress,
    )
    await _progress(progress, "plan", "running", "Freezing the episode roadmap and bounded todos.", pace=pace)
    state.status = RUNNING
    state.plan = [
        "Select domain skills and establish a typed source ledger.",
        "Apply source, confidentiality, and method policy before model context.",
        "Generate and execute an analytical Python program.",
        "Verify artifacts and feed concrete failures back within a two-pass bound.",
        "Collect human approval and emit a completion certificate.",
    ]
    state.todos = [{"task": item, "status": "pending"} for item in state.plan]
    state.record("episode_started", event_id=episode.event_id)
    state.save(state_path)
    await _progress(
        progress,
        "plan",
        "passed",
        "Five durable tasks established before analytical execution.",
        evidence={"todo_count": len(state.todos), "state": state_path.name},
        pace=pace,
    )

    await _progress(progress, "select", "running", "Ranking filesystem skills for this event episode.", pace=pace)
    selection: Selection = select_skills(_goal(episode), skills_root)
    state.selected_skills = selection.selected
    state.record("capabilities_selected", selected=selection.selected, deferred=selection.deferred)
    selection_path = out_dir / "capability-selection.json"
    _write_json(selection_path, selection.to_dict())
    await _progress(
        progress,
        "select",
        "passed",
        f"Loaded {len(selection.selected)}/11 skills; deferred {len(selection.deferred)} unrelated capabilities.",
        evidence={"selected_skills": selection.selected, "deferred_skills": selection.deferred},
        pace=pace,
    )

    await _progress(progress, "retrieve", "running", "Recording public and mock-internal source operations.", pace=pace)
    ledger = EvidenceLedger(episode_id=episode.event_id)
    ledger.ingest(episode)
    state.record("sources_retrieved", operations=episode.retrieval_log)
    await _progress(
        progress,
        "retrieve",
        "passed",
        "One public snapshot and four mock API operations linked to typed evidence.",
        evidence={"operations": len(episode.retrieval_log), "source_records": len(episode.source_records)},
        pace=pace,
    )

    await _progress(progress, "govern", "running", "Applying source and confidentiality policy before model context.", pace=pace)
    policy = admit(episode)
    _write_json(out_dir / "policy-decision.json", policy.to_dict())
    state.todos[0]["status"] = "done"
    state.todos[1]["status"] = "done"
    state.record(
        "policy_admission",
        admitted=len(policy.admitted_claim_ids),
        excluded=len(policy.excluded_claim_ids),
    )
    await _progress(
        progress,
        "govern",
        "passed",
        f"Admitted {len(policy.admitted_claim_ids)} claims; excluded {len(policy.excluded_claim_ids)} unsafe claims.",
        evidence={
            "decision": policy.decision,
            "policy_version": policy.version,
            "forbidden_fields": policy.forbidden_fields,
        },
        pace=pace,
    )

    client = ScriptedEquityClient()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        agent = create_harness_agent(
            client=client,
            name="equity-event-impact-analyst",
            description="Plans and executes an evidence-backed equity-event study.",
            agent_instructions=GOVERNED_PROMPT,
            skills_paths=selection.paths,
            disable_compaction=True,
            disable_file_memory=True,
            disable_web_search=True,
            disable_tool_auto_approval=True,
        )

    corrections: list[str] = []
    report: VerificationReport | None = None
    execution: ExecutionResult | None = None
    for iteration in range(1, MAX_ITERATIONS + 1):
        generation_status = "running" if iteration == 1 else "repairing"
        await _progress(
            progress,
            "generate",
            generation_status,
            "Generating governed analysis code."
            if iteration == 1
            else "Regenerating code with the concrete event-date correction.",
            evidence={"attempt": iteration},
            pace=pace,
        )
        proposal = await _ask(
            agent,
            prompt_for(
                episode.model_payload(
                    governed=True,
                    admitted_claim_ids=set(policy.admitted_claim_ids),
                ),
                mode="governed",
                corrections=corrections,
            ),
        )
        await _progress(
            progress,
            "generate",
            "passed",
            f"Attempt {iteration}: constrained Python artifact proposed for execution.",
            evidence={"attempt": iteration},
            pace=pace,
        )
        await _progress(
            progress,
            "execute",
            "running",
            f"Attempt {iteration}: running generated code with python -I.",
            pace=pace,
        )
        execution = execute_analysis_script(proposal["script"], out_dir)
        execution_status = "passed" if execution.success else "failed"
        execution_summary = (
            f"Attempt {iteration}: Python, JSON, HTML, and SVG artifacts produced."
            if execution.success
            else (
                f"Attempt {iteration}: generated program exited {execution.return_code}; artifacts rejected."
                if execution.return_code != 0
                else f"Attempt {iteration}: generated program omitted required artifacts; output rejected."
            )
        )
        await _progress(
            progress,
            "execute",
            execution_status,
            execution_summary,
            evidence={"exit_code": execution.return_code, "artifacts": ["generated_analysis.py", "analysis.json", "dashboard.html"]},
            pace=pace,
        )
        await _progress(
            progress,
            "verify",
            "running",
            f"Attempt {iteration}: independently evaluating nine deterministic checks.",
            pace=pace,
        )
        report = verify(episode, execution, policy, version=PATCHED_VERSION)
        save_report(report, out_dir / f"verification-{iteration}.json")
        progress.add_verification(iteration=iteration, report=report)
        if pace > 0:
            await asyncio.sleep(pace)
        state.record(
            "verification_pass",
            iteration=iteration,
            passed=report.passed,
            failures=[item.code for item in report.failures],
        )
        if report.passed:
            break
        if iteration < MAX_ITERATIONS:
            failure_codes = {failure.code for failure in report.failures}
            if "event_date_alignment" in failure_codes and "event_date_alignment" not in corrections:
                corrections.append("event_date_alignment")
                state.record(
                    "bounded_correction_requested",
                    correction="event_date_alignment",
                    detail=next(
                        failure.detail for failure in report.failures if failure.code == "event_date_alignment"
                    ),
                )
    if report is None or execution is None or not report.passed:
        failure_codes = [item.code for item in report.failures] if report else ["verification_unavailable"]
        await _progress(
            progress,
            "verify",
            "failed",
            f"Bounded verification exhausted; failures remain: {', '.join(failure_codes)}.",
            evidence={"attempts": MAX_ITERATIONS, "failures": failure_codes},
            pace=pace,
        )
        state.status = FAILED
        state.record("completion_denied", reason="bounded verifier loop exhausted")
        state.save(state_path)
        progress.finish("failed")
        raise CompletionDenied("Verifier failures remain after the bounded correction loop.")

    state.todos[2]["status"] = "done"
    state.todos[3]["status"] = "done"
    state.status = VERIFIED
    state.verifier_version = report.version
    state.record("completion_admitted_by_verifier", verifier=report.version)

    await _progress(
        progress,
        "approve",
        "running",
        "Presenting the verified dashboard for human review.",
        pace=pace,
    )
    reviewer = approval_provider(execution.dashboard_path, report) if approval_provider else None
    if not reviewer:
        state.record("human_approval_required", dashboard=str(execution.dashboard_path.name))
        state.save(state_path)
        progress.transition(
            "approve",
            "waiting",
            "Verified output is waiting for an explicit reviewer decision.",
        )
        progress.finish("awaiting_approval")
        raise ApprovalRequired("Verifier passed, but no reviewer approved publication.")
    receipt = _approval_receipt(trace_id, execution.dashboard_path, reviewer)
    state.status = APPROVED
    state.approval_receipt = receipt
    state.record("human_approval_recorded", receipt=receipt, reviewer=reviewer)
    await _progress(
        progress,
        "approve",
        "approved",
        f"Reviewer {reviewer} approved publication after 9/9 verification.",
        evidence={"approval_receipt": receipt, "reviewer": reviewer},
        pace=pace,
    )

    diagnosis = build_diagnosis(trace_id)
    lesson = diagnosis["candidate_lesson"]
    ledger.add_lesson_candidate(lesson)
    state.lesson_candidates.append(lesson)
    state.record("lesson_candidate_created", lesson_id=lesson["lesson_id"], auto_applied=False)

    await _progress(
        progress,
        "certify",
        "running",
        "Building the completion proof bundle from exact artifact bytes.",
        pace=pace,
    )
    certificate = build_certificate(
        event_id=episode.event_id,
        trace_id=trace_id,
        sources=episode.source_records,
        policy=policy,
        verification=report,
        approval_receipt=receipt,
        analysis_path=execution.analysis_path,
        dashboard_path=execution.dashboard_path,
        script_path=execution.script_path,
    )
    cert_path = out_dir / "evidence-certificate.json"
    write_certificate(certificate, cert_path)
    ledger_path = ledger.save(out_dir / "evidence-ledger.json")
    diagnosis_path = write_diagnosis(diagnosis, out_dir / "lesson-candidate.json")

    await _progress(
        progress,
        "certify",
        "certified",
        "Evidence certificate emitted; episode completion is independently auditable.",
        evidence={"certificate": cert_path.name, "trace_id": trace_id},
        pace=pace,
    )
    progress.finish("published")
    analysis, dashboard = _read_execution(execution)
    state.todos[4]["status"] = "done"
    state.status = PUBLISHED
    state.record("certificate_emitted", certificate=str(cert_path.name))
    state.save(state_path)
    outputs = {
        "analysis": str(execution.analysis_path),
        "dashboard": str(execution.dashboard_path),
        "generated_script": str(execution.script_path),
        "verification": str(out_dir / f"verification-{iteration}.json"),
        "certificate": str(cert_path),
        "ledger": str(ledger_path),
        "state": str(state_path),
        "lesson_candidate": str(diagnosis_path),
        "selection": str(selection_path),
        "policy": str(out_dir / "policy-decision.json"),
        "progress_json": str(progress.json_path),
        "progress_html": str(progress.html_path),
    }
    return RunResult(
        label="Run B - modern harness",
        analysis=analysis,
        dashboard=dashboard,
        execution=execution,
        report=report,
        iterations=iteration,
        selection=selection.to_dict(),
        policy_decision=policy.to_dict(),
        corrections=corrections,
        state=state,
        certificate=certificate,
        outputs=outputs,
    )


def run_lesson_review(trace_id: str, out_dir: Path, *, approved: bool) -> dict[str, Any]:
    """Simulate explicit methodology review after regression replay."""

    out_dir.mkdir(parents=True, exist_ok=True)
    diagnosis = build_diagnosis(trace_id)
    replay = {
        "case": "after-close-event-date",
        "base_verifier_missed_rule": True,
        "patched_verifier_caught_defect": True,
        "corrected_case_passed": True,
    }
    replay_passed = all(
        replay[key]
        for key in ("base_verifier_missed_rule", "patched_verifier_caught_defect", "corrected_case_passed")
    )
    lesson = review_and_promote(diagnosis, approved=approved, replay_passed=replay_passed)
    result = {"diagnosis": diagnosis, "regression_replay": replay, "reviewed_lesson": lesson}
    _write_json(out_dir / "lesson-review.json", result)
    return result

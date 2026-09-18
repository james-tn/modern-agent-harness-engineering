"""Live roadmap and control-status visualization for a governed episode."""

from __future__ import annotations

import html
import json
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

StatusSink = Callable[[dict[str, Any]], None]

STEP_DEFINITIONS = [
    {
        "id": "plan",
        "label": "Plan",
        "technique": "Plan/execute mode + durable todo state",
        "domain_asset": "equity-event-analysis SKILL.md",
        "control": "Freeze a five-task roadmap before analytical side effects.",
        "validation": "Every task has an explicit terminal state.",
    },
    {
        "id": "select",
        "label": "Select",
        "technique": "JIT filesystem SkillsProvider",
        "domain_asset": "capability selector + always-on policy/verifier",
        "control": "Load 8 of 11 skills; policy and verification stay always-on.",
        "validation": "Options, credit, and corporate-actions skills remain deferred.",
    },
    {
        "id": "retrieve",
        "label": "Retrieve",
        "technique": "Typed source adapters + evidence ledger",
        "domain_asset": "financial-source-retrieval SKILL.md",
        "control": "Use a public snapshot and four mock internal API calls.",
        "validation": "Persist source IDs, classifications, operations, and hashes.",
    },
    {
        "id": "govern",
        "label": "Govern",
        "technique": "Information-flow labels + sink admission",
        "domain_asset": "research-policy SKILL.md + policy 3.2.0",
        "control": "Exclude untrusted causality and exact portfolio fields.",
        "validation": "Policy 3.2.0 must return allow_after_approval.",
    },
    {
        "id": "generate",
        "label": "Generate",
        "technique": "Same model + constrained artifact contract",
        "domain_asset": "event-date + abnormal-return SKILL.md",
        "control": "Require Python, analysis JSON, and inline-SVG HTML.",
        "validation": "The model may propose completion but cannot certify it.",
    },
    {
        "id": "execute",
        "label": "Execute",
        "technique": "Isolated subprocess + timeout",
        "domain_asset": "interactive-briefing SKILL.md",
        "control": "Run standard-library code with python -I and a curated environment.",
        "validation": "Exit code 0 and all required artifacts must exist.",
    },
    {
        "id": "verify",
        "label": "Verify / repair",
        "technique": "External deterministic verifier + bounded loop",
        "domain_asset": "evidence-verification SKILL.md",
        "control": "Run nine checks with a maximum of two model attempts.",
        "validation": "Recompute formulas, business rules, report shape, and chart data.",
    },
    {
        "id": "approve",
        "label": "Approve",
        "technique": "Human-in-the-loop gate",
        "domain_asset": "shared-research-briefing sink policy",
        "control": "Approval is unavailable until the verifier passes 9 of 9.",
        "validation": "A reviewer receipt is required for certification.",
    },
    {
        "id": "certify",
        "label": "Certify",
        "technique": "Proof bundle + idempotency",
        "domain_asset": "equity completion-certificate schema",
        "control": "Hash source snapshots, code, JSON, HTML, policy, and trace.",
        "validation": "Completion evidence persists independently of model narration.",
    },
]

CONTRACTS = {
    "formula_contract": [
        "security_return = P[t] / P[t-1] - 1",
        "benchmark_return = B[t] / B[t-1] - 1",
        "abnormal_return = security_return - benchmark_return",
    ],
    "business_rules": [
        "after_close announcement -> next valid trading day",
        "adjusted prices are mandatory",
        "approved benchmark = CHIP",
        "shared sink receives exposure band only",
        "causal language requires primary evidence",
    ],
    "report_contract": [
        "six required sections are present",
        "every factual conclusion carries evidence IDs",
        "uncertainty and limitations are explicit",
        "inline SVG renders successfully",
        "chart data equals analysis.json",
        "synthetic / not-investment-advice notice is visible",
    ],
}

TERMINAL_SUCCESS = {"passed", "approved", "certified"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EpisodeProgress:
    """Persist and render every control transition for live demo display."""

    def __init__(
        self,
        out_dir: Path,
        *,
        event_id: str,
        trace_id: str,
        sink: StatusSink | None = None,
        open_browser: bool = False,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.json_path = self.out_dir / "episode-status.json"
        self.html_path = self.out_dir / "episode-status.html"
        self.sink = sink
        self.data: dict[str, Any] = {
            "schema_version": "1.0",
            "episode": {
                "event_id": event_id,
                "trace_id": trace_id,
                "status": "running",
                "current_step": "plan",
                "revision": 0,
                "updated_at": _now(),
            },
            "steps": [{**step, "status": "pending", "summary": "", "evidence": {}} for step in STEP_DEFINITIONS],
            "contracts": CONTRACTS,
            "verifier_attempts": [],
            "events": [],
        }
        self._write()
        if open_browser:
            webbrowser.open(self.html_path.resolve().as_uri())

    def transition(
        self,
        step_id: str,
        status: str,
        summary: str,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        step = next((item for item in self.data["steps"] if item["id"] == step_id), None)
        if step is None:
            raise KeyError(f"Unknown progress step: {step_id}")
        step["status"] = status
        step["summary"] = summary
        if evidence:
            step["evidence"].update(evidence)
        event = {
            "at": _now(),
            "step_id": step_id,
            "step_label": step["label"],
            "status": status,
            "summary": summary,
        }
        self.data["events"].append(event)
        self.data["episode"]["current_step"] = step_id
        self.data["episode"]["revision"] = self.data["episode"].get("revision", 0) + 1
        self.data["episode"]["updated_at"] = event["at"]
        self._write()
        if self.sink:
            self.sink(event)

    def add_verification(self, *, iteration: int, report: Any) -> None:
        attempt = {
            "iteration": iteration,
            "passed": report.passed,
            "checks": [check.to_dict() for check in report.checks],
            "failures": [check.code for check in report.failures],
        }
        self.data["verifier_attempts"].append(attempt)
        if report.passed:
            self.transition(
                "verify",
                "passed",
                f"Attempt {iteration}: 9/9 checks passed; completion admitted.",
                evidence={"attempts": iteration, "verifier_version": report.version, "failures": []},
            )
        else:
            passed = sum(check.passed for check in report.checks)
            failures = ", ".join(attempt["failures"])
            self.transition(
                "verify",
                "repairing",
                f"Attempt {iteration}: {passed}/{len(report.checks)} checks passed; failures: {failures}.",
                evidence={"attempts": iteration, "failures": attempt["failures"]},
            )

    def finish(self, status: str) -> None:
        self.data["episode"]["status"] = status
        self.data["episode"]["revision"] = self.data["episode"].get("revision", 0) + 1
        self.data["episode"]["updated_at"] = _now()
        self._write()

    @classmethod
    def fail_existing(cls, out_dir: Path, error: Exception) -> None:
        json_path = Path(out_dir) / "episode-status.json"
        if not json_path.exists():
            return
        tracker = cls.__new__(cls)
        tracker.out_dir = Path(out_dir)
        tracker.json_path = json_path
        tracker.html_path = tracker.out_dir / "episode-status.html"
        tracker.sink = None
        tracker.data = json.loads(json_path.read_text(encoding="utf-8"))
        current = tracker.data["episode"]["current_step"]
        tracker.transition(
            current,
            "failed",
            f"{type(error).__name__}: episode aborted; inspect runtime logs.",
        )
        tracker.finish("failed")

    def _write(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.json_path, json.dumps(self.data, indent=2))
        self._atomic_write(self.html_path, self._render_html())

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        for attempt in range(10):
            temporary.write_text(content, encoding="utf-8")
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02 * (attempt + 1))

    def _render_html(self) -> str:
        episode = self.data["episode"]
        complete = sum(step["status"] in TERMINAL_SUCCESS for step in self.data["steps"])
        percent = round(complete / len(self.data["steps"]) * 100)
        refresh = (
            ""
            if episode["status"] in {"published", "failed", "awaiting_approval"}
            else '<meta http-equiv="refresh" content="1">'
        )
        steps = "".join(self._render_step(index, step) for index, step in enumerate(self.data["steps"], 1))
        contracts = "".join(
            self._render_contract(title.replace("_", " "), items)
            for title, items in self.data["contracts"].items()
        )
        attempts = "".join(self._render_attempt(attempt) for attempt in self.data["verifier_attempts"])
        if not attempts:
            attempts = '<div class="empty">Verifier has not run yet.</div>'
        events = "".join(
            f'<li><time>{html.escape(event["at"][11:19])}</time>'
            f'<span class="event-status {html.escape(event["status"])}">{html.escape(event["status"])}</span>'
            f'<strong>{html.escape(event["step_label"])}</strong>'
            f'<span>{html.escape(event["summary"])}</span></li>'
            for event in reversed(self.data["events"][-12:])
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="episode-revision" content="{episode["revision"]}">
{refresh}<title>Equity Event Harness Control Plane</title>
<style>
:root{{--bg:#070b16;--panel:#101a2b;--panel2:#14243a;--line:#263a55;--text:#e7eef9;--muted:#91a4bd;
--cyan:#22d3ee;--blue:#38a7ff;--violet:#9b78ff;--green:#4ade91;--amber:#fbb63f;--red:#ff626e}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif}}
main{{max-width:1500px;margin:auto;padding:30px 34px 50px}}header{{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:end}}
.eyebrow{{color:var(--cyan);font-size:12px;font-weight:700;letter-spacing:.18em;text-transform:uppercase}}
h1{{font-size:34px;margin:8px 0 6px}}.muted{{color:var(--muted)}}.state{{text-align:right}}
.state strong{{display:block;color:var(--green);font-size:20px;text-transform:uppercase}}.bar{{height:9px;background:#1d2a40;border-radius:9px;margin:24px 0 12px;overflow:hidden}}
.bar>div{{height:100%;width:{percent}%;background:linear-gradient(90deg,var(--violet),var(--cyan),var(--green));transition:width .4s}}
.roadmap{{display:grid;grid-template-columns:repeat(9,minmax(125px,1fr));gap:10px;margin:16px 0 28px}}
.step{{position:relative;min-height:285px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}}
.step:after{{content:"";position:absolute;top:25px;right:-11px;width:11px;border-top:1px solid #60738e}}.step:last-child:after{{display:none}}
.step .n{{color:var(--muted);font-size:10px}}.step h2{{font-size:15px;margin:14px 0 8px}}.step p{{font-size:10px;color:var(--muted);line-height:1.4;margin:4px 0}}
.step .k{{color:var(--cyan);font-size:8px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-top:9px}}.step .summary{{color:var(--text)}}
.badge,.event-status{{display:inline-block;border-radius:999px;padding:4px 8px;font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}
.pending{{color:var(--muted)}}.running{{color:var(--blue)}}.repairing,.waiting{{color:var(--amber)}}.passed,.approved,.certified{{color:var(--green)}}.failed{{color:var(--red)}}
.step.running{{border-color:var(--blue);box-shadow:0 0 0 1px var(--blue)}}.step.repairing,.step.waiting{{border-color:var(--amber)}}.step.passed,.step.approved,.step.certified{{border-color:var(--green)}}
.grid{{display:grid;grid-template-columns:1.15fr .85fr;gap:18px}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px}}
.panel h2{{font-size:18px;margin:0 0 14px}}.contracts{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.contract{{background:var(--panel2);border-radius:12px;padding:15px}}.contract h3{{color:var(--cyan);font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 10px}}
.contract li{{font-size:11px;line-height:1.5;margin:7px 0;color:#cbd7e7}}.attempt{{border:1px solid var(--line);border-radius:12px;padding:13px;margin:10px 0}}
.attempt-head{{display:flex;justify-content:space-between;font-weight:700}}.checks{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px}}
.check{{font-size:10px;color:var(--muted)}}.check.pass:before{{content:"PASS ";color:var(--green);font-weight:700}}.check.fail:before{{content:"FAIL ";color:var(--red);font-weight:700}}
.events{{list-style:none;margin:0;padding:0}}.events li{{display:grid;grid-template-columns:58px 82px 95px 1fr;gap:8px;align-items:center;border-top:1px solid var(--line);padding:8px 0;font-size:11px}}
.events time{{color:var(--muted)}}.empty{{color:var(--muted);padding:20px 0}}footer{{margin-top:18px;color:var(--muted);font-size:10px}}
@media(max-width:1100px){{.roadmap{{grid-template-columns:repeat(3,1fr)}}.step:after{{display:none}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header><div><div class="eyebrow">Live domain harness control plane</div><h1>Equity Event Impact Analyst</h1>
<div class="muted">Roadmap, controls, validation, repair, and proof for <code>{html.escape(episode["event_id"])}</code></div></div>
<div class="state"><span class="muted">episode</span><strong>{html.escape(episode["status"])}</strong>
<span class="muted">{percent}% · {complete}/{len(self.data["steps"])} gates complete</span></div></header>
<div class="bar"><div></div></div><section class="roadmap">{steps}</section>
<section class="grid"><div class="panel"><h2>Domain contracts engineered into the harness</h2><div class="contracts">{contracts}</div>
<h2 style="margin-top:20px">Verifier attempts</h2>{attempts}</div>
<div class="panel"><h2>Realtime control events</h2><ol class="events">{events}</ol></div></section>
<footer>Generated from runtime state · same model across runs · synthetic illustrative data · not investment advice · trace {html.escape(episode["trace_id"])}</footer>
</main></body></html>"""

    @staticmethod
    def _render_step(index: int, step: dict[str, Any]) -> str:
        summary = step["summary"] or step["control"]
        evidence = ", ".join(step["evidence"].keys()) or "pending"
        return (
            f'<article class="step {html.escape(step["status"])}">'
            f'<span class="n">{index:02d}</span><span class="badge {html.escape(step["status"])}">'
            f'{html.escape(step["status"])}</span><h2>{html.escape(step["label"])}</h2>'
            f'<p class="k">Technique</p><p>{html.escape(step["technique"])}</p>'
            f'<p class="k">Domain asset</p><p>{html.escape(step["domain_asset"])}</p>'
            f'<p class="k">Control</p><p>{html.escape(step["control"])}</p>'
            f'<p class="k">Validation</p><p>{html.escape(step["validation"])}</p>'
            f'<p class="k">Runtime evidence</p><p class="summary">{html.escape(summary)} · {html.escape(evidence)}</p></article>'
        )

    @staticmethod
    def _render_contract(title: str, items: list[str]) -> str:
        rows = "".join(f"<li>{html.escape(item)}</li>" for item in items)
        return f'<article class="contract"><h3>{html.escape(title)}</h3><ul>{rows}</ul></article>'

    @staticmethod
    def _render_attempt(attempt: dict[str, Any]) -> str:
        state = "passed" if attempt["passed"] else "repairing"
        checks = "".join(
            f'<div class="check {"pass" if check["passed"] else "fail"}">{html.escape(check["code"])}</div>'
            for check in attempt["checks"]
        )
        return (
            f'<article class="attempt"><div class="attempt-head"><span>Attempt {attempt["iteration"]}</span>'
            f'<span class="{state}">{"9/9 PASS" if attempt["passed"] else "REPAIR REQUIRED"}</span></div>'
            f'<div class="checks">{checks}</div></article>'
        )

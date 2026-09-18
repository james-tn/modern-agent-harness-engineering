"""Credential-free HTTP tests for the local console and its real approval wait."""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import pytest

from equity_event.harness.verifier import Check, VerificationReport
from equity_event.live_config import HarnessConfig, profiles
from equity_event import ui
from equity_event.ui import MAX_BODY_BYTES, _nonce_styles, create_ui_server

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "demo" / "sample-input"
SKILLS = REPO / "demo" / "agent" / "skills"


class Console:
    def __init__(self, server, root: Path) -> None:
        self.server = server
        self.root = root
        self.closed = False
        self.thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True,
        )
        self.thread.start()

    def request(self, method: str, path: str, data=None, *, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        request_headers = {}
        body = raw
        if method == "POST":
            request_headers.update({
                "Content-Type": "application/json",
                "X-Harness-Nonce": self.server.nonce,
                "Origin": self.server.url,
            })
        if data is not None:
            body = json.dumps(data).encode()
        if headers:
            request_headers.update(headers)
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        result = (
            json.loads(payload)
            if response.getheader("Content-Type", "").startswith("application/json")
            else payload.decode("utf-8")
        )
        status, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return status, result, response_headers

    def start(self, config=None):
        status, result, _ = self.request(
            "POST", "/api/runs", {"config": config or profiles()["scripted"]["config"]},
        )
        assert status == 202, result
        return result

    def wait(self, run_id: str, statuses, timeout=3):
        if isinstance(statuses, str):
            statuses = {statuses}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, result, _ = self.request("GET", f"/api/runs/{run_id}")
            assert status == 200
            if result["status"] in statuses:
                return result
            time.sleep(0.01)
        pytest.fail(f"Run did not reach {statuses}: {result}")

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        for run in self.server.manager.runs.values():
            if run.thread:
                run.thread.join(timeout=2)


@pytest.fixture
def consoles():
    # Keep all test artifacts in this repository, not the OS temporary directory.
    root = REPO / ".test-harness-ui" / uuid.uuid4().hex
    root.mkdir(parents=True)
    active = []

    def create(runner, *, timeout=10, restore_from=None):
        if restore_from is not None:
            restore_from.close()
        directory = restore_from.root if restore_from is not None else root / str(len(active))
        server = create_ui_server(
            INPUTS, SKILLS, directory / "runs", memory_dir=directory / "memory",
            port=0, runner=runner, approval_timeout=timeout,
        )
        console = Console(server, directory)
        active.append(console)
        return console

    yield create
    for console in active:
        console.close()
    shutil.rmtree(root)
    try:
        root.parent.rmdir()
    except OSError:
        pass


async def finish_without_approval(_inputs, _skills, out_dir, **_kwargs):
    (out_dir / "result.json").write_text(json.dumps({"status": "test-finished"}), encoding="utf-8")
    return {"status": "test-finished"}


def make_report(passed=True):
    return VerificationReport("ui-test-verifier/1", [
        Check("event_date_alignment", passed, "Fixture verification evidence", "business_rule"),
    ])


async def wait_for_human(_inputs, _skills, out_dir, *, approval_provider, **_kwargs):
    dashboard = out_dir / "attempt-1" / "dashboard.html"
    dashboard.parent.mkdir()
    dashboard.write_text("<!doctype html><html><h1>Test reviewer artifact</h1></html>", encoding="utf-8")
    reviewer = approval_provider(dashboard, make_report())
    if not reviewer:
        raise PermissionError("Human approval was not granted.")
    return {"status": "published", "reviewer": reviewer}


async def finish_with_retained_evidence(_inputs, _skills, out_dir, **_kwargs):
    directory = out_dir / "attempt-01"
    directory.mkdir()
    (directory / "dashboard.html").write_text("<h1>Retained fixture preview</h1>", encoding="utf-8")
    (out_dir / "telemetry.json").write_text(
        json.dumps({"trace_id": "f" * 32, "spans": [], "events": []}), encoding="utf-8",
    )
    result = {"status": "unverified_preview", "certified": False, "dashboard": str(Path("attempt-01") / "dashboard.html")}
    (out_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return result


def test_bootstrap_serves_profiles_catalogue_and_nonce_page(consoles):
    console = consoles(finish_without_approval)
    status, page, headers = console.request("GET", "/")
    assert status == 200
    assert '<meta name="harness-nonce"' in page
    assert console.server.nonce in page
    assert "__HARNESS_NONCE__" not in page
    assert 'sandbox="allow-scripts"' in page
    assert "allow-same-origin" not in page
    assert "setInterval(poll, 700)" in page
    assert "Discovery exposes names and descriptions; it does not load skill instructions." in page
    assert "no live LLM" in page
    assert "Native MAF" in page
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "no-store"
    assert f"script-src 'nonce-{console.server.nonce}'" in headers["Content-Security-Policy"]
    assert f"style-src 'nonce-{console.server.style_nonce}'" in headers["Content-Security-Policy"]
    assert console.server.style_nonce != console.server.nonce
    assert f'<style nonce="{console.server.style_nonce}">' in page
    assert not re.search(r"<(?:script|link)[^>]+(?:src|href)=['\"]https?://", page)
    status, bootstrap, headers = console.request("GET", "/api/bootstrap")
    assert status == 200
    assert set(bootstrap["profiles"]) == {"governed", "naive", "scripted"}
    assert len(bootstrap["skills"]) == 11
    assert all(set(skill) == {"id", "name", "description", "mandatory"} for skill in bootstrap["skills"])
    assert bootstrap["optional_tools"] == ["public_source_search", "internal_api_lookup", "execute_analysis"]
    assert bootstrap["active_run_id"] is None
    assert bootstrap["runs"] == []
    assert "Access-Control-Allow-Origin" not in headers
    assert "nonce" not in bootstrap


def test_config_is_passed_to_the_same_async_runtime_and_output_is_empty(consoles):
    received = {}

    async def runner(inputs, skills, out_dir, **kwargs):
        assert not any(out_dir.iterdir()), "UI metadata must not make the runtime reject a nonempty directory."
        assert asyncio.get_running_loop().is_running()
        received.update(inputs=inputs, skills=skills, out_dir=out_dir, **kwargs)
        return {"status": "test-finished", "trace_id": "f" * 32}

    console = consoles(runner)
    edited = HarnessConfig(
        model="scripted", deployment="gpt-5.4", skill_mode="all_loaded",
        available_skills=["event-date-alignment"], enabled_tools=["execute_analysis"],
        memory_enabled=False, memory_scope="editable-scope", max_model_requests=11,
        max_tool_calls=22, max_execution_attempts=2, execution_timeout_seconds=9,
        gate_mode="observe",
    ).to_dict()
    started = console.start(edited)
    completed = console.wait(started["id"], "completed")
    assert received["config"].to_dict() == edited
    assert received["inputs"] == INPUTS.resolve()
    assert received["skills"] == SKILLS.resolve()
    assert received["memory_dir"] == (console.root / "memory").resolve()
    assert received["approval_kind"] == "interactive"
    assert callable(received["approval_provider"])
    assert received["out_dir"] == console.root / "runs" / started["id"]
    assert completed["config"] == edited
    assert completed["result"]["trace_id"] == "f" * 32
    persisted = json.loads((console.root / "runs" / ".console" / f"{started['id']}.json").read_text())
    assert persisted["status"] == "completed"
    assert persisted["config"] == edited


def test_define_groups_match_slide_vocabulary_and_fixed_runtime_facts(consoles):
    console = consoles(finish_without_approval)
    status, page, _ = console.request("GET", "/")
    assert status == 200
    for concept in (
        "HARNESS COMPONENTS", "BOUNDED AUTONOMY", "PROGRESSIVE TOOLING",
        "INTELLIGENT CONTEXT / CONTEXT HYGIENE", "ACCEPTANCE GATES",
    ):
        assert concept in page
    for fixed_fact in (
        "synthetic ACX earnings event", "AgentSession", "python -I", "not an OS sandbox",
        "3 identical calls", "Compaction is OFF", "No automatic trimming is wired",
        "Filtered synthetic source results", "9 independent checks always run",
        "Human approval is separate and unskippable", "local exporter",
    ):
        assert fixed_fact in page
    for key in HarnessConfig().to_dict():
        assert f"<code>{key}</code>" in page
    assert 'id="contrast-exposure"' in page
    assert 'id="contrast-memory"' in page
    assert 'id="contrast-gates"' in page
    assert "<details open>" not in page
    assert 'id="boundaries"' not in page


def test_cli_serve_signature_forwards_the_requested_roots_and_port(monkeypatch):
    received = {}

    def fake_serve(input_root, skills_root, out_dir, **kwargs):
        received.update(input_root=input_root, skills_root=skills_root, out_dir=out_dir, **kwargs)

    monkeypatch.setattr(ui, "serve_ui", fake_serve)
    ui.serve(INPUTS, SKILLS, REPO / "test-output", memory_dir=REPO / "test-memory", port=0)
    assert received == {
        "input_root": INPUTS, "skills_root": SKILLS, "out_dir": REPO / "test-output",
        "memory_dir": REPO / "test-memory", "port": 0,
    }


def test_rehearsal_guidance_separates_live_behavior_from_seeded_offline_failure(consoles):
    console = consoles(finish_without_approval)
    status, page, _ = console.request("GET", "/")
    assert status == 200
    assert "Warm up before the talk." in page
    assert "Reuse that memory scope on the next run to inspect actual recall." in page
    assert "Scripted model · seeded date near-miss" in page
    assert "Strict acceptance requests a bounded correction." in page
    assert "Observe only keeps the unverified preview." in page
    assert "An observe-only run may pass honestly" in page
    assert "Blocked · episode stopped" in page
    assert "Choose Scripted / offline manually" in page
    assert "no offline fallback is automatic" in page


def test_unused_controls_have_accessible_reasons_and_exact_runbook_labels(consoles):
    console = consoles(finish_without_approval)
    status, page, _ = console.request("GET", "/")
    assert status == 200
    assert ">Run harness</button>" in page
    assert ">Approve local result</button>" in page
    assert "Approve publication" not in page
    assert 'aria-describedby="deployment-help"' in page
    assert 'aria-describedby="memory-scope-help"' in page
    assert "Not used by the scripted model." in page
    assert "Not used while memory is disabled." in page
    assert "The seeded first attempt uses the wrong announcement date" in page
    assert profiles()["governed"]["name"] == "Progressive / governed"
    assert profiles()["naive"]["name"] == "All-loaded / observe-only"
    assert profiles()["scripted"]["name"] == "Scripted / offline"


def test_memory_labels_do_not_turn_an_empty_index_check_into_recall(consoles):
    console = consoles(finish_without_approval)
    status, page, _ = console.request("GET", "/")
    assert status == 200
    assert 'name === "memory_index_read") return "Memory index checked"' in page
    assert 'data.file_present === false) return "No prior observation"' in page
    assert 'data.file_present === true) return "Prior observation available"' in page
    assert 'name === "memory_read") return "Observation read"' in page
    assert 'name === "cross_run_memory_recalled") return "Cross-run recall"' in page


def test_approval_controls_start_disabled_even_when_hidden(consoles):
    console = consoles(finish_without_approval)
    status, page, _ = console.request("GET", "/")
    assert status == 200
    for control in ("approve-button", "reject-button", "reviewer"):
        tag = re.search(rf'<(?:input|button)\b[^>]*\bid="{control}"[^>]*>', page)
        assert tag is not None
        assert re.search(r"\sdisabled(?:\s|>)", tag.group()) is not None
    assert ">Approve local result</button>" in page


def test_actual_javascript_disables_nonactionable_and_settled_approval_controls():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable for the optional JavaScript state regression.")
    code = r"""
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const page = fs.readFileSync(process.argv[1], "utf8");
const script = page.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const helpers = script.slice(script.indexOf("function approvalIsActionable("), script.indexOf("function fillDefinition("));
const decision = script.slice(script.indexOf("async function decide("), script.indexOf('$("approve-button").addEventListener'));
const ids = ["approve-button", "reject-button", "reviewer"];
const fields = Object.fromEntries(ids.map(id => [id, {disabled: false, value: "automated-ui-validation", focus() {}}]));
const state = {run: null, selectedId: "r-current", approvalBusy: false};
const context = {
  state, $: id => fields[id], showError() {}, saveRun() {},
  renderRun(run) { state.run = run; context.updateApprovalControls(); }
};
vm.runInNewContext(helpers + decision, context);
const pending = () => ({id: "r-current", status: "awaiting_approval", approval: {status: "pending"}});
const disabled = expected => ids.forEach(id => assert.equal(fields[id].disabled, expected, id));
for (const run of [
  null, {id: "r-current", status: "running"},
  {id: "r-current", status: "completed", approval: {status: "approved"}},
  {...pending(), status: "failed"}, {...pending(), status: "interrupted"},
  {...pending(), restored: true}, {...pending(), id: "r-other"}
]) {
  state.run = run; context.updateApprovalControls(); disabled(true);
}
async function main() {
  state.run = pending(); context.updateApprovalControls(); disabled(false);
  let finish;
  context.api = () => new Promise(resolve => { finish = resolve; });
  const request = context.decide("approve");
  assert.equal(typeof finish, "function");
  disabled(true); context.updateApprovalControls(); disabled(true);
  finish({id: "r-current", status: "completed", approval: {status: "approved"}});
  await request;
  assert.equal(state.approvalBusy, false); disabled(true);

  state.run = pending();
  context.api = async () => { throw new Error("temporary connection failure"); };
  await context.decide("approve");
  disabled(false);

  state.selectedId = "r-other"; context.updateApprovalControls(); disabled(true);
  let calls = 0;
  context.api = async () => { calls++; };
  await context.decide("approve");
  assert.equal(calls, 0); disabled(true);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", code, str(ui.ASSET)], capture_output=True, text=True, timeout=15, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_javascript_never_polls_a_null_run_id():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable for the optional JavaScript polling regression.")
    code = r"""
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const script=fs.readFileSync(process.argv[1],"utf8").match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1];
const section=script.slice(script.indexOf("async function poll("),script.indexOf('$("definition-form").addEventListener'));
let calls=0;
const context={state:{selectedId:null,polling:false},api:()=>{calls++;throw new Error("Unexpected request");}};
vm.runInNewContext(section,context);
async function main() {
  for (const id of [null,undefined,""]) {
    context.state.selectedId=id;
    await context.poll();
    assert.equal(calls,0);
    assert.equal(context.state.polling,false);
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [node, "-e", code, str(ui.ASSET)], capture_output=True, text=True, timeout=15, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_style_nonce_rewrites_real_style_tags_only_and_preserves_css():
    source = (
        '<!doctype html>\r\n<!-- <style>comment</style> -->\r\n'
        '<style nonce="old" media="screen &amp; print">\r\nbody {color: red}\r\n</style>'
        '<script>const text = "<style>not a tag</style>";</script>'
        '<STYLE>svg {width: 100%}</STYLE>'
    )
    rendered = _nonce_styles(source, "style-only-nonce")
    assert rendered.count('nonce="style-only-nonce"') == 2
    assert 'nonce="old"' not in rendered
    assert 'media="screen &amp; print"' in rendered
    assert '<!-- <style>comment</style> -->' in rendered
    assert '<script>const text = "<style>not a tag</style>";</script>' in rendered
    assert "\r\nbody {color: red}\r\n" in rendered
    assert "<style nonce=\"style-only-nonce\">svg {width: 100%}</STYLE>" in rendered


def test_dashboard_style_nonce_supports_inherited_csp_without_exposing_request_nonce(consoles):
    original = '<!doctype html><style>body{background:#070b16}</style><h1>Fixture</h1>'

    async def runner(_inputs, _skills, out_dir, **_kwargs):
        (out_dir / "dashboard.html").write_text(original, encoding="utf-8")
        return {"status": "unverified_preview", "certified": False, "dashboard": "dashboard.html"}

    console = consoles(runner)
    run = console.wait(console.start()["id"], "completed")
    status, rendered, headers = console.request("GET", run["artifacts"]["dashboard"]["url"])
    assert status == 200
    assert f'<style nonce="{console.server.style_nonce}">' in rendered
    assert console.server.nonce not in rendered
    assert (console.root / "runs" / run["id"] / "dashboard.html").read_text(encoding="utf-8") == original
    assert headers["Content-Security-Policy"] == (
        "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'self'"
    )
    _, _, root_headers = console.request("GET", "/")
    assert "style-src 'unsafe-inline'" not in root_headers["Content-Security-Policy"]
    assert f"style-src 'nonce-{console.server.style_nonce}'" in root_headers["Content-Security-Policy"]


def test_run_lifecycle_waits_for_human_and_serves_only_registered_artifact(consoles):
    console = consoles(wait_for_human)
    started = console.start()
    waiting = console.wait(started["id"], "awaiting_approval")
    assert waiting["approval"]["status"] == "pending"
    assert waiting["approval"]["reviewer"] is None
    assert waiting["approval"]["report"]["passed"] is True
    time.sleep(0.03)
    still_waiting = console.wait(started["id"], "awaiting_approval")
    assert still_waiting["result"] is None
    status, page, headers = console.request("GET", waiting["approval"]["dashboard_url"])
    assert status == 200
    assert "Test reviewer artifact" in page
    assert "sandbox allow-scripts" in headers["Content-Security-Policy"]
    assert "allow-same-origin" not in headers["Content-Security-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    second_status, second, _ = console.request("POST", "/api/runs", {"config": profiles()["scripted"]["config"]})
    assert second_status == 409
    assert "already active" in second["error"]
    status, _, _ = console.request(
        "POST", f"/api/runs/{started['id']}/approval", {"decision": "approve", "reviewer": "Test Reviewer"},
    )
    assert status == 200
    completed = console.wait(started["id"], "completed")
    assert completed["approval"]["status"] == "approved"
    assert completed["approval"]["reviewer"] == "Test Reviewer"
    assert completed["result"]["reviewer"] == "Test Reviewer"
    status, _, _ = console.request(
        "POST", f"/api/runs/{started['id']}/approval", {"decision": "approve", "reviewer": "Second Reviewer"},
    )
    assert status == 409
    status, bootstrap, _ = console.request("GET", "/api/bootstrap")
    assert status == 200
    assert bootstrap["active_run_id"] is None
    assert bootstrap["runs"][0]["id"] == started["id"]
    assert console.start()["id"] != started["id"]


def test_rejection_releases_wait_without_approval(consoles):
    console = consoles(wait_for_human)
    started = console.start()
    console.wait(started["id"], "awaiting_approval")
    status, _, _ = console.request(
        "POST", f"/api/runs/{started['id']}/approval", {"decision": "reject", "reviewer": "Review Lead"},
    )
    assert status == 200
    rejected = console.wait(started["id"], "rejected")
    assert rejected["approval"]["status"] == "rejected"
    assert rejected["approval"]["reviewer"] == "Review Lead"
    assert "PermissionError" in rejected["error"]


def test_missing_human_approval_expires_not_auto_approves(consoles):
    console = consoles(wait_for_human, timeout=0.04)
    started = console.start()
    failed = console.wait(started["id"], "failed")
    assert failed["approval"]["status"] == "expired"
    assert failed["approval"]["reviewer"] is None
    assert "timed out" in failed["error"]
    assert failed["result"] is None


def test_observe_only_report_remains_failed_at_human_gate(consoles):
    async def runner(_inputs, _skills, out_dir, *, approval_provider, **_kwargs):
        dashboard = out_dir / "dashboard.html"
        dashboard.write_text("<h1>Unverified fixture preview</h1>", encoding="utf-8")
        reviewer = approval_provider(dashboard, make_report(False))
        return {"status": "unverified_preview", "reviewer": reviewer}

    console = consoles(runner)
    config = profiles()["scripted"]["config"]
    config["gate_mode"] = "observe"
    started = console.start(config)
    waiting = console.wait(started["id"], "awaiting_approval")
    assert waiting["approval"]["report"]["passed"] is False
    assert waiting["approval"]["status"] == "pending"
    assert set(waiting["artifacts"]) == {"dashboard"}


def test_observe_only_result_can_expose_explicit_uncertified_dashboard(consoles):
    async def runner(_inputs, _skills, out_dir, **_kwargs):
        dashboard = out_dir / "dashboard.html"
        dashboard.write_text("<h1>Unverified fixture preview</h1>", encoding="utf-8")
        return {"status": "unverified_preview", "certified": False, "dashboard": "dashboard.html"}

    console = consoles(runner)
    finished = console.wait(console.start()["id"], "completed")
    assert finished["result"]["certified"] is False
    assert finished["approval"] is None
    status, content, headers = console.request("GET", finished["artifacts"]["dashboard"]["url"])
    assert status == 200
    assert "Unverified fixture preview" in content
    assert "sandbox allow-scripts" in headers["Content-Security-Policy"]


def test_native_span_and_custom_event_snapshot_share_trace_and_redact_credentials(consoles):
    async def runner(_inputs, _skills, out_dir, **_kwargs):
        evidence = {
            "trace_id": "1" * 32,
            "spans": [{
                "trace_id": "1" * 32, "span_id": "2" * 16, "parent_span_id": None,
                "name": "chat fixture", "origin": "maf", "start_time": "2026-09-17T14:00:00Z",
                "end_time": "2026-09-17T14:00:01Z", "status": {"code": "OK"},
                "attributes": {"gen_ai.request.model": "fixture", "api_key": "not-for-browser"},
                "events": [],
            }],
            "events": [{
                "event": "skill.loaded", "id": "event-1", "at": "2026-09-17T14:00:00Z",
                "trace_id": "1" * 32, "span_id": "2" * 16, "skill": "event-date-alignment",
            }],
        }
        (out_dir / "telemetry.json").write_text(json.dumps(evidence), encoding="utf-8")
        (out_dir / "runtime-state.json").write_text(json.dumps({
            "status": "running", "Authorization": "Bearer sensitive-credential",
        }), encoding="utf-8")
        (out_dir / "result.json").write_text(json.dumps({"status": "fixture"}), encoding="utf-8")
        return {"status": "fixture"}

    console = consoles(runner)
    completed = console.wait(console.start()["id"], "completed")
    assert completed["telemetry"]["trace_id"] == "1" * 32
    assert completed["telemetry"]["spans"][0]["origin"] == "maf"
    assert completed["telemetry"]["spans"][0]["attributes"]["api_key"] == "[redacted]"
    assert completed["telemetry"]["events"][0]["span_id"] == "2" * 16
    assert completed["runtime_state"]["Authorization"] == "[redacted]"
    assert completed["result"]["status"] == "fixture"


def test_failure_keeps_telemetry_and_reports_safe_error(consoles):
    async def failing(_inputs, _skills, out_dir, **_kwargs):
        (out_dir / "telemetry.json").write_text('{"trace_id":"failed-trace","spans":[],"events":[]}', encoding="utf-8")
        raise RuntimeError("Request failed with Bearer test-sensitive-token")

    console = consoles(failing)
    result = console.wait(console.start()["id"], "failed")
    assert result["telemetry"]["trace_id"] == "failed-trace"
    assert result["error"] == "RuntimeError: Request failed with Bearer [redacted]"


def health_record(status, at):
    return {
        "status": status, "write_failures": 1, "consecutive_failures": int(status == "degraded"),
        "last_error": {"type": "PermissionError", "errno": 13, "winerror": 5},
        "last_failure_at": at if status == "degraded" else None,
        "last_success_at": at if status == "healthy" else None,
    }


@pytest.mark.parametrize("snapshot_status,sidecar_status,newest,expected_source,expected_status", [
    ("healthy", "degraded", "sidecar", "telemetry-health.json", "degraded"),
    ("healthy", "degraded", "snapshot", "telemetry.json", "healthy"),
    ("degraded", "healthy", "snapshot", "telemetry.json", "degraded"),
    ("degraded", "healthy", "sidecar", "telemetry-health.json", "healthy"),
    ("degraded", None, "snapshot", "telemetry.json", "degraded"),
    (None, "degraded", "sidecar", "telemetry-health.json", "degraded"),
])
def test_export_health_is_read_only_and_never_changes_completed_application_status(
    consoles, snapshot_status, sidecar_status, newest, expected_source, expected_status,
):
    console = consoles(finish_without_approval)
    run = console.wait(console.start()["id"], "completed")
    directory = console.server.manager.get(run["id"]).directory
    before = {}
    for source, status in (("snapshot", snapshot_status), ("sidecar", sidecar_status)):
        if status is None:
            continue
        at = "2026-09-17T22:00:02.123456789Z" if newest == source else "2026-09-17T22:00:01.123456789Z"
        data = {"trace_id": "c" * 32, "export_health": health_record(status, at)}
        path = directory / ("telemetry.json" if source == "snapshot" else "telemetry-health.json")
        path.write_text(json.dumps(data), encoding="utf-8")
        before[path] = path.read_bytes()
    _, response, _ = console.request("GET", f"/api/runs/{run['id']}")
    assert response["status"] == "completed"
    assert response["result"]["status"] == "test-finished"
    assert response["error"] is None
    assert response["export_health"]["status"] == expected_status
    assert response["export_health_source"] == expected_source
    assert response["export_health"]["last_error"]["winerror"] == 5
    if sidecar_status:
        assert response["telemetry_health"]["export_health"]["status"] == sidecar_status
    assert all(path.read_bytes() == contents for path, contents in before.items())


def test_sidecar_health_is_available_when_the_main_snapshot_is_unreadable(consoles):
    console = consoles(finish_without_approval)
    run = console.wait(console.start()["id"], "completed")
    directory = console.server.manager.get(run["id"]).directory
    (directory / "telemetry.json").write_text('{"trace_id":', encoding="utf-8")
    sidecar = {"trace_id": "d" * 32, "export_health": health_record("degraded", "2026-09-17T22:00:01Z")}
    (directory / "telemetry-health.json").write_text(json.dumps(sidecar), encoding="utf-8")
    _, response, _ = console.request("GET", f"/api/runs/{run['id']}")
    assert response["telemetry"] is None
    assert response["telemetry_health"] == sidecar
    assert response["export_health"]["status"] == "degraded"
    assert response["status"] == "completed"


def test_export_health_does_not_mix_trace_ids(consoles):
    console = consoles(finish_without_approval)
    run = console.wait(console.start()["id"], "completed")
    directory = console.server.manager.get(run["id"]).directory
    (directory / "telemetry.json").write_text(json.dumps({
        "trace_id": "a" * 32, "export_health": health_record("healthy", "2026-09-17T22:00:01Z"),
    }), encoding="utf-8")
    (directory / "telemetry-health.json").write_text(json.dumps({
        "trace_id": "b" * 32, "export_health": health_record("degraded", "2026-09-17T22:00:02Z"),
    }), encoding="utf-8")
    _, response, _ = console.request("GET", f"/api/runs/{run['id']}")
    assert response["export_health"]["status"] == "healthy"
    assert response["export_health_source"] == "telemetry.json"
    assert response["telemetry_health"]["trace_id"] == "b" * 32


def test_actual_javascript_warns_for_degraded_completed_runs_without_changing_status():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable for the optional JavaScript health regression.")
    code = r"""
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const page=fs.readFileSync(process.argv[1],"utf8");
const script=page.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const section=script.slice(script.indexOf("function renderExportHealth("),script.indexOf("function renderRun("));
const fields={"export-warning":{hidden:true},"export-health-json":{text:""}};
const context={$:id=>fields[id],setText:(id,text)=>{fields[id].text=text;}};
vm.runInNewContext(section,context);
const run={status:"completed",result:{certified:true},export_health:{status:"degraded",write_failures:2},export_health_source:"telemetry-health.json",telemetry_health:{trace_id:"fixture",export_health:{status:"degraded"}}};
const original=JSON.stringify(run);
context.renderExportHealth(run);
assert.equal(fields["export-warning"].hidden,false);
assert.equal(JSON.stringify(run),original);
assert.equal(JSON.parse(fields["export-health-json"].text).source,"telemetry-health.json");
assert.equal(JSON.parse(fields["export-health-json"].text).sidecar.trace_id,"fixture");
context.renderExportHealth({...run,export_health:{status:"healthy"}});
assert.equal(fields["export-warning"].hidden,true);
context.renderExportHealth({status:"completed",telemetry:{export_health:{status:"degraded"}}});
assert.equal(fields["export-warning"].hidden,false);
context.renderExportHealth({status:"completed"});
assert.equal(fields["export-warning"].hidden,true);
assert(page.includes("Evidence may be stale or incomplete."));
"""
    result = subprocess.run(
        [node, "-e", code, str(ui.ASSET)], capture_output=True, text=True, timeout=15, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("headers", [
    {"Origin": "https://foreign.example"},
    {"Origin": "null"},
    {"Host": "foreign.example"},
    {"Host": "127.0.0.1:1"},
    {"X-Harness-Nonce": ""},
    {"X-Harness-Nonce": "wrong-nonce"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_foreign_host_origin_or_missing_nonce_cannot_start_runs(consoles, headers):
    console = consoles(finish_without_approval)
    status, _, response_headers = console.request(
        "POST", "/api/runs", {"config": profiles()["scripted"]["config"]}, headers=headers,
    )
    assert status == 403
    assert not console.server.manager.runs
    assert "Access-Control-Allow-Origin" not in response_headers


def test_foreign_host_cannot_read_the_nonce_or_runtime_data(consoles):
    console = consoles(finish_without_approval)
    for path in ("/", "/api/bootstrap"):
        status, body, _ = console.request("GET", path, headers={"Host": "attacker.example"})
        assert status == 403
        assert console.server.nonce not in json.dumps(body)


def test_nonce_allows_non_browser_loopback_client_without_origin(consoles):
    console = consoles(finish_without_approval)
    connection = http.client.HTTPConnection("127.0.0.1", console.server.server_port, timeout=3)
    payload = json.dumps({"config": profiles()["scripted"]["config"]})
    connection.request("POST", "/api/runs", payload, {
        "Content-Type": "application/json", "X-Harness-Nonce": console.server.nonce,
    })
    response = connection.getresponse()
    assert response.status == 202
    response.read()
    connection.close()


@pytest.mark.parametrize("body,expected", [
    (b"x" * (MAX_BODY_BYTES + 1), 413),
    (b"{invalid", 400),
    (b'["not", "an", "object"]', 400),
    (b"{}", 400),
    (b'{"config":null}', 400),
    (b'{"config":{},"out_dir":"outside"}', 400),
], ids=["oversized", "malformed", "array", "empty", "null-config", "outside-path"])
def test_request_bodies_are_capped_and_shape_checked(consoles, body, expected):
    console = consoles(finish_without_approval)
    status, _, _ = console.request("POST", "/api/runs", raw=body)
    assert status == expected
    assert not console.server.manager.runs


@pytest.mark.parametrize("patch", [
    {"max_model_requests": 1000},
    {"max_tool_calls": 0},
    {"execution_timeout_seconds": 31},
    {"max_execution_attempts": True},
    {"memory_scope": "../outside"},
    {"enabled_tools": ["request_approval"]},
    {"available_skills": ["../outside"]},
    {"model": "unknown"},
    {"deployment": "arbitrary-host"},
    {"disable_policy": True},
    {"out_dir": "outside"},
])
def test_invalid_config_and_infrastructure_toggles_are_rejected(consoles, patch):
    console = consoles(finish_without_approval)
    config = {**profiles()["scripted"]["config"], **patch}
    status, _, _ = console.request("POST", "/api/runs", {"config": config})
    assert status == 400
    assert not console.server.manager.runs


@pytest.mark.parametrize("path", [
    "/../README.md", "/%2e%2e/README.md", "/api/runs/%2e%2e",
    "/api/runs/r-0000000000000000", "/api/runs/..%5c..%5cREADME.md",
    "/api/runs/%00", "/memory", "/demo/sample-input/internal-portfolio.json",
    "/api/bootstrap?file=README.md",
])
def test_unknown_paths_encoded_traversal_and_non_run_files_are_not_served(consoles, path):
    console = consoles(finish_without_approval)
    status, _, _ = console.request("GET", path)
    assert status == 404


def test_only_runtime_registered_dashboard_can_be_served(consoles):
    console = consoles(wait_for_human)
    started = console.start()
    console.wait(started["id"], "awaiting_approval")
    run = console.server.manager.get(started["id"])
    (run.directory / "secret.html").write_text("not an approved artifact", encoding="utf-8")
    for suffix in ("secret.html", "telemetry.json", "../secret.html", "%2e%2e%2fsecret.html", "attempt-1/dashboard.html"):
        status, _, _ = console.request("GET", f"/api/runs/{started['id']}/artifacts/{suffix}")
        assert status == 404


def test_runtime_cannot_register_an_outside_artifact(consoles):
    async def runner(_inputs, _skills, out_dir, *, approval_provider, **_kwargs):
        outside = out_dir.parent / "outside.html"
        outside.write_text("<h1>Outside run</h1>", encoding="utf-8")
        approval_provider(outside, make_report())
        return {}

    console = consoles(runner)
    result = console.wait(console.start()["id"], "failed")
    assert result["approval"] is None
    assert result["artifacts"] == {}
    assert "inside this run" in result["error"]


def test_symlink_escape_is_not_read_as_runtime_state(consoles):
    console = consoles(finish_without_approval)
    result = console.wait(console.start()["id"], "completed")
    run = console.server.manager.get(result["id"])
    outside = console.root / "private.json"
    outside.write_text('{"secret":"not allowed"}', encoding="utf-8")
    try:
        (run.directory / "runtime-state.json").symlink_to(outside)
    except OSError:
        pytest.skip("This Windows account cannot create symbolic links.")
    status, response, _ = console.request("GET", f"/api/runs/{run.id}")
    assert status == 200
    assert response["runtime_state"] is None


def test_partially_written_json_is_retried_on_the_next_poll(consoles):
    console = consoles(finish_without_approval)
    result = console.wait(console.start()["id"], "completed")
    run = console.server.manager.get(result["id"])
    path = run.directory / "telemetry.json"
    path.write_text('{"trace_id":', encoding="utf-8")
    _, result, _ = console.request("GET", f"/api/runs/{run.id}")
    assert result["telemetry"] is None
    path.write_text('{"trace_id":"recovered","spans":[],"events":[]}', encoding="utf-8")
    _, result, _ = console.request("GET", f"/api/runs/{run.id}")
    assert result["telemetry"]["trace_id"] == "recovered"


@pytest.mark.parametrize("legacy_metadata", [False, True])
def test_restart_restores_finished_history_and_retained_trace_without_rewriting_evidence(consoles, legacy_metadata):
    console = consoles(finish_with_retained_evidence)
    run = console.wait(console.start()["id"], "completed")
    console.close()
    metadata_path = console.root / "runs" / ".console" / f"{run['id']}.json"
    if legacy_metadata:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.pop("restored", None)
        metadata["artifacts"]["dashboard"].pop("relative_path")
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    before = {path: path.read_bytes() for path in (console.root / "runs").rglob("*") if path.is_file()}
    calls = []

    async def must_not_resume(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Saved history must never invoke a runtime.")

    restarted = consoles(must_not_resume, restore_from=console)
    _, bootstrap, _ = restarted.request("GET", "/api/bootstrap")
    assert bootstrap["active_run_id"] is None
    assert [item["id"] for item in bootstrap["runs"]] == [run["id"]]
    assert bootstrap["runs"][0]["restored"] is True
    retained = restarted.wait(run["id"], "completed")
    assert retained["telemetry"]["trace_id"] == "f" * 32
    assert retained["result"]["status"] == "unverified_preview"
    assert retained["result"]["certified"] is False
    status, dashboard, _ = restarted.request("GET", retained["artifacts"]["dashboard"]["url"])
    assert status == 200
    assert "Retained fixture preview" in dashboard
    assert not calls
    assert restarted.server.manager.get(run["id"]).thread is None
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize("old_status", ["running", "awaiting_approval"])
def test_restart_marks_stale_inflight_runs_interrupted_and_never_resumes_approval(consoles, old_status):
    console = consoles(wait_for_human)
    run = console.start()
    console.wait(run["id"], "awaiting_approval")
    metadata_path = console.root / "runs" / ".console" / f"{run['id']}.json"
    stale = json.loads(metadata_path.read_text(encoding="utf-8"))
    console.close()
    stale["status"] = old_status
    metadata_path.write_text(json.dumps(stale), encoding="utf-8")
    original = metadata_path.read_bytes()
    restarted = consoles(finish_without_approval, restore_from=console)
    retained = restarted.wait(run["id"], "interrupted")
    assert retained["restored"] is True
    assert retained["approval"]["status"] == "interrupted"
    assert "No execution or approval was resumed" in retained["error"]
    assert restarted.server.manager.active_id is None
    assert not restarted.server.manager.get(run["id"]).approval_event.is_set()
    assert restarted.server.manager.get(run["id"]).thread is None
    status, _, _ = restarted.request(
        "POST", f"/api/runs/{run['id']}/approval", {"decision": "approve", "reviewer": "Cannot resume"},
    )
    assert status == 409
    assert metadata_path.read_bytes() == original
    assert restarted.start()["id"] != run["id"]


@pytest.mark.parametrize("old_status", ["failed", "rejected"])
def test_restart_keeps_finished_failure_statuses(consoles, old_status):
    console = consoles(finish_without_approval)
    run = console.wait(console.start()["id"], "completed")
    console.close()
    metadata_path = console.root / "runs" / ".console" / f"{run['id']}.json"
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    saved["status"] = old_status
    metadata_path.write_text(json.dumps(saved), encoding="utf-8")
    restarted = consoles(finish_without_approval, restore_from=console)
    assert restarted.wait(run["id"], old_status)["restored"] is True


@pytest.mark.parametrize("defect", [
    "mismatched-id", "bad-config", "bad-time", "outside-artifact", "missing-directory",
    "oversized", "malformed", "foreign-url",
])
def test_restart_rejects_invalid_or_unowned_saved_metadata(consoles, defect):
    console = consoles(finish_with_retained_evidence)
    run = console.wait(console.start()["id"], "completed")
    console.close()
    path = console.root / "runs" / ".console" / f"{run['id']}.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    if defect == "mismatched-id":
        saved["id"] = "r-" + "0" * 16
    elif defect == "bad-config":
        saved["config"]["memory_scope"] = "../outside"
    elif defect == "bad-time":
        saved["created_at"] = "not-a-timestamp"
    elif defect == "outside-artifact":
        saved["artifacts"]["dashboard"]["relative_path"] = str(Path("..") / "outside.html")
    elif defect == "missing-directory":
        (console.root / "runs" / run["id"]).rename(console.root / "moved-run")
    elif defect == "foreign-url":
        saved["artifacts"]["dashboard"]["url"] = "https://foreign.example"
    path.write_text(json.dumps(saved), encoding="utf-8")
    if defect == "oversized":
        path.write_bytes(b" " * (ui.MAX_HISTORY_METADATA_BYTES + 1))
    elif defect == "malformed":
        path.write_text("{", encoding="utf-8")
    restarted = consoles(finish_without_approval, restore_from=console)
    _, bootstrap, _ = restarted.request("GET", "/api/bootstrap")
    assert bootstrap["runs"] == []
    assert bootstrap["active_run_id"] is None


def test_restart_caps_history_to_the_newest_metadata_files(consoles, monkeypatch):
    console = consoles(finish_without_approval)
    run = console.wait(console.start()["id"], "completed")
    console.close()
    metadata_dir = console.root / "runs" / ".console"
    original_path = metadata_dir / f"{run['id']}.json"
    saved = json.loads(original_path.read_text(encoding="utf-8"))
    os.utime(original_path, (0, 0))
    for index in range(1, 6):
        run_id = f"r-{index:016x}"
        (console.root / "runs" / run_id).mkdir()
        path = metadata_dir / f"{run_id}.json"
        path.write_text(json.dumps({**saved, "id": run_id}), encoding="utf-8")
        os.utime(path, (index, index))
    monkeypatch.setattr(ui, "MAX_HISTORY_RUNS", 2)
    restarted = consoles(finish_without_approval, restore_from=console)
    _, bootstrap, _ = restarted.request("GET", "/api/bootstrap")
    assert {item["id"] for item in bootstrap["runs"]} == {"r-0000000000000004", "r-0000000000000005"}


def test_restart_does_not_follow_a_linked_run_directory(consoles, monkeypatch):
    console = consoles(finish_without_approval)
    run = console.wait(console.start()["id"], "completed")
    console.close()
    directory = console.root / "runs" / run["id"]
    resolve = Path.resolve

    def redirected(path, *args, **kwargs):
        return console.root / "outside" if path == directory else resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    restarted = consoles(finish_without_approval, restore_from=console)
    _, bootstrap, _ = restarted.request("GET", "/api/bootstrap")
    assert bootstrap["runs"] == []


@pytest.mark.parametrize("body", [
    {"decision": "accept", "reviewer": "Reviewer"},
    {"decision": "approve", "reviewer": ""},
    {"decision": "approve", "reviewer": "  "},
    {"decision": "approve", "reviewer": "x" * 121},
    {"decision": "approve", "reviewer": "Bad\nName"},
    {"decision": "approve", "reviewer": "Reviewer", "certificate": True},
])
def test_approval_input_is_validated_without_releasing_the_wait(consoles, body):
    console = consoles(wait_for_human)
    run = console.start()
    console.wait(run["id"], "awaiting_approval")
    status, _, _ = console.request("POST", f"/api/runs/{run['id']}/approval", body)
    assert status == 400
    assert console.wait(run["id"], "awaiting_approval")["approval"]["status"] == "pending"


def test_foreign_origin_cannot_approve_a_run(consoles):
    console = consoles(wait_for_human)
    run = console.start()
    console.wait(run["id"], "awaiting_approval")
    status, _, _ = console.request(
        "POST", f"/api/runs/{run['id']}/approval",
        {"decision": "approve", "reviewer": "Foreign Reviewer"},
        headers={"Origin": "https://foreign.example"},
    )
    assert status == 403
    assert console.wait(run["id"], "awaiting_approval")["approval"]["status"] == "pending"


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.2", "example.com"])
def test_non_loopback_binding_is_rejected(host):
    with pytest.raises(ValueError, match="127.0.0.1"):
        create_ui_server(INPUTS, SKILLS, REPO / ".test-harness-ui", memory_dir=REPO, host=host, port=0)

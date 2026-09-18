"""Offline-safe coverage of the exact runtime used by the Azure model and console."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from equity_event.live import run_live_episode
from equity_event.live_config import HarnessConfig, profiles
from equity_event.runs import ApprovalRequired, CompletionDenied

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "demo" / "sample-input"
SKILLS = ROOT / "demo" / "agent" / "skills"


def execute(tmp_path, name, *, config=None, approve=True):
    return asyncio.run(run_live_episode(
        INPUT, SKILLS, tmp_path / name,
        config=config or HarnessConfig(model="scripted"),
        memory_dir=tmp_path / "memory",
        approval_provider=(lambda _artifact, _report: "offline-test") if approve else None,
        approval_kind="automated-test-not-human",
    ))


def events(path):
    return json.loads((path / "runtime-state.json").read_text(encoding="utf-8"))["events"]


def test_same_runtime_executes_calls_skills_and_cross_run_memory(tmp_path):
    first = execute(tmp_path, "first")
    second = execute(tmp_path, "second")
    assert first["certified"] and second["certified"]
    assert first["attempts"] == second["attempts"] == 2
    assert second["memory_recalled_from"] == first["trace_id"]
    assert first["trace_id"] != second["trace_id"]
    observed = events(tmp_path / "second")
    names = [item["event"] for item in observed]
    assert "cross_run_memory_recalled" in names
    assert names.index("memory_read") < names.index("plan_recorded")
    assert names.index("memory_written") < names.index("completion_admitted")
    assert names.index("skill_catalog_discovered") < names.index("skill_selected") < names.index("skill_loaded")
    assert names.index("skill_loaded") < names.index("skill_used")
    turns = [item for item in observed if item["event"] == "conversation_turn_started"]
    assert [item["phase"] for item in turns] == ["plan", "execute"]
    assert turns[0]["session_id"] == turns[1]["session_id"]
    assert "bounded_correction_requested" in names
    telemetry = json.loads((tmp_path / "second" / "telemetry.json").read_text(encoding="utf-8"))
    assert telemetry["trace_id"] == second["trace_id"]
    assert any("load_skill" in item["name"] for item in telemetry["spans"])
    assert any("execute_analysis" in item["name"] for item in telemetry["spans"])
    assert (tmp_path / "second" / "agent-session.json").is_file()


def test_observe_profile_does_not_certify_a_failed_preview(tmp_path):
    config = HarnessConfig(model="scripted", skill_mode="all_loaded", memory_enabled=False, gate_mode="observe")
    result = execute(tmp_path, "observe", config=config)
    assert result["status"] == "unverified_preview" and not result["certified"]
    assert not (tmp_path / "observe" / "evidence-certificate.json").exists()
    observed = events(tmp_path / "observe")
    assert any(item["event"] == "skill_preloaded" for item in observed)
    assert not any(item["event"] in {"skill_loaded", "memory_read", "memory_written"} for item in observed)


def test_no_approval_means_no_memory_or_certificate(tmp_path):
    with pytest.raises(ApprovalRequired):
        execute(tmp_path, "pending", approve=False)
    names = [item["event"] for item in events(tmp_path / "pending")]
    assert "approval_requested" in names
    assert "memory_written" not in names
    assert "completion_admitted" not in names


def test_attempt_budget_stops_unrepaired_output(tmp_path):
    with pytest.raises((CompletionDenied, RuntimeError)):
        execute(tmp_path, "bounded", config=HarnessConfig(model="scripted", max_execution_attempts=1))
    assert not (tmp_path / "bounded" / "evidence-certificate.json").exists()
    assert json.loads((tmp_path / "bounded" / "result.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("change", [
    {"memory_scope": "../outside"}, {"memory_enabled": "yes"}, {"enabled_tools": ["shell"]},
    {"available_skills": ["unknown"]}, {"max_tool_calls": 0}, {"max_execution_attempts": 99},
    {"max_model_requests": True}, {"execution_timeout_seconds": 0}, {"gate_mode": "disabled"},
    {"api_key": "not-a-real-key"},
    {"model": []}, {"deployment": {}}, {"skill_mode": None}, {"gate_mode": True},
])
def test_config_rejects_unsupported_or_unsafe_knobs(change):
    with pytest.raises(ValueError):
        HarnessConfig.from_dict(change)


def test_profiles_have_a_visible_honest_contrast():
    values = profiles()
    assert values["governed"]["config"]["model"] == "live"
    assert values["naive"]["config"]["skill_mode"] == "all_loaded"
    assert values["naive"]["config"]["gate_mode"] == "observe"
    assert not values["naive"]["config"]["memory_enabled"]
    assert values["scripted"]["config"]["model"] == "scripted"


def test_malformed_tool_arguments_are_returned_for_real_loop_recovery(tmp_path, monkeypatch):
    from equity_event.live import ScriptedToolClient

    original = ScriptedToolClient._next
    injected = []

    def malformed_once(client):
        name, args = original(client)
        if name == "public_source_search" and not injected:
            injected.append(True)
            return name, {"query": ""}
        return name, args

    monkeypatch.setattr(ScriptedToolClient, "_next", malformed_once)
    result = execute(tmp_path, "recovered")
    assert result["certified"] and injected
    rejected = [event for event in events(tmp_path / "recovered") if event["event"] == "control_rejected"]
    assert any("nonempty research query" in event["reason"] for event in rejected)
    telemetry = json.loads((tmp_path / "recovered" / "telemetry.json").read_text())
    assert any(span["status"]["code"] == "ERROR" for span in telemetry["spans"])


def test_model_refusal_cannot_self_declare_completion(tmp_path, monkeypatch):
    from equity_event.live import ScriptedToolClient

    monkeypatch.setattr(ScriptedToolClient, "_next", lambda _client: (None, {}))
    with pytest.raises(CompletionDenied, match="bounded continuations"):
        execute(tmp_path, "refused")
    result = json.loads((tmp_path / "refused" / "result.json").read_text())
    assert result["status"] == "failed"
    assert not (tmp_path / "refused" / "evidence-certificate.json").exists()
    assert not any(event["event"] == "memory_written" for event in events(tmp_path / "refused"))


def test_observe_mode_cannot_claim_a_preview_when_execution_produced_none(tmp_path, monkeypatch):
    from equity_event.live_analysis import execute_live_analysis

    def missing_outputs(*args, **kwargs):
        result = execute_live_analysis(*args, **kwargs)
        result.analysis_path.unlink()
        result.dashboard_path.unlink()
        return result

    monkeypatch.setattr("equity_event.live.execute_live_analysis", missing_outputs)
    config = HarnessConfig(model="scripted", gate_mode="observe", max_model_requests=20)
    with pytest.raises((CompletionDenied, RuntimeError)):
        execute(tmp_path, "no-preview", config=config)
    assert not any(event["event"] == "unverified_preview" for event in events(tmp_path / "no-preview"))
    assert json.loads((tmp_path / "no-preview" / "result.json").read_text())["status"] == "failed"


def test_memory_toggle_and_scope_change_the_next_episode(tmp_path):
    first = execute(tmp_path, "scope-first", config=HarnessConfig(model="scripted", memory_scope="scope-a"))
    isolated = execute(tmp_path, "scope-isolated", config=HarnessConfig(model="scripted", memory_scope="scope-b"))
    disabled = execute(tmp_path, "scope-disabled", config=HarnessConfig(model="scripted", memory_enabled=False))
    recalled = execute(tmp_path, "scope-recall", config=HarnessConfig(model="scripted", memory_scope="scope-a"))
    assert isolated["memory_recalled_from"] is None
    assert disabled["memory_recalled_from"] is None
    assert recalled["memory_recalled_from"] == first["trace_id"]
    assert not any(item["event"].startswith("memory_") for item in events(tmp_path / "scope-disabled"))


def test_live_cli_defaults_to_current_runtime_and_scratch_output():
    from equity_event.cli import DEFAULT_LIVE_OUT, build_parser

    parser = build_parser()
    args = parser.parse_args(["run"])
    assert args.profile == "governed" and args.model is None
    assert args.output == DEFAULT_LIVE_OUT
    assert parser.parse_args(["run", "--model", "scripted"]).model == "scripted"
    assert parser.parse_args(["serve"]).port == 8765
    assert parser.parse_args(["--output", "custom-output", "serve"]).output == Path("custom-output")


@pytest.mark.parametrize("command", ["compare", "run-a", "run-b", "diagnose", "source-check"])
def test_retired_cli_commands_are_not_advertised_or_executable(command):
    from equity_event.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as stopped:
        parser.parse_args([command])
    assert stopped.value.code == 2
    assert command not in parser.format_help()


def test_snapshot_replacement_retries_transient_windows_read_locks(tmp_path, monkeypatch, caplog):
    from equity_event.live import _write

    original = Path.replace
    attempts = []

    def locked_twice(path, target):
        attempts.append(target)
        if len(attempts) < 3:
            raise PermissionError("simulated Windows reader lock")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", locked_twice)
    monkeypatch.setattr("equity_event.live.time.sleep", lambda _delay: None)
    target = tmp_path / "state.json"
    _write(target, {"status": "running"})
    assert len(attempts) == 3
    assert json.loads(target.read_text()) == {"status": "running"}
    assert "temporarily locked" in caplog.text


def test_snapshot_replacement_fails_explicitly_after_retry_budget(tmp_path, monkeypatch):
    from equity_event.live import _write

    def denied(*_args):
        raise PermissionError("permanent write denial")

    monkeypatch.setattr(Path, "replace", denied)
    monkeypatch.setattr("equity_event.live.time.sleep", lambda _delay: None)
    with pytest.raises(PermissionError, match="permanent write denial"):
        _write(tmp_path / "state.json", {"status": "running"})


@pytest.mark.skipif(os.environ.get("EQUITY_LIVE_TEST") != "1", reason="Opt-in Azure token-auth integration test.")
def test_real_azure_episode_and_second_run_recall(tmp_path):
    config = HarnessConfig(memory_scope="live-integration")
    first = execute(tmp_path, "live-first", config=config)
    second = execute(tmp_path, "live-second", config=config)
    assert first["certified"] and second["certified"]
    assert first["deployment"] == "gpt-5.6-terra"
    assert second["memory_recalled_from"] == first["trace_id"]

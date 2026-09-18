"""Offline evidence that the console consumes MAF spans, not imitation wrappers."""

from __future__ import annotations

import asyncio
import errno
import json
import re
from pathlib import Path
from threading import enumerate as enumerate_threads
from time import monotonic

import pytest
from agent_framework import Agent, FunctionTool
from agent_framework.observability import OBSERVABILITY_SETTINGS
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI
from opentelemetry import trace as otel_trace
from opentelemetry.context import Context

from equity_event.live_telemetry import (
    APPLICATION_SCOPE,
    MAX_STRING_LENGTH,
    configure_local_telemetry,
)
from equity_event import live_telemetry
from equity_event.live_trace import trace_episode

try:
    import httpx2 as httpx
except ImportError:
    import httpx


def read_snapshot(directory: Path) -> dict:
    return json.loads((directory / "telemetry.json").read_text(encoding="utf-8"))


def test_root_application_events_and_inflight_spans_share_real_ids(tmp_path):
    async def exercise():
        with trace_episode(tmp_path, synthetic_fixture=True) as trace:
            assert re.fullmatch(r"[0-9a-f]{32}", trace.trace_id)
            root_context = otel_trace.get_current_span().get_span_context()
            assert trace.trace_id == f"{root_context.trace_id:032x}"
            roots = [span for span in read_snapshot(tmp_path)["spans"] if span["parent_span_id"] is None]
            assert len(roots) == 1
            root = roots[0]
            assert root["parent_span_id"] is None
            assert root["origin"] == "application"
            assert root["end_time"] is None
            assert root["status"]["code"] == "UNSET"
            discovery = trace.record("skill.catalog_discovered", skills=["event-study"])
            await asyncio.sleep(0)

            async def inspect_fixture(value: int) -> str:
                trace.record("skill.used", skill_id="event-study", value=value)
                snapshot = trace.flush()
                running = next(span for span in snapshot["spans"] if span["origin"] == "maf")
                assert running["end_time"] is None
                assert running["parent_span_id"] == root["span_id"]
                assert json.loads(running["attributes"]["gen_ai.tool.call.arguments"]) == {"value": 7}
                assert "gen_ai.tool.call.result" not in running["attributes"]
                return json.dumps({"synthetic_value": value * 2})

            tool = FunctionTool(name="inspect_fixture", description="Synthetic fixture inspection.", func=inspect_fixture)
            await tool.invoke(arguments={"value": 7}, tool_call_id="fixture-call-1")
            acceptance = trace.record("acceptance.passed", checks=9)
            assert [event["sequence"] for event in trace.events] == [1, 2, 3]
            assert discovery["id"] < acceptance["id"]
            assert discovery["span_id"] == root["span_id"]
            assert discovery["timestamp_unix_nano"] < acceptance["timestamp_unix_nano"]
            assert trace.path == tmp_path / "telemetry.json"
            return trace

    trace = asyncio.run(exercise())
    snapshot = read_snapshot(tmp_path)
    assert snapshot["events"] == trace.events
    assert len(snapshot["spans"]) == 2
    root, tool = snapshot["spans"]
    assert tool["name"] == "execute_tool inspect_fixture"
    assert tool["origin"] == "maf"
    assert tool["instrumentation_scope"]["name"] == "agent_framework"
    assert tool["instrumentation_scope"]["version"] == "1.18.0"
    assert tool["attributes"]["gen_ai.tool.call.id"] == "fixture-call-1"
    assert json.loads(tool["attributes"]["gen_ai.tool.call.result"]) == {"synthetic_value": 14}
    use = next(event for event in snapshot["events"] if event["event"] == "skill.used")
    assert use["span_id"] == tool["span_id"]
    assert use["parent_span_id"] == root["span_id"]
    assert use["origin"] == "application"
    assert tool["events"][0]["origin"] == "application"
    for span in snapshot["spans"]:
        assert re.fullmatch(r"[0-9a-f]{16}", span["span_id"])
        assert span["trace_id"] == trace.trace_id
        assert span["start_time_unix_nano"] <= span["end_time_unix_nano"]
        assert span["duration_ms"] >= 0
    assert sorted(path.name for path in tmp_path.iterdir()) == ["telemetry.json"]
    with pytest.raises(RuntimeError, match="active trace_episode"):
        trace.record("too.late")


@pytest.mark.parametrize("turn_count", [1, 2])
@pytest.mark.parametrize("transient_reader_lock", [False, True])
def test_real_agent_chat_and_tool_spans_without_a_network_request(tmp_path, turn_count, transient_reader_lock, monkeypatch):
    requests = []
    in_flight = []
    request_span_ids = []
    injected_locks = []
    original_read = Path.read_text

    def read_with_one_windows_lock(file, *args, **kwargs):
        current = otel_trace.get_current_span()
        if (
            transient_reader_lock and not injected_locks and len(requests) == 2 * turn_count
            and file == tmp_path / "telemetry.json" and getattr(current, "name", "").startswith("chat ")
        ):
            injected_locks.append(file)
            raise PermissionError(errno.EACCES, "simulated snapshot reader lock")
        return original_read(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_with_one_windows_lock)

    async def exercise():
        with trace_episode(tmp_path, synthetic_fixture=True) as trace:
            async def respond(request: httpx.Request) -> httpx.Response:
                body = json.loads(request.content)
                requests.append(body)
                span_id = f"{otel_trace.get_current_span().get_span_context().span_id:016x}"
                request_span_ids.append(span_id)
                deadline = monotonic() + 3
                last_read_error = None
                while True:
                    try:
                        snapshot = read_snapshot(tmp_path)
                    except (PermissionError, FileNotFoundError) as error:
                        last_read_error = error
                    else:
                        if any(
                            span["span_id"] == span_id
                            and span["attributes"].get("gen_ai.operation.name") == "chat"
                            and span["attributes"].get("gen_ai.input.messages")
                            and span["end_time"] is None
                            for span in snapshot["spans"]
                        ):
                            in_flight.append(snapshot)
                            break
                    if monotonic() >= deadline:
                        raise AssertionError(
                            f"Native in-flight attributes were not automatically persisted for {span_id}; "
                            f"export_health={trace.export_health}"
                        ) from last_read_error
                    await asyncio.sleep(0.02)
                assert request.url.path == "/v1/responses"
                call_id = f"call_synthetic_fixture_{turn + 1}"
                delivered_result = any(
                    item.get("type") == "function_call_output" and item.get("call_id") == call_id
                    for item in body["input"]
                )
                if not delivered_result:
                    output = [{
                        "id": f"fc_synthetic_fixture_{turn + 1}",
                        "type": "function_call",
                        "call_id": call_id,
                        "name": "fixture_price",
                        "arguments": '{"symbol":"SYNTH"}',
                        "status": "completed",
                    }]
                else:
                    output = [{
                        "id": f"msg_synthetic_fixture_{turn + 1}",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{
                            "type": "output_text",
                            "text": "Synthetic fixture price is 110.",
                            "annotations": [],
                        }],
                    }]
                return httpx.Response(200, json={
                    "id": f"fixture-response-{turn + 1}-{'final' if delivered_result else 'tool'}",
                    "object": "response",
                    "created_at": 1_785_974_400,
                    "model": "synthetic-model",
                    "status": "completed",
                    "output": output,
                    "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
                })

            async def fixture_price(symbol: str) -> str:
                trace.record("memory.recalled", source="synthetic-fixture", symbol=symbol)
                return json.dumps({"symbol": symbol, "close": 110, "classification": "synthetic"})

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
                async with AsyncOpenAI(
                    api_key="fixture-only-auth-value-DO-NOT-EXPORT",
                    base_url="https://synthetic.invalid/v1",
                    http_client=http_client,
                    # SDK retries must not repeat this assertion-bearing mock.
                    max_retries=0,
                ) as api_client:
                    client = OpenAIChatClient(model="synthetic-model", async_client=api_client)
                    agent = Agent(
                        client=client,
                        name="SyntheticEquityAgent",
                        instructions="Use the fixture_price tool for the synthetic fixture.",
                        tools=[fixture_price],
                    )
                    session = agent.create_session()
                    for turn in range(turn_count):
                        result = await agent.run(
                            f"Inspect SYNTH in the synthetic fixture, turn {turn + 1}.",
                            session=session,
                        )
                        assert "110" in result.text

    asyncio.run(exercise())
    snapshot = read_snapshot(tmp_path)
    assert len(requests) == 2 * turn_count
    assert len(injected_locks) == int(transient_reader_lock)
    assert len(set(request_span_ids)) == len(requests)
    assert len(in_flight) == len(requests)
    for span_id, captured in zip(request_span_ids, in_flight, strict=True):
        assert next(span for span in captured["spans"] if span["span_id"] == span_id)["end_time"] is None
    root = next(span for span in snapshot["spans"] if span["origin"] == "application")
    native = [span for span in snapshot["spans"] if span["origin"] == "maf"]
    agents = [span for span in native if span["attributes"]["gen_ai.operation.name"] == "invoke_agent"]
    chats = [span for span in native if span["attributes"]["gen_ai.operation.name"] == "chat"]
    tools = [span for span in native if span["attributes"]["gen_ai.operation.name"] == "execute_tool"]
    assert len(agents) == turn_count
    assert len(chats) == 2 * turn_count
    assert len(tools) == turn_count
    assert {span["parent_span_id"] for span in agents} == {root["span_id"]}
    assert {span["parent_span_id"] for span in chats} == {agent["span_id"] for agent in agents}
    assert {span["parent_span_id"] for span in tools} == {agent["span_id"] for agent in agents}
    assert len(native) == 4 * turn_count
    for tool in tools:
        assert json.loads(tool["attributes"]["gen_ai.tool.call.arguments"]) == {"symbol": "SYNTH"}
        assert json.loads(tool["attributes"]["gen_ai.tool.call.result"])["close"] == 110
    assert {tool["attributes"]["gen_ai.tool.call.id"] for tool in tools} == {
        f"call_synthetic_fixture_{turn + 1}" for turn in range(turn_count)
    }
    assert all(span["instrumentation_scope"]["name"] == "agent_framework" for span in native)
    assert all(span["attributes"]["gen_ai.usage.input_tokens"] == 11 for span in chats)
    assert all(span["attributes"]["gen_ai.usage.output_tokens"] == 7 for span in chats)
    assert all(agent["attributes"]["gen_ai.usage.input_tokens"] == 22 for agent in agents)
    assert all(agent["attributes"]["gen_ai.usage.output_tokens"] == 14 for agent in agents)
    for span in chats:
        assert json.loads(span["attributes"]["gen_ai.input.messages"])
        assert json.loads(span["attributes"]["gen_ai.output.messages"])
    assert any(
        span["attributes"].get("gen_ai.input.messages") and span["end_time"] is None
        for snapshot in in_flight for span in snapshot["spans"]
        if span["attributes"].get("gen_ai.operation.name") == "chat"
    )
    encoded = json.dumps(snapshot)
    assert "fixture-only-auth-value-DO-NOT-EXPORT" not in encoded
    assert "Authorization" not in encoded
    assert not any(worker.name == "equity-event-telemetry" for worker in enumerate_threads())


def test_sequential_runs_filter_other_traces_and_reuse_provider(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    with trace_episode(one, synthetic_fixture=True) as first:
        provider = otel_trace.get_tracer_provider()
        first.record("first.only", marker="first-run")
        with otel_trace.get_tracer("unrelated.library").start_as_current_span("foreign-trace", context=Context()):
            pass
    original = (one / "telemetry.json").read_bytes()
    with trace_episode(two, synthetic_fixture=True) as second:
        assert otel_trace.get_tracer_provider() is provider
        assert configure_local_telemetry() is configure_local_telemetry()
        second.record("second.only", marker="second-run")
        with otel_trace.get_tracer("unrelated.library").start_as_current_span("third-party-child"):
            pass
    assert first.trace_id != second.trace_id
    assert {span["trace_id"] for span in read_snapshot(two)["spans"]} == {second.trace_id}
    assert "first-run" not in json.dumps(read_snapshot(two))
    assert "foreign-trace" not in json.dumps(read_snapshot(one))
    assert [event["sequence"] for event in read_snapshot(two)["events"]] == [1]
    foreign = [span for span in read_snapshot(two)["spans"] if span["name"] == "third-party-child"]
    assert len(foreign) == 1
    assert foreign[0]["origin"] == "other"
    assert (one / "telemetry.json").read_bytes() == original
    assert not otel_trace.get_current_span().get_span_context().is_valid
    with pytest.raises(FileExistsError):
        with trace_episode(one):
            pass


def test_native_error_status_and_exception_are_preserved_safely(tmp_path):
    async def fail():
        raise ValueError("Synthetic failure; api_key=should-not-persist Bearer private-token")

    async def exercise():
        with trace_episode(tmp_path, synthetic_fixture=True):
            await FunctionTool(name="fixture_failure", func=fail).invoke(arguments={})

    with pytest.raises(ValueError, match="Synthetic failure"):
        asyncio.run(exercise())
    snapshot = read_snapshot(tmp_path)
    assert len(snapshot["spans"]) == 2
    for span in snapshot["spans"]:
        assert span["end_time"] is not None
        assert span["status"]["code"] == "ERROR"
        exception = next(event for event in span["events"] if event["name"] == "exception")
        assert exception["attributes"]["exception.type"].endswith("ValueError")
        assert "Synthetic failure" in exception["attributes"]["exception.message"]
    encoded = json.dumps(snapshot)
    assert "should-not-persist" not in encoded
    assert "private-token" not in encoded


def test_content_is_opt_in_and_framework_settings_are_restored(tmp_path):
    previous = (
        OBSERVABILITY_SETTINGS.enable_sensitive_data,
        OBSERVABILITY_SETTINGS.otel_semconv_stability_opt_in,
        OBSERVABILITY_SETTINGS.enable_message_events,
    )

    async def run():
        async def private_tool(prompt: str) -> str:
            return "private-tool-result"

        with trace_episode(tmp_path) as trace:
            assert not OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED
            trace.record("selection", prompt="private-prompt", arguments={"value": "private-value"})
            await FunctionTool(name="metadata_only", func=private_tool).invoke(arguments={"prompt": "private-tool-input"})

    asyncio.run(run())
    encoded = json.dumps(read_snapshot(tmp_path))
    for value in ("private-prompt", "private-value", "private-tool-input", "private-tool-result"):
        assert value not in encoded
    native_spans = [
        span for span in read_snapshot(tmp_path)["spans"]
        if span["origin"] == "maf" and span["attributes"].get("gen_ai.tool.name") == "metadata_only"
    ]
    assert len(native_spans) == 1
    native = native_spans[0]
    assert "gen_ai.tool.call.arguments" not in native["attributes"]
    assert "gen_ai.tool.call.result" not in native["attributes"]
    assert previous == (
        OBSERVABILITY_SETTINGS.enable_sensitive_data,
        OBSERVABILITY_SETTINGS.otel_semconv_stability_opt_in,
        OBSERVABILITY_SETTINGS.enable_message_events,
    )


def test_credentials_are_redacted_inside_native_json_and_application_events(tmp_path):
    async def exercise():
        with trace_episode(tmp_path, synthetic_fixture=True) as trace:
            async def fixture_result(api_key: str) -> str:
                return json.dumps({
                    "price": 110,
                    "nested": {
                        "apiKey": "native-api-value",
                        "access_token": "native-access-value",
                        "headers": {"Authorization": "native-header-value", "x-extra": "native-extra-value"},
                    },
                    "note": "password=inline-private-value Bearer inline-bearer-value",
                })

            await FunctionTool(name="fixture_secrets", func=fixture_result).invoke(
                arguments={"api_key": "native-argument-api-value"}
            )
            trace.record(
                "skill.loaded",
                source={"client_secret": "application-client-value", "safe": ["fixture"]},
                payload=json.dumps({"auth": "application-auth-value"}),
                response_headers={"x-extra": "application-header-value"},
                credential=object(),
                endpoint="https://user:private-url-password@fixture.invalid/data?api_key=private-url-key",
                input_tokens=123,
                output_tokens=45,
                unknown=object(),
                result={"value": float("nan"), "tuple": (1, 2)},
            )
            # The source labels still derive from actual instrumentation scope.
            assert otel_trace.get_current_span().instrumentation_scope.name == APPLICATION_SCOPE

    asyncio.run(exercise())
    snapshot = read_snapshot(tmp_path)
    encoded = json.dumps(snapshot)
    for value in (
        "native-api-value", "native-argument-api-value", "native-access-value", "native-header-value", "native-extra-value",
        "inline-private-value", "inline-bearer-value", "application-client-value",
        "application-auth-value", "application-header-value", "private-url-password", "private-url-key",
    ):
        assert value not in encoded
    event = snapshot["events"][0]
    assert event["input_tokens"] == 123
    assert event["output_tokens"] == 45
    assert event["unknown"] == "[object]"
    assert event["result"] == {"value": None, "tuple": [1, 2]}
    tool_spans = [
        span for span in snapshot["spans"]
        if span["origin"] == "maf" and span["attributes"].get("gen_ai.tool.name") == "fixture_secrets"
    ]
    assert len(tool_spans) == 1
    native_result = json.loads(tool_spans[0]["attributes"]["gen_ai.tool.call.result"])
    native_arguments = json.loads(tool_spans[0]["attributes"]["gen_ai.tool.call.arguments"])
    assert native_arguments == {"api_key": "[REDACTED]"}
    assert native_result["price"] == 110
    assert native_result["nested"]["headers"] == "[REDACTED]"


def test_large_fixture_content_remains_inspectable_and_json_valid(tmp_path):
    with trace_episode(tmp_path, synthetic_fixture=True) as trace:
        event = trace.record("fixture.large_result", result={"body": "x" * (MAX_STRING_LENGTH + 20)})
        assert event["result"]["body"].startswith("x" * 10_000)
        assert "TRUNCATED" in event["result"]["body"]
    assert json.loads((tmp_path / "telemetry.json").read_text())["events"][0]["id"] == event["id"]


def test_nested_episodes_fail_without_corrupting_active_run(tmp_path):
    with trace_episode(tmp_path / "first", synthetic_fixture=True) as trace:
        with pytest.raises(RuntimeError, match="already active"):
            with trace_episode(tmp_path / "nested", synthetic_fixture=True):
                pass
        trace.record("approval.required", approved=False)
    assert read_snapshot(tmp_path / "first")["events"][0]["event"] == "approval.required"
    assert not (tmp_path / "nested").exists()


def test_telemetry_module_exposes_the_same_episode_context(tmp_path):
    from equity_event.live_telemetry import trace_episode as telemetry_episode

    with telemetry_episode(tmp_path, synthetic_fixture=True) as trace:
        trace.record("episode_started")
    assert read_snapshot(tmp_path)["trace_id"] == trace.trace_id


def test_transient_windows_reader_lock_retries_with_bounded_backoff(tmp_path, monkeypatch):
    monkeypatch.setattr(live_telemetry, "SNAPSHOT_INTERVAL_SECONDS", 60)
    original = Path.replace
    calls = []
    delays = []
    with trace_episode(tmp_path, synthetic_fixture=True) as trace:
        def locked_twice(source, target):
            if source.name == "telemetry.json.partial":
                calls.append(target)
                if len(calls) <= 2:
                    raise PermissionError(errno.EACCES, "simulated Windows reader lock")
            return original(source, target)

        with monkeypatch.context() as fault:
            fault.setattr(Path, "replace", locked_twice)
            fault.setattr(live_telemetry, "sleep", delays.append)
            row = trace.record("completion_admitted")
        assert len(calls) == 3
        assert delays == list(live_telemetry.PERSISTENCE_RETRY_DELAYS[:2])
        assert trace.export_health["status"] == "healthy"
        assert read_snapshot(tmp_path)["events"][-1]["id"] == row["id"]
    assert not (tmp_path / "telemetry.json.partial").exists()


def test_exhausted_lock_is_visible_nonfatal_and_recovers_on_later_flush(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(live_telemetry, "SNAPSHOT_INTERVAL_SECONDS", 60)
    original = Path.replace
    attempts = []
    with trace_episode(tmp_path, synthetic_fixture=True) as trace:
        def always_locked(source, target):
            if source.name == "telemetry.json.partial":
                attempts.append(target)
                raise PermissionError(errno.EACCES, "simulated Windows reader lock")
            return original(source, target)

        with monkeypatch.context() as fault:
            fault.setattr(Path, "replace", always_locked)
            fault.setattr(live_telemetry, "sleep", lambda _delay: None)
            row = trace.record("memory_written", source="synthetic")
            assert len(attempts) == len(live_telemetry.PERSISTENCE_RETRY_DELAYS) + 1
            assert trace.events[-1]["id"] == row["id"]
            assert trace.export_health["status"] == "degraded"
            assert trace.export_health["write_failures"] == 1
            assert configure_local_telemetry().force_flush() is False
            health = json.loads((tmp_path / "telemetry-health.json").read_text())
            assert health["trace_id"] == trace.trace_id
            assert health["export_health"]["status"] == "degraded"
            assert health["export_health"]["last_error"]["type"] == "PermissionError"
        snapshot = trace.flush()
        assert snapshot["export_health"]["status"] == "healthy"
        assert snapshot["export_health"]["write_failures"] >= 1
        assert snapshot["events"][-1]["id"] == row["id"]
        assert json.loads((tmp_path / "telemetry-health.json").read_text())["export_health"]["status"] == "healthy"
    assert "Telemetry persistence degraded" in caplog.text
    assert "application outcome unchanged" in caplog.text
    assert "Telemetry persistence recovered" in caplog.text


def test_admitted_result_survives_final_export_failure_and_pending_trace_recovers(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(live_telemetry, "SNAPSHOT_INTERVAL_SECONDS", 60)
    monkeypatch.setattr(live_telemetry, "sleep", lambda _delay: None)
    original = Path.replace
    blocked = False
    state = {"status": "running", "certified": False}
    traces = []

    def failing_after_admission(source, target):
        if blocked and source.name == "telemetry.json.partial" and source.parent == tmp_path / "first":
            raise PermissionError(errno.EACCES, "simulated Windows reader lock after side effects")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", failing_after_admission)

    async def run():
        nonlocal blocked
        with trace_episode(tmp_path / "first", synthetic_fixture=True) as trace:
            traces.append(trace)

            async def complete_episode() -> str:
                nonlocal blocked
                state.update(status="completed", certified=True)
                trace.record("memory_written", source="synthetic")
                blocked = True
                trace.record("completion_admitted", certificate="synthetic-certificate.json")
                return json.dumps(state)

            await FunctionTool(name="complete_episode", func=complete_episode).invoke(arguments={})
            return state.copy()

    try:
        result = asyncio.run(run())
        assert result == {"status": "completed", "certified": True}
        trace = traces[0]
        assert trace.export_health["status"] == "degraded"
        assert trace.events[-1]["event"] == "completion_admitted"
    finally:
        blocked = False
        # Pending closed episodes remain reachable by the application processor,
        # even after trace_episode has returned to its caller.
        assert configure_local_telemetry().force_flush()
    first = read_snapshot(tmp_path / "first")
    assert first["export_health"]["status"] == "healthy"
    assert first["export_health"]["write_failures"] > 0
    assert len(first["spans"]) == 2
    assert all(span["end_time"] is not None and span["status"]["code"] != "ERROR" for span in first["spans"])
    assert {span["name"] for span in first["spans"]} == {"equity_event.episode", "execute_tool complete_episode"}
    assert "Telemetry persistence degraded" in caplog.text
    with trace_episode(tmp_path / "second", synthetic_fixture=True) as second:
        second.record("episode_started")
    assert read_snapshot(tmp_path / "first")["trace_id"] != read_snapshot(tmp_path / "second")["trace_id"]
    assert len(read_snapshot(tmp_path / "second")["spans"]) == 1
    assert not any(worker.name == "equity-event-telemetry" for worker in enumerate_threads())


def test_unwritable_health_sidecar_is_logged_without_losing_in_memory_health(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(live_telemetry, "SNAPSHOT_INTERVAL_SECONDS", 60)
    with trace_episode(tmp_path, synthetic_fixture=True) as trace:
        with monkeypatch.context() as fault:
            def unavailable(_source, _target):
                raise PermissionError(errno.EACCES, "simulated locked output directory")

            fault.setattr(Path, "replace", unavailable)
            fault.setattr(live_telemetry, "sleep", lambda _delay: None)
            snapshot = trace.flush()
            assert snapshot["export_health"]["status"] == "degraded"
            assert trace.export_health["last_error"]["errno"] == errno.EACCES
        assert trace.flush()["export_health"]["status"] == "healthy"
    assert "export-health sidecar could not be persisted" in caplog.text


def test_completed_successful_episodes_are_not_reflushed_or_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(live_telemetry, "SNAPSHOT_INTERVAL_SECONDS", 0.01)
    original_write = live_telemetry._atomic_json
    completed_paths = set()
    writes = []

    def record_write(destination, snapshot):
        assert destination not in completed_paths, "A successful closed episode was exported again."
        writes.append(destination)
        return original_write(destination, snapshot)

    monkeypatch.setattr(live_telemetry, "_atomic_json", record_write)
    processor = configure_local_telemetry()
    provider = otel_trace.get_tracer_provider()

    async def run():
        async def fixture_tool(value: int) -> str:
            await asyncio.sleep(0.02)
            return json.dumps({"synthetic_value": value})

        native_tool = FunctionTool(name="fixture_tool", func=fixture_tool)
        for index in range(5):
            with trace_episode(tmp_path / f"run-{index}", synthetic_fixture=True) as trace:
                assert otel_trace.get_tracer_provider() is provider
                await native_tool.invoke(arguments={"value": index})
                await native_tool.invoke(arguments={"value": index + 1})
                trace.record("completion_admitted")
            completed_paths.add(trace.path)
            assert trace.export_health["status"] == "healthy"
            assert processor._episode is None
            assert processor._pending == {}
            assert processor._refresh_thread is None
            assert not any(worker.name == "equity-event-telemetry" for worker in enumerate_threads())

    asyncio.run(run())
    exported = len(writes)
    assert processor.force_flush()
    assert len(writes) == exported
    assert len(completed_paths) == 5

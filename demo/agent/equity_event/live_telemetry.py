"""Local-only OpenTelemetry processing of MAF's own agent/chat/tool spans.

There are no model or tool instrumentation wrappers here. Instrumentation scope,
parentage, IDs, timings, usage, arguments and results come from the SDK spans.
Application events are projections of those same spans, not another event log.
"""

from __future__ import annotations

import errno
import json
import logging
import math
import re
from collections.abc import Mapping
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock, Thread, current_thread
from time import sleep, time_ns
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent_framework.observability import enable_instrumentation
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanLimits, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

if TYPE_CHECKING:
    from .live_trace import LiveTrace

APPLICATION_SCOPE = "equity_event.live_harness"
MAX_STRING_LENGTH = 131_072
SNAPSHOT_INTERVAL_SECONDS = 0.25
PERSISTENCE_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.25, 0.25)
_logger = logging.getLogger(__name__)
_REDACTED = "[REDACTED]"
_CONTENT_KEYS = {
    "arguments", "result", "results", "prompt", "prompts", "messages", "message",
    "content", "text", "input", "output", "instructions", "systeminstructions",
    "tooldefinitions", "stacktrace",
}
_TOKEN_COUNTS = {
    "inputtokens", "outputtokens", "totaltokens", "maxtokens", "maxoutputtokens",
    "maxcompletiontokens", "inputtokencount", "outputtokencount", "totaltokencount",
    "cachedtokens", "cachecreationinputtokens", "cachereadinputtokens", "reasoningtokens",
}
_SECRET_KEY = re.compile(
    r"authorization|authentication|credential|password|passwd|secret|cookie|"
    r"apikey|accesskey|accountkey|privatekey|connectionstring|headers?"
)
_BEARER = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(
    r"""(?ix)(\b(?:api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|id[-_ ]?token|
    authorization|password|passwd|client[-_ ]?secret|account[-_ ]?key|credential|
    token|secret)\b["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&}\]]+)"""
)
_JWT_OR_KEY = re.compile(r"\b(?:eyJ[\w-]+\.[\w-]+\.[\w-]+|sk-[\w-]{12,})\b")
_URL = re.compile(r"https?://[^\s<>\"']+")
_setup_lock = RLock()
_processor: LocalSpanProcessor | None = None


def _secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    leaf = re.sub(r"[^a-z0-9]", "", key.rsplit(".", 1)[-1].lower())
    if leaf in _TOKEN_COUNTS:
        return False
    return bool(
        _SECRET_KEY.search(normalized)
        or "token" in normalized
        or normalized in {"auth", "bearer", "key"}
    )


def _content_key(key: str) -> bool:
    leaf = re.sub(r"[^a-z0-9]", "", key.rsplit(".", 1)[-1].lower())
    return leaf in _CONTENT_KEYS or key in {
        "gen_ai.tool.definitions", "gen_ai.system_instructions",
    }


def _safe_url(match: re.Match[str]) -> str:
    try:
        parts = urlsplit(match.group())
        host = parts.netloc.rsplit("@", 1)[-1]
        query = urlencode([
            (key, _REDACTED if _secret_key(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ])
        return urlunsplit((parts.scheme, host, parts.path, query, ""))
    except ValueError:
        return "[REDACTED URL]"


def safe_value(value: Any, *, capture_content: bool, _depth: int = 0) -> Any:
    """Return bounded JSON primitives without credentials or arbitrary object reprs.

    MAF's structured message/tool attributes are JSON *strings*: decode, sanitize
    recursively and re-encode them while preserving their native attribute type.
    Token usage counts are retained; authentication tokens and all headers are not.
    """
    if _depth > 30:
        return "[MAX DEPTH]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED if _secret_key(str(key)) else
                "[CONTENT DISABLED]" if not capture_content and _content_key(str(key)) else
                safe_value(item, capture_content=capture_content, _depth=_depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [safe_value(item, capture_content=capture_content, _depth=_depth + 1) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                decoded = json.loads(value)
            except (ValueError, RecursionError):
                pass
            else:
                encoded = json.dumps(
                    safe_value(decoded, capture_content=capture_content, _depth=_depth + 1),
                    ensure_ascii=True,
                    allow_nan=False,
                )
                return encoded
        value = _URL.sub(_safe_url, value)
        value = _BEARER.sub(lambda match: f"{match.group(1)} {_REDACTED}", value)
        value = _SECRET_ASSIGNMENT.sub(lambda match: match.group(1) + _REDACTED, value)
        return _bounded(_JWT_OR_KEY.sub(_REDACTED, value))
    return f"[{type(value).__name__}]"


def _bounded(value: str) -> str:
    if len(value) <= MAX_STRING_LENGTH:
        return value
    return value[:MAX_STRING_LENGTH] + f" [TRUNCATED: {len(value)} characters]"


def _timestamp(value: int | None) -> str | None:
    if value is None:
        return None
    seconds, nanoseconds = divmod(value, 1_000_000_000)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{nanoseconds:09d}Z"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    replacement = path.with_suffix(path.suffix + ".partial")
    encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    try:
        for attempt in range(len(PERSISTENCE_RETRY_DELAYS) + 1):
            try:
                replacement.write_text(encoded, encoding="utf-8")
                replacement.replace(path)
                return
            except OSError as error:
                locked = (
                    isinstance(error, PermissionError)
                    or error.errno in {errno.EACCES, errno.EPERM, errno.EBUSY}
                    or getattr(error, "winerror", None) in {5, 32, 33}
                )
                if not locked or attempt == len(PERSISTENCE_RETRY_DELAYS):
                    raise
                sleep(PERSISTENCE_RETRY_DELAYS[attempt])
    finally:
        try:
            replacement.unlink(missing_ok=True)
        except OSError as error:
            _logger.warning("Telemetry temporary-file cleanup deferred (%s).", type(error).__name__)


def _origin(span: ReadableSpan) -> str:
    scope = span.instrumentation_scope
    name = scope.name if scope else ""
    if name == "agent_framework" or name.startswith(("agent_framework.", "agent_framework_")):
        return "maf"
    if name == APPLICATION_SCOPE:
        return "application"
    return "other"


class EpisodeSpans:
    """Thread-safe, trace-filtered snapshot of actual active/completed SDK spans."""

    def __init__(self, root: Span, path: Path, *, capture_content: bool) -> None:
        self.trace_id = f"{root.get_span_context().trace_id:032x}"
        self.path = path
        self.capture_content = capture_content
        self.lock = RLock()
        self._spans: dict[int, ReadableSpan] = {root.get_span_context().span_id: root}
        self._sequence = 0
        self._last_event_time = 0
        self.health_path = path.with_name("telemetry-health.json")
        self._export_health: dict[str, Any] = {
            "status": "healthy",
            "write_failures": 0,
            "consecutive_failures": 0,
            "last_error": None,
            "last_failure_at": None,
            "last_success_at": None,
        }

    @property
    def export_health(self) -> dict[str, Any]:
        with self.lock:
            return {**self._export_health}

    def next_event(self) -> tuple[int, int]:
        with self.lock:
            self._sequence += 1
            self._last_event_time = max(time_ns(), self._last_event_time + 1)
            return self._sequence, self._last_event_time

    def capture(self, span: ReadableSpan) -> None:
        context = span.context
        if context is not None and f"{context.trace_id:032x}" == self.trace_id:
            with self.lock:
                self._spans[context.span_id] = span
                self.flush()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            now = time_ns()
            spans = []
            application_events = []
            for span in self._spans.values():
                context = span.context
                if context is None:
                    continue
                span_id = f"{context.span_id:016x}"
                parent_id = f"{span.parent.span_id:016x}" if span.parent else None
                origin = _origin(span)
                scope = span.instrumentation_scope
                events = []
                for event in span.events:
                    attributes = safe_value(dict(event.attributes or {}), capture_content=self.capture_content)
                    is_application = attributes.get("harness.origin") == "application"
                    events.append({
                        "name": safe_value(event.name, capture_content=True),
                        "timestamp": _timestamp(event.timestamp),
                        "timestamp_unix_nano": event.timestamp,
                        "attributes": attributes,
                        "origin": "application" if is_application else origin,
                    })
                    if is_application and "harness.event.id" in attributes:
                        details = json.loads(attributes.get("harness.event.details", "{}"))
                        application_events.append({
                            **details,
                            "id": attributes["harness.event.id"],
                            "sequence": attributes["harness.event.sequence"],
                            "event": event.name,
                            "at": _timestamp(event.timestamp),
                            "timestamp": _timestamp(event.timestamp),
                            "timestamp_unix_nano": event.timestamp,
                            "trace_id": self.trace_id,
                            "span_id": span_id,
                            "parent_span_id": parent_id,
                            "origin": "application",
                        })
                spans.append({
                    "trace_id": self.trace_id,
                    "span_id": span_id,
                    "parent_span_id": parent_id,
                    "name": safe_value(span.name, capture_content=True),
                    "kind": span.kind.name,
                    "start_time": _timestamp(span.start_time),
                    "end_time": _timestamp(span.end_time),
                    "start_time_unix_nano": span.start_time,
                    "end_time_unix_nano": span.end_time,
                    "duration_ms": (
                        ((span.end_time or now) - span.start_time) / 1_000_000 if span.start_time is not None else None
                    ),
                    "status": {
                        "code": span.status.status_code.name,
                        "description": (
                            safe_value(span.status.description, capture_content=True) if self.capture_content else None
                        ),
                    },
                    "attributes": safe_value(dict(span.attributes or {}), capture_content=self.capture_content),
                    "events": events,
                    "origin": origin,
                    "instrumentation_scope": {
                        "name": scope.name if scope else None,
                        "version": scope.version if scope else None,
                        "schema_url": scope.schema_url if scope else None,
                    },
                    "dropped_attributes": span.dropped_attributes,
                    "dropped_events": span.dropped_events,
                })
            spans.sort(key=lambda row: (row["start_time_unix_nano"] or 0, row["span_id"]))
            application_events.sort(key=lambda row: row["sequence"])
            return {
                "schema_version": 1,
                "trace_id": self.trace_id,
                "capture_content": self.capture_content,
                "export_health": self.export_health,
                "spans": spans,
                "events": application_events,
            }

    def flush(self) -> dict[str, Any]:
        with self.lock:
            snapshot = self.snapshot()
            recovered = self._export_health["status"] == "degraded"
            healthy = {
                **self._export_health,
                "status": "healthy",
                "consecutive_failures": 0,
                "last_success_at": _timestamp(time_ns()),
            }
            snapshot["export_health"] = healthy
            try:
                _atomic_json(self.path, snapshot)
            except OSError as error:
                detail = {
                    "type": type(error).__name__,
                    "errno": error.errno,
                    "winerror": getattr(error, "winerror", None),
                }
                if not recovered or detail != self._export_health["last_error"]:
                    _logger.warning(
                        "Telemetry persistence degraded for trace %s after bounded retries; "
                        "native spans retained in memory for recovery; application outcome unchanged (%s).",
                        self.trace_id, type(error).__name__,
                    )
                self._export_health = {
                    **self._export_health,
                    "status": "degraded",
                    "write_failures": self._export_health["write_failures"] + 1,
                    "consecutive_failures": self._export_health["consecutive_failures"] + 1,
                    "last_error": detail,
                    "last_failure_at": _timestamp(time_ns()),
                }
                self._write_health()
                return self.snapshot()
            self._export_health = healthy
            if recovered:
                _logger.warning("Telemetry persistence recovered for trace %s; retained native spans exported.", self.trace_id)
                self._write_health()
            return snapshot

    def _write_health(self) -> None:
        try:
            _atomic_json(self.health_path, {"trace_id": self.trace_id, "export_health": self.export_health})
        except OSError as error:
            _logger.warning(
                "Telemetry export-health sidecar could not be persisted for trace %s (%s); "
                "health remains available in memory.", self.trace_id, type(error).__name__,
            )


class LocalSpanProcessor(SpanProcessor):
    """Route only the current episode's real trace to the local JSON snapshot."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._episode: EpisodeSpans | None = None
        self._pending: dict[str, EpisodeSpans] = {}
        self._stop_refresh: Event | None = None
        self._refresh_thread: Thread | None = None

    def begin(self, root: Span, path: Path, *, capture_content: bool) -> EpisodeSpans:
        with self._lock:
            if self._episode is not None:
                raise RuntimeError("A telemetry episode is already registered.")
            episode = EpisodeSpans(root, path, capture_content=capture_content)
            episode.flush()
            self._episode = episode
            if self._refresh_thread is None:
                stopped = Event()
                worker = Thread(
                    target=self._refresh,
                    args=(stopped,),
                    name="equity-event-telemetry",
                    daemon=True,
                )
                self._stop_refresh = stopped
                self._refresh_thread = worker
                try:
                    worker.start()
                except RuntimeError:
                    self._episode = None
                    self._stop_refresh = None
                    self._refresh_thread = None
                    raise
            return episode

    def finish(self, trace_id: str) -> None:
        worker = None
        with self._lock:
            if self._episode is not None and self._episode.trace_id == trace_id:
                if self._episode.export_health["status"] == "degraded":
                    self._pending[trace_id] = self._episode
                self._episode = None
                if not self._pending:
                    if self._stop_refresh is not None:
                        self._stop_refresh.set()
                    worker = self._refresh_thread
                    self._stop_refresh = None
                    self._refresh_thread = None
        if worker is not None and worker is not current_thread():
            worker.join()

    def _refresh(self, stopped: Event) -> None:
        # MAF sets message attributes after on_start; refresh without requiring
        # any UI or model wrapper to flush while the native request is awaiting.
        while not stopped.wait(SNAPSHOT_INTERVAL_SECONDS):
            self.force_flush()
            with self._lock:
                if self._episode is None and not self._pending:
                    if self._stop_refresh is stopped:
                        self._stop_refresh = None
                        self._refresh_thread = None
                    return

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        self._capture(span)

    def on_end(self, span: ReadableSpan) -> None:
        self._capture(span)

    def _capture(self, span: ReadableSpan) -> None:
        with self._lock:
            if self._episode is not None:
                self._episode.capture(span)

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        with self._lock:
            healthy = True
            if self._episode is not None:
                healthy = self._episode.flush()["export_health"]["status"] == "healthy"
            for trace_id, episode in list(self._pending.items()):
                if episode.flush()["export_health"]["status"] == "healthy":
                    del self._pending[trace_id]
                else:
                    healthy = False
        return healthy

    def shutdown(self) -> None:
        self.force_flush()
        with self._lock:
            if self._stop_refresh is not None:
                self._stop_refresh.set()
            worker = self._refresh_thread
            self._stop_refresh = None
            self._refresh_thread = None
        if worker is not None and worker is not current_thread():
            worker.join()


def configure_local_telemetry() -> LocalSpanProcessor:
    """Configure one application-wide SDK provider with no network/log exporters.

    MAF's ``configure_otel_providers`` also auto-discovers exporters from ambient
    OTEL environment variables, so use its instrumentation-only helper and an
    explicitly local SDK provider instead. Refuse an existing foreign provider:
    attaching here could also send fixture content to its remote processors.
    """
    global _processor
    with _setup_lock:
        if _processor is None:
            if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
                raise RuntimeError("Live demo telemetry requires its own local-only OpenTelemetry provider.")
            processor = LocalSpanProcessor()
            provider = TracerProvider(
                resource=Resource({"service.name": "equity-event-live-demo"}),
                sampler=ALWAYS_ON,
                span_limits=SpanLimits(max_attributes=512, max_events=100_000, max_event_attributes=64),
            )
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            enable_instrumentation(enable_sensitive_data=False, force=True)
            _processor = processor
        return _processor


def trace_episode(out_dir: Path, *, synthetic_fixture: bool = False) -> AbstractContextManager[LiveTrace]:
    """Expose the episode entrypoint alongside telemetry configuration."""
    from .live_trace import trace_episode as episode_context

    return episode_context(out_dir, synthetic_fixture=synthetic_fixture)

"""Episode context and application events on the native Agent Framework trace."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from agent_framework.observability import OBSERVABILITY_SETTINGS, enable_instrumentation
from opentelemetry import trace as otel_trace
from opentelemetry.context import Context

from .live_telemetry import APPLICATION_SCOPE, EpisodeSpans, configure_local_telemetry, safe_value

_episode_lock = Lock()


class LiveTrace:
    """A view of recorded OTel spans, not a parallel model/tool event recorder.

    Instances are created by :func:`trace_episode`; ``path`` is the single
    ``telemetry.json`` snapshot consumed by the local harness console.
    """

    def __init__(self, spans: EpisodeSpans) -> None:
        self._spans = spans
        self.trace_id = spans.trace_id
        self.path = spans.path

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._spans.snapshot()["events"]

    @property
    def export_health(self) -> dict[str, Any]:
        """Visible persistence health; a degraded export never changes run admission."""
        return self._spans.export_health

    def record(self, event: str, **details: Any) -> dict[str, Any]:
        """Attach an explicitly application-origin event to the active real span."""
        span = otel_trace.get_current_span()
        context = span.get_span_context()
        if f"{context.trace_id:032x}" != self.trace_id or not span.is_recording():
            raise RuntimeError("Application events must be recorded inside their active trace_episode.")
        if not isinstance(event, str) or not event.strip():
            raise ValueError("An application event needs a nonempty name.")
        with self._spans.lock:
            sequence, timestamp = self._spans.next_event()
            event_id = f"{self.trace_id}:{sequence:06d}"
            span.add_event(
                safe_value(event, capture_content=True),
                attributes={
                    "harness.origin": "application",
                    "harness.event.id": event_id,
                    "harness.event.sequence": sequence,
                    "harness.event.details": json.dumps(
                        safe_value(details, capture_content=self._spans.capture_content),
                        ensure_ascii=True,
                        allow_nan=False,
                    ),
                },
                timestamp=timestamp,
            )
            snapshot = self._spans.flush()
            return next(row for row in snapshot["events"] if row["id"] == event_id)

    def flush(self) -> dict[str, Any]:
        """Refresh spans, reporting nonfatal file failures in ``export_health``."""
        return self._spans.flush()


@contextmanager
def trace_episode(out_dir: Path, *, synthetic_fixture: bool = False) -> Iterator[LiveTrace]:
    """Start one isolated, locally exported OTel trace around sync or awaited work.

    Raw MAF message/tool attributes require explicit ``synthetic_fixture=True``.
    The caller must validate that its input is the demo's synthetic fixture first.
    Credential redaction is applied even in fixture mode. Concurrent/nested episodes
    are rejected because MAF's sensitive-data setting is application-wide.
    """
    if not _episode_lock.acquire(blocking=False):
        raise RuntimeError("A live trace episode is already active; serialize demo runs.")
    processor = None
    live_trace = None
    previous_sensitive = OBSERVABILITY_SETTINGS.enable_sensitive_data
    previous_semconv = OBSERVABILITY_SETTINGS.otel_semconv_stability_opt_in
    previous_message_events = OBSERVABILITY_SETTINGS.enable_message_events
    try:
        output = Path(out_dir)
        if (output / "telemetry.json").exists():
            raise FileExistsError(f"Trace already exists; choose a new output directory: {output}")
        output.mkdir(parents=True, exist_ok=True)
        processor = configure_local_telemetry()
        enable_instrumentation(enable_sensitive_data=synthetic_fixture, force=True)
        # MAF 1.18 emits tool arguments/results and messages as span attributes only
        # under this opt-in. Baseline message log events need no separate pipeline.
        OBSERVABILITY_SETTINGS.otel_semconv_stability_opt_in = "gen_ai_latest_experimental"
        OBSERVABILITY_SETTINGS.enable_message_events = False
        tracer = otel_trace.get_tracer(APPLICATION_SCOPE)
        with tracer.start_as_current_span(
            "equity_event.episode",
            context=Context(),
            attributes={
                "harness.origin": "application",
                "harness.synthetic_fixture": synthetic_fixture,
                "harness.telemetry": "native-agent-framework",
            },
        ) as root:
            if not root.is_recording():
                raise RuntimeError("Local OpenTelemetry recording is disabled.")
            spans = processor.begin(root, output / "telemetry.json", capture_content=synthetic_fixture)
            live_trace = LiveTrace(spans)
            yield live_trace
    finally:
        try:
            if live_trace is not None:
                live_trace.flush()
        finally:
            if processor is not None and live_trace is not None:
                processor.finish(live_trace.trace_id)
            OBSERVABILITY_SETTINGS.enable_sensitive_data = previous_sensitive
            OBSERVABILITY_SETTINGS.otel_semconv_stability_opt_in = previous_semconv
            OBSERVABILITY_SETTINGS.enable_message_events = previous_message_events
            _episode_lock.release()

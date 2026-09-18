"""Loopback-only harness console; no frontend build or additional server dependency.

``create_ui_server(..., port=0)`` supports embedded callers and tests.
``serve(...)`` and ``serve_ui(...)`` run the same server in the foreground. The runtime executes in
one background thread, with a fresh asyncio loop and an actual human approval wait.
Startup restores capped, validated saved history without resuming work or approval.
"""

from __future__ import annotations

import asyncio
import dataclasses
import html
import json
import logging
import re
import secrets
import threading
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from .harness.capabilities import ALWAYS_ON, discover_skills

MAX_BODY_BYTES = 64 * 1024
MAX_DISCARD_BYTES = 2 * MAX_BODY_BYTES
MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
MAX_HISTORY_RUNS = 100
MAX_HISTORY_SCAN = 1000
MAX_HISTORY_METADATA_BYTES = 64 * 1024
FINISHED_STATUSES = {"completed", "failed", "rejected", "interrupted"}
LOGGER = logging.getLogger(__name__)
RUN_ID = re.compile(r"r-[0-9a-f]{16}\Z")
SECRET_KEY = re.compile(
    r"^(?:authorization|proxy.authorization|api.?key|.*password|.*secret|"
    r"credential|credentials|access.token|refresh.token|token|connection.string)$",
    re.IGNORECASE,
)
SENSITIVE_TEXT = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|"
    r"((?:api[-_ ]?key|access[-_ ]?token|password|secret)\s*[:=]\s*)[^\s,;\"']+|"
    r"\bsk-[A-Za-z0-9_-]{12,}"
)
ASSET = Path(__file__).with_name("ui_assets") / "index.html"


class _StyleNonceParser(HTMLParser):
    def __init__(self, source: str, nonce: str) -> None:
        super().__init__(convert_charrefs=False)
        self.nonce = nonce
        self.line_offsets = [0, *(match.end() for match in re.finditer("\n", source))]
        self.edits: list[tuple[int, int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "style":
            return
        line, column = self.getpos()
        start = self.line_offsets[line - 1] + column
        raw = self.get_starttag_text()
        retained = "".join(
            f" {html.escape(name, quote=True)}"
            + (f'="{html.escape(value, quote=True)}"' if value is not None else "")
            for name, value in attrs if name != "nonce"
        )
        ending = "/>" if raw.endswith("/>") else ">"
        replacement = f'<style nonce="{html.escape(self.nonce, quote=True)}"{retained}{ending}'
        self.edits.append((start, start + len(raw), replacement))


def _nonce_styles(source: str, nonce: str) -> str:
    """Authorize style blocks without changing CSS, script content, or artifact files."""
    parser = _StyleNonceParser(source, nonce)
    parser.feed(source)
    parser.close()
    for start, end, replacement in reversed(parser.edits):
        source = source[:start] + replacement + source[end:]
    return source


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _public(value: Any) -> Any:
    """Keep accidental credential fields out of the inspectable evidence view."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if SECRET_KEY.fullmatch(str(key)) else _public(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return SENSITIVE_TEXT.sub(lambda match: (match[1] or match[2] or "") + "[redacted]", value)
    if value is None or type(value) in (int, float, bool):
        return value
    return str(value)


def _inside(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError("Artifact must be a file inside this run's output directory.")
    return resolved


def _read_json(root: Path, name: str) -> dict[str, Any] | None:
    try:
        path = _inside(root, root / name)
        if not path.is_file() or path.stat().st_size > MAX_EVIDENCE_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return _public(value) if isinstance(value, dict) else None
    except (OSError, ValueError, RecursionError):
        # Writers may be between writes; the next poll will retry the same file.
        return None


def _saved_object(path: Path) -> dict[str, Any]:
    if path.resolve() != path:
        raise ValueError("Saved history cannot follow links.")
    with path.open("rb") as handle:
        raw = handle.read(MAX_HISTORY_METADATA_BYTES + 1)
    if len(raw) > MAX_HISTORY_METADATA_BYTES:
        raise ValueError("Saved metadata exceeds 64 KiB.")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Saved metadata must be an object.")
    return value


def _select_export_health(
    telemetry: dict[str, Any] | None, sidecar: dict[str, Any] | None,
    trace_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    candidates = []
    for priority, (source, document) in enumerate((
        ("telemetry.json", telemetry), ("telemetry-health.json", sidecar),
    )):
        if not document or trace_id and document.get("trace_id") != trace_id:
            continue
        health = document.get("export_health")
        if not isinstance(health, dict) or health.get("status") not in ("healthy", "degraded"):
            continue
        timestamps = [datetime.min.replace(tzinfo=timezone.utc)]
        for field in ("last_success_at", "last_failure_at"):
            value = health.get(field)
            if not isinstance(value, str):
                continue
            try:
                stamp = datetime.fromisoformat(value)
            except ValueError:
                continue
            if stamp.tzinfo is not None:
                timestamps.append(stamp)
        candidates.append((max(timestamps), health["status"] == "degraded", priority, health, source))
    if not candidates:
        return None, None
    _, _, _, health, source = max(candidates, key=lambda item: item[:3])
    return health, source


@dataclasses.dataclass
class _Run:
    id: str
    directory: Path
    config: dict[str, Any]
    created_at: str = dataclasses.field(default_factory=_now)
    updated_at: str = dataclasses.field(default_factory=_now)
    status: str = "running"
    error: str | None = None
    result: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    artifacts: dict[str, Path] = dataclasses.field(default_factory=dict)
    approval_event: threading.Event = dataclasses.field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    restored: bool = False

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "config": self.config,
            "error": self.error,
            "approval": self.approval,
            "restored": self.restored,
            "artifacts": {
                name: {
                    "name": path.name, "url": f"/api/runs/{self.id}/artifacts/{name}",
                    "relative_path": str(path.relative_to(self.directory)),
                }
                for name, path in self.artifacts.items()
            },
        }


class _RunManager:
    def __init__(
        self, input_root: Path, skills_root: Path, out_dir: Path, memory_dir: Path,
        runner: Callable[..., Any] | None, approval_timeout: float,
    ) -> None:
        self.input_root = Path(input_root).resolve()
        self.skills_root = Path(skills_root).resolve()
        self.out_dir = Path(out_dir).resolve()
        self.memory_dir = Path(memory_dir).resolve()
        self.runner = runner
        self.approval_timeout = approval_timeout
        self.lock = threading.RLock()
        self.runs: dict[str, _Run] = {}
        self.active_id: str | None = None
        self.closed = False
        self._restore_saved_runs()

    def _restore_saved_runs(self) -> None:
        directory = self.out_dir / ".console"
        if not directory.exists():
            return
        try:
            if directory.resolve() != directory or not directory.is_dir():
                raise ValueError("Saved history must be an owned directory, not a link.")
            candidates = []
            for index, path in enumerate(directory.iterdir()):
                if index >= MAX_HISTORY_SCAN:
                    LOGGER.warning("Saved history scan capped at %s entries.", MAX_HISTORY_SCAN)
                    break
                if path.suffix == ".json" and RUN_ID.fullmatch(path.stem):
                    if path.resolve() == path and path.is_file():
                        candidates.append((path.stat().st_mtime_ns, path))
            restored = []
            for _, path in sorted(candidates, reverse=True):
                if len(restored) >= MAX_HISTORY_RUNS:
                    break
                try:
                    restored.append(self._restore_run(path))
                except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
                    LOGGER.warning("Skipping saved run %s: %s", path.name, _public(str(error)))
            self.runs.update(
                (run.id, run) for run in sorted(
                    restored, key=lambda item: (datetime.fromisoformat(item.created_at), item.id),
                )
            )
        except (OSError, ValueError) as error:
            LOGGER.warning("Cannot load saved harness history: %s", _public(str(error)))

    def _restore_run(self, path: Path) -> _Run:
        from .live_config import HarnessConfig

        data = _saved_object(path)
        required = {"id", "status", "created_at", "updated_at", "config", "error", "approval", "artifacts"}
        if not required <= data.keys() or data.keys() - required - {"restored"}:
            raise ValueError("Unexpected saved metadata fields.")
        if data["id"] != path.stem or data["status"] not in FINISHED_STATUSES | {"running", "awaiting_approval"}:
            raise ValueError("Invalid saved run identity or status.")
        directory = self.out_dir / data["id"]
        if directory.resolve() != directory or not directory.is_dir():
            raise ValueError("Saved run directory is missing or linked.")
        for field in ("created_at", "updated_at"):
            if not isinstance(data[field], str) or datetime.fromisoformat(data[field]).tzinfo is None:
                raise ValueError("Saved timestamps must include their timezone.")
        config = HarnessConfig.from_dict(data["config"]).to_dict()
        if config != data["config"]:
            raise ValueError("Saved configuration must contain every field.")
        if data["error"] is not None and not isinstance(data["error"], str):
            raise ValueError("Invalid saved error.")
        approval = data["approval"]
        if approval is not None:
            if not isinstance(approval, dict) or approval.get("status") not in {
                "pending", "approved", "rejected", "expired", "interrupted",
            }:
                raise ValueError("Invalid saved approval.")
            for field in ("requested_at", "decided_at"):
                if field in approval or field == "requested_at":
                    stamp = approval.get(field)
                    if not isinstance(stamp, str) or datetime.fromisoformat(stamp).tzinfo is None:
                        raise ValueError("Invalid saved approval timestamp.")
            if approval.get("dashboard_url") not in (None, f"/api/runs/{data['id']}/artifacts/dashboard"):
                raise ValueError("Invalid saved approval dashboard URL.")
            report = approval.get("report")
            if (
                not isinstance(report, dict) or type(report.get("passed")) is not bool
                or not isinstance(report.get("checks"), list) or len(report["checks"]) > 100
                or any(
                    not isinstance(check, dict) or type(check.get("passed")) is not bool
                    or not isinstance(check.get("code"), str)
                    for check in report["checks"]
                )
                or approval.get("reviewer") is not None and not isinstance(approval["reviewer"], str)
            ):
                raise ValueError("Invalid saved verifier report or reviewer.")
            approval = _public(approval)
        run = _Run(
            data["id"], directory, config, created_at=data["created_at"],
            updated_at=data["updated_at"], status=data["status"],
            error=_public(data["error"]), approval=approval, restored=True,
        )
        artifacts = data["artifacts"]
        if not isinstance(artifacts, dict) or set(artifacts) - {"dashboard"}:
            raise ValueError("Unknown saved artifact.")
        for name, artifact in artifacts.items():
            if not isinstance(artifact, dict) or artifact.get("url") != f"/api/runs/{run.id}/artifacts/{name}":
                raise ValueError("Invalid saved artifact URL.")
            relative = artifact.get("relative_path")
            if relative is None:
                # Older metadata kept only a basename; use its bounded result
                # manifest for attempt subdirectories, never scan arbitrary files.
                relative = artifact.get("name")
                if relative == "dashboard.html" and not (directory / relative).exists():
                    result_path = directory / "result.json"
                    if result_path.exists():
                        relative = _saved_object(result_path).get("dashboard", relative)
            if not isinstance(relative, str) or not relative or "\x00" in relative:
                raise ValueError("Invalid saved artifact path.")
            relative_path = Path(relative)
            if (
                relative_path.is_absolute() or relative_path.drive
                or any(part in (".", "..") or ":" in part for part in relative_path.parts)
                or relative_path.suffix.lower() != ".html"
            ):
                raise ValueError("Saved artifact path is not a relative HTML file.")
            if artifact.get("name") != relative_path.name:
                raise ValueError("Saved artifact name does not match its path.")
            candidate = directory / relative_path
            if _inside(directory, candidate) != candidate:
                raise ValueError("Saved artifacts cannot follow links.")
            if candidate.is_file():
                run.artifacts[name] = candidate
        if approval:
            approval["dashboard_url"] = (
                f"/api/runs/{run.id}/artifacts/dashboard" if "dashboard" in run.artifacts else None
            )
        if run.status not in FINISHED_STATUSES or approval and approval["status"] == "pending":
            run.status = "interrupted"
            run.error = "The previous server stopped before this run finished. No execution or approval was resumed."
            if approval and approval["status"] == "pending":
                approval["status"] = "interrupted"
        return run

    def bootstrap(self) -> dict[str, Any]:
        from .live_config import OPTIONAL_TOOLS, profiles

        skills = [
            {
                "id": skill.path.name, "name": skill.name, "description": skill.description,
                "mandatory": skill.name in ALWAYS_ON,
            }
            for skill in discover_skills(self.skills_root)
        ]
        with self.lock:
            return {
                "profiles": profiles(),
                "skills": skills,
                "optional_tools": list(OPTIONAL_TOOLS),
                "active_run_id": self.active_id,
                "runs": [run.metadata() for run in reversed(list(self.runs.values()))],
                "approval_timeout_seconds": self.approval_timeout,
                "boundaries": [
                    "Research policy and verifier observation are always on.",
                    "Only constrained arithmetic can execute; tools cannot run arbitrary code.",
                    "Publication always needs a human decision. No email is sent.",
                    "Observe-only previews are not verified completion certificates.",
                ],
            }

    def _save(self, run: _Run) -> None:
        run.updated_at = _now()
        metadata_dir = self.out_dir / ".console"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        staging = metadata_dir / f"{run.id}.json.next"
        staging.write_text(json.dumps(_public(run.metadata()), indent=2), encoding="utf-8")
        staging.replace(metadata_dir / f"{run.id}.json")

    def start(self, raw_config: dict[str, Any]) -> _Run:
        from .live_config import HarnessConfig

        config = HarnessConfig.from_dict(raw_config)
        normalized = config.to_dict()
        names = {skill.path.name for skill in discover_skills(self.skills_root)}
        unknown = set(normalized["available_skills"]) - names
        if unknown:
            raise ValueError("Unknown skills: " + ", ".join(sorted(unknown)))
        with self.lock:
            if self.closed:
                raise RuntimeError("The server is shutting down.")
            if self.active_id is not None:
                raise RuntimeError("A run is already active. Finish or reject its approval first.")
            run_id = "r-" + secrets.token_hex(8)
            directory = self.out_dir / run_id
            directory.mkdir(parents=True, exist_ok=False)
            run = _Run(run_id, directory, normalized)
            self.runs[run_id] = run
            self.active_id = run_id
            try:
                self._save(run)
                run.thread = threading.Thread(
                    target=self._execute, args=(run, config), daemon=True,
                    name=f"harness-{run_id}",
                )
                run.thread.start()
            except Exception:
                self.active_id = None
                self.runs.pop(run_id, None)
                raise
            return run

    def _approval(self, run: _Run, dashboard: Path, report: Any) -> str | None:
        path = _inside(run.directory, Path(dashboard))
        if not path.is_file() or path.suffix.lower() != ".html":
            raise ValueError("The reviewer dashboard must be an HTML file in this run.")
        report_data = report.to_dict() if hasattr(report, "to_dict") else _public(report)
        if not isinstance(report_data, dict):
            raise ValueError("The approval request must include a verifier report.")
        with self.lock:
            if self.closed:
                return None
            run.approval_event.clear()
            run.artifacts["dashboard"] = path
            run.approval = {
                "status": "pending", "requested_at": _now(),
                "report": _public(report_data), "reviewer": None,
                "dashboard_url": f"/api/runs/{run.id}/artifacts/dashboard",
                "timeout_seconds": self.approval_timeout,
            }
            run.status = "awaiting_approval"
            self._save(run)
        signaled = run.approval_event.wait(self.approval_timeout)
        with self.lock:
            if not signaled and run.approval["status"] == "pending":
                run.approval["status"] = "expired"
                run.approval["decided_at"] = _now()
            accepted = run.approval["status"] == "approved"
            run.status = "running"
            self._save(run)
            return run.approval["reviewer"] if accepted else None

    def decide(self, run: _Run, decision: str, reviewer: str) -> None:
        if decision not in ("approve", "reject"):
            raise ValueError("Decision must be approve or reject.")
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 120:
            raise ValueError("Enter a reviewer name between 1 and 120 characters.")
        if any(ord(character) < 32 for character in reviewer):
            raise ValueError("Reviewer names cannot contain control characters.")
        with self.lock:
            if (
                run.status != "awaiting_approval" or not run.approval
                or run.approval["status"] != "pending"
            ):
                raise RuntimeError("This run has no pending human approval.")
            run.approval.update(
                status="approved" if decision == "approve" else "rejected",
                reviewer=reviewer.strip(), decided_at=_now(),
            )
            self._save(run)
            run.approval_event.set()

    def _execute(self, run: _Run, config: Any) -> None:
        try:
            runner = self.runner
            if runner is None:
                from .live import run_live_episode

                runner = run_live_episode
            result = asyncio.run(
                runner(
                    self.input_root, self.skills_root, run.directory,
                    config=config, memory_dir=self.memory_dir,
                    approval_provider=lambda dashboard, report: self._approval(run, dashboard, report),
                    approval_kind="interactive",
                )
            )
            with self.lock:
                run.result = _public(result)
                if (
                    isinstance(result, dict) and result.get("dashboard")
                    and result.get("status") in ("completed", "unverified_preview")
                ):
                    dashboard = _inside(run.directory, run.directory / result["dashboard"])
                    if not dashboard.is_file() or dashboard.suffix.lower() != ".html":
                        raise ValueError("The result dashboard must be an HTML file in this run.")
                    run.artifacts["dashboard"] = dashboard
                run.status = "completed"
        except Exception as error:
            with self.lock:
                run.error = _public(f"{type(error).__name__}: {error}")[:2000]
                run.status = "failed"
        finally:
            with self.lock:
                if run.approval and run.approval["status"] in ("rejected", "expired"):
                    run.status = "rejected" if run.approval["status"] == "rejected" else "failed"
                    if run.approval["status"] == "expired":
                        run.error = "Human approval timed out. Start a new run to review again."
                try:
                    self._save(run)
                finally:
                    self.active_id = None

    def get(self, run_id: str) -> _Run:
        if not RUN_ID.fullmatch(run_id):
            raise KeyError(run_id)
        with self.lock:
            return self.runs[run_id]

    def snapshot(self, run: _Run) -> dict[str, Any]:
        with self.lock:
            snapshot = run.metadata()
            snapshot["result"] = _read_json(run.directory, "result.json") or run.result
            snapshot["runtime_state"] = _read_json(run.directory, "runtime-state.json")
            snapshot["telemetry"] = _read_json(run.directory, "telemetry.json")
            snapshot["telemetry_health"] = _read_json(run.directory, "telemetry-health.json")
            trace_id = (snapshot["telemetry"] or {}).get("trace_id") or (snapshot["result"] or {}).get("trace_id")
            snapshot["export_health"], snapshot["export_health_source"] = _select_export_health(
                snapshot["telemetry"], snapshot["telemetry_health"], trace_id,
            )
            return _public(snapshot)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            for run in self.runs.values():
                if run.approval and run.approval["status"] == "pending":
                    run.approval["status"] = "rejected"
                    run.approval_event.set()


class HarnessUIServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], manager: _RunManager) -> None:
        self.manager = manager
        self.nonce = secrets.token_urlsafe(32)
        self.style_nonce = secrets.token_urlsafe(32)
        super().__init__(address, _Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def server_close(self) -> None:
        self.manager.close()
        super().server_close()


class _Handler(BaseHTTPRequestHandler):
    server: HarnessUIServer
    server_version = "HarnessConsole"
    sys_version = ""

    def log_message(self, _format: str, *args: Any) -> None:
        # Do not dump model content, reviewer names, or nonce headers into logs.
        return

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def _send(
        self, status: int, content: bytes, content_type: str, *, artifact: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if artifact:
            self.send_header(
                "Content-Security-Policy",
                "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; "
                "style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'self'",
            )
        else:
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'none'; script-src 'nonce-{self.server.nonce}'; "
                f"style-src 'nonce-{self.server.style_nonce}'; connect-src 'self'; "
                "frame-src 'self'; img-src 'self' data:; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'",
            )
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(_public(data), ensure_ascii=True).encode(), "application/json")

    def _deny(self, message: str, *, mutation: bool) -> bool:
        # Closing with an unread body can reset the socket before a Windows client
        # receives the rejection. Consume only a bounded, explicitly sized body.
        if mutation and self.headers.get("Transfer-Encoding") is None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if 0 < length <= MAX_DISCARD_BYTES:
                    self.rfile.read(length)
            except (ValueError, OSError):
                pass
        self._json(403, {"error": message})
        return False

    def _trusted(self, *, mutation: bool = False) -> bool:
        host = self.headers.get("Host", "")
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in hosts or len(self.headers.get_all("Host", [])) != 1:
            return self._deny("Only the local harness host is accepted.", mutation=mutation)
        if mutation:
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{host}":
                return self._deny("Foreign origins cannot change a harness run.", mutation=True)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self._deny("Cross-site requests are not allowed.", mutation=True)
            nonce = self.headers.get("X-Harness-Nonce", "")
            if not secrets.compare_digest(nonce, self.server.nonce):
                return self._deny("Missing local session nonce. Reload this page.", mutation=True)
        return True

    def _parts(self) -> list[str]:
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Unexpected URL.")
        path = unquote(parsed.path)
        parts = path.split("/")[1:]
        if any(part in (".", "..") or "\\" in part or "\x00" in part for part in parts):
            raise ValueError("Invalid path.")
        return parts

    def do_GET(self) -> None:
        if not self._trusted():
            return
        try:
            parts = self._parts()
            if parts == [""]:
                page = ASSET.read_text(encoding="utf-8").replace("__HARNESS_NONCE__", self.server.nonce)
                page = _nonce_styles(page, self.server.style_nonce)
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif parts == ["favicon.ico"]:
                self._send(204, b"", "image/x-icon")
            elif parts == ["api", "bootstrap"]:
                self._json(200, self.server.manager.bootstrap())
            elif len(parts) == 3 and parts[:2] == ["api", "runs"]:
                self._json(200, self.server.manager.snapshot(self.server.manager.get(parts[2])))
            elif len(parts) == 5 and parts[:2] == ["api", "runs"] and parts[3] == "artifacts":
                run = self.server.manager.get(parts[2])
                with self.server.manager.lock:
                    path = _inside(run.directory, run.artifacts[parts[4]])
                    if not path.is_file() or path.stat().st_size > MAX_EVIDENCE_BYTES:
                        raise KeyError(parts[4])
                    content = _nonce_styles(
                        path.read_text(encoding="utf-8"), self.server.style_nonce,
                    ).encode("utf-8")
                self._send(200, content, "text/html; charset=utf-8", artifact=True)
            else:
                self._json(404, {"error": "Not found."})
        except (KeyError, FileNotFoundError, ValueError):
            self._json(404, {"error": "Not found."})
        except Exception:
            self._json(500, {"error": "Could not read local harness data. Check the server setup."})

    def _body(self) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding") is not None:
            raise ValueError("Chunked request bodies are not accepted.")
        if len(self.headers.get_all("Content-Length", [])) != 1:
            raise ValueError("A single Content-Length is required.")
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            if length <= MAX_DISCARD_BYTES:
                self.rfile.read(length)
            raise OverflowError("Request body exceeds 64 KiB.")
        if length <= 0:
            raise ValueError("A JSON request body is required.")
        payload = self.rfile.read(length)
        if len(payload) != length:
            raise ValueError("Incomplete request body.")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise ValueError("Content-Type must be application/json.")
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("The request body must be a JSON object.")
        return value

    def do_POST(self) -> None:
        if not self._trusted(mutation=True):
            return
        try:
            parts = self._parts()
            body = self._body()
            if parts == ["api", "runs"]:
                if set(body) != {"config"} or not isinstance(body["config"], dict):
                    raise ValueError("Send a single config object; paths are controlled by the server.")
                run = self.server.manager.start(body["config"])
                self._json(202, self.server.manager.snapshot(run))
            elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "approval":
                if set(body) != {"decision", "reviewer"}:
                    raise ValueError("Approval requires a decision and a reviewer name.")
                run = self.server.manager.get(parts[2])
                self.server.manager.decide(run, body["decision"], body["reviewer"])
                self._json(200, self.server.manager.snapshot(run))
            else:
                self._json(404, {"error": "Not found."})
        except OverflowError as error:
            self._json(413, {"error": str(error)})
        except (ValueError, TypeError, RecursionError) as error:
            self._json(400, {"error": str(error)[:600]})
        except KeyError:
            self._json(404, {"error": "Run not found."})
        except RuntimeError as error:
            self._json(409, {"error": str(error)})
        except Exception:
            self._json(500, {"error": "Could not start the run. Check the local output directory."})

    def do_OPTIONS(self) -> None:
        self._json(405, {"error": "Cross-origin API access is not supported."})


def create_ui_server(
    input_root: Path, skills_root: Path, out_dir: Path, *,
    memory_dir: Path, host: str = "127.0.0.1", port: int = 8765,
    runner: Callable[..., Any] | None = None, approval_timeout: float = 600,
) -> HarnessUIServer:
    """Create an unstarted local server; callers own serve_forever and server_close.

    Set ``port=0`` for an ephemeral port and read ``server.url`` after creation.
    The optional runner must implement the async ``run_live_episode`` signature.
    Output and memory locations are startup configuration, never HTTP inputs.
    """
    if host != "127.0.0.1":
        raise ValueError("The harness UI can bind only to 127.0.0.1.")
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    if not 0 < approval_timeout <= 3600:
        raise ValueError("Approval timeout must be between 0 and 3600 seconds.")
    manager = _RunManager(input_root, skills_root, out_dir, memory_dir, runner, approval_timeout)
    return HarnessUIServer((host, port), manager)


def serve_ui(
    input_root: Path, skills_root: Path, out_dir: Path, *,
    memory_dir: Path, host: str = "127.0.0.1", port: int = 8765,
    runner: Callable[..., Any] | None = None, approval_timeout: float = 600,
) -> None:
    """Serve the primary live console until interrupted; never open an arbitrary file."""
    server = create_ui_server(
        input_root, skills_root, out_dir, memory_dir=memory_dir, host=host, port=port,
        runner=runner, approval_timeout=approval_timeout,
    )
    print(f"Harness console: {server.url} (local only; Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def serve(
    input_root: Path, skills_root: Path, out_root: Path, *,
    memory_dir: Path, port: int = 8765,
) -> None:
    """CLI entrypoint; each episode receives a fresh directory beneath out_root."""
    serve_ui(input_root, skills_root, out_root, memory_dir=memory_dir, port=port)

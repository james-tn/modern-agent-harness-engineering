"""Exercise Windows sharing violations with a real deny-all filesystem handle."""

from __future__ import annotations

import asyncio
import ctypes
import json
import sys
import threading
import time
from pathlib import Path

import pytest

from equity_event.live import run_live_episode
from equity_event.live_config import HarnessConfig

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows file-sharing semantics.")
def test_real_exclusive_lock_does_not_invalidate_an_accepted_episode(tmp_path):
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    invalid_handle = ctypes.c_void_p(-1).value
    output = tmp_path / "locked-episode"
    acquired = threading.Event()
    failures = []

    def hold_exclusive_lock():
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            # FileShare.None blocks readers and atomic replacement of this real file.
            handle = kernel.CreateFileW(
                str(output / "telemetry.json"), 0x80000000, 0, None, 3, 0x80, None,
            )
            if handle != invalid_handle:
                acquired.set()
                try:
                    time.sleep(3)
                finally:
                    if not kernel.CloseHandle(handle):
                        failures.append(ctypes.WinError(ctypes.get_last_error()))
                return
            error = ctypes.get_last_error()
            if error not in {2, 3, 5, 32}:
                failures.append(ctypes.WinError(error))
                return
            time.sleep(0.005)
        failures.append(TimeoutError("No telemetry file could be exclusively locked."))

    locker = threading.Thread(target=hold_exclusive_lock, name="windows-deny-all-lock")
    locker.start()
    try:
        result = asyncio.run(run_live_episode(
            ROOT / "demo" / "sample-input", ROOT / "demo" / "agent" / "skills", output,
            config=HarnessConfig(model="scripted", memory_scope="os-lock-regression"),
            memory_dir=tmp_path / "memory",
            approval_provider=lambda _artifact, _report: "automated-os-lock-test",
            approval_kind="automated-os-lock-test-not-human",
        ))
    finally:
        locker.join(timeout=20)
    assert not locker.is_alive() and acquired.is_set()
    assert not failures, failures
    assert result["status"] == "completed" and result["certified"]
    persisted = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert persisted == result
    telemetry = json.loads((output / "telemetry.json").read_text(encoding="utf-8"))
    health = telemetry["export_health"]
    assert health["status"] == "healthy"
    assert health["write_failures"] >= 1
    assert health["consecutive_failures"] == 0
    assert health["last_error"]["winerror"] == 5
    assert any(span["origin"] == "maf" for span in telemetry["spans"])
    assert any(event["event"] == "completion_admitted" for event in telemetry["events"])
    assert (output / "telemetry-health.json").is_file()

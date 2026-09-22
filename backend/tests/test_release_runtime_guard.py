"""Regression coverage for the Windows release-runtime hardening
(release_runtime_guard.py + release_main.main()).

Windows-specific primitives (ctypes mutex, MessageBoxW) are mocked so these
tests run in the normal pytest environment without popping a real dialog or
depending on actual Windows mutex semantics. Port/readiness tests use real
loopback sockets on ephemeral high ports (never 8000/3000 themselves) so
they stay deterministic without sleeping more than a few hundred ms.
"""
import os
import socket
import sys
import threading
import time

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import release_runtime_guard as grd  # noqa: E402
import release_main  # noqa: E402


# ============================================================== port helpers

def _listen_on(port: int):
    """Start a bare-bones TCP listener the test can use as an occupied port."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    return srv


def _free_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_is_port_free_true_for_unoccupied_port():
    port = _free_ephemeral_port()
    assert grd.is_port_free("127.0.0.1", port) is True


def test_is_port_free_false_for_occupied_port():
    port = _free_ephemeral_port()
    srv = _listen_on(port)
    try:
        assert grd.is_port_free("127.0.0.1", port) is False
    finally:
        srv.close()


def test_wait_until_ready_true_once_listener_starts():
    """G. readiness: frontend becomes available -> detected promptly."""
    port = _free_ephemeral_port()

    def _start_late():
        time.sleep(0.2)
        srv = _listen_on(port)
        time.sleep(0.5)
        srv.close()

    t = threading.Thread(target=_start_late, daemon=True)
    t.start()
    assert grd.wait_until_ready("127.0.0.1", port, timeout=3.0, interval=0.1) is True
    t.join(timeout=2)


def test_wait_until_ready_false_on_timeout_no_endless_wait():
    """F/H. readiness: nothing ever listens -> times out, does not hang."""
    port = _free_ephemeral_port()
    started = time.monotonic()
    result = grd.wait_until_ready("127.0.0.1", port, timeout=0.5, interval=0.1)
    elapsed = time.monotonic() - started
    assert result is False
    assert elapsed < 2.0  # bounded, never an endless wait


# ============================================================ mutex helpers

class _FakeKernel32:
    """Stand-in for ctypes.WinDLL('kernel32', ...) - simulates
    CreateMutexW/CloseHandle/GetLastError without touching a real mutex."""

    def __init__(self, last_error: int):
        self._last_error = last_error
        self.closed_handles = []

    def CreateMutexW(self, _sec_attrs, _initial_owner, _name):
        return 12345  # any truthy fake handle

    def CloseHandle(self, handle):
        self.closed_handles.append(handle)
        return True


def test_acquire_mutex_first_instance(monkeypatch):
    fake = _FakeKernel32(last_error=0)
    monkeypatch.setattr(grd, "_IS_WINDOWS", True)
    monkeypatch.setattr(grd.ctypes, "WinDLL", lambda *a, **k: fake)
    monkeypatch.setattr(grd.ctypes, "get_last_error", lambda: fake._last_error)
    handle, already_running = grd.acquire_single_instance_mutex("Local\\Test")
    assert handle == 12345
    assert already_running is False


def test_acquire_mutex_second_instance(monkeypatch):
    fake = _FakeKernel32(last_error=grd.ERROR_ALREADY_EXISTS)
    monkeypatch.setattr(grd, "_IS_WINDOWS", True)
    monkeypatch.setattr(grd.ctypes, "WinDLL", lambda *a, **k: fake)
    monkeypatch.setattr(grd.ctypes, "get_last_error", lambda: fake._last_error)
    handle, already_running = grd.acquire_single_instance_mutex("Local\\Test")
    assert handle == 12345  # still a valid handle to the EXISTING mutex
    assert already_running is True


def test_release_mutex_closes_handle(monkeypatch):
    fake = _FakeKernel32(last_error=0)
    monkeypatch.setattr(grd, "_IS_WINDOWS", True)
    monkeypatch.setattr(grd.ctypes, "WinDLL", lambda *a, **k: fake)
    grd.release_single_instance_mutex(99)
    assert fake.closed_handles == [99]


def test_release_mutex_none_handle_is_a_noop(monkeypatch):
    monkeypatch.setattr(grd, "_IS_WINDOWS", True)
    grd.release_single_instance_mutex(None)  # must not raise


# ========================================================== messagebox mocks

def test_show_conflict_messagebox_calls_win32_api(monkeypatch):
    calls = []
    monkeypatch.setattr(grd, "_IS_WINDOWS", True)

    class _FakeUser32:
        def MessageBoxW(self, *args):
            calls.append(args)

    class _FakeWindll:
        user32 = _FakeUser32()

    monkeypatch.setattr(grd.ctypes, "windll", _FakeWindll())
    grd.show_conflict_messagebox(8000)
    assert len(calls) == 1
    _, message, title, _flags = calls[0]
    assert "8000" in message
    assert "Eyzon Optics" in title


def test_show_failure_messagebox_calls_win32_api(monkeypatch):
    calls = []
    monkeypatch.setattr(grd, "_IS_WINDOWS", True)

    class _FakeUser32:
        def MessageBoxW(self, *args):
            calls.append(args)

    class _FakeWindll:
        user32 = _FakeUser32()

    monkeypatch.setattr(grd.ctypes, "windll", _FakeWindll())
    grd.show_failure_messagebox("boom")
    assert len(calls) == 1
    assert "boom" in calls[0][1]


def test_messagebox_non_windows_prints_instead_of_raising(monkeypatch, capsys):
    monkeypatch.setattr(grd, "_IS_WINDOWS", False)
    grd.show_conflict_messagebox(3000)
    captured = capsys.readouterr()
    assert "3000" in captured.err


# ================================================== release_main.main() flow

def test_main_second_instance_opens_browser_once_and_skips_ports(monkeypatch):
    """D/E. second-instance mutex condition -> server startup skipped,
    existing frontend URL opened exactly once, port checks never run."""
    monkeypatch.setattr(release_main, "acquire_single_instance_mutex",
                         lambda name: (111, True))
    released = []
    monkeypatch.setattr(release_main, "release_single_instance_mutex",
                         lambda h: released.append(h))

    def _fail_if_called(*a, **k):
        raise AssertionError("port check must not run for a second instance")

    monkeypatch.setattr(release_main, "is_port_free", _fail_if_called)

    opened = []
    monkeypatch.setattr(release_main.webbrowser, "open", lambda url: opened.append(url))

    def _fail_if_run(*a, **k):
        raise AssertionError("uvicorn must never start for a second instance")

    monkeypatch.setattr(release_main.asyncio, "run", _fail_if_run)

    rc = release_main.main()
    assert rc == 0
    assert opened == [release_main.FRONTEND_URL]
    assert released == [111]


def test_main_occupied_backend_port_shows_conflict_and_exits(monkeypatch):
    """B. occupied 8000 -> conflict detected, no server start attempted."""
    monkeypatch.setattr(release_main, "acquire_single_instance_mutex",
                         lambda name: (222, False))
    released = []
    monkeypatch.setattr(release_main, "release_single_instance_mutex",
                         lambda h: released.append(h))
    monkeypatch.setattr(release_main, "is_port_free",
                         lambda host, port: port != release_main.BACKEND_PORT)
    conflicts = []
    monkeypatch.setattr(release_main, "show_conflict_messagebox", conflicts.append)

    def _fail_if_run(*a, **k):
        raise AssertionError("uvicorn must never start when a port is occupied")

    monkeypatch.setattr(release_main.asyncio, "run", _fail_if_run)

    rc = release_main.main()
    assert rc == 1
    assert conflicts == [release_main.BACKEND_PORT]
    assert released == [222]


def test_main_occupied_frontend_port_shows_conflict_and_exits(monkeypatch):
    """C. occupied 3000 -> conflict detected, no server start attempted."""
    monkeypatch.setattr(release_main, "acquire_single_instance_mutex",
                         lambda name: (333, False))
    monkeypatch.setattr(release_main, "release_single_instance_mutex", lambda h: None)
    monkeypatch.setattr(release_main, "is_port_free",
                         lambda host, port: port != release_main.FRONTEND_PORT)
    conflicts = []
    monkeypatch.setattr(release_main, "show_conflict_messagebox", conflicts.append)
    monkeypatch.setattr(release_main.asyncio, "run",
                         lambda *a, **k: (_ for _ in ()).throw(
                             AssertionError("uvicorn must never start")))

    rc = release_main.main()
    assert rc == 1
    assert conflicts == [release_main.FRONTEND_PORT]


def test_main_free_ports_normal_start_path_and_mutex_released(monkeypatch):
    """A. free ports -> preflight passes and startup proceeds; mutex always
    released afterward even on the success path."""
    monkeypatch.setattr(release_main, "acquire_single_instance_mutex",
                         lambda name: (444, False))
    released = []
    monkeypatch.setattr(release_main, "release_single_instance_mutex",
                         lambda h: released.append(h))
    monkeypatch.setattr(release_main, "is_port_free", lambda host, port: True)
    ran = []

    def _fake_run(coro):
        ran.append(coro)
        coro.close()  # never actually awaited in this test - avoid an "unawaited" warning

    monkeypatch.setattr(release_main.asyncio, "run", _fake_run)

    rc = release_main.main()
    assert rc == 0
    assert len(ran) == 1
    assert released == [444]


def test_main_startup_failure_shows_message_exits_nonzero_and_releases_mutex(monkeypatch):
    """H. timeout/failure -> clear failure path, non-zero exit, mutex still
    released (no leaked handle on the failure branch)."""
    monkeypatch.setattr(release_main, "acquire_single_instance_mutex",
                         lambda name: (555, False))
    released = []
    monkeypatch.setattr(release_main, "release_single_instance_mutex",
                         lambda h: released.append(h))
    monkeypatch.setattr(release_main, "is_port_free", lambda host, port: True)

    def _boom(coro):
        coro.close()  # never actually awaited in this test
        raise RuntimeError("bind failed unexpectedly")

    monkeypatch.setattr(release_main.asyncio, "run", _boom)
    failures = []
    monkeypatch.setattr(release_main, "show_failure_messagebox", failures.append)

    rc = release_main.main()
    assert rc == 1
    assert len(failures) == 1
    assert "bind failed unexpectedly" in failures[0]
    assert released == [555]

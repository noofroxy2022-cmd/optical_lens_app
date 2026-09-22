"""Windows release-runtime safety helpers for release_main.py.

Single-instance guard (named mutex), port-conflict pre-flight, and frontend
readiness polling. Pure and side-effect-free at import time - importing this
module never touches a mutex, a socket, or a message box - so it is fully
unit-testable and mockable. release_main.py is the only production caller.

This ships only as part of the Windows standalone release, so the real
ctypes/mutex/MessageBoxW calls only run on win32. On any other platform they
are safe no-ops (never "already running", ports checked with plain sockets,
conflict/failure text printed to stderr instead of a message box) so the
backend test suite - which may run on a non-Windows CI/dev machine - never
breaks importing or exercising this module.
"""
from __future__ import annotations

import ctypes
import socket
import sys
import time
from typing import Optional

MUTEX_NAME = r"Local\EyzonOpticsRuntimeV1"
ERROR_ALREADY_EXISTS = 183

_IS_WINDOWS = sys.platform == "win32"


def acquire_single_instance_mutex(name: str = MUTEX_NAME):
    """Create/open the named mutex. Returns (handle, already_running).

    handle is truthy whenever a real Windows mutex handle was obtained -
    including when already_running is True, since CreateMutexW still hands
    back a valid handle to the EXISTING mutex object in that case. Always
    pass whatever handle comes back to release_single_instance_mutex()
    exactly once when the process is done with it, even if already_running
    was True. On non-Windows platforms, or if CreateMutexW itself fails,
    returns (None, False) - never mistakenly reports "already running".
    """
    if not _IS_WINDOWS:
        return None, False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return None, False
    already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    return handle, already_running


def release_single_instance_mutex(handle) -> None:
    """Close a handle returned by acquire_single_instance_mutex(). Safe to
    call with None (non-Windows, or an acquire failure)."""
    if not _IS_WINDOWS or not handle:
        return
    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def is_port_free(host: str, port: int, timeout: float = 0.5) -> bool:
    """True if nothing is currently accepting TCP connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) != 0


def wait_until_ready(host: str, port: int, timeout: float = 30.0,
                      interval: float = 0.3) -> bool:
    """Poll host:port until it accepts a connection or timeout elapses.

    Returns True the moment it becomes reachable, False if the timeout is
    hit first - callers must never open a browser tab on a False result."""
    deadline = time.monotonic() + timeout
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(interval)
            if s.connect_ex((host, port)) == 0:
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


_MB_ICONERROR = 0x10
_MB_OK = 0x0


def show_conflict_messagebox(port: int) -> None:
    """A legitimate Eyzon instance was NOT already running (the mutex proved
    that), yet `port` is occupied by something else - a foreign/unrelated
    conflict. Never kill or connect to the owner; just tell the user."""
    title = "Eyzon Optics - تعارض في المنفذ"
    message = (
        f"تعذر تشغيل Eyzon Optics لأن المنفذ {port} مستخدم بالفعل بواسطة "
        "برنامج آخر.\n\nأغلق البرنامج الآخر ثم أعد تشغيل Eyzon Optics."
    )
    _show_messagebox(title, message)


def show_failure_messagebox(text: str) -> None:
    """The application failed to start for some other reason."""
    title = "Eyzon Optics - خطأ في التشغيل"
    _show_messagebox(title, text)


def _show_messagebox(title: str, message: str) -> None:
    if not _IS_WINDOWS:
        print(f"{title}: {message}", file=sys.stderr)
        return
    ctypes.windll.user32.MessageBoxW(0, message, title, _MB_ICONERROR | _MB_OK)

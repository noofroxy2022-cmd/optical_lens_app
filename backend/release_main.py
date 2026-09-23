"""Standalone Windows release entry point.

Packages the existing FastAPI backend (unmodified) together with the
prebuilt React production assets, so the target machine needs no Python,
Node, npm, or Git. This file is a thin wrapper only: it does not touch
app/main.py, app/database.py, or any matching/pricing logic.

Runs two local-only ASGI servers in one process:
  - 127.0.0.1:8000  -> the real FastAPI app (app.main.app), untouched
  - 127.0.0.1:3000  -> the prebuilt dashboard static files (with SPA fallback)

All app-relative paths (release_runtime.db, uploads/temp, backups/) are
resolved relative to the folder containing this executable/script, not the
caller's current directory, so double-clicking the release launcher from
anywhere still finds the approved database next to it.

Runtime hardening (2026-09-22): before doing any of that, this file first
acquires a named Windows mutex (release_runtime_guard.MUTEX_NAME) to detect
whether an Eyzon Optics instance is already running. A second launch never
attempts to bind the ports again - it just opens the existing instance's
browser tab and exits. Only once this process is proven to be the sole
instance does it pre-flight-check that ports 8000/3000 are actually free
(a positive mutex result cannot be spoofed by an unrelated program that
merely happens to be sitting on one of these ports); the chdir + app import
+ server startup below only happen after both checks pass, so a foreign
port conflict is reported with a clear message instead of silently
crashing partway through import/startup.
"""
import asyncio
import os
import sys
import webbrowser

from release_runtime_guard import (
    MUTEX_NAME,
    acquire_single_instance_mutex,
    release_single_instance_mutex,
    is_port_free,
    wait_until_ready,
    show_conflict_messagebox,
    show_failure_messagebox,
)
from release_db_guard import validate_release_db

BACKEND_PORT = 8000
FRONTEND_PORT = 3000
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"
_READY_TIMEOUT_SECONDS = 60.0


def _release_dir() -> str:
    """Folder holding release_runtime.db and this executable/script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bundled_dir() -> str:
    """Folder holding read-only bundled assets (the dashboard build)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


async def _serve() -> None:
    """Start both servers and wait for the frontend to become reachable
    before opening the browser exactly once. If either server fails, the
    other is cancelled too - never left running alone."""
    # Must happen BEFORE importing app.main: app/routers/uploads.py creates
    # its "uploads/temp" directory relative to CWD at import time, and the
    # default DATABASE_URL ("sqlite:///./release_runtime.db") resolves
    # relative to CWD at first connection.
    os.chdir(_release_dir())

    from app.main import app as backend_app  # noqa: E402 (import after chdir)

    import uvicorn  # noqa: E402
    from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
    from starlette.staticfiles import StaticFiles  # noqa: E402

    static_dir = os.path.join(_bundled_dir(), "dashboard_build")

    class SPAStaticFiles(StaticFiles):
        """Serves the CRA build; falls back to index.html for client-side routes."""

        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404 and not path.startswith("static/"):
                    return await super().get_response("index.html", scope)
                raise

    frontend_app = SPAStaticFiles(directory=static_dir, html=True)

    backend_server = uvicorn.Server(
        uvicorn.Config(backend_app, host="127.0.0.1", port=BACKEND_PORT, log_level="warning")
    )
    frontend_server = uvicorn.Server(
        uvicorn.Config(frontend_app, host="127.0.0.1", port=FRONTEND_PORT, log_level="warning")
    )

    backend_task = asyncio.create_task(backend_server.serve())
    frontend_task = asyncio.create_task(frontend_server.serve())

    opened = False

    async def _open_browser_when_ready() -> None:
        nonlocal opened
        loop = asyncio.get_running_loop()
        ready = await loop.run_in_executor(
            None, wait_until_ready, "127.0.0.1", FRONTEND_PORT, _READY_TIMEOUT_SECONDS, 0.3
        )
        if ready and not opened:
            opened = True
            webbrowser.open(FRONTEND_URL)

    readiness_task = asyncio.create_task(_open_browser_when_ready())

    done, pending = await asyncio.wait(
        {backend_task, frontend_task}, return_when=asyncio.FIRST_EXCEPTION
    )
    readiness_task.cancel()
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc


def main() -> int:
    """Entry point. Returns a process exit code - never raises."""
    handle, already_running = acquire_single_instance_mutex(MUTEX_NAME)
    try:
        if already_running:
            # A legitimate Eyzon Optics instance already owns the mutex -
            # never bind the ports again, never kill it. Just surface it.
            webbrowser.open(FRONTEND_URL)
            return 0

        # DB validation happens before any port check, before os.chdir, and
        # before app.main is ever imported - a missing/invalid database
        # must never be silently auto-created by SQLite's/SQLAlchemy's
        # default connect-on-first-query behavior in app/database.py.
        db_path = os.path.join(_release_dir(), "release_runtime.db")
        db_result = validate_release_db(db_path)
        if not db_result.ok:
            show_failure_messagebox(
                f"تعذر تشغيل Eyzon Optics: قاعدة البيانات {db_result.reason}.\n"
                "لم يتم تشغيل التطبيق."
            )
            return 1

        # This process now owns the mutex, so any occupied port below is
        # PROVABLY a foreign/unrelated conflict, not our own prior instance.
        for port in (BACKEND_PORT, FRONTEND_PORT):
            if not is_port_free("127.0.0.1", port):
                show_conflict_messagebox(port)
                return 1

        try:
            asyncio.run(_serve())
        except Exception as exc:  # defensive: startup must never crash silently
            show_failure_messagebox(f"Eyzon Optics failed to start:\n{exc}")
            return 1
        return 0
    finally:
        release_single_instance_mutex(handle)


if __name__ == "__main__":
    sys.exit(main())

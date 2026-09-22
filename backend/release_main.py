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
"""
import asyncio
import os
import sys
import threading
import webbrowser


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


RELEASE_DIR = _release_dir()

# Must happen BEFORE importing app.main: app/routers/uploads.py creates its
# "uploads/temp" directory relative to CWD at import time, and the default
# DATABASE_URL ("sqlite:///./release_runtime.db") resolves relative to CWD
# at first connection.
os.chdir(RELEASE_DIR)

from app.main import app as backend_app  # noqa: E402  (import after chdir)

import uvicorn  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

STATIC_DIR = os.path.join(_bundled_dir(), "dashboard_build")


class SPAStaticFiles(StaticFiles):
    """Serves the CRA build; falls back to index.html for client-side routes."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("static/"):
                return await super().get_response("index.html", scope)
            raise


frontend_app = SPAStaticFiles(directory=STATIC_DIR, html=True)

BACKEND_PORT = 8000
FRONTEND_PORT = 3000


def _open_browser():
    webbrowser.open(f"http://127.0.0.1:{FRONTEND_PORT}")


async def _run():
    backend_server = uvicorn.Server(
        uvicorn.Config(backend_app, host="127.0.0.1", port=BACKEND_PORT, log_level="warning")
    )
    frontend_server = uvicorn.Server(
        uvicorn.Config(frontend_app, host="127.0.0.1", port=FRONTEND_PORT, log_level="warning")
    )
    threading.Timer(1.5, _open_browser).start()
    await asyncio.gather(backend_server.serve(), frontend_server.serve())


if __name__ == "__main__":
    asyncio.run(_run())

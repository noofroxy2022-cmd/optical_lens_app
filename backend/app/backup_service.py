"""Local SQLite backup: daily automatic snapshots, keep last 7, manual
Backup Now, listing / status.

Design notes
------------
* Snapshots use the SQLite online backup API (`sqlite3.Connection.backup`),
  which is safe while the app keeps reading/writing - it never locks or
  corrupts the live database and produces a single self-consistent file.
* Backups live in a dedicated folder (``<db_dir>/backups`` by default, or
  ``$OPTICAL_BACKUP_DIR``) - never alongside as the active file, never the
  active file itself. Only ``optical_lens_*.db`` files are ever rotated.
* RESTORE IS OFFLINE ONLY. A running process must never copy over the live
  SQLite file or delete its ``-wal`` / ``-shm`` while FastAPI/SQLAlchemy may
  hold open connections. `restore_instructions()` only validates a chosen
  snapshot and returns the manual steps; it performs no filesystem change.
* Nothing here touches node_modules / build / *.pyc / caches - only the
  authoritative app DB file.
"""
from __future__ import annotations

import os
import sqlite3
import datetime as _dt
from typing import List, Dict, Any, Optional

from app import database

_PREFIX = "optical_lens_"
KEEP = 7


def _db_path() -> Optional[str]:
    url = database.engine.url
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    return os.path.abspath(url.database)


def is_sqlite() -> bool:
    return _db_path() is not None


def backup_dir() -> str:
    env = os.getenv("OPTICAL_BACKUP_DIR")
    if env:
        d = os.path.abspath(env)
    else:
        base = os.path.dirname(_db_path() or os.getcwd())
        d = os.path.join(base, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def _integrity_ok(path: str) -> bool:
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            list(con.execute("SELECT name FROM sqlite_master LIMIT 1"))
            return bool(row) and row[0] == "ok"
        finally:
            con.close()
    except Exception:
        return False


def _describe(path: str) -> Dict[str, Any]:
    st = os.stat(path)
    return {
        "name": os.path.basename(path),
        "size_bytes": st.st_size,
        "created_at": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }


def list_backups() -> List[Dict[str, Any]]:
    d = backup_dir()
    out = []
    for name in os.listdir(d):
        if name.startswith(_PREFIX) and name.endswith(".db"):
            out.append(_describe(os.path.join(d, name)))
    out.sort(key=lambda b: b["name"], reverse=True)
    return out


def create_backup(reason: str = "manual") -> Dict[str, Any]:
    src_path = _db_path()
    if src_path is None:
        raise RuntimeError("automatic backup supports SQLite databases only")
    if not os.path.exists(src_path):
        raise RuntimeError(f"database file not found: {src_path}")

    # microsecond suffix so two manual "Backup Now" clicks in the same second
    # never collide on one filename (daily prefix check keys only on %Y%m%d-)
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_reason = "".join(c for c in (reason or "manual") if c.isalnum() or c in "-_") or "manual"
    name = f"{_PREFIX}{ts}_{safe_reason}.db"
    dst_path = os.path.join(backup_dir(), name)

    src = sqlite3.connect(src_path)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            with dst:
                src.backup(dst)          # online hot-backup: no lock, no corruption
        finally:
            dst.close()
    finally:
        src.close()

    info = _describe(dst_path)
    info["integrity_ok"] = _integrity_ok(dst_path)
    info["reason"] = safe_reason
    if not info["integrity_ok"]:
        os.remove(dst_path)
        raise RuntimeError("backup failed integrity_check and was discarded")
    return info


def rotate(keep: int = KEEP) -> List[str]:
    """Delete the oldest daily/manual snapshots beyond `keep`. Safety
    (pre_restore_*) snapshots and the live DB are never touched."""
    d = backup_dir()
    snaps = sorted(
        (n for n in os.listdir(d) if n.startswith(_PREFIX) and n.endswith(".db")),
        reverse=True,
    )
    removed = []
    for name in snaps[keep:]:
        try:
            os.remove(os.path.join(d, name))
            removed.append(name)
        except OSError:
            pass
    return removed


def _today_tag() -> str:
    return _dt.datetime.now().strftime("%Y%m%d")


def ensure_daily_backup() -> Optional[Dict[str, Any]]:
    """Create today's snapshot if one does not already exist, then rotate.
    Safe to call repeatedly; never raises to the caller."""
    if not is_sqlite():
        return None
    try:
        tag = _today_tag()
        for b in list_backups():
            if b["name"].startswith(f"{_PREFIX}{tag}-"):
                return None                       # already have today's
        info = create_backup(reason="daily")
        rotate()
        return info
    except Exception:
        return None


def restore_instructions(name: str) -> Dict[str, Any]:
    """Validate a chosen snapshot and return the MANUAL, OFFLINE restore steps.

    This function never touches the live database. Replacing the active SQLite
    file (and removing its -wal / -shm) from inside a running FastAPI/SQLAlchemy
    process is unsafe, so restore is an operator action performed with the
    server stopped.
    """
    if not is_sqlite():
        raise RuntimeError("restore applies to SQLite databases only")
    if not name or "/" in name or "\\" in name or not name.endswith(".db"):
        raise ValueError("invalid backup name")
    src = os.path.join(backup_dir(), name)
    if not os.path.isfile(src):
        raise FileNotFoundError(name)
    integrity = _integrity_ok(src)

    live = _db_path()
    return {
        "performed": False,
        "requires_shutdown": True,
        "chosen_backup": name,
        "chosen_backup_ok": integrity,
        "backup_path": src,
        "live_db_path": live,
        "message": (
            "الاسترجاع يتم دون اتصال (Offline) فقط. أوقف الخادم أولاً، ثم استبدل ملف "
            "قاعدة البيانات يدوياً، ثم أعد تشغيل الخادم."
        ),
        "steps": [
            "أوقف خادم الـ API بالكامل.",
            f"احتفظ بنسخة من قاعدة البيانات الحالية: {live}",
            f"انسخ {src} إلى {live} (استبدال).",
            f"احذف {os.path.basename(live)}-wal و {os.path.basename(live)}-shm إن وُجدا "
            "بجانب قاعدة البيانات.",
            "أعد تشغيل خادم الـ API.",
        ],
    }

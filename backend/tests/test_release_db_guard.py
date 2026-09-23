"""Regression coverage for the release-only DB startup guard
(release_db_guard.py). Every fixture uses a disposable file under
pytest's own tmp_path - backend/release_runtime.db is never referenced.
"""
import hashlib
import os
import sys

import pytest
from sqlalchemy import create_engine

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models  # noqa: E402  (registers all ORM tables on Base.metadata)

import release_db_guard as guard  # noqa: E402


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _build_real_schema(path: str) -> None:
    """A) valid fixture built from the ACTUAL app.models schema - every
    table, not just the three core ones - so this proves the guard passes
    a genuine (if data-empty) optical_lens_app database."""
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()


# ------------------------------------------------------------------ A
def test_a_valid_real_schema_passes(tmp_path):
    db_path = str(tmp_path / "valid.db")
    _build_real_schema(db_path)

    result = guard.validate_release_db(db_path)

    assert result.ok is True
    assert result.reason is None


# ------------------------------------------------------------------ B
def test_b_missing_db_fails_and_creates_no_file(tmp_path):
    db_path = str(tmp_path / "does_not_exist.db")
    assert not os.path.exists(db_path)

    result = guard.validate_release_db(db_path)

    assert result.ok is False
    assert result.reason
    assert not os.path.exists(db_path), "validation must never create the missing file"


# ------------------------------------------------------------------ C
def test_c_zero_byte_db_fails(tmp_path):
    db_path = str(tmp_path / "zero_byte.db")
    open(db_path, "wb").close()

    result = guard.validate_release_db(db_path)

    assert result.ok is False
    assert result.reason


# ------------------------------------------------------------------ D
def test_d_corrupt_non_sqlite_db_fails(tmp_path):
    db_path = str(tmp_path / "corrupt.db")
    with open(db_path, "wb") as f:
        f.write(b"not a sqlite database, just garbage bytes\x00\x01\x02")

    result = guard.validate_release_db(db_path)

    assert result.ok is False
    assert result.reason


# ------------------------------------------------------------------ E
def test_e_valid_sqlite_with_no_application_schema_fails(tmp_path):
    db_path = str(tmp_path / "wrong_app.db")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as con:
        con.exec_driver_sql("CREATE TABLE unrelated_table (id INTEGER PRIMARY KEY)")
    engine.dispose()

    result = guard.validate_release_db(db_path)

    assert result.ok is False
    assert result.reason


# ------------------------------------------------------------------ F
def test_f_valid_sqlite_missing_one_core_table_fails(tmp_path):
    """companies + lens_models present, prescriptions missing."""
    db_path = str(tmp_path / "partial.db")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as con:
        con.exec_driver_sql(
            "CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT)"
        )
        con.exec_driver_sql(
            "CREATE TABLE lens_models (id INTEGER PRIMARY KEY, company_id INTEGER)"
        )
    engine.dispose()

    result = guard.validate_release_db(db_path)

    assert result.ok is False
    assert result.reason


# ------------------------------------------------------------------ G
def test_g_read_only_validation_does_not_modify_a_valid_db(tmp_path):
    db_path = str(tmp_path / "untouched.db")
    _build_real_schema(db_path)
    before_hash = _sha256(db_path)
    before_mtime = os.path.getmtime(db_path)

    result = guard.validate_release_db(db_path)

    assert result.ok is True
    assert _sha256(db_path) == before_hash
    assert os.path.getmtime(db_path) == before_mtime
    # no SQLite side files (-wal/-shm/-journal) were left behind either
    assert not os.path.exists(db_path + "-wal")
    assert not os.path.exists(db_path + "-shm")
    assert not os.path.exists(db_path + "-journal")


# ------------------------------------------------------------------ core-table evidence
def test_core_tables_are_the_minimal_documented_set():
    assert guard.CORE_TABLES == ("companies", "lens_models", "prescriptions")

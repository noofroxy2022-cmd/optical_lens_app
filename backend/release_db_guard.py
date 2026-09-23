"""Release-only, read-only startup validation for release_runtime.db.

Runs BEFORE app.main is ever imported and before uvicorn starts serving,
so a missing/invalid database can never be silently auto-created by
SQLite's/SQLAlchemy's default connect-and-create-on-first-query behavior
(confirmed present in app/database.py's default DATABASE_URL). Pure
stdlib sqlite3 only - no ORM/app import - so this module stays usable
even when release_runtime.db does not match app.models at all, and it
never performs migrations or touches business/catalog/matching code.

This validates SCHEMA IDENTITY only (this file is genuinely an
initialized optical_lens_app runtime database), never commercial DATA
(row counts, specific companies/products/prices) - see CORE_TABLES.
"""
from __future__ import annotations

import os
import sqlite3
from typing import NamedTuple, Optional

# The smallest set of tables that proves "this is an initialized
# optical_lens_app runtime database, not merely a valid empty SQLite
# file". All three are schema ROOTS with no dependency on catalog-ingest
# state, each one the direct target of a router already mounted in
# app.main:
#   - companies    -> companies.router; zero FK dependencies of its own;
#                     lens_models.company_id depends on it, so nothing
#                     in the catalog hierarchy can exist without it.
#   - lens_models   -> lens_models.router; every other catalog-side table
#                     (lens_variants, variant_pricing, power_ranges,
#                     coatings, catalogs, catalog_extractions) exists
#                     only to support rows in this table.
#   - prescriptions -> prescriptions.router, the entry point for the
#                     seller-facing search/match workflow; zero FK
#                     dependencies of its own.
# Every other application table is a leaf hanging off one of these three
# roots, so future schema additions/changes never require touching this
# guard. Presence is checked, not row count: a correctly migrated but
# data-empty database still passes - this guard proves schema identity,
# never commercial content.
CORE_TABLES = ("companies", "lens_models", "prescriptions")


class DbValidationResult(NamedTuple):
    ok: bool
    reason: Optional[str]  # short, human-readable; never a stack trace


def validate_release_db(db_path: str) -> DbValidationResult:
    """Read-only validation. Never creates, writes to, or migrates db_path.

    Opens the file with SQLite's URI read-only mode (mode=ro), which
    itself cannot create a file, in addition to the explicit existence
    check below - two independent guarantees against accidental creation.
    """
    if not os.path.isfile(db_path):
        return DbValidationResult(False, "قاعدة البيانات غير موجودة")

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return DbValidationResult(False, "تعذر فتح قاعدة البيانات")

    try:
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError:
            return DbValidationResult(False, "قاعدة البيانات تالفة")

        if not row or row[0] != "ok":
            return DbValidationResult(False, "قاعدة البيانات تالفة")

        try:
            existing = {
                r[0]
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        except sqlite3.DatabaseError:
            return DbValidationResult(False, "قاعدة البيانات تالفة")

        missing = [t for t in CORE_TABLES if t not in existing]
        if missing:
            return DbValidationResult(False, "قاعدة البيانات غير متوافقة مع هذا التطبيق")

        return DbValidationResult(True, None)
    finally:
        con.close()

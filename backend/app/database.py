"""
إعداد قاعدة البيانات.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


# V1.4.4: normal (no-override) startup uses the certified V1.4.3 release
# runtime DB - backend/release_runtime.db - never the historical
# optical_lens.db (kept on disk, untouched, as the pre-release archive) and
# never the dev-only v12_dev.db (which stays reachable only via an explicit
# DATABASE_URL override, e.g. .claude/launch.json's "backend" dev config).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./release_runtime.db")

engine = create_engine(DATABASE_URL)


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable SQLite foreign-key enforcement (OFF by default in SQLite).

    Without this, ON DELETE RESTRICT on the commercial-pricing FKs is ignored on
    the local SQLite database and historical VariantPricing could be deleted
    with its parent. No effect on PostgreSQL (listener not registered there).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


if engine.dialect.name == "sqlite":
    event.listen(engine, "connect", _set_sqlite_pragma)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

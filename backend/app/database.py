"""
إعداد قاعدة البيانات.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./optical_lens.db")

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

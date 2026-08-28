"""
إعداد قاعدة البيانات - PostgreSQL للإنتاج
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://optical:optical123@localhost:5432/optical_db")
# للتطوير: SQLite
DATABASE_URL = "sqlite:///./optical_lens.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

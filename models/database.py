"""Database connection management (SQLAlchemy + SQLite)"""

import os
import sqlite3
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def get_db_path():
    """Get database path based on environment (EC2 vs local)"""
    if os.path.exists("/home/ec2-user"):
        return "/home/ec2-user/app.db"
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, "app.db")


DATABASE_URL = f"sqlite:///{get_db_path()}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


@contextmanager
def get_session():
    """Context manager for SQLAlchemy sessions"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db():
    """Context manager for database connections"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database tables"""
    from . import organization, user, recording, sign, auth_token, api_key, model_history  # noqa: F401

    Base.metadata.create_all(bind=engine)

    print(f"✅ Database initialized at: {get_db_path()}")

"""Database engine and session management.

Uses synchronous SQLAlchemy since FastAPI runs synchronous endpoints in a 
threadpool and the background worker operates as a blocking loop. This 
avoids unnecessary async complexity while keeping operations easy to debug.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Automatically reconnects if Supabase drops idle connections
    pool_size=5,
    max_overflow=5,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Session:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI dependency for injecting database sessions into route handlers."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
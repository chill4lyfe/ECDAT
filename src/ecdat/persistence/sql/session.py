from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ecdat.settings import get_settings

settings = get_settings()
engine: Engine | None
SessionLocal: sessionmaker[Session] | None
try:
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
except (ModuleNotFoundError, ImportError):
    # Allows scanner/unit-test use without a PostgreSQL driver. Docker production image
    # installs psycopg and therefore enables durable persistence automatically.
    engine = None
    SessionLocal = None

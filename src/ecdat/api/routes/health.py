from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ecdat.persistence.sql.session import engine
from ecdat.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ecdat-api", "version": "1.0.0"}


@router.get("/health/ready")
async def readiness() -> dict[str, object]:
    settings = get_settings()
    checks: dict[str, dict[str, str]] = {}

    try:
        if engine is None:
            raise RuntimeError("PostgreSQL driver unavailable")
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except (SQLAlchemyError, RuntimeError) as exc:
        checks["postgres"] = {"status": "error", "detail": type(exc).__name__}

    try:
        from redis.asyncio import Redis
        redis = Redis.from_url(settings.redis_url)
        try:
            await redis.ping()
            checks["redis"] = {"status": "ok"}
        finally:
            await redis.aclose()
    except Exception as exc:
        checks["redis"] = {"status": "error", "detail": type(exc).__name__}

    try:
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        try:
            await driver.verify_connectivity()
            checks["neo4j"] = {"status": "ok"}
        finally:
            await driver.close()
    except Exception as exc:
        checks["neo4j"] = {"status": "error", "detail": type(exc).__name__}

    ready = all(item["status"] == "ok" for item in checks.values())
    return {"status": "ready" if ready else "degraded", "version": "1.0.0", "checks": checks}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ecdat.api.routes.auth import router as auth_router
from ecdat.api.routes.exports import router as exports_router
from ecdat.api.routes.health import router as health_router
from ecdat.api.routes.intake import router as intake_router
from ecdat.api.routes.migration import router as migration_router
from ecdat.api.routes.reports import router as reports_router
from ecdat.api.routes.risk import router as risk_router
from ecdat.api.routes.scanners import router as scanners_router
from ecdat.api.routes.scans import router as scans_router
from ecdat.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    app = FastAPI(
        title="ECDAT API",
        version="1.0.0",
        description="Enterprise cryptographic discovery, evidence-linked topology analysis, quantum-readiness scenarios, migration planning and reporting.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/v1")
    app.include_router(exports_router, prefix="/v1")
    app.include_router(scanners_router, prefix="/v1")
    app.include_router(scans_router, prefix="/v1")
    app.include_router(intake_router, prefix="/v1")
    app.include_router(migration_router, prefix="/v1")
    app.include_router(reports_router, prefix="/v1")
    app.include_router(risk_router, prefix="/v1")
    return app

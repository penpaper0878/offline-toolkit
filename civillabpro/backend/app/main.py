"""CivilLabPro OS API.

Each module contributes a router; this file only assembles them. The same app
serves the web deployment (PostgreSQL) and the offline desktop shell (SQLite).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.errors import install_handlers
from app.modules.dashboard.router import router as dashboard_router
from app.modules.identity.router import auth as auth_router
from app.modules.identity.router import users as users_router
from app.modules.projects.router import router as projects_router
from app.modules.structural.router import router as structural_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> Any:
    get_engine()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CivilLabPro OS API",
        version=__version__,
        description="Indian civil engineering operating system: platform services and code-compliant design engines.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Content-Disposition"])
    install_handlers(app)

    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/health", tags=["system"])
    def health() -> dict[str, Any]:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__, "database": get_engine().dialect.name, "environment": settings.env}

    for r in (auth_router, users_router, projects_router, structural_router, dashboard_router):
        v1.include_router(r)
    app.include_router(v1)
    return app


app = create_app()

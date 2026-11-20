"""CivilLabPro OS API.

Each module contributes a router; this file only assembles them. The same app
serves the web deployment (PostgreSQL) and the offline desktop shell (SQLite).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.errors import NotFound, install_handlers
from app.modules.dashboard.router import router as dashboard_router
from app.modules.identity.router import auth as auth_router
from app.modules.identity.router import users as users_router
from app.modules.projects.router import router as projects_router
from app.modules.structural.router import router as structural_router
from app.modules.transfer.router import router as transfer_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> Any:
    get_engine()
    yield


class _ImmutableAssets(StaticFiles):
    """Build output with content hashes in the file names: safe to cache for a year."""

    async def get_response(self, path: str, scope: Any) -> Any:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _serve_client(app: FastAPI, static_dir: Path) -> None:
    """Serve the built single-page client: real files as they are, every other path as index.html."""
    root = static_dir.resolve()
    if (root / "assets").is_dir():
        app.mount("/assets", _ImmutableAssets(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def client(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise NotFound("No such API endpoint.")
        target = (root / path).resolve()
        inside = target == root or root in target.parents  # never follow ../ out of the client folder
        file = target if path and inside and target.is_file() else root / "index.html"
        # index.html and the service worker must be revalidated so a new build is picked up at once.
        return FileResponse(file, headers={"Cache-Control": "no-cache"})


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

    for r in (auth_router, users_router, transfer_router, projects_router, structural_router, dashboard_router):
        v1.include_router(r)
    app.include_router(v1)
    if settings.static_dir is not None:
        if not (settings.static_dir / "index.html").is_file():
            raise RuntimeError(f"CLP_STATIC_DIR={settings.static_dir} has no index.html: build the web client first (npm run build).")
        _serve_client(app, settings.static_dir)
    return app


app = create_app()

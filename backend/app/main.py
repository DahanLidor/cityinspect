"""
CityInspect FastAPI application factory.
"""
from __future__ import annotations

import os
import pathlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.database import create_tables
from app.core.events import bus
from app.core.logging import get_logger, setup_logging
from app.core.security import decode_token
from app.routers import auth, detections, pipeline, stats, tickets, work_orders
from app.routers import admin_chat, people, whatsapp, workflow
from app.ws.hub import hub

settings = get_settings()
setup_logging(debug=settings.debug)
logger = get_logger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Routers ───────────────────────────────────────────────────────────────
    for router in [
        auth.router, detections.router, tickets.router, stats.router,
        work_orders.router, pipeline.router,
        people.router, workflow.router, whatsapp.router, admin_chat.router,
    ]:
        app.include_router(router)

    # ── Static uploads ────────────────────────────────────────────────────────
    @app.get("/uploads/{filename}")
    def serve_upload(filename: str) -> FileResponse:
        path = os.path.join(settings.upload_path, filename)
        if not os.path.exists(path):
            from fastapi import HTTPException
            raise HTTPException(404)
        return FileResponse(path)

    # ── Operational dashboard ─────────────────────────────────────────────────
    @app.get("/dashboard")
    def serve_dashboard() -> HTMLResponse:
        p = pathlib.Path(__file__).parent.parent / "dashboard.html"
        if p.exists():
            return HTMLResponse(content=p.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health")
    def health():
        return {"status": "healthy", "version": settings.version}

    # ── WebSocket ─────────────────────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket, token: str = ""):
        # Optional auth: if token provided, resolve role
        role = "viewer"
        user_id = None
        if token:
            username = decode_token(token)
            if username:
                role = "field_team"  # simplified; could look up DB role

        await hub.connect(ws, user_id=user_id, role=role)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(ws)

    # ── React SPA fallback ────────────────────────────────────────────────────
    frontend_build = pathlib.Path(__file__).parent.parent / "frontend_build"
    if frontend_build.exists():
        static_dir = frontend_build / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str) -> FileResponse:
            file = frontend_build / full_path
            if file.exists() and file.is_file():
                return FileResponse(str(file))
            index = frontend_build / "index.html"
            if index.exists():
                return FileResponse(str(index))
            from fastapi import HTTPException
            raise HTTPException(404, "Frontend not found")

    # ── Startup ───────────────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup() -> None:
        logger.info("Starting CityInspect", extra={"version": settings.version})
        await create_tables()
        from app.core.database import _async_session
        from app.seed import seed
        from app.services.people_engine import PeopleEngine
        async with _async_session() as db:
            await seed(db)
            # Sync contacts from YAML on startup
            engine = PeopleEngine(db)
            try:
                synced = await engine.sync_contacts("tel-aviv")
                logger.info("Synced %d contacts for tel-aviv", synced)
                await db.commit()
            except Exception as exc:
                logger.warning("Contact sync failed (non-fatal): %s", exc)
                await db.rollback()
        await bus.connect()
        await bus.start_listeners()
        logger.info("Startup complete")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await bus.stop()
        await bus.disconnect()
        logger.info("CityInspect shutdown complete")

    return app


app = create_app()

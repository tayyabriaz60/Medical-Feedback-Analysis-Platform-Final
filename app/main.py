"""
FastAPI application main entry point
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
import webbrowser
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.db import AsyncSessionLocal, init_db
from app.logging_config import get_logger, setup_logging
from app.middleware.logging import RequestLoggingMiddleware
from app.routers import analytics, feedback, health
from app.routers import auth as auth_router
from app.services.auth_service import ensure_admin_user, ensure_or_update_admin_user, get_secret_key
from app.sockets.events import sio
from app.utils.errors import APIError, api_error_handler, generic_error_handler

logger = get_logger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)


def _validate_configuration() -> None:
    """Ensure critical environment variables are set before startup."""
    get_secret_key()  # Raises if invalid
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL environment variable is required")
    if not os.getenv("GOOGLE_API_KEY"):
        logger.warning("GOOGLE_API_KEY missing – AI analysis will be disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    setup_logging()
    logger.info("Starting Medical Feedback Analysis Platform")
    _validate_configuration()

    await init_db()
    logger.info("Database initialized")

    try:
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if admin_email and admin_password:
            async with AsyncSessionLocal() as seed_session:
                # Smart admin management: create, update, or do nothing
                user, status = await ensure_or_update_admin_user(
                    seed_session, admin_email, admin_password, role="admin"
                )
                logger.info(f"Admin user {status}: {admin_email} (ID: {user.id})")
        else:
            logger.info("Admin bootstrap skipped - set ADMIN_EMAIL/ADMIN_PASSWORD to enable")
    except Exception as exc:  # pragma: no cover
        logger.exception("Admin bootstrap failed: %s", exc)

    _maybe_open_browser()

    yield

    logger.info("Application shutdown complete")


def _maybe_open_browser() -> None:
    if os.getenv("AUTO_OPEN_BROWSER", "0") != "1":
        return
    lock_path = os.path.join(tempfile.gettempdir(), "mfap_browser_open.lock")
    should_open = True
    if os.path.exists(lock_path):
        last_mtime = os.path.getmtime(lock_path)
        if (time.time() - last_mtime) < 120:
            should_open = False
    if should_open:
        with open(lock_path, "w", encoding="utf-8") as lock_file:
            lock_file.write(str(time.time()))
        port = os.getenv("PORT", "8000")
        url = f"http://localhost:{port}/"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        logger.info("Opening browser at %s", url)


app = FastAPI(
    title="Medical Feedback Analysis Platform",
    description="Backend API for analyzing medical feedback using Gemini AI",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration - allow specific origins
allowed_origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
    "https://deployment-18e3.onrender.com",  # Update with your actual Render URL
]

# Allow all origins in development, specific in production
if os.getenv("ENVIRONMENT", "production").lower() == "development":
    allowed_origins.append("*")

# Add middlewares (order matters - add logging first, then CORS)
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,  # Now safe with specific origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

app.include_router(feedback.router)
app.include_router(analytics.router)
app.include_router(auth_router.router)
app.include_router(health.router)

frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/staff", include_in_schema=False)
    async def serve_staff_login():
        staff_path = os.path.join(frontend_path, "staff_login.html")
        if os.path.exists(staff_path):
            return FileResponse(staff_path)
        return {"message": "Staff login page not found"}

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {
            "message": "Medical Feedback Analysis Platform API",
            "version": "1.0.0",
            "docs": "/docs",
        }

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon():
        icon_path = os.path.join(frontend_path, "favicon.ico")
        if os.path.exists(icon_path):
            return FileResponse(icon_path)
        return Response(status_code=204)
else:

    @app.get("/")
    async def root():
        return {
            "message": "Medical Feedback Analysis Platform API",
            "version": "1.0.0",
            "docs": "/docs",
        }


asgi_app = socketio.ASGIApp(sio, app)

__all__ = ["app", "asgi_app"]


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:asgi_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )


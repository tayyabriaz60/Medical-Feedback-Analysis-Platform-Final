"""
Health and diagnostics endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
import time


from app.db import AsyncSessionLocal, get_pool_stats, check_db_connection

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    """Return service and database health information."""
    db_connected = await check_db_connection()
    pool_stats = get_pool_stats()

    return {
        "service": "medical-feedback-api",
        "status": "healthy" if db_connected else "degraded",
        "database": {"connected": db_connected, "pool": pool_stats},
    }


@router.get("/ping")
async def ping():
    """Simple ping endpoint with DB latency measurement."""
    latency_ms = None
    try:
        start = time.perf_counter()
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar()
        latency_ms = (time.perf_counter() - start) * 1000
    except Exception:
        latency_ms = None
    return {"status": "ok", "db_latency_ms": latency_ms}



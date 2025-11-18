"""
Analytics API routes
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.feedback_service import FeedbackService
from app.deps import require_role

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", dependencies=[Depends(require_role("admin", "staff"))])
async def get_analytics_summary(
    db: AsyncSession = Depends(get_db)
):
    """Get analytics summary"""
    from app.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Fetching analytics summary")
    try:
        summary = await FeedbackService.get_analytics_summary(db)
        return summary
    except Exception as e:
        logger.exception(f"Failed to fetch analytics summary: {e}")
        # Return empty summary instead of crashing
        return {
            "total_feedback": 0,
            "by_status": {},
            "by_sentiment": {},
            "by_urgency": {},
            "by_department": {},
            "average_rating": 0.0
        }


@router.get("/trends", dependencies=[Depends(require_role("admin", "staff"))])
async def get_analytics_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days for trends"),
    db: AsyncSession = Depends(get_db)
):
    """Get analytics trends"""
    from app.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info(f"Fetching analytics trends for {days} days")
    try:
        trends = await FeedbackService.get_analytics_trends(db, days=days)
        return trends
    except Exception as e:
        logger.exception(f"Failed to fetch analytics trends: {e}")
        # Return empty trends instead of crashing
        return {
            "daily_feedback": [],
            "sentiment_trends": [],
            "urgency_trends": []
        }


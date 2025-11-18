"""
Business logic for handling feedback, actions, and analytics.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.logging_config import get_logger
from app.models.actions import Action
from app.models.analysis import Analysis
from app.models.feedback import Feedback
from app.services.gemini_service import gemini_service
from app.utils.helpers import format_datetime

logger = get_logger(__name__)


class FeedbackService:
    """Service encapsulating feedback business logic."""

    @staticmethod
    async def create_feedback(
        db: AsyncSession,
        patient_name: Optional[str],
        visit_date: datetime,
        department: str,
        doctor_name: Optional[str],
        feedback_text: str,
        rating: int,
    ) -> Feedback:
        feedback = Feedback(
            patient_name=patient_name,
            visit_date=visit_date,
            department=department,
            doctor_name=doctor_name,
            feedback_text=feedback_text,
            rating=rating,
            status="pending_analysis",
        )
        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)
        logger.info("Feedback created: id=%s department=%s", feedback.id, department)
        return feedback

    @staticmethod
    async def get_feedback_by_id(db: AsyncSession, feedback_id: int) -> Optional[Feedback]:
        result = await db.execute(
            select(Feedback)
            .options(selectinload(Feedback.analysis), selectinload(Feedback.actions))
            .where(Feedback.id == feedback_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_feedback(
        db: AsyncSession,
        department: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        priority: Optional[str] = None,
        sentiment: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Feedback], int]:
        query = select(Feedback)
        count_query = select(func.count(Feedback.id))

        conditions = []
        if department:
            conditions.append(Feedback.department == department)
        if start_date:
            conditions.append(Feedback.visit_date >= start_date)
        if end_date:
            conditions.append(Feedback.visit_date <= end_date)
        if status:
            conditions.append(Feedback.status == status)

        if priority or sentiment or category:
            query = query.join(Analysis, Feedback.id == Analysis.feedback_id)
            count_query = count_query.select_from(Feedback).join(Analysis)
            if priority:
                conditions.append(Analysis.urgency == priority)
            if sentiment:
                conditions.append(Analysis.sentiment == sentiment)
            if category:
                conditions.append(
                    or_(
                        Analysis.primary_category == category,
                        Analysis.subcategories.contains([category]),
                    )
                )

        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        result = await db.execute(count_query)
        total = int(result.scalar() or 0)

        query = (
            query.options(selectinload(Feedback.analysis))
            .order_by(Feedback.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await db.execute(query)
        feedbacks = rows.scalars().unique().all()
        return feedbacks, total

    @staticmethod
    async def analyze_feedback_async(db: AsyncSession, feedback_id: int) -> Optional[Analysis]:
        feedback = await FeedbackService.get_feedback_by_id(db, feedback_id)
        if not feedback:
            logger.warning("Feedback %s not found for analysis", feedback_id)
            return None

        if feedback.analysis:
            return feedback.analysis

        analysis_result = await gemini_service.analyze_feedback_with_retry(
            feedback_text=feedback.feedback_text,
            department=feedback.department,
            doctor_name=feedback.doctor_name,
            visit_date=format_datetime(feedback.visit_date),
            rating=feedback.rating,
        )

        if "error" in analysis_result:
            logger.error(
                "Analysis failed for feedback %s: %s", feedback_id, analysis_result["error"]
            )
            return None

        analysis = Analysis(
            feedback_id=feedback_id,
            sentiment=analysis_result.get("sentiment", "neutral"),
            confidence_score=analysis_result.get("confidence_score", 0.5),
            emotions=analysis_result.get("emotions", []),
            urgency=analysis_result.get("urgency", "low"),
            urgency_reason=analysis_result.get("urgency_reason"),
            urgency_flags=analysis_result.get("urgency_flags", []),
            primary_category=analysis_result.get("primary_category"),
            subcategories=analysis_result.get("subcategories", []),
            medical_concerns=analysis_result.get("medical_concerns"),
            actionable_insights=analysis_result.get("actionable_insights"),
            key_points=analysis_result.get("key_points", []),
        )
        db.add(analysis)
        feedback.status = "reviewed"
        await db.commit()
        await db.refresh(analysis)
        logger.info(
            "Analysis saved for feedback %s sentiment=%s urgency=%s",
            feedback_id,
            analysis.sentiment,
            analysis.urgency,
        )
        return analysis

    @staticmethod
    async def update_feedback_status(
        db: AsyncSession,
        feedback_id: int,
        status: str,
        staff_note: Optional[str] = None,
        assigned_department: Optional[str] = None,
    ) -> Optional[Feedback]:
        feedback = await FeedbackService.get_feedback_by_id(db, feedback_id)
        if not feedback:
            return None

        feedback.status = status
        action = Action(
            feedback_id=feedback_id,
            status=status,
            staff_note=staff_note,
            assigned_department=assigned_department,
        )
        db.add(action)
        await db.commit()
        await db.refresh(feedback)
        logger.info("Feedback %s status updated to %s", feedback_id, status)
        return feedback

    @staticmethod
    async def mark_analysis_failed(db: AsyncSession, feedback_id: int) -> None:
        await db.execute(
            update(Feedback).where(Feedback.id == feedback_id).values(status="analysis_failed")
        )
        await db.commit()
        logger.error("Feedback %s marked as analysis_failed", feedback_id)

    @staticmethod
    async def get_analytics_summary(db: AsyncSession) -> Dict[str, Any]:
        total_result = await db.execute(select(func.count(Feedback.id)))
        total_feedback = int(total_result.scalar() or 0)

        sentiment_query = select(Analysis.sentiment, func.count(Analysis.id)).group_by(
            Analysis.sentiment
        )
        sentiment_result = await db.execute(sentiment_query)
        sentiment_breakdown = {row[0]: row[1] for row in sentiment_result.fetchall()}

        rating_query = (
            select(
                Feedback.department,
                func.avg(Feedback.rating).label("avg_rating"),
                func.count(Feedback.id).label("count"),
            )
            .group_by(Feedback.department)
        )
        rating_result = await db.execute(rating_query)
        department_ratings = [
            {
                "department": row.department,
                "average_rating": float(row.avg_rating),
                "feedback_count": row.count,
            }
            for row in rating_result
        ]

        category_query = (
            select(Analysis.primary_category, func.count(Analysis.id).label("count"))
            .where(Analysis.primary_category.isnot(None))
            .group_by(Analysis.primary_category)
            .order_by(func.count(Analysis.id).desc())
            .limit(10)
        )
        category_result = await db.execute(category_query)
        top_issues = [
            {"category": row.primary_category, "count": row.count} for row in category_result
        ]

        return {
            "total_feedback": total_feedback,
            "sentiment_breakdown": sentiment_breakdown,
            "department_ratings": department_ratings,
            "top_issues": top_issues,
        }

    @staticmethod
    async def get_analytics_trends(db: AsyncSession, days: int = 30) -> Dict[str, Any]:
        start_date = datetime.now() - timedelta(days=days)

        sentiment_query = (
            select(
                func.date(Feedback.created_at).label("date"),
                Analysis.sentiment,
                func.count(Analysis.id).label("count"),
            )
            .join(Analysis)
            .where(Feedback.created_at >= start_date)
            .group_by(func.date(Feedback.created_at), Analysis.sentiment)
            .order_by(func.date(Feedback.created_at))
        )
        sentiment_result = await db.execute(sentiment_query)
        sentiment_trends: Dict[str, Dict[str, int]] = {}
        for row in sentiment_result:
            date_str = str(row.date)
            sentiment_trends.setdefault(date_str, {})[row.sentiment] = row.count

        category_query = (
            select(
                func.date(Feedback.created_at).label("date"),
                Analysis.primary_category,
                func.count(Analysis.id).label("count"),
            )
            .join(Analysis)
            .where(Feedback.created_at >= start_date, Analysis.primary_category.isnot(None))
            .group_by(func.date(Feedback.created_at), Analysis.primary_category)
            .order_by(func.date(Feedback.created_at))
        )
        category_result = await db.execute(category_query)
        category_trends: Dict[str, Dict[str, int]] = {}
        for row in category_result:
            date_str = str(row.date)
            category_trends.setdefault(date_str, {})[row.primary_category] = row.count

        dept_query = (
            select(
                Feedback.department,
                func.avg(Feedback.rating).label("avg_rating"),
                func.count(Feedback.id).label("total_feedback"),
                func.sum(case((Analysis.urgency == "critical", 1), else_=0)).label(
                    "critical_count"
                ),
            )
            .outerjoin(Analysis)
            .where(Feedback.created_at >= start_date)
            .group_by(Feedback.department)
        )
        dept_result = await db.execute(dept_query)
        department_performance = [
            {
                "department": row.department,
                "average_rating": float(row.avg_rating or 0),
                "total_feedback": row.total_feedback,
                "critical_feedback_count": row.critical_count or 0,
            }
            for row in dept_result
        ]

        return {
            "sentiment_trends": sentiment_trends,
            "category_trends": category_trends,
            "department_performance": department_performance,
        }

    @staticmethod
    async def retry_failed_analyses(db: AsyncSession, max_retries: int = 3) -> int:
        failed_query = select(Feedback).where(Feedback.status == "analysis_failed")
        result = await db.execute(failed_query)
        feedbacks = result.scalars().all()
        retried = 0
        for feedback in feedbacks[:max_retries]:
            analysis = await FeedbackService.analyze_feedback_async(db, feedback.id)
            if analysis:
                feedback.status = "reviewed"
                retried += 1
                logger.info("Successfully retried analysis for feedback %s", feedback.id)
        await db.commit()
        return retried


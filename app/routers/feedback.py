"""
Feedback API routes
"""
from typing import Iterator, List, Optional
from datetime import datetime
import csv
import io

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, get_db
from app.logging_config import get_logger
from app.services.feedback_service import FeedbackService
from app.utils.helpers import validate_rating
from app.deps import require_role
from app.sockets.events import emit_new_feedback, emit_urgent_alert, emit_analysis_complete

# Import limiter from main app
try:
    from app.main import limiter
except ImportError:
    # Fallback if imported before limiter setup
    limiter = None

logger = get_logger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])


# Pydantic models
class FeedbackCreate(BaseModel):
    patient_name: Optional[str] = None
    visit_date: datetime
    department: str
    doctor_name: Optional[str] = None
    feedback_text: str = Field(..., min_length=10)
    rating: int = Field(..., ge=1, le=5)
    
    @validator('rating')
    def validate_rating(cls, v):
        if not validate_rating(v):
            raise ValueError('Rating must be between 1 and 5')
        return v


class FeedbackUpdate(BaseModel):
    status: str = Field(..., pattern="^(reviewed|in_progress|resolved)$")
    staff_note: Optional[str] = None
    assigned_department: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    patient_name: Optional[str]
    visit_date: datetime
    department: str
    doctor_name: Optional[str]
    feedback_text: str
    rating: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class AnalysisResponse(BaseModel):
    id: int
    feedback_id: int
    sentiment: str
    confidence_score: float
    emotions: Optional[List[str]]
    urgency: str
    urgency_reason: Optional[str]
    urgency_flags: Optional[List[str]]
    primary_category: Optional[str]
    subcategories: Optional[List[str]]
    medical_concerns: Optional[dict]
    actionable_insights: Optional[str]
    key_points: Optional[List[str]]
    
    class Config:
        from_attributes = True


class FeedbackDetailResponse(FeedbackResponse):
    analysis: Optional[AnalysisResponse] = None
    actions: Optional[List[dict]] = None


@router.post("", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    request: Request,
    feedback_data: FeedbackCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Submit new feedback"""
    try:
        feedback = await FeedbackService.create_feedback(
            db=db,
            patient_name=feedback_data.patient_name,
            visit_date=feedback_data.visit_date,
            department=feedback_data.department,
            doctor_name=feedback_data.doctor_name,
            feedback_text=feedback_data.feedback_text,
            rating=feedback_data.rating
        )
        
        # Emit new feedback event
        await emit_new_feedback(feedback)
        
        # Trigger background analysis
        background_tasks.add_task(
            analyze_feedback_background,
            feedback_id=feedback.id,
        )
        
        return feedback
        
    except Exception as e:
        logger.exception("Failed to create feedback")
        raise HTTPException(status_code=500, detail="Error creating feedback")


async def analyze_feedback_background(feedback_id: int):
    """Background task for analyzing feedback"""
    async with AsyncSessionLocal() as background_session:
        try:
            logger.info("Starting AI analysis for feedback %s", feedback_id)
            analysis = await FeedbackService.analyze_feedback_async(background_session, feedback_id)
            if analysis:
                await emit_analysis_complete(feedback_id, analysis)
                if analysis.urgency == "critical":
                    feedback = await FeedbackService.get_feedback_by_id(background_session, feedback_id)
                    if feedback:
                        await emit_urgent_alert(feedback, analysis)
            else:
                await FeedbackService.mark_analysis_failed(background_session, feedback_id)
                logger.error("Analysis failed for feedback %s", feedback_id)
        except Exception as exc:  # pragma: no cover
            logger.exception("Background analysis crashed for feedback %s", feedback_id)
            await FeedbackService.mark_analysis_failed(background_session, feedback_id)


@router.get("/all", response_model=dict, dependencies=[Depends(require_role("admin", "staff"))])
async def get_all_feedback(
    department: Optional[str] = Query(None, description="Filter by department"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    priority: Optional[str] = Query(None, description="Filter by urgency (critical/high/medium/low)"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db)
):
    """Get all feedback with filters"""
    logger.info("Fetching all feedback with filters")
    try:
        feedbacks, total = await FeedbackService.get_all_feedback(
            db=db,
            department=department,
            start_date=start_date,
            end_date=end_date,
            priority=priority,
            sentiment=sentiment,
            category=category,
            status=status,
            limit=limit,
            offset=offset
        )
        
        # Convert to response format
        feedback_list = []
        for feedback in feedbacks:
            try:
                feedback_dict = {
                    "id": feedback.id,
                    "patient_name": feedback.patient_name,
                    "visit_date": feedback.visit_date.isoformat() if feedback.visit_date else None,
                    "department": feedback.department,
                    "doctor_name": feedback.doctor_name,
                    "feedback_text": feedback.feedback_text,
                    "rating": feedback.rating,
                    "status": feedback.status,
                    "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
                    "urgency": feedback.analysis.urgency if feedback.analysis else None,
                    "sentiment": feedback.analysis.sentiment if feedback.analysis else None,
                    "primary_category": feedback.analysis.primary_category if feedback.analysis else None,
                    "analysis_status": "completed" if feedback.analysis else "pending"
                }
                feedback_list.append(feedback_dict)
            except Exception:
                # Skip problematic feedback items
                logger.exception("Error processing feedback %s", feedback.id)
                continue
        
        response = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "feedbacks": feedback_list
        }
        
        # CSV export
        if format == "csv":
            return StreamingResponse(
                generate_feedback_csv(feedback_list),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=feedback_export.csv"},
            )
        
        return response
        
    except Exception as e:
        logger.exception(f"Failed to fetch feedback: {e}")
        # Return empty response instead of crashing
        return {
            "total": 0,
            "limit": limit,
            "offset": offset,
            "feedbacks": []
        }


@router.get("/urgent", response_model=dict, dependencies=[Depends(require_role("admin", "staff"))])
async def get_urgent_feedback(
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """Get all urgent/critical feedback"""
    logger.info("Fetching urgent feedback")
    try:
        feedbacks, total = await FeedbackService.get_all_feedback(
            db=db,
            priority="critical",
            limit=limit,
            offset=0
        )
        
        feedback_list = []
        for feedback in feedbacks:
            try:
                feedback_dict = {
                    "id": feedback.id,
                    "patient_name": feedback.patient_name,
                    "visit_date": feedback.visit_date.isoformat() if feedback.visit_date else None,
                    "department": feedback.department,
                    "doctor_name": feedback.doctor_name,
                    "feedback_text": feedback.feedback_text,
                    "rating": feedback.rating,
                    "status": feedback.status,
                    "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
                    "urgency": feedback.analysis.urgency if feedback.analysis else None,
                    "urgency_reason": feedback.analysis.urgency_reason if feedback.analysis else None,
                    "urgency_flags": feedback.analysis.urgency_flags if feedback.analysis else None,
                    "sentiment": feedback.analysis.sentiment if feedback.analysis else None,
                    "primary_category": feedback.analysis.primary_category if feedback.analysis else None,
                    "actionable_insights": feedback.analysis.actionable_insights if feedback.analysis else None
                }
                feedback_list.append(feedback_dict)
            except Exception:
                logger.exception("Error processing urgent feedback %s", feedback.id)
                continue
        
        return {
            "total": total,
            "urgent_feedbacks": feedback_list
        }
    except Exception as e:
        logger.exception(f"Failed to fetch urgent feedback: {e}")
        # Return empty response instead of crashing
        return {
            "total": 0,
            "urgent_feedbacks": []
        }


@router.get("/{feedback_id}", response_model=FeedbackDetailResponse, dependencies=[Depends(require_role("admin", "staff"))])
async def get_feedback(
    feedback_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get single feedback with full analysis"""
    feedback = await FeedbackService.get_feedback_by_id(db, feedback_id)
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    # Convert to response
    response_data = {
        "id": feedback.id,
        "patient_name": feedback.patient_name,
        "visit_date": feedback.visit_date,
        "department": feedback.department,
        "doctor_name": feedback.doctor_name,
        "feedback_text": feedback.feedback_text,
        "rating": feedback.rating,
        "status": feedback.status,
        "created_at": feedback.created_at,
        "analysis": None,
        "actions": None
    }
    
    if feedback.analysis:
        response_data["analysis"] = {
            "id": feedback.analysis.id,
            "feedback_id": feedback.analysis.feedback_id,
            "sentiment": feedback.analysis.sentiment,
            "confidence_score": feedback.analysis.confidence_score,
            "emotions": feedback.analysis.emotions,
            "urgency": feedback.analysis.urgency,
            "urgency_reason": feedback.analysis.urgency_reason,
            "urgency_flags": feedback.analysis.urgency_flags,
            "primary_category": feedback.analysis.primary_category,
            "subcategories": feedback.analysis.subcategories,
            "medical_concerns": feedback.analysis.medical_concerns,
            "actionable_insights": feedback.analysis.actionable_insights,
            "key_points": feedback.analysis.key_points
        }
    
    if feedback.actions:
        response_data["actions"] = [
            {
                "id": action.id,
                "status": action.status,
                "staff_note": action.staff_note,
                "assigned_department": action.assigned_department,
                "created_at": action.created_at.isoformat() if action.created_at else None
            }
            for action in feedback.actions
        ]
    
    return response_data


@router.post("/{feedback_id}/update", response_model=FeedbackResponse, dependencies=[Depends(require_role("admin", "staff"))])
async def update_feedback(
    feedback_id: int,
    update_data: FeedbackUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update feedback status and add staff notes"""
    feedback = await FeedbackService.update_feedback_status(
        db=db,
        feedback_id=feedback_id,
        status=update_data.status,
        staff_note=update_data.staff_note,
        assigned_department=update_data.assigned_department
    )
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    return feedback


@router.post("/{feedback_id}/retry-analysis", response_model=dict, dependencies=[Depends(require_role("admin", "staff"))])
async def retry_analysis(
    feedback_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Retry AI analysis for a feedback that failed"""
    feedback = await FeedbackService.get_feedback_by_id(db, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    # Reset status if it was analysis_failed
    if feedback.status == "analysis_failed":
        feedback.status = "pending_analysis"
        await db.commit()
    
    # Trigger background analysis
    background_tasks.add_task(
        analyze_feedback_background,
        feedback_id=feedback_id,
    )
    
    return {"message": "Analysis retry initiated", "feedback_id": feedback_id}


def generate_feedback_csv(feedbacks: List[dict]) -> Iterator[str]:
    """Stream feedback rows as CSV."""
    buffer = io.StringIO()
    fieldnames = [
        "id",
        "patient_name",
        "visit_date",
        "department",
        "doctor_name",
        "feedback_text",
        "rating",
        "status",
        "sentiment",
        "urgency",
        "primary_category",
        "created_at",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for item in feedbacks:
        writer.writerow({
            "id": item.get("id"),
            "patient_name": item.get("patient_name") or "",
            "visit_date": item.get("visit_date") or "",
            "department": item.get("department") or "",
            "doctor_name": item.get("doctor_name") or "",
            "feedback_text": item.get("feedback_text") or "",
            "rating": item.get("rating"),
            "status": item.get("status") or "",
            "sentiment": item.get("sentiment") or "",
            "urgency": item.get("urgency") or "",
            "primary_category": item.get("primary_category") or "",
            "created_at": item.get("created_at") or "",
        })
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


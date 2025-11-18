"""
Socket.IO event handlers for real-time alerts.
"""
from __future__ import annotations

from typing import Dict

import socketio
from jose import JWTError, jwt

from app.logging_config import get_logger
from app.models.analysis import Analysis
from app.models.feedback import Feedback
from app.services.auth_service import get_secret_key

logger = get_logger(__name__)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

connected_clients: set[str] = set()
STAFF_ROOM = "staff_room"


def _extract_token(auth_payload: Dict) -> str | None:
    if not isinstance(auth_payload, dict):
        return None
    bearer = auth_payload.get("token") or auth_payload.get("Authorization")
    if bearer and bearer.lower().startswith("bearer "):
        return bearer.split(" ", 1)[1]
    return None


@sio.event
async def connect(sid, environ, auth):
    token = _extract_token(auth)
    try:
        if token:
            payload = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
            role = payload.get("role")
            if role in ("admin", "staff"):
                await sio.enter_room(sid, STAFF_ROOM)
                connected_clients.add(sid)
                logger.info("Socket connected: %s role=%s", sid, role)
                await sio.emit("connected", {"message": "Connected to staff updates"}, room=sid)
                return
    except JWTError:
        logger.warning("Invalid Socket.IO token for %s", sid)
    await sio.disconnect(sid)


@sio.event
async def disconnect(sid):
    connected_clients.discard(sid)
    logger.info("Socket disconnected: %s", sid)


@sio.event
async def request_updates(sid, data):
    await sio.emit("updates_enabled", {"message": "Real-time updates enabled"}, room=sid)


@sio.event
async def staff_action(sid, data):
    feedback_id = data.get("feedback_id")
    action = data.get("action")
    await sio.emit(
        "staff_action_update",
        {"feedback_id": feedback_id, "action": action, "staff_id": sid},
        room=STAFF_ROOM,
    )


async def emit_new_feedback(feedback: Feedback):
    feedback_data = {
        "id": feedback.id,
        "patient_name": feedback.patient_name,
        "department": feedback.department,
        "rating": feedback.rating,
        "status": feedback.status,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        "preview": feedback.feedback_text[:100] + "..."
        if len(feedback.feedback_text) > 100
        else feedback.feedback_text,
    }
    await sio.emit("new_feedback", feedback_data, room=STAFF_ROOM)
    logger.debug("Emitted new_feedback for %s", feedback.id)


async def emit_urgent_alert(feedback: Feedback, analysis: Analysis):
    alert_data = {
        "feedback_id": feedback.id,
        "patient_name": feedback.patient_name,
        "department": feedback.department,
        "urgency": analysis.urgency,
        "urgency_reason": analysis.urgency_reason,
        "urgency_flags": analysis.urgency_flags,
        "sentiment": analysis.sentiment,
        "primary_category": analysis.primary_category,
        "feedback_preview": feedback.feedback_text[:200] + "..."
        if len(feedback.feedback_text) > 200
        else feedback.feedback_text,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }
    await sio.emit("urgent_alert", alert_data, room=STAFF_ROOM)
    logger.warning("Emitted urgent alert for feedback %s", feedback.id)


async def emit_analysis_complete(feedback_id: int, analysis: Analysis):
    analysis_data = {
        "feedback_id": feedback_id,
        "sentiment": analysis.sentiment,
        "urgency": analysis.urgency,
        "primary_category": analysis.primary_category,
        "confidence_score": analysis.confidence_score,
    }
    await sio.emit("analysis_complete", analysis_data, room=STAFF_ROOM)
    logger.debug("Emitted analysis_complete for %s", feedback_id)


async def emit_dashboard_stats_update(stats: dict):
    await sio.emit("dashboard_stats_update", stats, room=STAFF_ROOM)
    logger.debug("Emitted dashboard stats update")


"""
Async Gemini AI service for analyzing medical feedback.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from app.logging_config import get_logger
from app.utils.helpers import (
    extract_categories,
    extract_medical_concerns,
    extract_urgency_flags,
    extract_urgency_level,
    extract_urgency_reason,
    parse_json_safely,
)
from app.utils.prompts import get_analysis_prompt

load_dotenv()
logger = get_logger(__name__)


class GeminiService:
    """Service for interacting with Gemini AI via HTTPx with Circuit Breaker Pattern."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.base_url = os.getenv(
            "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        )
        # Model name should be just the model identifier, not "models/..."
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.timeout = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))
        
        # Circuit breaker state
        self.failure_count = 0
        self.circuit_open_until = None
        self.max_failures_before_open = 5
        self.circuit_open_duration = 60  # seconds

    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open (service temporarily unavailable)."""
        if self.circuit_open_until and time.time() < self.circuit_open_until:
            return True
        if self.circuit_open_until and time.time() >= self.circuit_open_until:
            # Circuit reset, log it
            logger.info("Circuit breaker reset - attempting service recovery")
            self.circuit_open_until = None
            self.failure_count = 0
        return False

    def record_success(self) -> None:
        """Record successful call - reset failure count."""
        if self.failure_count > 0:
            logger.info(f"Gemini API success - resetting failure count from {self.failure_count}")
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record failed call - increment failure count and open circuit if needed."""
        self.failure_count += 1
        logger.warning(f"Gemini API failure recorded ({self.failure_count}/{self.max_failures_before_open})")
        
        if self.failure_count >= self.max_failures_before_open:
            self.circuit_open_until = time.time() + self.circuit_open_duration
            logger.error(
                f"Circuit breaker OPEN - Gemini API temporarily unavailable for {self.circuit_open_duration}s"
            )

    async def analyze_feedback(
        self,
        feedback_text: str,
        department: str,
        doctor_name: Optional[str] = None,
        visit_date: Optional[str] = None,
        rating: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Analyze feedback using Gemini AI."""
        if not self.api_key:
            logger.error("Gemini API key missing")
            return {"error": "Gemini API not configured. Set GOOGLE_API_KEY."}

        prompt = get_analysis_prompt(
            feedback_text=feedback_text,
            department=department,
            doctor_name=doctor_name,
            visit_date=visit_date,
            rating=rating,
        )

        # Construct URL: base_url/models/{model}:generateContent
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": [],
        }

        try:
            logger.debug("Calling Gemini API: %s (model: %s)", url, self.model)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            error_text = exc.response.text[:500] if exc.response.text else "No error text"
            logger.error(
                "Gemini HTTP error %s for URL %s: %s",
                status,
                url,
                error_text
            )
            if status == 429:
                retry_after = int(exc.response.headers.get("Retry-After", "60"))
                return {"error": "Gemini rate limit exceeded", "retry_after": retry_after}
            return {"error": f"Gemini API error ({status})", "retry": status >= 500}
        except httpx.TimeoutException:
            logger.error("Gemini request timed out after %s seconds", self.timeout)
            return {"error": "Gemini API timeout", "retry": True}
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected Gemini error: %s", exc)
            return {"error": "Unexpected Gemini error", "retry": True}

        response_text = self._extract_text(data)
        if not response_text:
            return {"error": "No analysis returned from Gemini"}

        analysis_data = parse_json_safely(response_text)
        if not analysis_data:
            logger.warning("Failed to parse Gemini response: %s", response_text[:200])
            return {"error": "Failed to parse Gemini response", "retry": False}

        result = {
            "sentiment": analysis_data.get("sentiment", "neutral"),
            "confidence_score": float(analysis_data.get("confidence_score", 0.5)),
            "emotions": analysis_data.get("emotions", []),
            "urgency": extract_urgency_level(analysis_data.get("urgency", {})),
            "urgency_reason": extract_urgency_reason(analysis_data.get("urgency", {})),
            "urgency_flags": extract_urgency_flags(analysis_data.get("urgency", {})),
            "primary_category": None,
            "subcategories": [],
            "medical_concerns": None,
            "actionable_insights": analysis_data.get("actionable_insights", ""),
            "key_points": analysis_data.get("key_points", []),
        }

        primary, subcategories = extract_categories(analysis_data.get("categories", {}))
        result["primary_category"] = primary
        result["subcategories"] = subcategories
        result["medical_concerns"] = extract_medical_concerns(
            analysis_data.get("medical_concerns", {})
        )

        logger.info(
            "Gemini analysis complete: sentiment=%s urgency=%s",
            result["sentiment"],
            result["urgency"],
        )
        return result

    async def analyze_feedback_with_retry(
        self,
        feedback_text: str,
        department: str,
        doctor_name: Optional[str] = None,
        visit_date: Optional[str] = None,
        rating: Optional[int] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Analyze feedback with exponential backoff retries and circuit breaker."""
        # Check if circuit is open
        if self.is_circuit_open():
            return {
                "error": "Gemini API temporarily unavailable (circuit breaker open)",
                "retry": False,
            }
        
        last_result: Dict[str, Any] = {"error": "Unknown error"}
        for attempt in range(max_retries):
            result = await self.analyze_feedback(
                feedback_text=feedback_text,
                department=department,
                doctor_name=doctor_name,
                visit_date=visit_date,
                rating=rating,
            )
            if "error" not in result:
                self.record_success()
                return result
            
            last_result = result
            
            # Non-retryable errors
            if not result.get("retry", False) and "retry_after" not in result:
                self.record_failure()
                return result
            
            # Calculate wait time with exponential backoff (capped at 30 seconds)
            wait_time = result.get("retry_after") or min(2**attempt, 30)
            logger.info(f"Retrying Gemini analysis (attempt {attempt + 1}/{max_retries}) after {wait_time}s")
            await asyncio.sleep(wait_time)
        
        # All retries exhausted
        self.record_failure()
        logger.error(f"Gemini analysis failed after {max_retries} attempts")
        return last_result

    @staticmethod
    def _extract_text(response: Dict[str, Any]) -> Optional[str]:
        candidates = response.get("candidates") or []
        if not candidates:
            return None
        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )
        if not parts:
            return None
        return parts[0].get("text")


gemini_service = GeminiService()


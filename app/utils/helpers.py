"""
Helper functions for validation, formatting, and error handling
"""
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import json
import re


def validate_rating(rating: int) -> bool:
    """Validate rating is between 1 and 5"""
    return 1 <= rating <= 5


def format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime to ISO string"""
    if dt is None:
        return None
    return dt.isoformat()


def parse_json_safely(json_str: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON string, handling common issues"""
    try:
        # Remove markdown code blocks if present
        json_str = re.sub(r'```json\s*', '', json_str)
        json_str = re.sub(r'```\s*', '', json_str)
        json_str = json_str.strip()
        
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def extract_urgency_level(urgency_data: Dict[str, Any]) -> str:
    """Extract urgency level from analysis data"""
    if isinstance(urgency_data, dict):
        return urgency_data.get("level", "low")
    return str(urgency_data) if urgency_data else "low"


def extract_urgency_reason(urgency_data: Dict[str, Any]) -> Optional[str]:
    """Extract urgency reason from analysis data"""
    if isinstance(urgency_data, dict):
        return urgency_data.get("reason")
    return None


def extract_urgency_flags(urgency_data: Dict[str, Any]) -> Optional[List[str]]:
    """Extract urgency flags from analysis data"""
    if isinstance(urgency_data, dict):
        flags = urgency_data.get("flags", [])
        return flags if isinstance(flags, list) else []
    return []


def extract_categories(categories_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[List[str]]]:
    """Extract primary category and subcategories"""
    if isinstance(categories_data, dict):
        primary = categories_data.get("primary")
        subcategories = categories_data.get("subcategories", [])
        if not isinstance(subcategories, list):
            subcategories = []
        return primary, subcategories
    return None, []


def extract_medical_concerns(concerns_data: Dict[str, Any]) -> Optional[Dict[str, List[str]]]:
    """Extract medical concerns structure"""
    if isinstance(concerns_data, dict):
        return {
            "symptoms": concerns_data.get("symptoms", []),
            "complications": concerns_data.get("complications", []),
            "treatment_side_effects": concerns_data.get("treatment_side_effects", []),
            "medication_issues": concerns_data.get("medication_issues", [])
        }
    return None


def is_critical_urgency(urgency: str) -> bool:
    """Check if urgency level is critical"""
    return urgency.lower() == "critical"


def format_error_response(message: str, details: Optional[str] = None) -> Dict[str, Any]:
    """Format error response"""
    response = {"error": message}
    if details:
        response["details"] = details
    return response


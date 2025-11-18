"""
Reusable Gemini AI prompt templates for medical feedback analysis
"""

FEEDBACK_ANALYSIS_PROMPT = """
You are a medical feedback analysis AI. Analyze the following patient feedback and provide a comprehensive analysis in JSON format.

Patient Feedback:
{feedback_text}

Visit Details:
- Department: {department}
- Doctor: {doctor_name}
- Visit Date: {visit_date}
- Rating: {rating}/5

Please analyze this feedback and return a JSON object with the following structure:

{{
    "sentiment": "positive|negative|neutral|mixed",
    "confidence_score": 0.0-1.0,
    "emotions": ["angry", "grateful", "worried", "frustrated", "satisfied"],
    "urgency": {{
        "level": "critical|high|medium|low",
        "reason": "explanation of urgency level",
        "flags": ["medical_complications", "severe_pain", "safety_concerns", "harassment"]
    }},
    "categories": {{
        "primary": "main category name",
        "subcategories": ["category1", "category2", ...]
    }},
    "medical_concerns": {{
        "symptoms": ["symptom1", "symptom2"],
        "complications": ["complication1"],
        "treatment_side_effects": ["side_effect1"],
        "medication_issues": ["issue1"]
    }},
    "actionable_insights": "What needs follow-up or action",
    "key_points": [
        "Key point 1",
        "Key point 2",
        "Key point 3"
    ]
}}

Important guidelines:
1. If the feedback mentions severe pain, medical complications, safety concerns, or harassment, mark urgency as "critical"
2. Be thorough in detecting medical concerns that may need immediate attention
3. Provide specific, actionable insights
4. Return ONLY valid JSON, no additional text or markdown formatting
"""


def get_analysis_prompt(feedback_text: str, department: str, doctor_name: str = None, visit_date: str = None, rating: int = None) -> str:
    """Generate the analysis prompt with feedback details"""
    return FEEDBACK_ANALYSIS_PROMPT.format(
        feedback_text=feedback_text,
        department=department,
        doctor_name=doctor_name or "Not specified",
        visit_date=visit_date or "Not specified",
        rating=rating or "Not specified"
    )
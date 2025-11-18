from sqlalchemy import JSON, Column, Float, Index, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.db import Base


class Analysis(Base):
    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("feedback.id"), unique=True, nullable=False)
    sentiment = Column(String(50), nullable=False, index=True)
    confidence_score = Column(Float, nullable=False)
    emotions = Column(JSON, nullable=True)
    urgency = Column(String(50), nullable=False, index=True)
    urgency_reason = Column(Text, nullable=True)
    urgency_flags = Column(JSON, nullable=True)
    primary_category = Column(String(100), nullable=True, index=True)
    subcategories = Column(JSON, nullable=True)
    medical_concerns = Column(JSON, nullable=True)
    actionable_insights = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True)
    analyzed_at = Column(String(50), nullable=True)

    feedback = relationship("Feedback", back_populates="analysis")

    __table_args__ = (
        Index("ix_analysis_urgency_sentiment", "urgency", "sentiment"),
        Index("ix_analysis_category_urgency", "primary_category", "urgency"),
    )


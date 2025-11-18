from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    patient_name = Column(String(255), nullable=True)
    visit_date = Column(DateTime, nullable=False, index=True)
    department = Column(String(100), nullable=False, index=True)
    doctor_name = Column(String(255), nullable=True)
    feedback_text = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)
    status = Column(String(50), default="pending_analysis", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    analysis = relationship("Analysis", back_populates="feedback", uselist=False, cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="feedback", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_feedback_department_status", "department", "status"),
        Index("ix_feedback_created_status", "created_at", "status"),
    )


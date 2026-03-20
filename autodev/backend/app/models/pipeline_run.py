import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    zoho_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zoho_task_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    zoho_task_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    zoho_task_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        default="task_received",
        nullable=False,
    )
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    feature_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="pipeline_runs")
    triggered_by_user = relationship("User", back_populates="pipeline_runs", foreign_keys=[triggered_by_user_id])
    plans = relationship("Plan", back_populates="pipeline_run", cascade="all, delete-orphan")
    agent_runs = relationship("AgentRun", back_populates="pipeline_run", cascade="all, delete-orphan")
    test_results = relationship("TestResult", back_populates="pipeline_run", cascade="all, delete-orphan")
    merge_requests = relationship("MergeRequest", back_populates="pipeline_run", cascade="all, delete-orphan")

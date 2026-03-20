import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    frontend_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    frontend_tech: Mapped[str | None] = mapped_column(String(50), nullable=True)
    backend_tech: Mapped[str | None] = mapped_column(String(50), nullable=True)
    test_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    gitlab_repo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    gitlab_project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gitlab_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # stored encrypted
    base_branch: Mapped[str] = mapped_column(String(100), default="develop")
    pr_checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    git_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "github", "gitlab", or None
    repo_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # "owner/repo" for GitHub
    zoho_portal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zoho_project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    server_start_command: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. "uvicorn main:app --port 8001"
    server_port: Mapped[int | None] = mapped_column(nullable=True)  # port the server listens on
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="projects")
    pipeline_runs = relationship("PipelineRun", back_populates="project", cascade="all, delete-orphan")

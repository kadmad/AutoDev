import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.services.redis_service import publish_log, publish_stage


@dataclass
class AgentResult:
    success: bool
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0


class BaseAgent(ABC):
    agent_type: str = "base"

    def __init__(self, run_id: str):
        self.run_id = run_id

    @abstractmethod
    async def run(self, **kwargs) -> AgentResult:
        """Execute agent logic."""
        ...

    def publish_log(self, line: str):
        publish_log(self.run_id, line, agent=self.agent_type)

    def publish_stage(self, stage: str):
        publish_stage(self.run_id, stage)

    async def _record_agent_run(self, db, status: str, output: str = "", error: str = None, exit_code: int = 0):
        """Store agent run record in DB."""
        from app.models.agent_run import AgentRun
        from sqlalchemy import select

        result = await db.execute(
            select(AgentRun).where(
                AgentRun.pipeline_run_id == uuid.UUID(self.run_id),
                AgentRun.agent_type == self.agent_type,
                AgentRun.status == "running",
            ).order_by(AgentRun.started_at.desc()).limit(1)
        )
        agent_run = result.scalar_one_or_none()
        if agent_run:
            agent_run.status = status
            agent_run.output_log = output
            agent_run.error = error
            agent_run.exit_code = exit_code
            agent_run.completed_at = datetime.utcnow()
            await db.commit()

    async def _create_agent_run(self, db):
        """Create a new agent run record."""
        from app.models.agent_run import AgentRun

        agent_run = AgentRun(
            pipeline_run_id=uuid.UUID(self.run_id),
            agent_type=self.agent_type,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(agent_run)
        await db.commit()
        await db.refresh(agent_run)
        return agent_run

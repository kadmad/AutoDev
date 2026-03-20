"""
Zoho Watcher — polls Zoho Projects every N seconds via rq-scheduler.
Creates pipeline runs for newly assigned tasks.
"""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.user import User, ZohoConfig
from app.models.project import Project
from app.models.pipeline_run import PipelineRun
from app.services.zoho_service import get_tasks
from app.services.redis_service import enqueue_pipeline


async def poll_zoho():
    """Poll all configured Zoho accounts for new tasks."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ZohoConfig))
        configs = result.scalars().all()

        for config in configs:
            try:
                tasks = await get_tasks(config, db)
                for task in tasks:
                    await _process_task(db, config, task)
            except Exception as e:
                print(f"[ZohoWatcher] Error polling config {config.id}: {e}")


async def _process_task(db: AsyncSession, config: ZohoConfig, task: dict):
    task_id = str(task.get("id", ""))
    if not task_id:
        return

    # Check if already being processed
    existing = await db.execute(
        select(PipelineRun).where(
            PipelineRun.zoho_task_id == task_id,
            PipelineRun.status.notin_(["completed", "failed"]),
        )
    )
    if existing.scalar_one_or_none():
        return

    # Check if task is assigned to this user
    assignees = task.get("details", {}).get("owners", {}).get("users", [])
    if config.zoho_user_id and not any(str(a.get("id")) == config.zoho_user_id for a in assignees):
        return

    # Find project for this user
    proj_result = await db.execute(
        select(Project).where(Project.user_id == config.user_id).limit(1)
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        return

    # Create pipeline run
    run = PipelineRun(
        project_id=project.id,
        triggered_by_user_id=config.user_id,
        zoho_task_id=task_id,
        zoho_task_title=task.get("name", ""),
        zoho_task_description=task.get("description", ""),
        status="task_received",
        current_stage="task_received",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    enqueue_pipeline(str(run.id), str(project.id))
    print(f"[ZohoWatcher] Created pipeline run {run.id} for task {task_id}")


def run_poll_zoho():
    """Entry point for rq-scheduler — runs sync wrapper."""
    asyncio.run(poll_zoho())

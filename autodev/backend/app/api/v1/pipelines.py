from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.pipeline_run import PipelineRun
from app.models.agent_run import AgentRun
from app.schemas.pipeline import (
    PipelineTriggerRequest,
    PipelineRunResponse,
    PipelineRunSummary,
)
from app.services.redis_service import enqueue_pipeline

router = APIRouter()


# ── Collection routes (no path param) — MUST come before /{run_id} routes ──

@router.get("/pipelines", response_model=list[PipelineRunSummary])
async def list_pipelines(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 500,
    offset: int = 0,
    archived: bool = Query(False),
):
    result = await db.execute(
        select(PipelineRun)
        .options(selectinload(PipelineRun.merge_requests))
        .join(Project)
        .where(Project.user_id == current_user.id, PipelineRun.archived == archived)
        .order_by(PipelineRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post("/pipelines/trigger", response_model=PipelineRunSummary, status_code=201)
async def trigger_pipeline(
    data: PipelineTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.id == data.project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    run = PipelineRun(
        project_id=data.project_id,
        triggered_by_user_id=current_user.id,
        zoho_task_id=data.zoho_task_id,
        zoho_task_number=data.zoho_task_number or None,
        zoho_task_title=data.zoho_task_title,
        zoho_task_description=data.zoho_task_description,
        status="task_received",
        current_stage="task_received",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    enqueue_pipeline(str(run.id), str(project.id))
    return run


class BulkDeleteRequest(BaseModel):
    run_ids: Optional[List[UUID]] = None  # None = delete all completed+failed
    statuses: Optional[List[str]] = None  # e.g. ["completed", "failed"]


@router.post("/pipelines/bulk-delete")
async def bulk_delete_pipelines(
    data: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proj_result = await db.execute(
        select(Project.id).where(Project.user_id == current_user.id)
    )
    project_ids = list(proj_result.scalars().all())

    query = select(PipelineRun).where(PipelineRun.project_id.in_(project_ids))
    if data.run_ids:
        query = query.where(PipelineRun.id.in_(data.run_ids))
    else:
        allowed = data.statuses or ["completed", "failed"]
        query = query.where(PipelineRun.status.in_(allowed))

    result = await db.execute(query)
    runs = result.scalars().all()

    # Explicit IDs: delete all. No IDs (bulk clean-up): only completed/failed.
    to_delete = runs if data.run_ids else [r for r in runs if r.status in ("completed", "failed")]
    for run in to_delete:
        await db.delete(run)
    await db.commit()
    return {"deleted": len(to_delete)}


class BulkArchiveRequest(BaseModel):
    run_ids: Optional[List[UUID]] = None  # None = archive all completed+failed


@router.post("/pipelines/bulk-archive")
async def bulk_archive_pipelines(
    data: BulkArchiveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proj_result = await db.execute(
        select(Project.id).where(Project.user_id == current_user.id)
    )
    project_ids = list(proj_result.scalars().all())

    query = select(PipelineRun).where(
        PipelineRun.project_id.in_(project_ids),
        PipelineRun.archived == False,  # noqa: E712
    )
    if data.run_ids:
        query = query.where(PipelineRun.id.in_(data.run_ids))
    else:
        query = query.where(PipelineRun.status.in_(["completed", "failed"]))

    result = await db.execute(query)
    runs = result.scalars().all()

    # Explicit IDs: archive all. No IDs: only completed/failed.
    to_archive = runs if data.run_ids else [r for r in runs if r.status in ("completed", "failed")]
    for run in to_archive:
        run.archived = True
    await db.commit()
    return {"archived": len(to_archive)}


@router.post("/pipelines/bulk-unarchive")
async def bulk_unarchive_pipelines(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proj_result = await db.execute(
        select(Project.id).where(Project.user_id == current_user.id)
    )
    project_ids = list(proj_result.scalars().all())

    result = await db.execute(
        select(PipelineRun).where(
            PipelineRun.project_id.in_(project_ids),
            PipelineRun.archived == True,  # noqa: E712
        )
    )
    runs = result.scalars().all()
    for run in runs:
        run.archived = False
    await db.commit()
    return {"unarchived": len(runs)}


# ── Per-run routes — parameterised, must come AFTER all static paths ──

@router.get("/pipelines/{run_id}/diff")
async def get_pipeline_diff(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return list of files changed in the pipeline's feature branch vs base branch."""
    result = await db.execute(
        select(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    proj_result = await db.execute(select(Project).where(Project.id == run.project_id))
    project = proj_result.scalar_one_or_none()
    project_dir = project.backend_dir or project.frontend_dir or "/tmp"

    from app.services.github_service import get_changed_files
    files = await get_changed_files(project_dir)

    total_add = sum(f["additions"] for f in files)
    total_del = sum(f["deletions"] for f in files)
    n = len(files)
    summary = f"{n} file{'s' if n != 1 else ''} changed"
    if total_add or total_del:
        summary += f", +{total_add} −{total_del}"

    return {"files": files, "summary": summary}


@router.get("/pipelines/{run_id}", response_model=PipelineRunResponse)
async def get_pipeline(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .options(
            selectinload(PipelineRun.plans),
            selectinload(PipelineRun.agent_runs),
            selectinload(PipelineRun.test_results),
            selectinload(PipelineRun.merge_requests),
        )
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


@router.post("/pipelines/{run_id}/cancel")
async def cancel_pipeline(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    if run.status in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Pipeline already finished")
    run.status = "failed"
    run.error_message = "Cancelled by user"
    await db.commit()
    return {"status": "cancelled"}


@router.post("/pipelines/{run_id}/resume")
async def resume_pipeline(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    if run.status not in ("failed",):
        raise HTTPException(status_code=400, detail="Only failed pipelines can be resumed")
    run.status = "task_received"
    run.current_stage = "task_received"
    run.error_message = None
    await db.commit()
    enqueue_pipeline(str(run.id), str(run.project_id))
    return {"status": "resumed"}


@router.delete("/pipelines/{run_id}", status_code=204)
async def delete_pipeline(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    await db.delete(run)
    await db.commit()


@router.post("/pipelines/{run_id}/archive")
async def archive_pipeline(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    run.archived = True
    await db.commit()
    return {"status": "archived"}


@router.post("/pipelines/{run_id}/unarchive")
async def unarchive_pipeline(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    run.archived = False
    await db.commit()
    return {"status": "unarchived"}


@router.get("/pipelines/{run_id}/logs")
async def get_pipeline_logs(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentRun)
        .join(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == current_user.id)
        .order_by(AgentRun.started_at)
    )
    agents = result.scalars().all()
    return [{"agent_type": a.agent_type, "output_log": a.output_log, "status": a.status} for a in agents]

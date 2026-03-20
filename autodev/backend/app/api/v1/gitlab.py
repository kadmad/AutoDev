from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.pipeline_run import PipelineRun
from app.models.merge_request import MergeRequest
from app.schemas.pipeline import MergeRequestResponse
from app.services.redis_service import publish_stage

router = APIRouter()


async def _get_run(run_id: UUID, user: User, db: AsyncSession) -> PipelineRun:
    result = await db.execute(
        select(PipelineRun)
        .join(Project)
        .where(PipelineRun.id == run_id, Project.user_id == user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


@router.get("/pipelines/{run_id}/mr", response_model=MergeRequestResponse)
async def get_mr(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    result = await db.execute(
        select(MergeRequest)
        .where(MergeRequest.pipeline_run_id == run.id)
        .order_by(MergeRequest.created_at.desc())
        .limit(1)
    )
    mr = result.scalar_one_or_none()
    if not mr:
        raise HTTPException(status_code=404, detail="No merge request created yet")
    return mr


@router.post("/pipelines/{run_id}/mr/confirm-merge")
async def confirm_merge(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    if run.status != "mr_open":
        raise HTTPException(status_code=400, detail="Pipeline is not in mr_open stage")

    result = await db.execute(
        select(MergeRequest)
        .where(MergeRequest.pipeline_run_id == run.id)
        .order_by(MergeRequest.created_at.desc())
        .limit(1)
    )
    mr = result.scalar_one_or_none()
    if mr:
        mr.status = "merged"

    run.status = "completed"
    run.current_stage = "completed"
    await db.commit()

    publish_stage(str(run_id), "completed")
    return {"status": "completed"}

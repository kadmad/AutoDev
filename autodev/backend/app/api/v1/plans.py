from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.pipeline_run import PipelineRun
from app.models.plan import Plan
from app.schemas.pipeline import PlanResponse, PlanApproveRequest, PlanReplanRequest
from app.services.redis_service import publish_stage, enqueue_pipeline

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


@router.get("/pipelines/{run_id}/plan", response_model=PlanResponse)
async def get_plan(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    result = await db.execute(
        select(Plan)
        .where(Plan.pipeline_run_id == run.id)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan generated yet")
    return plan


@router.post("/pipelines/{run_id}/plan/approve", response_model=PlanResponse)
async def approve_plan(
    run_id: UUID,
    data: PlanApproveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    if run.status != "plan_review":
        raise HTTPException(status_code=400, detail=f"Pipeline is in '{run.status}' stage, not 'plan_review'")

    result = await db.execute(
        select(Plan)
        .where(Plan.pipeline_run_id == run.id)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan to approve")

    plan.approved_by = current_user.id
    plan.approved_at = datetime.utcnow()
    if data.user_edits:
        plan.user_edits = data.user_edits

    run.status = "developing"
    run.current_stage = "developing"
    await db.commit()
    await db.refresh(plan)

    publish_stage(str(run_id), "developing")
    enqueue_pipeline(str(run_id), str(run.project_id))  # re-enqueue rq job

    return plan


@router.post("/pipelines/{run_id}/plan/replan", response_model=PlanResponse)
async def replan(
    run_id: UUID,
    data: PlanReplanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    if run.status != "plan_review":
        raise HTTPException(status_code=400, detail="Pipeline is not in plan_review stage")

    result = await db.execute(
        select(Plan)
        .where(Plan.pipeline_run_id == run.id)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    old_plan = result.scalar_one_or_none()
    new_version = (old_plan.version + 1) if old_plan else 1

    # Store feedback and restart planning
    new_plan = Plan(
        pipeline_run_id=run.id,
        content="",  # Will be filled by planner agent
        version=new_version,
        user_edits=data.feedback,
    )
    db.add(new_plan)

    run.status = "planning"
    run.current_stage = "planning"
    await db.commit()
    await db.refresh(new_plan)

    publish_stage(str(run_id), "planning")
    enqueue_pipeline(str(run_id), str(run.project_id))  # re-enqueue rq job

    return new_plan

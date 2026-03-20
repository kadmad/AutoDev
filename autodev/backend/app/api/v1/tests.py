import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, ZohoConfig
from app.models.project import Project
from app.models.pipeline_run import PipelineRun
from app.models.test_result import TestResult
from app.schemas.pipeline import (
    TestResultResponse, TestApproveRequest, TestReworkRequest, TestScenariosUpdateRequest,
)
from app.services.redis_service import publish_stage, enqueue_pipeline
from app.services.zoho_service import update_task_status

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


async def _get_test(run: PipelineRun, db: AsyncSession) -> TestResult | None:
    result = await db.execute(
        select(TestResult)
        .where(TestResult.pipeline_run_id == run.id)
        .order_by(TestResult.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/pipelines/{run_id}/tests", response_model=TestResultResponse)
async def get_test_results(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    test = await _get_test(run, db)
    if not test:
        raise HTTPException(status_code=404, detail="No test results yet")
    return test


@router.put("/pipelines/{run_id}/tests/scenarios")
async def update_scenarios(
    run_id: UUID,
    data: TestScenariosUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save user-edited scenario list without advancing the pipeline."""
    run = await _get_run(run_id, current_user, db)
    if run.status != "testing":
        raise HTTPException(status_code=400, detail="Pipeline is not in testing stage")

    test = await _get_test(run, db)
    if not test:
        raise HTTPException(status_code=404, detail="No test result record found")

    scenarios = [s.model_dump() for s in data.scenarios]
    test.scenarios = json.dumps(scenarios)
    test.total = len(scenarios)
    await db.commit()
    return {"status": "saved"}


@router.post("/pipelines/{run_id}/tests/approve")
async def approve_tests(
    run_id: UUID,
    data: TestApproveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    if run.status != "testing":
        raise HTTPException(status_code=400, detail="Pipeline is not in testing stage")

    scenarios = [s.model_dump() for s in data.scenarios]
    passed = sum(1 for s in scenarios if s["status"] == "passed")
    failed = sum(1 for s in scenarios if s["status"] == "failed")
    pending = sum(1 for s in scenarios if s["status"] == "pending")

    test = await _get_test(run, db)
    if test:
        test.scenarios = json.dumps(scenarios)
        test.total = len(scenarios)
        test.passed = passed
        test.failed = failed
        test.skipped = pending
        test.approved_by = current_user.id
        test.approved_at = datetime.utcnow()

    # Post test report to Zoho
    if run.zoho_task_id:
        await _post_zoho_test_report(run, scenarios, passed, failed, pending, db)

    run.status = "creating_mr"
    run.current_stage = "creating_mr"
    await db.commit()

    publish_stage(str(run_id), "creating_mr")
    enqueue_pipeline(str(run_id), str(run.project_id))
    return {"status": "approved", "next_stage": "creating_mr"}


@router.post("/pipelines/{run_id}/tests/skip")
async def skip_tests(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    if run.status != "testing":
        raise HTTPException(status_code=400, detail="Pipeline is not in testing stage")

    test = await _get_test(run, db)
    if not test:
        skipped_rec = TestResult(
            pipeline_run_id=run.id,
            total=0, passed=0, failed=0, skipped=0,
            raw_output="Testing skipped by user",
        )
        db.add(skipped_rec)

    run.status = "creating_mr"
    run.current_stage = "creating_mr"
    await db.commit()

    publish_stage(str(run_id), "creating_mr")
    enqueue_pipeline(str(run_id), str(run.project_id))
    return {"status": "skipped", "next_stage": "creating_mr"}


@router.post("/pipelines/{run_id}/tests/rework")
async def rework_tests(
    run_id: UUID,
    data: TestReworkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(run_id, current_user, db)
    if run.status != "testing":
        raise HTTPException(status_code=400, detail="Pipeline is not in testing stage")

    run.status = "developing"
    run.current_stage = "developing"
    run.error_message = f"Test rework requested: {data.feedback}"
    await db.commit()

    publish_stage(str(run_id), "developing")
    enqueue_pipeline(str(run_id), str(run.project_id))
    return {"status": "rework_requested"}


async def _post_zoho_test_report(run: PipelineRun, scenarios: list, passed: int, failed: int, pending: int, db: AsyncSession):
    """Post a manual test report comment to the Zoho task."""
    try:
        project_result = await db.execute(
            select(Project).where(Project.id == run.project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            return

        config_result = await db.execute(
            select(ZohoConfig).where(ZohoConfig.user_id == project.user_id)
        )
        config = config_result.scalar_one_or_none()
        if not config:
            return

        total = len(scenarios)
        lines = [
            f"🧪 Manual Testing Complete — {passed}/{total} scenarios passed\n",
            f"• Passed: {passed}  |  Failed: {failed}  |  Pending: {pending}\n",
        ]
        for s in scenarios:
            icon = "✅" if s["status"] == "passed" else "❌" if s["status"] == "failed" else "⏭"
            lines.append(f"{icon} {s['name']}")
            if s.get("expected"):
                lines.append(f"   Expected: {s['expected']}")

        comment = "\n".join(lines)
        from app.services.zoho_service import PIPELINE_STAGE_TO_ZOHO_STATUS
        zoho_status = PIPELINE_STAGE_TO_ZOHO_STATUS.get("creating_mr", "90")
        await update_task_status(
            config=config,
            task_id=run.zoho_task_id,
            status_name=zoho_status,
            comment=comment,
            db=db,
            portal_name=project.zoho_portal_name or None,
            project_id=project.zoho_project_id or None,
        )
    except Exception:
        pass  # Never block the pipeline over a Zoho comment failure

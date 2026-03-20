import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db, AsyncSessionLocal
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


class PlaywrightRetryRequest(BaseModel):
    scenario_ids: List[str]


@router.post("/pipelines/{run_id}/tests/retry-playwright")
async def retry_playwright_scenarios(
    run_id: UUID,
    data: PlaywrightRetryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run specific Playwright scenarios without restarting the whole pipeline."""
    run = await _get_run(run_id, current_user, db)
    if run.status != "testing":
        raise HTTPException(status_code=400, detail="Pipeline is not in testing stage")

    test = await _get_test(run, db)
    if not test or not test.scenarios:
        raise HTTPException(status_code=404, detail="No test scenarios found")

    # Load project
    proj_result = await db.execute(select(Project).where(Project.id == run.project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.server_start_command or not project.server_port:
        raise HTTPException(status_code=400, detail="No server_start_command / server_port configured on project")

    # Parse stored scenarios and filter to requested playwright ones
    try:
        all_scenarios = json.loads(test.scenarios)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not parse stored scenarios")

    id_set = set(data.scenario_ids)
    retry_scenarios = [s for s in all_scenarios if s.get("id") in id_set and s.get("type") == "playwright"]
    if not retry_scenarios:
        raise HTTPException(status_code=400, detail="No matching playwright scenarios found for the given IDs")

    test_id = test.id

    # ── Start project server ───────────────────────────────────────────────────
    server_proc = await asyncio.create_subprocess_shell(
        project.server_start_command,
        cwd=project.backend_dir or project.frontend_dir or "/tmp",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.sleep(5)

    browser_output = None
    try:
        from app.agents.browser_test_agent import BrowserTestAgent
        from app.agents.orchestrator import _parse_per_scenario_results

        b_agent = BrowserTestAgent(run_id=str(run_id))
        # Close the FastAPI-managed session before the long operation
        await db.close()

        b_result = await asyncio.wait_for(
            b_agent.run(
                project_dir=project.backend_dir or project.frontend_dir or "/tmp",
                port=project.server_port,
                task_title=run.zoho_task_title or "",
                task_description=run.zoho_task_description or "",
                scenarios=retry_scenarios,
                db=None,
            ),
            timeout=600,  # 10 min max
        )
        browser_output = b_result.output
        per_scenario = _parse_per_scenario_results(browser_output or "", retry_scenarios)
        for s in retry_scenarios:
            s["status"] = per_scenario.get(s["id"], "failed" if not b_result.success else "passed")

    except asyncio.TimeoutError:
        for s in retry_scenarios:
            s["status"] = "failed"
        browser_output = "Retry timed out after 10 minutes."
    except Exception as exc:
        for s in retry_scenarios:
            s["status"] = "failed"
        browser_output = f"Retry error: {exc}"
    finally:
        try:
            server_proc.terminate()
        except ProcessLookupError:
            pass

    # Merge updated retry statuses back into the full scenario list
    updated_map = {s["id"]: s for s in retry_scenarios}
    merged = [updated_map.get(s["id"], s) for s in all_scenarios]

    # Recalculate overall playwright status
    pw_scenarios = [s for s in merged if s.get("type") == "playwright"]
    new_browser_status = "passed" if pw_scenarios and all(s["status"] == "passed" for s in pw_scenarios) else "failed"

    # Persist with a fresh session (old session may be closed)
    async with AsyncSessionLocal() as fresh_db:
        fresh_test = await fresh_db.get(TestResult, test_id)
        if fresh_test:
            fresh_test.scenarios = json.dumps(merged)
            fresh_test.browser_test_status = new_browser_status
            if browser_output:
                # Append retry output to existing report
                existing = fresh_test.browser_test_output or ""
                fresh_test.browser_test_output = (
                    existing + f"\n\n---\n**Retry run:**\n\n{browser_output}" if existing else browser_output
                )
            await fresh_db.commit()

    return {"scenarios": json.dumps(merged), "browser_test_status": new_browser_status}


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

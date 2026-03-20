"""
/task-assign  — external webhook endpoint (no JWT required)

Called by Zoho when a task is assigned:
  POST http://localhost:8000/task-assign
       ?task_owner=user@email.com
       &description=<task description>
       &task_id=<numeric zoho task id>
       &platform=zoho
"""
import re
import html as html_lib
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User, ZohoConfig
from app.models.project import Project
from app.models.pipeline_run import PipelineRun
from app.services.redis_service import enqueue_pipeline

router = APIRouter()


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities, returning clean plain text."""
    # Decode HTML entities (&amp; → &, &lt; → <, etc.)
    text = html_lib.unescape(text)
    # Replace block-level tags with newlines so text from different divs doesn't run together
    text = re.sub(r'<(?:br|p|div|li|tr|h[1-6])[^>]*/?>', '\n', text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Collapse multiple blank lines into one, strip each line
    lines = [line.strip() for line in text.splitlines()]
    lines = [l for l in lines if l]
    return '\n'.join(lines).strip()


def _extract_title(description: str) -> str:
    for line in description.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return description[:120] or "Untitled Task"


async def _find_user_and_project(
    task_owner_email: str,
    db: AsyncSession,
    zoho_project_id: str = "",
    zoho_project_name: str = "",
) -> tuple[User | None, Project | None]:
    # Resolve user by AutoDev email or linked Zoho email
    user_result = await db.execute(
        select(User).where(User.email == task_owner_email)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        zoho_result = await db.execute(
            select(ZohoConfig).where(ZohoConfig.zoho_email == task_owner_email)
        )
        zoho_cfg = zoho_result.scalar_one_or_none()
        if zoho_cfg:
            user_result2 = await db.execute(
                select(User).where(User.id == zoho_cfg.user_id)
            )
            user = user_result2.scalar_one_or_none()

    if not user:
        return None, None

    # 1. Exact match on Zoho project ID (most reliable)
    if zoho_project_id:
        r = await db.execute(
            select(Project).where(
                Project.user_id == user.id,
                Project.zoho_project_id == zoho_project_id,
            )
        )
        project = r.scalar_one_or_none()
        if project:
            return user, project

    # 2. Case-insensitive match on stored zoho_project_name
    if zoho_project_name:
        r = await db.execute(
            select(Project).where(
                Project.user_id == user.id,
                Project.zoho_project_name.ilike(zoho_project_name),
            )
        )
        project = r.scalar_one_or_none()
        if project:
            return user, project

        # 3. Fall back: AutoDev project name matches the Zoho project name
        r = await db.execute(
            select(Project).where(
                Project.user_id == user.id,
                Project.name.ilike(zoho_project_name),
            )
        )
        project = r.scalar_one_or_none()
        if project:
            return user, project

    # 4. Last resort: first project (backwards compat for single-project setups)
    r = await db.execute(
        select(Project).where(Project.user_id == user.id).limit(1)
    )
    project = r.scalar_one_or_none()
    return user, project


async def _handle_task_assign(
    task_owner: str,
    description: str,
    platform: str,
    db: AsyncSession,
    task_id: str = "",
    task_number: str = "",
    task_title: str = "",
    zoho_project_id: str = "",
    zoho_project_name: str = "",
) -> dict:
    task_owner       = task_owner.strip()
    task_id          = task_id.strip()
    task_number      = task_number.strip()
    zoho_project_id  = zoho_project_id.strip()
    zoho_project_name = zoho_project_name.strip()

    # Strip HTML from both title and description before storing
    description = _strip_html(description).strip()
    task_title  = _strip_html(task_title).strip()

    print(
        f"[task-assign] task_owner={task_owner!r} task_id={task_id!r} "
        f"task_number={task_number!r} task_title={task_title!r} "
        f"zoho_project_id={zoho_project_id!r} zoho_project_name={zoho_project_name!r} "
        f"description={description[:80]!r}",
        flush=True,
    )

    if not task_owner or not description:
        raise HTTPException(status_code=400, detail="task_owner and description are required")

    user, project = await _find_user_and_project(
        task_owner, db,
        zoho_project_id=zoho_project_id,
        zoho_project_name=zoho_project_name,
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"No AutoDev user found for email '{task_owner}'. "
                   "The email must match your AutoDev login email or your Zoho email in settings.",
        )

    if not project:
        hint = ""
        if zoho_project_name or zoho_project_id:
            hint = (
                f" No project matched Zoho project "
                f"{'ID=' + zoho_project_id if zoho_project_id else ''}"
                f"{'name=' + zoho_project_name if zoho_project_name else ''}."
                " Set the matching Zoho Project Name on your AutoDev project."
            )
        raise HTTPException(
            status_code=422,
            detail=f"User '{task_owner}' has no project configured.{hint} "
                   "Create one at http://localhost:3000/projects/new",
        )

    # Use explicit task_title if provided, otherwise derive from description
    title = task_title or _extract_title(description)

    run = PipelineRun(
        project_id=project.id,
        triggered_by_user_id=user.id,
        zoho_task_id=task_id or None,
        zoho_task_number=task_number or None,
        zoho_task_title=title,
        zoho_task_description=description,
        status="task_received",
        current_stage="task_received",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    enqueue_pipeline(str(run.id), str(project.id))

    return {
        "status": "accepted",
        "run_id": str(run.id),
        "pipeline_url": f"http://localhost:3000/pipelines/{run.id}",
        "message": f"Pipeline started for '{title}'.",
    }


@router.post("/task-assign")
async def task_assign_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Params can come as query string OR body (JSON / form-encoded)
    params = request.query_params
    body: dict = {}

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            body = {}
    else:
        try:
            form = await request.form()
            body = dict(form)
        except Exception:
            body = {}

    task_owner  = body.get("task_owner")   or params.get("task_owner",   "")
    description = body.get("description")  or params.get("description",  "")
    platform    = body.get("platform")     or params.get("platform",     "zoho")
    task_id     = body.get("task_id")      or params.get("task_id",      "")
    task_number = body.get("task_number")  or params.get("task_number",  "")
    # Accept task title under several common field names Zoho may use
    task_title  = (
        body.get("task_title")  or params.get("task_title",  "") or
        body.get("task_name")   or params.get("task_name",   "") or
        body.get("name")        or params.get("name",        "") or
        body.get("title")       or params.get("title",       "")
    )
    # Zoho project identification — used to route to the right AutoDev project
    zoho_project_id = (
        body.get("project_id")   or params.get("project_id",   "") or
        body.get("projectId")    or params.get("projectId",    "")
    )
    zoho_project_name = (
        body.get("project_name") or params.get("project_name", "") or
        body.get("projectName")  or params.get("projectName",  "")
    )

    return await _handle_task_assign(
        task_owner, description, platform, db,
        task_id, task_number, task_title,
        zoho_project_id, zoho_project_name,
    )

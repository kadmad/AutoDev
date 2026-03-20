from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, ZohoConfig
from app.models.project import Project
from app.models.pipeline_run import PipelineRun
from app.schemas.user import ZohoConfigResponse
from app.services.zoho_service import (
    get_zoho_auth_url,
    exchange_code_for_tokens,
    fetch_zoho_userinfo,
    save_tokens,
    get_portals,
    get_projects_for_portal,
    refresh_zoho_token,
)
from app.services.redis_service import enqueue_pipeline

router = APIRouter()


# ─── OAuth ───────────────────────────────────────────────────────────────────

@router.get("/zoho/auth/url")
async def get_auth_url(current_user: User = Depends(get_current_user)):
    """Return the Zoho OAuth authorization URL for the frontend to redirect to."""
    return {"url": get_zoho_auth_url()}


@router.post("/zoho/auth/callback")
async def zoho_auth_callback(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange the authorization code returned by Zoho for access + refresh tokens.
    Frontend posts: { "code": "<auth_code>" }
    """
    code = body.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Exchange code for tokens
    try:
        token_data = await exchange_code_for_tokens(code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Zoho token exchange failed: {e}")

    # Find or create ZohoConfig for this user
    result = await db.execute(
        select(ZohoConfig).where(ZohoConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Zoho config not found. Complete the setup step first.",
        )

    # Fetch Zoho user profile to auto-populate email and user ID
    userinfo = await fetch_zoho_userinfo(token_data.get("access_token", ""))
    if userinfo:
        config.zoho_email = userinfo.get("email") or userinfo.get("Email") or config.zoho_email
        config.zoho_user_id = str(userinfo.get("ZUID") or userinfo.get("sub") or config.zoho_user_id or "")

    await save_tokens(config, token_data, db)
    await db.refresh(config)

    return {
        "status": "connected",
        "zoho": ZohoConfigResponse.from_orm_with_status(config),
    }


@router.get("/zoho/auth/status", response_model=ZohoConfigResponse)
async def zoho_auth_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current Zoho connection status (used by the notification banner)."""
    result = await db.execute(
        select(ZohoConfig).where(ZohoConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Zoho not configured")
    return ZohoConfigResponse.from_orm_with_status(config)


# ─── Portals & Projects ──────────────────────────────────────────────────────

@router.get("/zoho/portals")
async def list_zoho_portals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all Zoho portals accessible to the connected account."""
    result = await db.execute(select(ZohoConfig).where(ZohoConfig.user_id == current_user.id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Zoho not configured")

    token = await refresh_zoho_token(config, db)
    if not token:
        raise HTTPException(status_code=401, detail="Zoho token expired — reconnect OAuth")

    try:
        portals = await get_portals(token, api_domain=config.api_domain)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Zoho API error: {e}")

    return [{"id": p.get("id"), "name": p.get("name"), "display": p.get("display")} for p in portals]


@router.get("/zoho/portals/{portal_name}/projects")
async def list_zoho_projects(
    portal_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all projects in the given Zoho portal."""
    result = await db.execute(select(ZohoConfig).where(ZohoConfig.user_id == current_user.id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Zoho not configured")

    token = await refresh_zoho_token(config, db)
    if not token:
        raise HTTPException(status_code=401, detail="Zoho token expired — reconnect OAuth")

    try:
        projects = await get_projects_for_portal(token, portal_name, api_domain=config.api_domain)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Zoho API error: {e}")

    return [{"id": p.get("id_string") or p.get("id"), "name": p.get("name")} for p in projects]


# ─── Webhook ─────────────────────────────────────────────────────────────────

@router.post("/webhooks/zoho")
async def zoho_webhook(
    request: Request,
    x_zoho_webhook_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()

    if x_zoho_webhook_secret:
        result = await db.execute(
            select(ZohoConfig).where(ZohoConfig.webhook_secret == x_zoho_webhook_secret)
        )
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    else:
        portal = payload.get("portal", {}).get("name", "")
        result = await db.execute(
            select(ZohoConfig).where(ZohoConfig.portal_name == portal)
        )
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=404, detail="No config found for this portal")

    task_data = payload.get("task", {})
    task_id = str(task_data.get("id", ""))
    task_title = task_data.get("name", "")
    task_description = task_data.get("description", "")

    result = await db.execute(
        select(Project).where(Project.user_id == config.user_id).limit(1)
    )
    project = result.scalar_one_or_none()
    if not project:
        return {"status": "ignored", "reason": "no project configured"}

    existing = await db.execute(
        select(PipelineRun).where(
            PipelineRun.zoho_task_id == task_id,
            PipelineRun.status.notin_(["completed", "failed"]),
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "ignored", "reason": "pipeline already running"}

    run = PipelineRun(
        project_id=project.id,
        triggered_by_user_id=config.user_id,
        zoho_task_id=task_id,
        zoho_task_title=task_title,
        zoho_task_description=task_description,
        status="task_received",
        current_stage="task_received",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    enqueue_pipeline(str(run.id), str(project.id))
    return {"status": "accepted", "run_id": str(run.id)}

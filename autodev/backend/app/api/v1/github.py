"""
GitHub OAuth endpoints.

GET  /github/auth/url        — return OAuth URL (requires JWT)
POST /github/auth/callback   — exchange code, save git config, return status
GET  /github/auth/status     — return current connection or 404
GET  /github/repos           — list repos for connected user
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.git_config import GitConfig
from app.services import github_service

router = APIRouter()


# ---------- Pydantic response schemas ----------

class GitConfigResponse(BaseModel):
    id: str
    provider: str
    username: str | None
    email: str | None
    avatar_url: str | None
    token_expired: bool
    is_connected: bool

    model_config = {"from_attributes": True}


# ---------- Helpers ----------

def _git_config_to_response(cfg: GitConfig) -> GitConfigResponse:
    return GitConfigResponse(
        id=str(cfg.id),
        provider=cfg.provider,
        username=cfg.username,
        email=cfg.email,
        avatar_url=cfg.avatar_url,
        token_expired=cfg.token_expired,
        is_connected=bool(cfg.access_token) and not cfg.token_expired,
    )


# ---------- Endpoints ----------

@router.get("/github/auth/url")
async def get_github_auth_url(
    current_user: User = Depends(get_current_user),
):
    """Return the GitHub OAuth authorization URL."""
    url = github_service.get_github_auth_url()
    return {"url": url}


class CallbackRequest(BaseModel):
    code: str


@router.post("/github/auth/callback")
async def github_callback(
    body: CallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange authorization code for a GitHub access token,
    fetch user info, and upsert the GitConfig record.
    """
    # Exchange code for token
    token_data = await github_service.exchange_code_for_token(body.code)
    access_token = token_data.get("access_token")
    if not access_token:
        error = token_data.get("error_description") or token_data.get("error") or "Token exchange failed"
        raise HTTPException(status_code=400, detail=error)

    # Fetch GitHub user profile
    gh_user = await github_service.get_github_user(access_token)

    # Upsert GitConfig
    result = await db.execute(
        select(GitConfig).where(
            GitConfig.user_id == current_user.id,
            GitConfig.provider == "github",
        )
    )
    cfg = result.scalar_one_or_none()

    if cfg is None:
        cfg = GitConfig(
            user_id=current_user.id,
            provider="github",
        )
        db.add(cfg)

    cfg.access_token = access_token
    cfg.refresh_token = None
    cfg.token_expiry = None
    cfg.token_expired = False
    cfg.username = gh_user.get("login")
    cfg.email = gh_user.get("email")
    cfg.provider_user_id = str(gh_user.get("id", ""))
    cfg.avatar_url = gh_user.get("avatar_url")
    cfg.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(cfg)

    return {"status": "connected", "git": _git_config_to_response(cfg)}


@router.get("/github/auth/status")
async def github_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current GitHub connection status or 404 if not connected."""
    result = await db.execute(
        select(GitConfig).where(
            GitConfig.user_id == current_user.id,
            GitConfig.provider == "github",
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="GitHub not connected")
    return _git_config_to_response(cfg)


@router.get("/github/repos")
async def list_github_repos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a list of repos for the connected GitHub account."""
    result = await db.execute(
        select(GitConfig).where(
            GitConfig.user_id == current_user.id,
            GitConfig.provider == "github",
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg or not cfg.access_token:
        raise HTTPException(status_code=404, detail="GitHub not connected")

    repos = await github_service.list_user_repos(cfg.access_token)
    return [
        {
            "full_name": r.get("full_name"),
            "name": r.get("name"),
            "private": r.get("private", False),
            "default_branch": r.get("default_branch", "main"),
        }
        for r in repos
    ]

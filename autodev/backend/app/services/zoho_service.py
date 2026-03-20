import httpx
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import ZohoConfig
from app.config import settings

ZOHO_API_BASE = "https://projectsapi.zoho.com/restapi"
ZOHO_ACCOUNTS_BASE = "https://accounts.zoho.com"


def get_zoho_auth_url() -> str:
    """Return the Zoho OAuth authorization URL."""
    return (
        f"{ZOHO_ACCOUNTS_BASE}/oauth/v2/auth"
        f"?scope=ZohoProjects.portals.READ,ZohoProjects.projects.READ,ZohoProjects.tasks.ALL"
        f"&client_id={settings.ZOHO_CLIENT_ID}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&redirect_uri={settings.ZOHO_REDIRECT_URI}"
    )


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ZOHO_ACCOUNTS_BASE}/oauth/v2/token",
            data={
                "code": code,
                "client_id": settings.ZOHO_CLIENT_ID,
                "client_secret": settings.ZOHO_CLIENT_SECRET,
                "redirect_uri": settings.ZOHO_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise ValueError(f"Zoho token exchange error: {data['error']}")

    return data


async def refresh_zoho_token(config: ZohoConfig, db: AsyncSession) -> Optional[str]:
    """
    Refresh the access token if it's close to expiry.
    On failure, sets token_expired=True and returns None (caller must skip Zoho calls).
    """
    # Still valid (5-min buffer)
    if (
        config.access_token
        and config.token_expiry
        and config.token_expiry > datetime.utcnow() + timedelta(minutes=5)
        and not config.token_expired
    ):
        return config.access_token

    if not config.refresh_token:
        # No way to refresh — mark expired so the UI banner shows
        if db:
            await _mark_expired(config, db)
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{ZOHO_ACCOUNTS_BASE}/oauth/v2/token",
                data={
                    "refresh_token": config.refresh_token,
                    "client_id": settings.ZOHO_CLIENT_ID,
                    "client_secret": settings.ZOHO_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                },
            )
            data = resp.json()

        if "error" in data or "access_token" not in data:
            await _mark_expired(config, db)
            return None

        config.access_token = data["access_token"]
        config.token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
        config.token_expired = False
        await db.commit()
        return config.access_token

    except Exception:
        await _mark_expired(config, db)
        return None


async def _mark_expired(config: ZohoConfig, db: AsyncSession):
    config.token_expired = True
    config.access_token = None
    await db.commit()


async def fetch_zoho_userinfo(access_token: str) -> dict:
    """
    Fetch the authenticated Zoho user's profile.
    Returns dict with at least 'Email' and 'ZUID' keys.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{ZOHO_ACCOUNTS_BASE}/oauth/v2/userinfo",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
        if resp.is_success:
            return resp.json()
    return {}


async def save_tokens(config: ZohoConfig, token_data: dict, db: AsyncSession):
    """Persist OAuth tokens returned from Zoho onto the ZohoConfig row."""
    config.access_token = token_data.get("access_token")
    config.refresh_token = token_data.get("refresh_token", config.refresh_token)
    config.token_expiry = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
    config.token_expired = False
    await db.commit()


async def get_portals(token: str) -> list[dict]:
    """Return list of portals the user has access to."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/portals/",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("portals", [])


async def get_projects_for_portal(token: str, portal_name: str) -> list[dict]:
    """Return list of projects in the given portal."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/portal/{portal_name}/projects/",
            headers={"Authorization": f"Zoho-oauthtoken {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("projects", [])


async def get_tasks(config: ZohoConfig, db: AsyncSession) -> list[dict]:
    """Get tasks assigned to user from Zoho Projects. Returns [] if token expired."""
    token = await refresh_zoho_token(config, db)
    if not token:
        return []

    url = f"{ZOHO_API_BASE}/portal/{config.portal_name}/projects/{config.project_id}/tasks/"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Zoho-oauthtoken {token}"},
                params={"owner": config.zoho_user_id} if config.zoho_user_id else {},
            )
            resp.raise_for_status()
            return resp.json().get("tasks", [])
    except Exception:
        return []


async def update_task_status(
    config: ZohoConfig,
    task_id: str,
    status_name: str,
    comment: Optional[str] = None,
    db: AsyncSession = None,
    portal_name: Optional[str] = None,
    project_id: Optional[str] = None,
) -> str | bool:
    """
    Update a Zoho task status.
    portal_name/project_id override the config values when provided (per-project config).
    Raises ValueError with detail if the API call fails, so the caller can log it.
    Returns False (without raising) if the token is expired.
    Returns the confirmed status name string on success.
    """
    portal = portal_name or config.portal_name
    pid = project_id or config.project_id

    if portal in ("", "pending", None) or pid in ("", "pending", None):
        raise ValueError(
            f"Zoho not configured: portal_name={portal!r}, "
            f"project_id={pid!r}. "
            "Go to Settings → Integrations and set your Zoho portal name and project ID."
        )

    if not task_id.isdigit():
        raise ValueError(
            f"task_id {task_id!r} is not a numeric ID. "
            "Zoho's REST API requires the numeric long ID (Task.ID_LONG). "
            "Check your webhook URL: use task_id=${Task.ID_LONG}, not Task.TASKID."
        )

    token = await refresh_zoho_token(config, db)
    if not token:
        return False  # Token expired — skip silently, pipeline continues

    url = f"{ZOHO_API_BASE}/portal/{portal}/projects/{pid}/tasks/{task_id}/"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Zoho-oauthtoken {token}"},
                data={"percent_complete": str(status_name)},
            )
            # Always surface the response so mismatches are visible in logs
            if not resp.is_success:
                raise ValueError(
                    f"Zoho API {resp.status_code} for task {task_id}: {resp.text[:500]}"
                )
            # Parse confirmed status from response so caller can log it
            confirmed_status = status_name  # default fallback
            try:
                body = resp.json()
                confirmed_status = (
                    body.get("tasks", [{}])[0].get("status", {}).get("name")
                    or body.get("task", {}).get("status", {}).get("name")
                    or status_name
                )
            except Exception:
                pass
            if comment:
                await client.post(
                    f"{url}comments/",
                    headers={"Authorization": f"Zoho-oauthtoken {token}"},
                    data={"content": comment},
                )
        return confirmed_status
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Zoho request failed: {e}") from e


PIPELINE_STAGE_TO_ZOHO_STATUS = {
    "task_received": "10",
    "planning":      "10",
    "plan_review":   "20",
    "developing":    "70",
    "testing":       "80",
    "test_review":   "80",
    "creating_mr":   "90",
    "mr_open":       "90",
    "completed":     "100",
    "failed":        "10",
}


async def post_zoho_comment(
    config: ZohoConfig,
    task_id: str,
    comment: str,
    db: AsyncSession = None,
    portal_name: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bool:
    """Post a comment on a Zoho task without changing its status."""
    portal = portal_name or config.portal_name
    pid = project_id or config.project_id
    if not portal or not pid or not task_id or not task_id.isdigit():
        return False

    token = await refresh_zoho_token(config, db)
    if not token:
        return False

    url = f"{ZOHO_API_BASE}/portal/{portal}/projects/{pid}/tasks/{task_id}/comments/"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Zoho-oauthtoken {token}"},
                data={"content": comment},
            )
            return resp.is_success
    except Exception:
        return False

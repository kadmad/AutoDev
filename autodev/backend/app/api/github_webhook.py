"""
/github-webhook  — receives GitHub PR events (no JWT required).

Set up in GitHub → repo → Settings → Webhooks:
  Payload URL : http://<your-server>:8000/github-webhook
  Content type: application/json
  Secret      : value of GITHUB_WEBHOOK_SECRET in backend/.env
  Events      : Pull requests, Pull request reviews, Pull request review comments, Issue comments
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.merge_request import MergeRequest
from app.models.pipeline_run import PipelineRun
from app.models.project import Project
from app.models.user import ZohoConfig
from app.services.redis_service import publish_log, publish_stage, publish_pipeline_event
from app.services.zoho_service import post_zoho_comment

router = APIRouter()


def _verify_signature(body: bytes, signature_header: str) -> bool:
    """Return True if the payload matches the configured webhook secret."""
    if not settings.GITHUB_WEBHOOK_SECRET:
        return True  # No secret configured — skip verification (dev mode)
    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


async def _find_run_by_branch(branch: str, db: AsyncSession):
    """Return (pipeline_run, merge_request, project, zoho_config) for a branch, or Nones."""
    mr_result = await db.execute(
        select(MergeRequest)
        .where(MergeRequest.source_branch == branch)
        .order_by(MergeRequest.created_at.desc())
        .limit(1)
    )
    mr = mr_result.scalar_one_or_none()
    if not mr:
        return None, None, None, None

    run_result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == mr.pipeline_run_id)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        return None, mr, None, None

    proj_result = await db.execute(
        select(Project).where(Project.id == run.project_id)
    )
    project = proj_result.scalar_one_or_none()

    zoho_cfg = None
    if run.zoho_task_id and project:
        zc_result = await db.execute(
            select(ZohoConfig).where(ZohoConfig.user_id == project.user_id)
        )
        zoho_cfg = zc_result.scalar_one_or_none()

    return run, mr, project, zoho_cfg


@router.post("/github-webhook")
async def github_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()

    if not _verify_signature(body, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    content_type = request.headers.get("content-type", "")
    print(f"[GH-webhook] event={event!r} content-type={content_type!r}", flush=True)
    try:
        if "application/json" in content_type:
            payload = await request.json()
        else:
            # GitHub can send as application/x-www-form-urlencoded with JSON in 'payload' field
            import json as _json
            from urllib.parse import parse_qs
            form_data = parse_qs(body.decode("utf-8", errors="replace"))
            raw = form_data.get("payload", ["{}"])[0]
            payload = _json.loads(raw)
    except Exception as e:
        print(f"[GH-webhook] parse failed: {e!r} body[:200]={body[:200]!r}", flush=True)
        return {"ok": True}

    action = payload.get("action", "")
    print(f"[GH-webhook] action={action!r}", flush=True)

    # ── Pull Request opened/closed/merged ─────────────────────────────
    if event == "pull_request":
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        branch = pr.get("head", {}).get("ref", "")
        pr_url = pr.get("html_url", "")
        pr_title = pr.get("title", "")
        # Construct URL from repo + number if html_url is absent
        if not pr_url:
            repo = payload.get("repository", {})
            repo_full = repo.get("full_name", "") or f"{repo.get('owner', {}).get('login', '')}/{repo.get('name', '')}"
            pr_number = payload.get("number", "")
            if repo_full and pr_number:
                pr_url = f"https://github.com/{repo_full}/pull/{pr_number}"

        if action == "closed":
            merged = pr.get("merged", False)
            logger.info("[GH-webhook] PR closed event: branch=%r merged=%s url=%r", branch, merged, pr_url)

            run, mr, project, zoho_cfg = await _find_run_by_branch(branch, db)

            # Fallback: match by PR URL stored in merge_requests.mr_url
            if not mr and pr_url:
                fb_result = await db.execute(
                    select(MergeRequest).where(MergeRequest.mr_url == pr_url).limit(1)
                )
                mr_fb = fb_result.scalar_one_or_none()
                if mr_fb:
                    logger.info("[GH-webhook] Matched via mr_url fallback (branch in DB: %r)", mr_fb.source_branch)
                    run_result = await db.execute(
                        select(PipelineRun).where(PipelineRun.id == mr_fb.pipeline_run_id)
                    )
                    run = run_result.scalar_one_or_none()
                    mr = mr_fb
                    if run:
                        proj_result = await db.execute(select(Project).where(Project.id == run.project_id))
                        project = proj_result.scalar_one_or_none()
                        if project:
                            zc_result = await db.execute(select(ZohoConfig).where(ZohoConfig.user_id == project.user_id))
                            zoho_cfg = zc_result.scalar_one_or_none()

            if not mr:
                logger.warning("[GH-webhook] No MergeRequest found for branch=%r or url=%r — cannot update pipeline", branch, pr_url)
            else:
                logger.info("[GH-webhook] Found MR pipeline_run_id=%s run_status=%s", mr.pipeline_run_id, run.status if run else "NO RUN")

            if mr:
                mr.status = "merged" if merged else "closed"

            if run and run.status not in ("completed", "failed", "closed"):
                run_id = str(run.id)
                # Capture all attributes BEFORE commit (commit expires ORM objects)
                zoho_task_id = run.zoho_task_id
                user_id = str(project.user_id) if project else None
                portal = project.zoho_portal_name if project else None
                proj_id = project.zoho_project_id if project else None

                if merged:
                    run.status = "completed"
                    run.current_stage = "completed"
                    await db.commit()
                    publish_stage(run_id, "completed")
                    publish_log(run_id, "[GitHub] PR merged → pipeline marked completed ✅")
                    if user_id:
                        publish_pipeline_event(user_id, run_id, "completed", "completed")
                    if zoho_cfg and zoho_task_id:
                        await post_zoho_comment(
                            config=zoho_cfg,
                            task_id=zoho_task_id,
                            comment=f"✅ PR merged and pipeline completed.\n\n{pr_url}",
                            db=db,
                            portal_name=portal,
                            project_id=proj_id,
                        )
                else:
                    run.status = "closed"
                    # Keep current_stage as pr_open so UI highlights the right stage
                    run.error_message = f"PR closed without merging: {pr_url}"
                    await db.commit()
                    publish_stage(run_id, "closed")
                    publish_log(run_id, "[GitHub] PR closed (not merged) → pipeline marked closed")
                    if user_id:
                        publish_pipeline_event(user_id, run_id, "closed", "closed")
                    if zoho_cfg and zoho_task_id:
                        await post_zoho_comment(
                            config=zoho_cfg,
                            task_id=zoho_task_id,
                            comment=f"❌ PR was closed without merging.\n\nPR: {pr_url}",
                            db=db,
                            portal_name=portal,
                            project_id=proj_id,
                        )
            await db.commit()

    # ── PR Review submitted ────────────────────────────────────────────
    elif event == "pull_request_review":
        review = payload.get("review", {})
        pr = payload.get("pull_request", {})
        branch = pr.get("head", {}).get("ref", "")
        reviewer = review.get("user", {}).get("login", "Someone")
        state = review.get("state", "commented").upper()
        body_text = (review.get("body") or "").strip()
        pr_url = pr.get("html_url", "")

        if body_text:
            run, mr, project, zoho_cfg = await _find_run_by_branch(branch, db)
            if zoho_cfg and run and run.zoho_task_id:
                state_icon = {"APPROVED": "✅", "CHANGES_REQUESTED": "🔄", "COMMENTED": "💬"}.get(state, "💬")
                comment = (
                    f"{state_icon} GitHub PR Review — {state} by @{reviewer}\n\n"
                    f"{body_text}\n\n"
                    f"PR: {pr_url}"
                )
                await post_zoho_comment(
                    config=zoho_cfg,
                    task_id=run.zoho_task_id,
                    comment=comment,
                    db=db,
                    portal_name=project.zoho_portal_name if project else None,
                    project_id=project.zoho_project_id if project else None,
                )

    # ── Inline PR review comment ───────────────────────────────────────
    elif event == "pull_request_review_comment":
        comment_obj = payload.get("comment", {})
        pr = payload.get("pull_request", {})
        branch = pr.get("head", {}).get("ref", "")
        author = comment_obj.get("user", {}).get("login", "Someone")
        body_text = (comment_obj.get("body") or "").strip()
        file_path = comment_obj.get("path", "")
        pr_url = pr.get("html_url", "")

        if body_text:
            run, mr, project, zoho_cfg = await _find_run_by_branch(branch, db)
            if zoho_cfg and run and run.zoho_task_id:
                location = f" on `{file_path}`" if file_path else ""
                comment = (
                    f"💬 GitHub PR comment{location} by @{author}\n\n"
                    f"{body_text}\n\n"
                    f"PR: {pr_url}"
                )
                await post_zoho_comment(
                    config=zoho_cfg,
                    task_id=run.zoho_task_id,
                    comment=comment,
                    db=db,
                    portal_name=project.zoho_portal_name if project else None,
                    project_id=project.zoho_project_id if project else None,
                )

    # ── Regular comment on PR (issue_comment on a pull request) ──────
    elif event == "issue_comment":
        issue = payload.get("issue", {})
        if "pull_request" not in issue:
            return {"ok": True}  # Regular issue comment, not a PR — ignore
        comment_obj = payload.get("comment", {})
        pr_api_url = issue.get("pull_request", {}).get("url", "")
        author = comment_obj.get("user", {}).get("login", "Someone")
        body_text = (comment_obj.get("body") or "").strip()
        pr_html_url = issue.get("html_url", "")

        if body_text and pr_api_url:
            # Derive branch from PR URL by fetching the PR — instead, look up by PR html_url
            # Match by mr_url stored in our DB
            mr_result = await db.execute(
                select(MergeRequest)
                .where(MergeRequest.mr_url == pr_html_url)
                .limit(1)
            )
            mr = mr_result.scalar_one_or_none()
            if mr:
                run_result = await db.execute(
                    select(PipelineRun).where(PipelineRun.id == mr.pipeline_run_id)
                )
                run = run_result.scalar_one_or_none()
                if run and run.zoho_task_id:
                    proj_result = await db.execute(
                        select(Project).where(Project.id == run.project_id)
                    )
                    project = proj_result.scalar_one_or_none()
                    zc_result = await db.execute(
                        select(ZohoConfig).where(ZohoConfig.user_id == project.user_id)
                    )
                    zoho_cfg = zc_result.scalar_one_or_none()
                    if zoho_cfg:
                        await post_zoho_comment(
                            config=zoho_cfg,
                            task_id=run.zoho_task_id,
                            comment=f"💬 GitHub PR comment by @{author}\n\n{body_text}\n\nPR: {pr_html_url}",
                            db=db,
                            portal_name=project.zoho_portal_name if project else None,
                            project_id=project.zoho_project_id if project else None,
                        )

    return {"ok": True}

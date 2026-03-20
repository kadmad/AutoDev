"""
GitHub OAuth and API service.
Uses httpx.AsyncClient for all HTTP calls.
"""
import asyncio
import re
from typing import Optional
import httpx

from app.config import settings


def get_github_auth_url() -> str:
    """Return the GitHub OAuth authorization URL."""
    params = (
        f"client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
        f"&scope=repo,user:email"
    )
    return f"https://github.com/login/oauth/authorize?{params}"


async def exchange_code_for_token(code: str) -> dict:
    """Exchange the OAuth authorization code for an access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_github_user(token: str) -> dict:
    """Fetch the authenticated user's profile from GitHub."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def list_user_repos(token: str) -> list[dict]:
    """Return up to 50 repos for the authenticated user, sorted by recently updated."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user/repos",
            params={"sort": "updated", "per_page": 50},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_repo_info(token: str, owner: str, repo: str) -> dict:
    """Return basic repo info including default_branch."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def create_pull_request(
    token: str,
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str,
) -> dict:
    """
    Create a Pull Request on GitHub.
    If the requested base branch doesn't exist, falls back to the repo's default_branch.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )

        if resp.status_code == 422:
            # Base branch may not exist — retry with the repo's default branch
            try:
                repo_info = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                default_branch = repo_info.json().get("default_branch", "main")
            except Exception:
                default_branch = "main"

            if default_branch != base:
                retry = await client.post(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                    json={
                        "title": title,
                        "body": body,
                        "head": head,
                        "base": default_branch,
                    },
                )
                if retry.status_code < 300:
                    return retry.json()

            # Surface the original 422 with the full response body
            detail = resp.json()
            raise httpx.HTTPStatusError(
                f"422 from GitHub: {detail}",
                request=resp.request,
                response=resp,
            )

        resp.raise_for_status()
        return resp.json()


async def commit_to_feature_branch(
    project_dir: str,
    branch_name: str,
    base_branch: str = "main",
    commit_message: str = "",
) -> tuple[bool, str]:
    """
    Stage all of Claude's changes and commit them to a local feature branch.
    Does NOT push to remote — that happens after tests are approved.

    The feature branch is always (re-)created from base_branch so subsequent
    rework cycles produce a single clean commit on top of the latest base.
    Returns (success: bool, message: str).
    """
    async def _run(*args: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    # Verify this is a git repo
    rc, _, _ = await _run("git", "rev-parse", "--git-dir")
    if rc != 0:
        return False, "Not a git repository — skipping local commit"

    # Stash Claude's uncommitted changes so we can safely switch branches
    rc, stash_out, _ = await _run("git", "stash", "--include-untracked")
    has_stash = rc == 0 and "No local changes to save" not in stash_out

    # Create (or reset) the feature branch from the local base branch
    rc, out, err = await _run("git", "checkout", "-B", branch_name, base_branch)
    if rc != 0:
        # Fallback: create/switch without specifying a start point
        rc2, out2, err2 = await _run("git", "checkout", "-B", branch_name)
        if rc2 != 0:
            if has_stash:
                await _run("git", "stash", "pop")
            return False, f"git checkout failed: {err2}"

    # Re-apply Claude's changes onto the feature branch
    if has_stash:
        await _run("git", "stash", "pop")
        # rc=1 can mean conflicts but files are still applied; treat as non-fatal

    # Stage all changes
    rc, out, err = await _run("git", "add", "-A")
    if rc != 0:
        return False, f"git add failed: {err}"

    # Nothing to commit? That's fine — branch exists, diff will be empty
    rc_s, status_out, _ = await _run("git", "status", "--porcelain")
    if not status_out.strip():
        return True, f"Branch {branch_name} created (nothing new to commit)"

    # Commit
    commit_msg = commit_message or re.sub(r'\bAILegal\b', 'AI Legal', f"[AutoDev] {branch_name}")
    rc, out, err = await _run("git", "commit", "-m", commit_msg)
    if rc not in (0, 1):
        return False, f"git commit failed: {err}"

    return True, f"Changes committed locally to branch {branch_name}"


async def push_committed_branch(
    project_dir: str,
    branch_name: str,
    token: str,
    repo_full_name: str,
) -> tuple[bool, str]:
    """
    Push an already-committed local feature branch to GitHub.
    The branch must already exist locally (committed by commit_to_feature_branch).
    Returns (success: bool, message: str).
    """
    remote_url = f"https://{token}@github.com/{repo_full_name}.git"

    async def _run(*args: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    # Make sure we're on the feature branch
    rc, _, err = await _run("git", "checkout", branch_name)
    if rc != 0:
        return False, f"Could not checkout {branch_name}: {err}"

    # Push with --force-with-lease (handles rework re-commits cleanly)
    rc, out, err = await _run("git", "push", "--force-with-lease", remote_url, branch_name)
    if rc != 0:
        # Retry without lease (branch may not exist remotely yet)
        rc2, out2, err2 = await _run("git", "push", remote_url, branch_name)
        if rc2 != 0:
            return False, f"git push failed: {err2}"

    return True, f"Branch {branch_name} pushed to {repo_full_name}"


async def get_changed_files(
    project_dir: str,
) -> list[dict]:
    """
    Return files with uncommitted changes in the working directory.
    Covers both tracked modifications and new (untracked) files.
    Each entry: {"path": str, "additions": int, "deletions": int}
    """
    async def _run(*args: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    rc, _, _ = await _run("git", "rev-parse", "--git-dir")
    if rc != 0:
        return []

    files: dict[str, dict] = {}

    # Tracked modifications (vs HEAD)
    rc, out, _ = await _run("git", "diff", "HEAD", "--numstat")
    for line in (out or "").strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            add_str, del_str, path = parts
            try:
                files[path] = {
                    "path": path,
                    "additions": int(add_str) if add_str != "-" else 0,
                    "deletions": int(del_str) if del_str != "-" else 0,
                }
            except ValueError:
                pass

    # New (untracked) files — no line stats available
    rc, out, _ = await _run("git", "ls-files", "--others", "--exclude-standard")
    for path in (out or "").strip().splitlines():
        path = path.strip()
        if path and path not in files:
            files[path] = {"path": path, "additions": 0, "deletions": 0}

    return list(files.values())


async def push_branch(
    project_dir: str,
    branch_name: str,
    token: str,
    repo_full_name: str,
    base_branch: str = "main",
    commit_message: str = "",
) -> tuple[bool, str]:
    """
    Legacy helper: commit locally then push in one step.
    Prefer commit_to_feature_branch + push_committed_branch for new code.
    """
    ok, msg = await commit_to_feature_branch(project_dir, branch_name, base_branch, commit_message)
    if not ok:
        return False, msg
    return await push_committed_branch(project_dir, branch_name, token, repo_full_name)

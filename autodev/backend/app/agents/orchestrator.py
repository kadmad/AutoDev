"""
Pipeline Orchestrator — state machine that drives pipeline runs.
Called by the rq worker for each pipeline run.
"""
import asyncio
import traceback
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.pipeline_run import PipelineRun
from app.models.project import Project
from app.models.plan import Plan
from app.models.test_result import TestResult
from app.models.merge_request import MergeRequest
from app.models.user import ZohoConfig
from app.models.git_config import GitConfig
import re
import json
import uuid as _uuid
from app.agents.planner import PlannerAgent
from app.agents.backend_developer import BackendDeveloperAgent
from app.agents.frontend_developer import FrontendDeveloperAgent
from app.agents.monolithic_developer import MonolithicDeveloperAgent
from app.agents.pr_creator import PRCreatorAgent, PRCreatorAgent as PRC
from app.agents.zoho_updater import ZohoUpdaterAgent
from app.services.redis_service import publish_stage, publish_log, publish_pipeline_event
from app.services import github_service


async def run_pipeline(run_id: str, project_id: str):
    """Main orchestrator entry point — called by rq worker."""
    async with AsyncSessionLocal() as db:
        try:
            run = await _get_run(db, run_id)
            if not run:
                return

            project = await _get_project(db, project_id)
            if not project:
                return

            await _orchestrate(db, run, project)
        except Exception as e:
            # Fetch run again in case the session is poisoned
            tb = traceback.format_exc()
            error_msg = repr(e) if not str(e) else str(e)
            print(f"[Orchestrator] UNCAUGHT EXCEPTION for run {run_id}:\n{tb}", flush=True)
            try:
                async with AsyncSessionLocal() as db2:
                    run2 = await _get_run(db2, run_id)
                    if run2:
                        await _fail(db2, run2, error_msg)
            except Exception:
                pass


async def _orchestrate(db: AsyncSession, run: PipelineRun, project: Project):
    run_id = str(run.id)

    # Stage: task_received → planning
    if run.status == "task_received":
        # Immediately mark In Progress in Zoho before doing anything else
        await _update_zoho(db, run, project, "planning")
        await _transition(db, run, "planning")

    # Stage: planning
    if run.status == "planning":
        await _do_planning(db, run, project)
        return  # Pause at plan_review

    # Stage: developing (triggered by /plan/approve)
    came_from_development = False
    if run.status == "developing":
        await _do_development(db, run, project)
        came_from_development = True
        # Fall through: _do_development transitions to "testing",
        # so the next if block runs immediately in the same orchestrator call.

    # Stage: testing — run playwright tests, then pause for human verification
    if run.status == "testing":
        if came_from_development:
            # Always re-run: fresh code was just written, playwright must re-test
            await _do_testing(db, run, project)
        else:
            # Re-enqueued while paused at testing (e.g. server restart) —
            # only run setup if no scenarios exist yet.
            existing = await db.execute(
                select(TestResult).where(TestResult.pipeline_run_id == run.id).limit(1)
            )
            tr = existing.scalar_one_or_none()
            has_scenarios = tr and tr.scenarios and tr.scenarios not in ('[]', '', 'null')
            if not has_scenarios:
                await _do_testing(db, run, project)
        return  # Pause here — user reviews results and clicks approve/rework

    # Stage: creating_mr (triggered by /tests/approve)
    if run.status == "creating_mr":
        await _do_create_mr(db, run, project)
        return


async def _do_planning(db: AsyncSession, run: PipelineRun, project: Project):
    run_id = str(run.id)

    # Find previous feedback if replanning
    last_plan_result = await db.execute(
        select(Plan)
        .where(Plan.pipeline_run_id == run.id)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    last_plan = last_plan_result.scalar_one_or_none()
    feedback = last_plan.user_edits if last_plan else ""

    agent = PlannerAgent(run_id)
    cwd = project.monolithic_dir or project.backend_dir or project.frontend_dir or "/tmp"

    result = await agent.run(
        project_dir=cwd,
        frontend_tech=project.frontend_tech or "react",
        backend_tech=project.backend_tech or "fastapi",
        task_title=run.zoho_task_title or "Untitled Task",
        task_description=run.zoho_task_description or "",
        previous_feedback=feedback,
        db=db,
    )

    if not result.success:
        await _fail(db, run, result.error or "Planning failed")
        return

    # Upsert plan (update content if replanning, else create)
    version = (last_plan.version if last_plan else 0) + 1
    if last_plan and not last_plan.content:
        # Empty plan created by replan API — fill it
        last_plan.content = result.output
        last_plan.version = version
    else:
        plan = Plan(
            pipeline_run_id=run.id,
            content=result.output,
            version=version,
        )
        db.add(plan)

    await _transition(db, run, "plan_review")
    await db.commit()
    publish_stage(run_id, "plan_review")
    await _update_zoho(db, run, project, "plan_review", comment=_fmt_plan_comment(result.output))


async def _do_development(db: AsyncSession, run: PipelineRun, project: Project):
    run_id = str(run.id)

    # Get approved plan
    plan_result = await db.execute(
        select(Plan)
        .where(Plan.pipeline_run_id == run.id, Plan.approved_at.isnot(None))
        .order_by(Plan.version.desc())
        .limit(1)
    )
    plan = plan_result.scalar_one_or_none()
    plan_content = plan.content if plan else ""

    await _update_zoho(db, run, project, "developing", comment=_fmt_dev_start_comment(run, project))

    project_dir = project.monolithic_dir or project.backend_dir or project.frontend_dir or "/tmp"
    base_branch = project.base_branch or "develop"

    # Pull latest from base branch before starting work to reduce merge conflicts
    publish_log(run_id, f"[system] Pulling latest from {base_branch} before development...")
    pull_proc = await asyncio.create_subprocess_exec(
        "git", "pull", "origin", base_branch,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    pull_stdout, pull_stderr = await pull_proc.communicate()
    if pull_proc.returncode == 0:
        publish_log(run_id, f"[system] git pull origin {base_branch} — OK")
    else:
        publish_log(run_id, f"[system] git pull origin {base_branch} — warning: {pull_stderr.decode().strip()[:200]}")

    # Capture HEAD SHA before agents run so we can undo any commits they make
    head_before = await _git_head_sha(project_dir)

    tasks = []
    task_number = run.zoho_task_number or ""

    if project.monolithic_dir:
        # Single agent handles everything in one directory (Django, Rails, etc.)
        publish_log(run_id, f"[Orchestrator] Monolithic project — running single agent in {project.monolithic_dir}")
        mono_agent = MonolithicDeveloperAgent(run_id)
        tech_stack = " + ".join(filter(None, [project.backend_tech, project.frontend_tech]))
        tasks.append(mono_agent.run(
            project_dir=project.monolithic_dir,
            task_title=run.zoho_task_title or "",
            approved_plan=plan_content,
            tech_stack=tech_stack,
            task_number=task_number,
            db=db,
        ))
    else:
        # Separate backend / frontend agents run in parallel
        if project.backend_dir:
            backend_agent = BackendDeveloperAgent(run_id)
            tasks.append(backend_agent.run(
                backend_dir=project.backend_dir,
                backend_tech=project.backend_tech or "fastapi",
                task_title=run.zoho_task_title or "",
                approved_plan=plan_content,
                task_number=task_number,
                db=db,
            ))

        if project.frontend_dir:
            frontend_agent = FrontendDeveloperAgent(run_id)
            tasks.append(frontend_agent.run(
                frontend_dir=project.frontend_dir,
                frontend_tech=project.frontend_tech or "react",
                task_title=run.zoho_task_title or "",
                approved_plan=plan_content,
                task_number=task_number,
                db=db,
            ))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception) or (hasattr(r, "success") and not r.success):
                error = str(r) if isinstance(r, Exception) else r.error
                await _fail(db, run, f"Development failed: {error}")
                return

    # Safety net: if the agents committed despite being told not to, undo those
    # commits while keeping all file changes in the working directory.
    if head_before:
        await _undo_agent_commits(project_dir, head_before, run_id)

    # Pre-compute branch name and store it so the testing stage diff endpoint
    # can reference it, but do NOT commit or push yet — that happens only after
    # the user approves the manual test cases.
    branch_name = PRC.make_branch_name(
        run.zoho_task_id or str(run.id),
        run.zoho_task_title or "autodev-task",
        task_number=run.zoho_task_number or "",
    )
    run.feature_branch = branch_name
    await db.commit()

    await _transition(db, run, "testing")
    await db.commit()
    publish_stage(run_id, "testing")


async def _do_testing(db: AsyncSession, run: PipelineRun, project: Project):
    run_id = str(run.id)

    await _update_zoho(db, run, project, "testing", comment=_fmt_testing_comment())

    # Get the latest plan (prefer approved, fall back to any)
    plan_result = await db.execute(
        select(Plan)
        .where(Plan.pipeline_run_id == run.id)
        .order_by(Plan.approved_at.desc().nullslast(), Plan.version.desc())
        .limit(1)
    )
    plan = plan_result.scalar_one_or_none()
    plan_content = plan.content if plan else ""

    publish_log(run_id, f"[Orchestrator] Plan content length: {len(plan_content)} chars")
    if plan_content:
        # Log the test scenarios section of the plan for debugging
        snippet_start = plan_content.lower().find("manual test")
        if snippet_start == -1:
            snippet_start = plan_content.lower().find("scenario")
        if snippet_start >= 0:
            publish_log(run_id, f"[Orchestrator] Plan snippet: {plan_content[snippet_start:snippet_start+400]}")
    all_scenarios = _extract_scenarios_from_plan(plan_content)
    playwright_scenarios = [s for s in all_scenarios if s.get('type') == 'playwright']
    manual_scenarios = [s for s in all_scenarios if s.get('type') != 'playwright']
    publish_log(run_id, f"[Orchestrator] Extracted {len(playwright_scenarios)} playwright + {len(manual_scenarios)} manual scenario(s)")
    for i, s in enumerate(all_scenarios):
        publish_log(run_id, f"[Orchestrator]   [{i+1}] [{s.get('type','manual')}] {s['name']}")

    browser_output = None
    browser_status = "skipped"

    if playwright_scenarios and project.server_start_command and project.server_port:
        publish_log(run_id, "[Orchestrator] Starting project server for browser tests...")
        server_proc = await asyncio.create_subprocess_shell(
            project.server_start_command,
            cwd=project.backend_dir or project.frontend_dir or "/tmp",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.sleep(5)  # allow server to boot
        try:
            from app.agents.browser_test_agent import BrowserTestAgent
            b_agent = BrowserTestAgent(run_id=run_id)
            # Close the DB session before the long-running browser test so the
            # connection isn't held idle (PostgreSQL drops idle connections).
            await db.close()
            b_result = await b_agent.run(
                project_dir=project.backend_dir or project.frontend_dir or "/tmp",
                port=project.server_port,
                task_title=run.zoho_task_title or "",
                task_description=run.zoho_task_description or "",
                scenarios=playwright_scenarios,
                db=None,
            )
            browser_output = b_result.output
            # Parse per-scenario results and update each playwright scenario's status
            per_scenario = _parse_per_scenario_results(browser_output or "", playwright_scenarios)
            for s in playwright_scenarios:
                s['status'] = per_scenario.get(s['id'], 'failed' if not b_result.success else 'passed')
            browser_status = "passed" if all(s['status'] == 'passed' for s in playwright_scenarios) else "failed"
        except Exception as e:
            publish_log(run_id, f"[Orchestrator] Browser tests error: {e}\n{traceback.format_exc()}")
            browser_status = "error"
            for s in playwright_scenarios:
                s['status'] = 'pending'
        finally:
            try:
                server_proc.terminate()
            except ProcessLookupError:
                pass  # process already exited — that's fine
            publish_log(run_id, "[Orchestrator] Project server stopped")
    elif playwright_scenarios:
        publish_log(run_id, "[Orchestrator] No server configured — playwright scenarios skipped")
        browser_status = "skipped"
    else:
        publish_log(run_id, "[Orchestrator] No playwright scenarios — skipping browser tests")

    # Combine: playwright first (with auto-status), then manual
    scenarios = playwright_scenarios + manual_scenarios

    publish_log(run_id, "[Orchestrator] Waiting for user to complete manual testing…")

    # Use a fresh DB session after potentially long browser test gap
    from app.models.test_result import TestResult
    async with AsyncSessionLocal() as fresh_db:
        test = TestResult(
            pipeline_run_id=run.id,
            total=len(scenarios),
            passed=0,
            failed=0,
            skipped=0,
            scenarios=json.dumps(scenarios),
            raw_output=f"{len(playwright_scenarios)} playwright + {len(manual_scenarios)} manual scenario(s)",
            browser_test_output=browser_output,
            browser_test_status=browser_status,
        )
        fresh_db.add(test)
        await fresh_db.commit()

    # Stay at 'testing' — this is the interactive human gate.
    # The user will tick off scenarios and click "Testing Done".
    # The approve_tests API endpoint will then advance to creating_mr.
    publish_stage(run_id, "testing")


async def _do_create_mr(db: AsyncSession, run: PipelineRun, project: Project):
    run_id = str(run.id)

    # Fetch the user's git config, preferring the provider set on the project
    preferred_provider = project.git_provider  # "github", "gitlab", or None
    git_config = None

    if preferred_provider:
        gc_result = await db.execute(
            select(GitConfig).where(
                GitConfig.user_id == project.user_id,
                GitConfig.provider == preferred_provider,
            )
        )
        git_config = gc_result.scalar_one_or_none()

    # Fall back: pick any connected provider if project has no explicit provider set
    if git_config is None and not preferred_provider:
        gc_result = await db.execute(
            select(GitConfig)
            .where(GitConfig.user_id == project.user_id, GitConfig.access_token.isnot(None))
            .limit(1)
        )
        git_config = gc_result.scalar_one_or_none()

    # Determine whether any git provider is configured
    has_github = project.git_provider == "github" or (
        git_config and git_config.provider == "github" and git_config.access_token
    )
    has_gitlab = project.git_provider == "gitlab" or project.gitlab_repo_url or project.gitlab_project_id

    if not has_github and not has_gitlab:
        publish_log(run_id, "[Orchestrator] No git provider configured — skipping PR creation")
        await _transition(db, run, "completed")
        await db.commit()
        publish_stage(run_id, "completed")
        await _update_zoho(
            db, run, project, "completed",
            comment="✅ AutoDev implementation complete. No git provider is configured, so no PR was created.",
        )
        return

    await _update_zoho(db, run, project, "creating_mr")

    # Get plan content
    plan_result = await db.execute(
        select(Plan)
        .where(Plan.pipeline_run_id == run.id)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    plan = plan_result.scalar_one_or_none()

    branch_name = PRC.make_branch_name(
        run.zoho_task_id or str(run.id),
        run.zoho_task_title or "autodev-task",
        task_number=run.zoho_task_number or "",
    )
    run.feature_branch = branch_name
    await db.commit()

    # Resolve provider and token
    effective_provider = project.git_provider or (git_config.provider if git_config else None)
    effective_token = (
        git_config.access_token
        if git_config and git_config.access_token
        else (project.gitlab_token or "")
    )
    effective_repo = project.repo_full_name or ""
    project_dir = project.backend_dir or project.frontend_dir or "/tmp"

    # Fetch final test scenarios (if user ran manual testing)
    test_scenarios = None
    _tr_result = await db.execute(
        select(TestResult)
        .where(TestResult.pipeline_run_id == run.id)
        .order_by(TestResult.created_at.desc())
        .limit(1)
    )
    _tr = _tr_result.scalar_one_or_none()
    if _tr and _tr.scenarios:
        try:
            test_scenarios = json.loads(_tr.scenarios)
        except Exception:
            pass

    agent = PRCreatorAgent(run_id)
    result = await agent.run(
        feature_branch=branch_name,
        base_branch=project.base_branch,
        task_title=run.zoho_task_title or "",
        task_description=run.zoho_task_description or "",
        plan_content=plan.content if plan else "",
        pr_checklist=project.pr_checklist or [],
        gitlab_repo_url=project.gitlab_repo_url or "",
        gitlab_project_id=project.gitlab_project_id or "",
        gitlab_token=project.gitlab_token or "",
        git_provider=effective_provider,
        repo_full_name=effective_repo,
        git_token=effective_token,
        project_dir=project_dir,
        task_number=run.zoho_task_number or "",
        test_scenarios=test_scenarios,
        db=db,
    )

    if not result.success:
        await _fail(db, run, result.error or "MR creation failed")
        return

    # Parse MR URL, ID, and actual base branch from output
    mr_url = ""
    mr_id = ""
    actual_base_branch = project.base_branch  # default; overridden if GitHub used a fallback
    for line in result.output.splitlines():
        if "MR created:" in line:
            mr_url = line.split("MR created:")[-1].strip()
        if "MR ID:" in line:
            mr_id = line.split("MR ID:")[-1].strip()
        if "Base branch:" in line:
            actual_base_branch = line.split("Base branch:")[-1].strip()

    # Save MR record with the branch GitHub actually used
    mr = MergeRequest(
        pipeline_run_id=run.id,
        gitlab_mr_id=mr_id,
        mr_url=mr_url,
        title=f"[AutoDev] {run.zoho_task_title}",
        source_branch=branch_name,
        target_branch=actual_base_branch,
        status="open",
    )
    db.add(mr)

    # Transition to pr_open — pipeline stays here until GitHub webhook fires.
    # Completed/closed is set only when the PR is merged or closed on GitHub.
    await _transition(db, run, "pr_open")
    await db.commit()
    publish_stage(run_id, "pr_open")

    # Post PR link to Zoho as a comment only — do NOT change the % complete
    if run.zoho_task_id:
        config_result = await db.execute(
            select(ZohoConfig).where(ZohoConfig.user_id == project.user_id)
        )
        config = config_result.scalar_one_or_none()
        if config:
            from app.services.zoho_service import post_zoho_comment
            await post_zoho_comment(
                config=config,
                task_id=run.zoho_task_id,
                comment=_fmt_pr_comment(
                    branch_name=branch_name,
                    base_branch=actual_base_branch,
                    mr_url=mr_url,
                    task_title=run.zoho_task_title or "",
                ),
                db=db,
                portal_name=project.zoho_portal_name or None,
                project_id=project.zoho_project_id or None,
            )


async def _fail(db: AsyncSession, run: PipelineRun, error: str):
    # Rollback any failed transaction before writing — prevents "session in error state" bug
    try:
        await db.rollback()
    except Exception:
        pass
    run.status = "failed"
    # Keep current_stage as the actual last stage so UI can highlight where it failed
    run.error_message = error
    await db.commit()
    publish_stage(str(run.id), "failed")
    publish_log(str(run.id), f"[Orchestrator] Pipeline FAILED: {error}")
    try:
        project = await _get_project(db, str(run.project_id))
        if project:
            publish_pipeline_event(str(project.user_id), str(run.id), "failed", "failed")
    except Exception:
        pass


async def _transition(db: AsyncSession, run: PipelineRun, new_status: str):
    run.status = new_status
    run.current_stage = new_status
    await db.commit()
    publish_log(str(run.id), f"[Orchestrator] → {new_status}")
    project = await _get_project(db, str(run.project_id))
    if project:
        publish_pipeline_event(str(project.user_id), str(run.id), new_status, new_status)


async def _update_zoho(db: AsyncSession, run: PipelineRun, project: Project, stage: str, comment: str = None):
    if not run.zoho_task_id:
        return
    config_result = await db.execute(
        select(ZohoConfig).where(ZohoConfig.user_id == project.user_id)
    )
    config = config_result.scalar_one_or_none()
    if not config:
        return

    updater = ZohoUpdaterAgent(str(run.id))
    await updater.run(
        pipeline_stage=stage,
        zoho_task_id=run.zoho_task_id,
        zoho_config=config,
        db=db,
        comment=comment,
        portal_name=project.zoho_portal_name or None,
        project_id=project.zoho_project_id or None,
    )


def _fmt_plan_comment(plan_content: str) -> str:
    body = plan_content[:3000] + ("…\n[truncated]" if len(plan_content) > 3000 else "")
    return (
        "📋 AutoDev generated an implementation plan — awaiting your approval.\n\n"
        + body
    )


def _fmt_dev_start_comment(run: PipelineRun, project: Project) -> str:
    lines = ["🚀 AutoDev has started implementation based on the approved plan.\n"]
    if project.backend_dir and project.backend_tech:
        lines.append(f"• Backend ({project.backend_tech}): {project.backend_dir}")
    if project.frontend_dir and project.frontend_tech:
        lines.append(f"• Frontend ({project.frontend_tech}): {project.frontend_dir}")
    lines.append("\nCode changes are being written now.")
    return "\n".join(lines)


def _fmt_testing_comment() -> str:
    return (
        "✅ Implementation complete. Manual test scenarios have been prepared.\n\n"
        "Please review the test scenarios in the AutoDev dashboard and verify each one manually."
    )


def _find_plan_section(plan_content: str, header_pattern: str) -> str:
    """
    Robust line-by-line section extractor.
    Finds the first line containing header_pattern (case-insensitive),
    then captures body lines until the next heading-like line.
    Handles any prefix: '3. **Playwright...', '## Playwright...', '**Playwright...', etc.
    """
    header_re = re.compile(header_pattern, re.IGNORECASE)
    # Matches lines that start a new section (number+dot, #heading, or bold ALL-CAPS word)
    next_heading_re = re.compile(r'^\s*(?:#{1,6}\s|\d+\.\s|[-*]\s*\*\*[A-Z]|\*\*[A-Z])', re.IGNORECASE)

    lines = plan_content.splitlines()
    start = None
    for i, line in enumerate(lines):
        if header_re.search(line):
            start = i + 1
            break
    if start is None:
        return ""

    body_lines = []
    for line in lines[start:]:
        # Stop at the next major section heading
        if next_heading_re.match(line) and body_lines:
            break
        body_lines.append(line)

    return "\n".join(body_lines).strip()


def _parse_scenario_chunks(section: str, prefix_pattern: str, type_tag: str) -> list[dict]:
    """Split a plan section on scenario headings and return structured dicts."""
    results = []
    chunks = re.split(r'(?i)(?:\*\*\s*)?' + prefix_pattern + r'\s*', section)
    for chunk in chunks[1:]:
        chunk = chunk.strip()
        if not chunk:
            continue
        name_m = re.match(r'(.+?)(?=\*\*|\s+Steps?:|\s+Expected|\n|$)', chunk)
        name = name_m.group(1).strip() if name_m else chunk.split('\n')[0].strip()
        if not name:
            continue
        steps_m = re.search(r'\*{0,2}[Ss]teps?\*{0,2}:?\s*(.+?)(?=\s*\*{0,2}[Ee]xpected[^:]*:|\Z)', chunk, re.DOTALL)
        expected_m = re.search(r'\*{0,2}[Ee]xpected[^:\n]*:\*{0,2}\s*(.+)', chunk, re.DOTALL)
        results.append({
            'id': str(_uuid.uuid4())[:8],
            'name': name,
            'steps': steps_m.group(1).strip() if steps_m else '',
            'expected': expected_m.group(1).strip() if expected_m else '',
            'status': 'pending',
            'type': type_tag,
        })
    return results


def _extract_scenarios_from_plan(plan_content: str) -> list[dict]:
    """
    Parse test scenarios from the plan, splitting into 'playwright' and 'manual' types.
    New planner format produces two sections:
      - "Playwright Test Scenarios" → type: "playwright"
      - "Manual Test Scenarios"    → type: "manual"
    Fallback for old plans: all scenarios tagged as "manual".
    """
    if not plan_content:
        return []

    playwright_section = _find_plan_section(plan_content, r'Playwright\s+Test\s+Scenarios?')
    manual_section = _find_plan_section(plan_content, r'Manual\s+Test\s+Scenarios?')

    scenarios: list[dict] = []

    if playwright_section:
        scenarios.extend(_parse_scenario_chunks(playwright_section, r'Playwright\s+Scenario:', 'playwright'))

    if manual_section:
        # Use strict prefix so "Playwright Scenario:" is NOT matched here
        scenarios.extend(_parse_scenario_chunks(manual_section, r'(?<!Playwright\s)Scenario:', 'manual'))

    if scenarios:
        return scenarios

    # ── Fallback: old plan format — parse ALL scenario types from whole doc ──
    # Tag "Playwright Scenario:" items as playwright, plain "Scenario:" as manual.
    all_scenarios = _parse_scenario_chunks(plan_content, r'Playwright\s+Scenario:', 'playwright')
    all_scenarios += [
        s for s in _parse_scenario_chunks(plan_content, r'(?<![Pp]laywright\s)Scenario:', 'manual')
        # deduplicate by name against already-found playwright ones
        if not any(p['name'] == s['name'] for p in all_scenarios)
    ]
    if all_scenarios:
        return all_scenarios

    # ── Last resort: numbered / bullet list items ──
    fallback_section = _find_plan_section(
        plan_content, r'(?:Manual\s+)?Test\s+(?:Scenarios?|Cases?|Steps?)'
    ) or plan_content
    for m in re.finditer(
        r'(?:^|\n)[ \t]*(?:\d+[\.\)]\s+|\-\s+|\*\s+)([^\n]{8,})',
        fallback_section,
    ):
        name = m.group(1).strip()
        if name.startswith('→') or len(name) < 8:
            continue
        scenarios.append({
            'id': str(_uuid.uuid4())[:8],
            'name': name,
            'steps': '',
            'expected': '',
            'status': 'pending',
            'type': 'manual',
        })

    return scenarios


def _parse_per_scenario_results(output: str, scenarios: list[dict]) -> dict[str, str]:
    """
    Match per-scenario pass/fail from Claude's markdown report.
    Returns {scenario_id: "passed" | "failed"}.
    Looks for the scenario name followed by a "Status: PASSED/FAILED" line.
    """
    results = {}
    for s in scenarios:
        pattern = re.compile(
            re.escape(s['name']) + r'.*?[-*]\s*Status:\s*(PASSED|FAILED)',
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(output)
        if m:
            results[s['id']] = m.group(1).lower()
    return results


def _fmt_pr_comment(branch_name: str, base_branch: str, mr_url: str, task_title: str) -> str:
    lines = [
        "🎉 AutoDev has created a Pull Request and is ready for review.\n",
        f"• Title: {task_title}",
        f"• Branch: {branch_name} → {base_branch}",
    ]
    if mr_url:
        lines.append(f"• PR URL: {mr_url}")
    lines.append("\nPlease review, merge the PR, then confirm completion in AutoDev.")
    return "\n".join(lines)


async def _git_head_sha(project_dir: str) -> str:
    """Return current HEAD commit SHA, or empty string if not a git repo."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


async def _undo_agent_commits(project_dir: str, original_sha: str, run_id: str):
    """
    If the agents committed anything (HEAD changed), reset back to original_sha
    using --mixed so all changes remain as unstaged working-directory files.
    """
    current_sha = await _git_head_sha(project_dir)
    if not current_sha or current_sha == original_sha:
        return  # nothing to undo

    publish_log(run_id, f"[Orchestrator] Agent committed (HEAD moved {original_sha[:8]}→{current_sha[:8]}); resetting to keep changes unstaged …")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "reset", "--mixed", original_sha,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            publish_log(run_id, "[Orchestrator] Agent commits undone — changes are now unstaged (will commit after test approval)")
        else:
            publish_log(run_id, f"[Orchestrator] WARNING: git reset failed: {stderr.decode().strip()}")
    except Exception as e:
        publish_log(run_id, f"[Orchestrator] WARNING: could not undo agent commits: {e}")


async def _get_run(db: AsyncSession, run_id: str) -> PipelineRun | None:
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == UUID(run_id))
    )
    return result.scalar_one_or_none()


async def _get_project(db: AsyncSession, project_id: str) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == UUID(project_id))
    )
    return result.scalar_one_or_none()

from app.agents.base import BaseAgent, AgentResult
from app.services.claude_service import run_claude


class FrontendDeveloperAgent(BaseAgent):
    agent_type = "frontend_dev"

    async def run(
        self,
        frontend_dir: str,
        frontend_tech: str,
        task_title: str,
        approved_plan: str,
        task_number: str = "",
        db=None,
    ) -> AgentResult:
        if db:
            await self._create_agent_run(db)

        self.publish_log(f"[FrontendDev] Starting frontend implementation for: {task_title}")

        commit_ref = f"ZOHO #{task_number}: {task_title}" if task_number else f"[AutoDev] {task_title}"

        prompt = f"""Implement the following plan in this {frontend_tech} codebase.
Focus ONLY on frontend changes.

TASK: {task_title}

APPROVED IMPLEMENTATION PLAN:
{approved_plan}

Instructions:
- Only implement the "Frontend Changes" section of the plan
- Follow existing code conventions and patterns in the codebase
- Write clean, production-ready code
- Do not modify backend files
- IMPORTANT: Do NOT run git commit, git add, or git push. Leave all changes as uncommitted working directory changes. Committing will be handled separately after manual test review.

Start implementing now."""

        output_lines = []

        async def on_line(line: str):
            self.publish_log(line)
            output_lines.append(line)

        full_output, exit_code = await run_claude(
            cwd=frontend_dir,
            prompt=prompt,
            stream_callback=on_line,
        )

        if exit_code != 0:
            error = f"FrontendDev exited with code {exit_code}"
            self.publish_log(f"[FrontendDev] ERROR: {error}")
            if db:
                await self._record_agent_run(db, "failed", full_output, error, exit_code)
            return AgentResult(success=False, output=full_output, error=error, exit_code=exit_code)

        self.publish_log(f"[FrontendDev] Frontend implementation complete")
        if db:
            await self._record_agent_run(db, "completed", full_output, exit_code=exit_code)

        return AgentResult(success=True, output=full_output, exit_code=exit_code)

from app.agents.base import BaseAgent, AgentResult
from app.services.claude_service import run_claude


class MonolithicDeveloperAgent(BaseAgent):
    agent_type = "monolithic_dev"

    async def run(
        self,
        project_dir: str,
        task_title: str,
        approved_plan: str,
        tech_stack: str = "",
        task_number: str = "",
        db=None,
    ) -> AgentResult:
        if db:
            await self._create_agent_run(db)

        self.publish_log(f"[MonolithicDev] Starting implementation for: {task_title}")

        prompt = f"""Implement the following plan in this codebase.
This is a monolithic project — backend and frontend live in the same directory.

TASK: {task_title}
{f'TECH STACK: {tech_stack}' if tech_stack else ''}

APPROVED IMPLEMENTATION PLAN:
{approved_plan}

Instructions:
- Implement ALL changes described in the plan — backend, frontend, templates, static files,
  HTML files, CSS, JavaScript, config files, and anything else specified.
- Create every file mentioned in the plan at the exact path specified.
- Follow existing code conventions and patterns in the codebase.
- Write clean, production-ready code.
- IMPORTANT: Do NOT run git commit, git add, or git push. Leave all changes as uncommitted
  working directory changes. Committing will be handled separately after test review.

Start implementing now."""

        output_lines = []

        async def on_line(line: str):
            self.publish_log(line)
            output_lines.append(line)

        full_output, exit_code = await run_claude(
            cwd=project_dir,
            prompt=prompt,
            stream_callback=on_line,
        )

        if exit_code != 0:
            error = f"MonolithicDev exited with code {exit_code}"
            self.publish_log(f"[MonolithicDev] ERROR: {error}")
            if db:
                await self._record_agent_run(db, "failed", full_output, error, exit_code)
            return AgentResult(success=False, output=full_output, error=error, exit_code=exit_code)

        self.publish_log("[MonolithicDev] Implementation complete")
        if db:
            await self._record_agent_run(db, "completed", full_output, exit_code=exit_code)

        return AgentResult(success=True, output=full_output, exit_code=exit_code)

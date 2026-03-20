import re
from app.agents.base import BaseAgent, AgentResult
from app.services.claude_service import run_claude


class PlannerAgent(BaseAgent):
    agent_type = "planner"

    async def run(
        self,
        project_dir: str,
        frontend_tech: str,
        backend_tech: str,
        task_title: str,
        task_description: str,
        previous_feedback: str = "",
        db=None,
    ) -> AgentResult:
        if db:
            await self._create_agent_run(db)

        self.publish_log(f"[Planner] Starting planning for: {task_title}")

        feedback_section = ""
        if previous_feedback:
            feedback_section = f"\n\nPREVIOUS FEEDBACK TO INCORPORATE:\n{previous_feedback}"

        prompt = f"""You are planning implementation for a software task.

TASK TITLE: {task_title}
TASK DESCRIPTION: {task_description}

TECH STACK:
- Frontend: {frontend_tech}
- Backend: {backend_tech}
{feedback_section}

Analyze the codebase and generate a detailed implementation plan including:

1. **Backend Changes**
   - New/modified files
   - API endpoints to add/change
   - Database model changes
   - Business logic

2. **Frontend Changes**
   - New/modified components or pages
   - API integration points
   - State management changes

3. **Playwright Test Scenarios** (Automated via browser)
   For features that can be verified through browser automation: UI interactions, form submissions,
   navigation flows, visible API responses, CRUD operations in the UI, etc.
   List 3–5 scenarios. Use this EXACT format for EACH:

   **Playwright Scenario: [Short descriptive name]**
   Steps: [Step 1] → [Step 2] → [Step 3]
   Expected: [What should appear or happen in the browser]

4. **Manual Test Scenarios** (Human judgment required)
   ONLY for things that CANNOT be automated: visual/design review, external email/SMS verification,
   complex multi-system business rules, or environment-specific checks.
   List 1–3 scenarios (fewer is fine — only include what truly needs a human).
   Use this EXACT format for EACH:

   **Scenario: [Short descriptive name]**
   Steps: [Step 1] → [Step 2] → [Step 3]
   Expected: [What the tester should see or verify]

5. **Implementation Order**
   - Step-by-step sequence

Output as structured markdown with clear headings. Be specific about file paths and function names."""

        output_lines = []

        async def on_line(line: str):
            self.publish_log(line)
            output_lines.append(line)

        full_output, exit_code = await run_claude(
            cwd=project_dir,
            prompt=prompt,
            plan_mode=True,
            stream_callback=on_line,
        )

        if exit_code != 0:
            error = f"Planner exited with code {exit_code}"
            self.publish_log(f"[Planner] ERROR: {error}")
            if db:
                await self._record_agent_run(db, "failed", full_output, error, exit_code)
            return AgentResult(success=False, output=full_output, error=error, exit_code=exit_code)

        self.publish_log(f"[Planner] Planning complete ({len(output_lines)} lines)")
        if db:
            await self._record_agent_run(db, "completed", full_output, exit_code=exit_code)

        return AgentResult(success=True, output=full_output, exit_code=exit_code)

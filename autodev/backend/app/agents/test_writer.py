"""
TestWriterAgent — generates Playwright tests in a temp directory outside the
target project, so the project's codebase is never modified.

Directory: /tmp/autodev_tests/{run_id}/
  e2e/               ← generated .spec.ts files
  playwright.config.ts
  package.json       ← minimal, just needs @playwright/test
"""
import json
import os
import textwrap
from app.agents.base import BaseAgent, AgentResult
from app.services.claude_service import run_claude


class TestWriterAgent(BaseAgent):
    agent_type = "test_writer"

    def tests_dir(self, run_id: str) -> str:
        return f"/tmp/autodev_tests/{run_id}"

    async def run(
        self,
        run_id: str,
        project_dir: str,
        approved_plan: str,
        task_title: str,
        task_description: str,
        backend_tech: str,
        server_start_command: str,
        server_port: int,
        db=None,
    ) -> AgentResult:
        if db:
            await self._create_agent_run(db)

        tests_dir = self.tests_dir(run_id)
        e2e_dir = os.path.join(tests_dir, "e2e")
        os.makedirs(e2e_dir, exist_ok=True)

        self.publish_log(f"[TestWriter] Generating Playwright tests in {tests_dir}")
        self.publish_log(f"[TestWriter] Target project: {project_dir}")
        self.publish_log(f"[TestWriter] Server: {server_start_command} (port {server_port})")

        # Write minimal package.json so npm/npx works
        pkg = {"name": "autodev-tests", "private": True, "devDependencies": {"@playwright/test": "^1.40.0"}}
        with open(os.path.join(tests_dir, "package.json"), "w") as f:
            json.dump(pkg, f, indent=2)

        # Write playwright.config.ts using the project's server start command
        config = textwrap.dedent(f"""\
            import {{ defineConfig, devices }} from '@playwright/test'

            export default defineConfig({{
              testDir: './e2e',
              fullyParallel: false,
              retries: 1,
              reporter: 'list',
              timeout: 30000,
              use: {{
                baseURL: 'http://localhost:{server_port}',
                headless: true,
              }},
              webServer: {{
                command: '{server_start_command}',
                cwd: '{project_dir}',
                port: {server_port},
                timeout: 60000,
                reuseExistingServer: true,
              }},
              projects: [
                {{ name: 'chromium', use: {{ ...devices['Desktop Chrome'] }} }},
              ],
            }})
            """)
        with open(os.path.join(tests_dir, "playwright.config.ts"), "w") as f:
            f.write(config)

        # Determine base URL and protocol hint for Claude
        is_api = backend_tech.lower() in ("fastapi", "django", "express", "rails", "flask")
        test_style = (
            "API endpoint tests using page.request (GET/POST to REST endpoints)"
            if is_api
            else "browser UI tests using page.goto, page.fill, page.click"
        )

        prompt = f"""You are writing Playwright end-to-end tests for a project.

IMPORTANT: Write the tests in the directory {e2e_dir}/
Do NOT modify any files in {project_dir} — the target project is read-only.

PROJECT INFO:
- Directory: {project_dir}
- Tech: {backend_tech}
- Server: http://localhost:{server_port}

TASK BEING TESTED: {task_title}
{task_description}

APPROVED PLAN (read the "Test Cases" section for what to test):
{approved_plan}

INSTRUCTIONS:
1. Read the project structure in {project_dir} to understand routes, endpoints, and models
2. Extract the "Test Cases" from the approved plan above
3. Write {test_style}
4. Create test files in {e2e_dir}/ (e.g. {e2e_dir}/feature.spec.ts)
5. Cover 2-4 realistic test scenarios based on the plan
6. Use proper Playwright assertions (expect(...).toBe, toBeVisible, etc.)
7. Handle authentication if the API requires it (read existing auth code to understand)
8. Do NOT create playwright.config.ts — it already exists at {tests_dir}/playwright.config.ts

After writing tests, run: cd {tests_dir} && npx --yes playwright install chromium --with-deps 2>/dev/null; npx --yes playwright test --reporter=list
to verify the tests compile and run. Fix any issues you find."""

        output_lines = []

        async def on_line(line: str):
            self.publish_log(line)
            output_lines.append(line)

        full_output, exit_code = await run_claude(
            cwd=tests_dir,
            prompt=prompt,
            stream_callback=on_line,
        )

        if exit_code != 0:
            error = f"TestWriter exited with code {exit_code}"
            self.publish_log(f"[TestWriter] ERROR: {error}")
            if db:
                await self._record_agent_run(db, "failed", full_output, error, exit_code)
            return AgentResult(success=False, output=full_output, error=error, exit_code=exit_code)

        # Check that at least one spec file was created
        spec_files = [f for f in os.listdir(e2e_dir) if f.endswith(".spec.ts")]
        if spec_files:
            self.publish_log(f"[TestWriter] Created {len(spec_files)} test file(s): {', '.join(spec_files)}")
        else:
            self.publish_log("[TestWriter] WARNING: No .spec.ts files found in e2e/ dir")

        if db:
            await self._record_agent_run(db, "completed", full_output, exit_code=exit_code)

        return AgentResult(success=True, output=full_output, exit_code=exit_code)

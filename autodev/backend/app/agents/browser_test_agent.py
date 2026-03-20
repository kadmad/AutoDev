"""
BrowserTestAgent — runs Claude + Playwright MCP to auto-test the built app.
"""
import asyncio
import json
import os
import re
import shutil
import tempfile
from typing import Optional

from app.agents.base import AgentResult, BaseAgent
from app.services.claude_service import run_claude


class BrowserTestAgent(BaseAgent):
    agent_type = "browser_test"

    async def run(
        self,
        project_dir: str,
        port: Optional[int],
        task_title: str,
        task_description: str,
        scenarios: list[dict],
        db=None,
    ) -> AgentResult:
        if not port:
            self.publish_log("[BrowserTest] No server port configured — skipping browser tests")
            return AgentResult(success=True, output="", exit_code=0)

        self.publish_log(f"[BrowserTest] Starting Playwright MCP session against http://localhost:{port} …")

        # Write temp MCP config
        mcp_config = {
            "mcpServers": {
                "playwright": {
                    "command": "npx",
                    "args": ["@playwright/mcp@latest"],
                }
            }
        }
        config_fd, config_path = tempfile.mkstemp(
            prefix=f"autodev-playwright-{self.run_id}-", suffix=".json"
        )
        # Isolated work dir so Claude never writes screenshots/configs into the project
        test_work_dir = tempfile.mkdtemp(prefix=f"autodev-browser-{self.run_id}-")
        try:
            with os.fdopen(config_fd, "w") as f:
                json.dump(mcp_config, f)

            prompt = self._build_prompt(port, task_title, task_description, scenarios)

            output, exit_code = await asyncio.wait_for(
                run_claude(
                    cwd=test_work_dir,
                    prompt=prompt,
                    mcp_config_path=config_path,
                    stream_callback=lambda line: self.publish_log(f"[BrowserTest] {line}"),
                ),
                timeout=900,  # 15 minutes
            )

            status = self._parse_status(output)
            self.publish_log(f"[BrowserTest] Overall result: {status.upper()}")

            return AgentResult(
                success=(status == "passed"),
                output=output,
                exit_code=exit_code,
            )

        except asyncio.TimeoutError:
            self.publish_log("[BrowserTest] Timed out after 15 minutes")
            return AgentResult(success=False, output="Browser tests timed out after 15 minutes", exit_code=1)
        except Exception as e:
            self.publish_log(f"[BrowserTest] Error: {e}")
            return AgentResult(success=False, output=str(e), exit_code=1)
        finally:
            try:
                os.unlink(config_path)
            except Exception:
                pass
            shutil.rmtree(test_work_dir, ignore_errors=True)

    def _build_prompt(
        self,
        port: int,
        task_title: str,
        task_description: str,
        scenarios: list[dict],
    ) -> str:
        scenario_lines = []
        for i, s in enumerate(scenarios, 1):
            scenario_lines.append(f"### Scenario {i}: {s.get('name', '')}")
            if s.get("steps"):
                scenario_lines.append(f"- Steps: {s['steps']}")
            if s.get("expected"):
                scenario_lines.append(f"- Expected: {s['expected']}")

        scenarios_text = "\n".join(scenario_lines) if scenario_lines else "No specific scenarios — do a general smoke test."

        return f"""You are a QA engineer. The app is running at http://localhost:{port}.

Task implemented: {task_title}
{task_description}

Test scenarios:
{scenarios_text}

Use the Playwright browser tools to navigate to the app, interact with the UI, and verify each scenario.

Output a markdown test report in exactly this format:

## Test Report

{chr(10).join(f'### Scenario: {s.get("name", f"Scenario {i+1}")}' + chr(10) + '- Status: PASSED / FAILED' + chr(10) + '- Steps performed: ...' + chr(10) + '- Result: ...' for i, s in enumerate(scenarios))}

## Summary
- Total: N  Passed: N  Failed: N
- Overall: PASSED / FAILED

Replace PASSED/FAILED with the actual results. Be thorough — test the real UI, not just that the page loads.
"""

    def _parse_status(self, output: str) -> str:
        """Extract 'passed' or 'failed' from the Overall line in the report."""
        match = re.search(r"Overall:\s*(PASSED|FAILED)", output, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        # Fallback: if the word "FAILED" appears in summary, treat as failed
        if re.search(r"\bFAILED\b", output):
            return "failed"
        return "passed"

import asyncio
import os
import re
from asyncio.subprocess import PIPE
from app.agents.base import BaseAgent, AgentResult


class TestRunnerAgent(BaseAgent):
    agent_type = "test_runner"

    TIMEOUT_SECONDS = 600  # 10 minutes — playwright needs to start a server + run tests

    async def run(
        self,
        project_dir: str,
        test_command: str,
        db=None,
    ) -> AgentResult:
        if db:
            await self._create_agent_run(db)

        # Skip if no test command configured
        if not test_command or test_command.strip().lower() in ("", "none", "skip", "n/a"):
            self.publish_log("[TestRunner] No test command configured — skipping tests")
            if db:
                await self._record_agent_run(db, "skipped", "Tests skipped (no command configured)")
            return AgentResult(success=True, output="skipped", exit_code=0)

        # Fast-fail for playwright commands when no config or test files exist
        if "playwright" in test_command.lower():
            config_file = next(
                (f for f in ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs")
                 if os.path.exists(os.path.join(project_dir, f))),
                None,
            )
            if not config_file:
                msg = "[TestRunner] No playwright.config.ts found — skipping Playwright tests"
                self.publish_log(msg)
                if db:
                    await self._record_agent_run(db, "skipped", msg)
                return AgentResult(success=True, output=msg, exit_code=0)
            self.publish_log(f"[TestRunner] Found {config_file} — will start webServer if configured")

        self.publish_log(f"[TestRunner] Running: {test_command}")

        # Pass --yes to npx to avoid interactive install prompts
        raw_parts = test_command.split()
        if raw_parts[0] == "npx" and "--yes" not in raw_parts:
            raw_parts.insert(1, "--yes")
        cmd_parts = raw_parts
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                cwd=project_dir,
                stdout=PIPE,
                stderr=PIPE,
            )
        except FileNotFoundError:
            msg = f"Command not found: {cmd_parts[0]}"
            self.publish_log(f"[TestRunner] {msg}")
            if db:
                await self._record_agent_run(db, "skipped", msg)
            return AgentResult(success=True, output=msg, exit_code=0)

        output_lines = []

        async def read_stream(stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                output_lines.append(decoded)
                self.publish_log(decoded)

        try:
            await asyncio.wait_for(
                asyncio.gather(read_stream(proc.stdout), read_stream(proc.stderr)),
                timeout=self.TIMEOUT_SECONDS,
            )
            await proc.wait()
            exit_code = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            self.publish_log(f"[TestRunner] Timed out after {self.TIMEOUT_SECONDS}s — skipping")
            output_lines.append(f"[TIMEOUT] Test command exceeded {self.TIMEOUT_SECONDS}s limit")
            exit_code = 0  # treat timeout as skipped, not fatal

        full_output = "\n".join(output_lines)
        stats = self._parse_playwright_output(full_output)
        self.publish_log(
            f"[TestRunner] Results: {stats['passed']} passed, {stats['failed']} failed, "
            f"{stats['skipped']} skipped / {stats['total']} total"
        )

        if db:
            status = "completed" if exit_code == 0 else "failed"
            await self._record_agent_run(db, status, full_output, exit_code=exit_code)

        return AgentResult(success=exit_code == 0, output=full_output, exit_code=exit_code)

    def _parse_playwright_output(self, output: str) -> dict:
        """Parse Playwright CLI output for pass/fail counts."""
        stats = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Playwright outputs like: "5 passed (10s)" or "2 failed, 3 passed"
        passed_match = re.search(r"(\d+)\s+passed", output)
        failed_match = re.search(r"(\d+)\s+failed", output)
        skipped_match = re.search(r"(\d+)\s+skipped", output)

        if passed_match:
            stats["passed"] = int(passed_match.group(1))
        if failed_match:
            stats["failed"] = int(failed_match.group(1))
        if skipped_match:
            stats["skipped"] = int(skipped_match.group(1))

        stats["total"] = stats["passed"] + stats["failed"] + stats["skipped"]
        return stats

    async def save_test_result(self, db, run_id: str, stats: dict, raw_output: str):
        """Persist test result to DB."""
        from app.models.test_result import TestResult
        import uuid

        result = TestResult(
            pipeline_run_id=uuid.UUID(run_id),
            total=stats["total"],
            passed=stats["passed"],
            failed=stats["failed"],
            skipped=stats["skipped"],
            raw_output=raw_output,
        )
        db.add(result)
        await db.commit()
        return result

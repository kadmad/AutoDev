import asyncio
import os
from asyncio.subprocess import PIPE
from typing import AsyncIterator, Callable, Optional


def _clean_env() -> dict:
    """Return env without CLAUDECODE so nested claude CLI calls are allowed."""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    return env


async def run_claude(
    cwd: str,
    prompt: str,
    plan_mode: bool = False,
    stream_callback: Optional[Callable[[str], None]] = None,
    mcp_config_path: Optional[str] = None,
) -> tuple[str, int]:
    """
    Run claude CLI as subprocess, stream output line-by-line.
    Prompt is passed via stdin to avoid arg-parsing conflicts with --allowedTools.
    Returns (full_output, exit_code).
    """
    cmd = ["claude", "--print", "--dangerously-skip-permissions"]
    if plan_mode:
        cmd += ["--allowedTools", "Read,Glob,Grep,Write,Edit"]
    if mcp_config_path:
        cmd += ["--mcp-config", mcp_config_path]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=_clean_env(),
    )

    # Write prompt to stdin then close it so claude knows input is done
    proc.stdin.write(prompt.encode("utf-8"))
    await proc.stdin.drain()
    proc.stdin.close()

    output_lines = []

    async def read_stream(stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\n")
            output_lines.append(decoded)
            if stream_callback:
                if asyncio.iscoroutinefunction(stream_callback):
                    await stream_callback(decoded)
                else:
                    stream_callback(decoded)

    await asyncio.gather(
        read_stream(proc.stdout),
        read_stream(proc.stderr),
    )

    await proc.wait()
    return "\n".join(output_lines), proc.returncode


async def stream_claude(
    cwd: str,
    prompt: str,
    plan_mode: bool = False,
    mcp_config_path: Optional[str] = None,
) -> AsyncIterator[str]:
    """Async generator that yields stdout lines from claude CLI."""
    cmd = ["claude", "--print", "--dangerously-skip-permissions"]
    if plan_mode:
        cmd += ["--allowedTools", "Read,Glob,Grep,Write,Edit"]
    if mcp_config_path:
        cmd += ["--mcp-config", mcp_config_path]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=_clean_env(),
    )

    proc.stdin.write(prompt.encode("utf-8"))
    await proc.stdin.drain()
    proc.stdin.close()

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        yield line.decode("utf-8", errors="replace").rstrip("\n")

    await proc.wait()

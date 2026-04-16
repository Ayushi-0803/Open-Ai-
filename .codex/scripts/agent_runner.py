"""
Agent Runner — spawns LLM sub-agents as subprocesses.
Supports Codex CLI, Claude Code, and Cursor CLI.
The runtime is auto-detected or configurable, with Codex preferred.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional


# ── Runtime detection ────────────────────────────────────────────────

def detect_runtime() -> str:
    """Auto-detect which agentic runtime is available."""
    if shutil.which("codex"):
        return "codex"
    if shutil.which("claude"):
        return "claude-code"
    if shutil.which("cursor-agent"):
        return "cursor"
    raise RuntimeError(
        "No agentic runtime found. Install one of:\n"
        "  - Codex CLI:   https://github.com/openai/codex\n"
        "  - Claude Code: https://code.claude.com\n"
        "  - Cursor CLI:  https://cursor.com/cli"
    )


# ── Agent spawning per runtime ───────────────────────────────────────

def _build_prompt(skill_path: str, context: dict) -> str:
    """
    Build the full prompt for a sub-agent:
    1. Read the skill file
    2. Append context variables as a ## Context section
    """
    with open(skill_path, encoding="utf-8") as f:
        skill_content = f.read()

    context_lines = [f"- **{k}**: {v}" for k, v in context.items()]
    context_section = "## Context\n" + "\n".join(context_lines)

    return f"{skill_content}\n\n{context_section}"


def spawn_claude_code(skill_path: str, context: dict,
                      model: Optional[str] = None,
                      timeout: int = 1800) -> dict:
    """Spawn a Claude Code sub-agent."""
    prompt = _build_prompt(skill_path, context)
    allowed_tools = context.get("allowed_tools", "Read,Write,Edit,Bash,Glob,Grep")
    cmd = ["claude", "-p", "--allowedTools", allowed_tools]
    if model:
        cmd.extend(["--model", model])

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=context.get("working_dir", os.getcwd()),
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "runtime": "claude-code",
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT", "runtime": "claude-code"}


def spawn_codex(skill_path: str, context: dict,
                model: Optional[str] = None,
                timeout: int = 1800) -> dict:
    """Spawn a Codex CLI sub-agent."""
    prompt = _build_prompt(skill_path, context)

    cmd = ["codex", "exec", "--full-auto", "--sandbox", "workspace-write"]
    if model:
        cmd.extend(["--model", model])
    cmd.extend(["--", prompt])

    try:
        result = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=context.get("working_dir", os.getcwd()),
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "runtime": "codex",
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT", "runtime": "codex"}


def spawn_cursor(skill_path: str, context: dict,
                 model: Optional[str] = None,
                 timeout: int = 1800) -> dict:
    """Spawn a Cursor CLI sub-agent."""
    prompt = _build_prompt(skill_path, context)
    
    cmd = [
        "cursor-agent", "-p",
        "--force",
        "--approve-mcps",
        "--output-format", "stream-json",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.extend(["--", prompt])

    try:
        result = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd=context.get("working_dir", os.getcwd()),
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "runtime": "cursor",
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT", "runtime": "cursor"}


# ── Unified interface ────────────────────────────────────────────────

RUNTIME_SPAWNERS = {
    "claude-code": spawn_claude_code,
    "codex": spawn_codex,
    "cursor": spawn_cursor,
}


def spawn_agent(skill_path: str, context: dict,
                runtime: Optional[str] = None,
                model: Optional[str] = "gpt-5.4",
                timeout: int = 1800) -> dict:
    """
    Spawn a sub-agent using the specified or auto-detected runtime.
    
    Args:
        skill_path: Path to the skill/instruction file
        context:    Dict of context variables injected into the prompt
        runtime:    'claude-code', 'codex', 'cursor', or None (auto-detect)
        model:      Model name override (optional)
        timeout:    Max seconds to wait for agent completion
    
    Returns:
        Dict with keys: exit_code, stdout, stderr, runtime
    """
    if runtime is None:
        runtime = os.environ.get("MIGRATION_RUNTIME", detect_runtime())

    spawner = RUNTIME_SPAWNERS.get(runtime)
    if not spawner:
        raise ValueError(
            f"Unknown runtime: {runtime}. "
            f"Supported: {list(RUNTIME_SPAWNERS.keys())}"
        )

    return spawner(skill_path, context, model=model, timeout=timeout)


# ── Filesystem polling ───────────────────────────────────────────────

def poll_for_completion(output_dir: str,
                        success_markers: list[str],
                        timeout: int = 1800,
                        interval: int = 15) -> str:
    """
    Poll a directory for completion markers.
    
    Args:
        output_dir:      Directory to watch
        success_markers: List of filenames that indicate success (e.g., ["DISCOVERY.md"])
        timeout:         Max seconds to wait
        interval:        Seconds between polls
    
    Returns:
        'success', 'failure', or 'timeout'
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            files = os.listdir(output_dir)
        except FileNotFoundError:
            time.sleep(interval)
            continue

        # Check for any success marker
        for marker in success_markers:
            if marker in files:
                return "success"

        # Check for failure
        if "ERROR" in files:
            return "failure"

        time.sleep(interval)

    return "timeout"

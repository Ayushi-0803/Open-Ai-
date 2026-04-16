#!/usr/bin/env python3
"""
Deterministic recipe verification runner.

Runs recipe-provided verification hooks from a recipe's verify/ directory and
writes a stable parity-results.json artifact for the review phase.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".sh", ".py"}


def discover_hooks(verify_dir: Path) -> list[Path]:
    hooks: list[Path] = []
    for path in sorted(verify_dir.iterdir()):
        if path.is_dir():
            continue
        if path.suffix in SUPPORTED_SUFFIXES or os.access(path, os.X_OK):
            hooks.append(path)
    return hooks


def command_for_hook(hook: Path) -> list[str]:
    if hook.suffix == ".sh":
        return ["bash", str(hook)]
    if hook.suffix == ".py":
        return [sys.executable, str(hook)]
    return [str(hook)]


def run_hook(hook: Path, target_path: Path, env: dict[str, str]) -> dict[str, Any]:
    cmd = command_for_hook(hook)
    try:
        result = subprocess.run(
            cmd,
            cwd=target_path,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        return {
            "name": hook.name,
            "path": str(hook),
            "command": cmd,
            "status": "pass" if result.returncode == 0 else "fail",
            "exitCode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "name": hook.name,
            "path": str(hook),
            "command": cmd,
            "status": "fail",
            "exitCode": -1,
            "stdout": "",
            "stderr": "TIMEOUT",
        }
    except Exception as exc:  # pragma: no cover - defensive path
        return {
            "name": hook.name,
            "path": str(hook),
            "command": cmd,
            "status": "fail",
            "exitCode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


def build_env(source_path: Path, target_path: Path, recipe_root: Path, verify_dir: Path, manifest_path: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    env["SOURCE_PATH"] = str(source_path)
    env["TARGET_PATH"] = str(target_path)
    env["RECIPE_ROOT"] = str(recipe_root)
    env["RECIPE_VERIFY_DIR"] = str(verify_dir)
    if manifest_path is not None:
        env["MIGRATION_MANIFEST_PATH"] = str(manifest_path)
    return env


def run_recipe_verify(source_path: Path, target_path: Path, recipe_root: Path, verify_dir: Path, output_path: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    if not verify_dir.exists() or not verify_dir.is_dir():
        report = {
            "status": "skipped",
            "reason": f"verify directory not found: {verify_dir}",
            "hooks": [],
            "summary": {"total": 0, "passed": 0, "failed": 0},
        }
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    hooks = discover_hooks(verify_dir)
    if not hooks:
        report = {
            "status": "skipped",
            "reason": f"no supported verification hooks in {verify_dir}",
            "hooks": [],
            "summary": {"total": 0, "passed": 0, "failed": 0},
        }
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    env = build_env(source_path, target_path, recipe_root, verify_dir, manifest_path)
    hook_results = [run_hook(hook, target_path, env) for hook in hooks]
    failed = [hook for hook in hook_results if hook["status"] != "pass"]
    report = {
        "status": "pass" if not failed else "fail",
        "reason": "" if not failed else "one or more recipe verification hooks failed",
        "hooks": hook_results,
        "summary": {
            "total": len(hook_results),
            "passed": sum(1 for hook in hook_results if hook["status"] == "pass"),
            "failed": len(failed),
        },
    }
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    if len(sys.argv) not in {6, 7}:
        print(
            "Usage: recipe_verify_runner.py <source-path> <target-path> <recipe-root> <verify-dir> <output-path> [manifest-path]",
            file=sys.stderr,
        )
        return 1

    source_path = Path(sys.argv[1]).resolve()
    target_path = Path(sys.argv[2]).resolve()
    recipe_root = Path(sys.argv[3]).resolve()
    verify_dir = Path(sys.argv[4]).resolve()
    output_path = Path(sys.argv[5]).resolve()
    manifest_path = Path(sys.argv[6]).resolve() if len(sys.argv) == 7 else None
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = run_recipe_verify(source_path, target_path, recipe_root, verify_dir, output_path, manifest_path)
    print(f"Wrote parity results to {output_path} with status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

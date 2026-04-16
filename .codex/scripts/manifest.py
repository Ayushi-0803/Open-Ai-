"""
Manifest utilities — read, write, and update migration-manifest.json.
This is the single source of truth for migration state.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional


def load(path: str) -> dict:
    """Load manifest from disk."""
    with open(path) as f:
        return json.load(f)


def save(path: str, manifest: dict):
    """Save manifest to disk atomically (write to temp, then rename)."""
    target = Path(path)
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(target))
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def update_phase(path: str, phase: str, status: str, extra: Optional[dict] = None):
    """
    Update a phase's status in the manifest. This is the ONLY function
    that should modify phase state — it ensures consistency.
    """
    manifest = load(path)

    if phase not in manifest["phases"]:
        manifest["phases"][phase] = {}

    manifest["phases"][phase]["status"] = status

    if status == "done":
        manifest["phases"][phase]["completedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif status == "awaiting_approval":
        manifest["phases"][phase]["awaitingApprovalAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif status == "approved":
        manifest["phases"][phase]["approvedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif status == "failed":
        manifest["phases"][phase]["failedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    if extra:
        manifest["phases"][phase].update(extra)

    # Update overall status
    all_done = all(
        p.get("status") == "done"
        for p in manifest["phases"].values()
    )
    if all_done:
        manifest["meta"]["status"] = "complete"
    elif status == "failed":
        manifest["meta"]["status"] = "failed"
    else:
        manifest["meta"]["status"] = "in_progress"

    save(path, manifest)
    return manifest


def add_checkpoint(path: str, phase: str, git_ref: str):
    """Record a git checkpoint for rollback support."""
    manifest = load(path)
    manifest["checkpoints"].append({
        "phase": phase,
        "gitRef": git_ref,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    save(path, manifest)


def update_phase_artifacts(path: str, phase: str, artifacts: dict):
    """Record artifact metadata for a phase."""
    manifest = load(path)
    if phase not in manifest["phases"]:
        manifest["phases"][phase] = {}
    manifest["phases"][phase]["artifacts"] = artifacts
    save(path, manifest)
    return manifest


def get_phase_status(path: str, phase: str) -> str:
    """Get the current status of a phase."""
    manifest = load(path)
    return manifest.get("phases", {}).get(phase, {}).get("status", "pending")


def get_meta(path: str, key: str, default=None):
    """Get a value from the manifest's meta section."""
    manifest = load(path)
    return manifest.get("meta", {}).get(key, default)

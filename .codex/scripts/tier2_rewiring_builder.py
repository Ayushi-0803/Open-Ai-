#!/usr/bin/env python3
"""
Deterministic Tier 2 rewiring aggregator with optional safe literal rewrites.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from tier2_common import (
    load_manifest_context,
    load_json,
    phase_output_dir,
    resolve_existing_target_file,
    safe_domain_token,
    write_json,
    write_text,
)


FRAMEWORK_DIR = Path(__file__).resolve().parents[1]


def apply_safe_rewrites(target_root: Path, rewrites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for rewrite in rewrites:
        source_file = rewrite.get("resolvedTargetFile")
        dependency_target = rewrite.get("resolvedDependencyTarget")
        dependency_path = rewrite.get("dependencyPath")
        if not source_file or not dependency_target or not dependency_path:
            continue
        target_file_path = Path(source_file)
        if not target_file_path.exists():
            continue
        original = target_file_path.read_text(encoding="utf-8")
        replacement_token = str(Path(dependency_target).relative_to(target_root)) if dependency_target.startswith(str(target_root)) else dependency_target
        if dependency_path not in original or replacement_token == dependency_path:
            continue
        updated = original.replace(dependency_path, replacement_token)
        if updated == original:
            continue
        target_file_path.write_text(updated, encoding="utf-8")
        applied.append(
            {
                "targetFile": str(target_file_path.resolve()),
                "from": dependency_path,
                "to": replacement_token,
            }
        )
    return applied


def build_rewiring(manifest_context: dict[str, Any], output_dir: Path, apply_changes: bool) -> dict[str, Any]:
    summaries_dir = manifest_context["summaries_dir"]
    plan_overview = load_json(phase_output_dir(summaries_dir, "domain_planning") / "domain-plan-overview.json")
    execution_overview_path = phase_output_dir(summaries_dir, "domain_execution") / "domain-execution-overview.json"
    execution_overview = load_json(execution_overview_path) if execution_overview_path.exists() else {"domains": []}
    target_root = Path(manifest_context["meta"].get("targetPath", "")).resolve()

    rewrites: list[dict[str, Any]] = []
    for domain_entry in plan_overview.get("domains", []):
        if not isinstance(domain_entry, dict):
            continue
        payload = load_json(Path(domain_entry["rewiringImportsPath"]))
        for item in payload.get("plannedImports", []):
            if not isinstance(item, dict):
                continue
            patched = dict(item)
            if target_root.exists():
                patched["resolvedTargetFile"] = patched.get("resolvedTargetFile") or resolve_existing_target_file(target_root, patched.get("targetFileCandidates", []))
                patched["resolvedDependencyTarget"] = patched.get("resolvedDependencyTarget") or resolve_existing_target_file(target_root, patched.get("targetDependencyCandidates", []))
                patched["safeRewrite"] = bool(patched["resolvedTargetFile"] and patched["resolvedDependencyTarget"])
            rewrites.append(patched)

    batches = []
    for index, rewrite in enumerate(sorted(rewrites, key=lambda item: (item.get("sourcePath", ""), item.get("dependencyPath", ""))), start=1):
        batches.append(
            {
                "id": f"rewire-{index}",
                "domain": rewrite.get("sourceDomain"),
                "targetFile": rewrite.get("resolvedTargetFile"),
                "dependencyTarget": rewrite.get("resolvedDependencyTarget"),
                "status": "ready" if rewrite.get("safeRewrite") else "manual-review",
                "rewrite": rewrite,
            }
        )

    applied = apply_safe_rewrites(target_root, rewrites) if apply_changes and target_root.exists() else []
    execution_statuses = {
        entry.get("name"): entry.get("status")
        for entry in execution_overview.get("domains", [])
        if isinstance(entry, dict) and entry.get("name")
    }
    payload = {
        "summary": {
            "totalBatches": len(batches),
            "safeRewriteCandidates": sum(1 for item in batches if item["status"] == "ready"),
            "appliedRewriteCount": len(applied),
            "manualReviewCount": sum(1 for item in batches if item["status"] != "ready"),
        },
        "globalRewriteMap": [
            {
                "domain": rewrite.get("sourceDomain"),
                "sourcePath": rewrite.get("sourcePath"),
                "dependencyPath": rewrite.get("dependencyPath"),
                "dependencyDomain": rewrite.get("dependencyDomain"),
                "resolvedTargetFile": rewrite.get("resolvedTargetFile"),
                "resolvedDependencyTarget": rewrite.get("resolvedDependencyTarget"),
                "safeRewrite": rewrite.get("safeRewrite", False),
            }
            for rewrite in rewrites
        ],
        "batches": batches,
        "executionStatusByDomain": execution_statuses,
        "appliedEdits": applied,
    }
    summary = {
        "status": "ready" if not any(item["status"] != "ready" for item in batches) else "needs-review",
        "appliedEdits": applied,
        "remainingManualWork": [
            {
                "sourcePath": item["rewrite"].get("sourcePath"),
                "dependencyPath": item["rewrite"].get("dependencyPath"),
                "reason": "unresolved target mapping" if not item["rewrite"].get("safeRewrite") else "manual confirmation required",
            }
            for item in batches
            if item["status"] != "ready"
        ],
    }
    return payload, summary


def write_markdown(output_dir: Path, summary: dict[str, Any]):
    lines = [
        "# REWIRING",
        "",
        f"- Status: {summary['status']}",
        f"- Applied edits: {len(summary['appliedEdits'])}",
        f"- Remaining manual items: {len(summary['remainingManualWork'])}",
    ]
    if summary["remainingManualWork"]:
        lines.extend(["", "## Manual Review"])
        for item in summary["remainingManualWork"][:20]:
            lines.append(f"- {item['sourcePath']} -> {item['dependencyPath']}: {item['reason']}")
    write_text(output_dir / "REWIRING.md", "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest_path")
    parser.add_argument("output_dir")
    parser.add_argument("--apply", action="store_true", dest="apply_changes")
    args = parser.parse_args()

    manifest_context = load_manifest_context(args.manifest_path, FRAMEWORK_DIR)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload, summary = build_rewiring(manifest_context, output_dir, args.apply_changes)
    write_json(output_dir / "rewiring-batches.json", payload)
    write_json(output_dir / "rewiring-summary.json", summary)
    write_markdown(output_dir, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

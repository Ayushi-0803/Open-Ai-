#!/usr/bin/env python3
"""
Deterministic Tier 2 domain execution prebuilder.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tier2_common import (
    infer_target_candidate_paths,
    load_manifest_context,
    load_json,
    phase_output_dir,
    resolve_existing_target_file,
    safe_domain_token,
    write_json,
    write_text,
)


FRAMEWORK_DIR = Path(__file__).resolve().parents[1]


def build_execution(manifest_context: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    summaries_dir = manifest_context["summaries_dir"]
    plan_overview = load_json(phase_output_dir(summaries_dir, "domain_planning") / "domain-plan-overview.json")
    target_root = Path(manifest_context["meta"].get("targetPath", "")).resolve()
    overview_domains: list[dict[str, Any]] = []

    for domain_entry in plan_overview.get("domains", []):
        if not isinstance(domain_entry, dict):
            continue
        domain = domain_entry.get("name")
        if not domain:
            continue
        token = safe_domain_token(domain)
        planning_payload = load_json(Path(domain_entry["decoupledFilesPath"]))
        execution_dir = output_dir / token / "execution"
        files = []
        existing_targets = 0
        for rel_path in planning_payload.get("ownedFiles", []):
            candidates = infer_target_candidate_paths(rel_path)
            resolved_target = resolve_existing_target_file(target_root, candidates) if target_root.exists() else None
            if resolved_target:
                existing_targets += 1
            files.append(
                {
                    "sourcePath": rel_path,
                    "targetCandidates": candidates,
                    "resolvedTarget": resolved_target,
                    "status": "present" if resolved_target else "pending",
                }
            )

        status = "completed" if files and existing_targets == len(files) else ("partial" if existing_targets else "no-op")
        payload = {
            "domain": domain,
            "status": status,
            "summary": {
                "plannedFileCount": len(files),
                "resolvedTargetCount": existing_targets,
                "pendingCount": len(files) - existing_targets,
            },
            "files": files,
            "notes": [
                "This execution artifact is prebuilt from the domain plan.",
                "The execution agent should update statuses after applying or reviewing migration edits.",
            ],
        }
        json_path = (execution_dir / f"execution.{token}.json").resolve()
        md_path = (execution_dir / f"execution.{token}.md").resolve()
        write_json(json_path, payload)
        write_text(
            md_path,
            "\n".join(
                [
                    f"# {domain} Execution",
                    "",
                    f"- Status: {status}",
                    f"- Planned files: {payload['summary']['plannedFileCount']}",
                    f"- Resolved targets: {payload['summary']['resolvedTargetCount']}",
                    f"- Pending targets: {payload['summary']['pendingCount']}",
                ]
            ),
        )
        overview_domains.append(
            {
                "name": domain,
                "status": status,
                "executionJson": str(json_path),
                "summaryMd": str(md_path),
            }
        )

    return {
        "summary": {
            "totalDomains": len(overview_domains),
            "completedDomains": sum(1 for item in overview_domains if item["status"] == "completed"),
        },
        "domains": overview_domains,
    }


def write_markdown(output_dir: Path, payload: dict):
    lines = [
        "# DOMAIN_EXECUTION",
        "",
        f"- Domains: {payload['summary']['totalDomains']}",
        f"- Completed domains: {payload['summary']['completedDomains']}",
        "",
        "## Domain Status",
    ]
    for domain in payload.get("domains", []):
        lines.append(f"- {domain['name']}: {domain['status']}")
    write_text(output_dir / "DOMAIN_EXECUTION.md", "\n".join(lines))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tier2_domain_execution_builder.py <manifest-path> <output-dir>", file=sys.stderr)
        return 1

    manifest_context = load_manifest_context(sys.argv[1], FRAMEWORK_DIR)
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_execution(manifest_context, output_dir)
    write_json(output_dir / "domain-execution-overview.json", payload)
    write_markdown(output_dir, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Deterministic Tier 2 integration review checker.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from discovery_builder import build_artifacts
from tier2_common import load_manifest_context, load_json, phase_output_dir, write_json, write_text


FRAMEWORK_DIR = Path(__file__).resolve().parents[1]


def check_exists(label: str, path: str | None) -> dict[str, Any]:
    exists = bool(path) and Path(path).exists()
    return {
        "name": label,
        "status": "pass" if exists else "fail",
        "details": {
            "path": path,
            "exists": exists,
        },
    }


def build_cross_domain_checks(target_root: Path, domain_plan_overview: dict[str, Any]) -> list[dict[str, Any]]:
    if not target_root.exists():
        return [
            {
                "name": "cross-domain-imports",
                "status": "human-review",
                "details": {
                    "reason": f"target path not found: {target_root}",
                },
            }
        ]

    artifacts = build_artifacts(target_root)
    dep_graph = artifacts["dep_graph"]
    ownership: dict[str, str] = {}
    plan_files_by_domain: dict[str, set[str]] = {}
    for entry in domain_plan_overview.get("domains", []):
        if not isinstance(entry, dict):
            continue
        payload = load_json(Path(entry["decoupledFilesPath"]))
        paths = set(payload.get("ownedFiles", []))
        plan_files_by_domain[entry["name"]] = paths
        for path in paths:
            ownership[path] = entry["name"]

    violations = []
    for rel_path, entry in dep_graph.get("files", {}).items():
        file_domain = ownership.get(rel_path)
        if not file_domain or not isinstance(entry, dict):
            continue
        for dependency in entry.get("imports", {}).get("internal", []):
            dependency_domain = ownership.get(str(dependency))
            if dependency_domain and dependency_domain != file_domain:
                violations.append(
                    {
                        "path": rel_path,
                        "fileDomain": file_domain,
                        "dependencyPath": str(dependency),
                        "dependencyDomain": dependency_domain,
                    }
                )

    return [
        {
            "name": "cross-domain-imports",
            "status": "pass" if not violations else "human-review",
            "details": {
                "violations": violations[:200],
                "checkedFiles": len(dep_graph.get("files", {})),
            },
        }
    ]


def build_review(manifest_context: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    summaries_dir = manifest_context["summaries_dir"]
    domain_plan_overview = load_json(phase_output_dir(summaries_dir, "domain_planning") / "domain-plan-overview.json")
    domain_execution_overview = load_json(phase_output_dir(summaries_dir, "domain_execution") / "domain-execution-overview.json")
    rewiring_summary = load_json(phase_output_dir(summaries_dir, "rewiring") / "rewiring-summary.json")
    parity_path = output_dir / "parity-results.json"
    parity_results = load_json(parity_path) if parity_path.exists() else {"status": "missing", "summary": {"total": 0, "failed": 0}}

    checks = [
        check_exists("domain-plan-overview", str((phase_output_dir(summaries_dir, "domain_planning") / "domain-plan-overview.json").resolve())),
        check_exists("domain-execution-overview", str((phase_output_dir(summaries_dir, "domain_execution") / "domain-execution-overview.json").resolve())),
        check_exists("rewiring-summary", str((phase_output_dir(summaries_dir, "rewiring") / "rewiring-summary.json").resolve())),
    ]

    missing_references = []
    for domain in domain_plan_overview.get("domains", []):
        if not isinstance(domain, dict):
            continue
        for key in ("decoupledFilesPath", "rewiringImportsPath", "agentsPath", "summaryMd"):
            path = domain.get(key)
            if not isinstance(path, str) or not Path(path).exists():
                missing_references.append({"phase": "domain_planning", "domain": domain.get("name"), "key": key, "path": path})
    for domain in domain_execution_overview.get("domains", []):
        if not isinstance(domain, dict):
            continue
        for key in ("executionJson", "summaryMd"):
            path = domain.get(key)
            if not isinstance(path, str) or not Path(path).exists():
                missing_references.append({"phase": "domain_execution", "domain": domain.get("name"), "key": key, "path": path})

    checks.append(
        {
            "name": "artifact-reference-consistency",
            "status": "pass" if not missing_references else "fail",
            "details": {
                "missingReferences": missing_references[:200],
            },
        }
    )
    checks.extend(build_cross_domain_checks(Path(manifest_context["meta"].get("targetPath", "")).resolve(), domain_plan_overview))
    checks.append(
        {
            "name": "recipe-parity",
            "status": "pass" if parity_results.get("status") in {"pass", "skipped"} else "fail",
            "details": {
                "status": parity_results.get("status"),
                "summary": parity_results.get("summary", {}),
                "reason": parity_results.get("reason", ""),
            },
        }
    )
    checks.append(
        {
            "name": "rewiring-status",
            "status": "pass" if rewiring_summary.get("status") in {"ready", "skipped"} else "human-review",
            "details": rewiring_summary,
        }
    )

    execution_failures = [
        {
            "domain": entry.get("name"),
            "status": entry.get("status"),
        }
        for entry in domain_execution_overview.get("domains", [])
        if isinstance(entry, dict) and entry.get("status") not in {"pass", "completed", "no-op"}
    ]
    if execution_failures:
        checks.append(
            {
                "name": "domain-execution-status",
                "status": "fail",
                "details": {
                    "domains": execution_failures,
                },
            }
        )

    fail_checks = [item["name"] for item in checks if item["status"] == "fail"]
    human_checks = [item["name"] for item in checks if item["status"] == "human-review"]
    passed_checks = [item["name"] for item in checks if item["status"] == "pass"]
    return {
        "checks": checks,
        "routing": {
            "pass": passed_checks,
            "fail": fail_checks,
            "human": human_checks,
        },
        "summary": {
            "status": "fail" if fail_checks else ("human-review" if human_checks else "pass"),
            "totalChecks": len(checks),
            "passed": len(passed_checks),
            "failed": len(fail_checks),
            "humanReview": len(human_checks),
        },
    }


def write_markdown(output_dir: Path, payload: dict):
    lines = [
        "# INTEGRATION_REVIEW",
        "",
        f"- Status: {payload['summary']['status']}",
        f"- Passed: {payload['summary']['passed']}",
        f"- Failed: {payload['summary']['failed']}",
        f"- Human review: {payload['summary']['humanReview']}",
        "",
        "## Checks",
    ]
    for check in payload.get("checks", []):
        lines.append(f"- {check['name']}: {check['status']}")
    write_text(output_dir / "INTEGRATION_REVIEW.md", "\n".join(lines))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tier2_integration_checker.py <manifest-path> <output-dir>", file=sys.stderr)
        return 1

    manifest_context = load_manifest_context(sys.argv[1], FRAMEWORK_DIR)
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_review(manifest_context, output_dir)
    write_json(output_dir / "integration-review.json", payload)
    write_markdown(output_dir, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Phase artifact validator for the migration framework.

Validates required files and minimal structural contracts so the orchestrator can
fail fast before proceeding to the next stage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def require_file(path: Path, errors: list[str]):
    if not path.exists():
        errors.append(f"Missing file: {path}")
        return
    if path.is_file() and path.stat().st_size == 0:
        errors.append(f"Empty file: {path}")


def require_non_empty_dir(path: Path, errors: list[str]):
    if not path.exists():
        errors.append(f"Missing directory: {path}")
        return
    if not path.is_dir():
        errors.append(f"Expected directory, found file: {path}")
        return
    if not any(path.iterdir()):
        errors.append(f"Empty directory: {path}")


def validate_discovery(output_dir: Path, errors: list[str]):
    dep_graph = output_dir / "dep-graph.json"
    file_manifest = output_dir / "file-manifest.json"
    symbol_index = output_dir / "symbol-index.json"
    dynamic_risk_report = output_dir / "dynamic-risk-report.json"
    shard_dir = output_dir / "dependency-shards"
    shard_index = shard_dir / "index.json"
    summary = output_dir / "DISCOVERY.md"
    for path in (dep_graph, file_manifest, symbol_index, dynamic_risk_report, shard_index, summary):
        require_file(path, errors)
    require_non_empty_dir(shard_dir, errors)
    if errors:
        return
    dep_graph_json = load_json(dep_graph)
    file_manifest_json = load_json(file_manifest)
    symbol_index_json = load_json(symbol_index)
    dynamic_risk_json = load_json(dynamic_risk_report)
    if not dep_graph_json.get("files"):
        errors.append("dep-graph.json must contain a non-empty 'files' object")
    if not isinstance(file_manifest_json.get("files"), list) or not file_manifest_json["files"]:
        errors.append("file-manifest.json must contain a non-empty 'files' array")
    if not isinstance(symbol_index_json.get("symbols"), list):
        errors.append("symbol-index.json must contain a 'symbols' array")
    if not isinstance(dynamic_risk_json.get("files"), list):
        errors.append("dynamic-risk-report.json must contain a 'files' array")


def validate_planning(output_dir: Path, errors: list[str]):
    required = [
        output_dir / "planning-input.json",
        output_dir / "risk-policy.json",
        output_dir / "PLAN.md",
        output_dir / "AGENTS.md",
        output_dir / "migration-batches.json",
        output_dir / "planning-overview.json",
    ]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    planning_input = load_json(output_dir / "planning-input.json")
    batches = load_json(output_dir / "migration-batches.json")
    overview = load_json(output_dir / "planning-overview.json")
    risk_policy = load_json(output_dir / "risk-policy.json")
    if not isinstance(planning_input.get("batchPlan"), list) or not planning_input["batchPlan"]:
        errors.append("planning-input.json must contain a non-empty 'batchPlan' array")
    if not isinstance(batches.get("batches"), list) or not batches["batches"]:
        errors.append("migration-batches.json must contain a non-empty 'batches' array")
    if not isinstance(overview.get("artifactContracts"), list) or not overview["artifactContracts"]:
        errors.append("planning-overview.json must contain non-empty artifactContracts")
    if not isinstance(risk_policy, dict) or not risk_policy:
        errors.append("risk-policy.json must contain a non-empty object")


def validate_execution(output_dir: Path, errors: list[str]):
    required = [output_dir / "EXECUTION.md", output_dir / "execution-summary.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    summary = load_json(output_dir / "execution-summary.json")
    if not isinstance(summary.get("batches"), list) or not summary["batches"]:
        errors.append("execution-summary.json must contain a non-empty 'batches' array")


def validate_review(output_dir: Path, errors: list[str]):
    required = [
        output_dir / "REVIEW.md",
        output_dir / "review-results.json",
        output_dir / "validation-report.json",
        output_dir / "parity-results.json",
    ]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    validation = load_json(output_dir / "validation-report.json")
    if not isinstance(validation.get("checks"), list) or not validation["checks"]:
        errors.append("validation-report.json must contain a non-empty 'checks' array")


def validate_reiterate(output_dir: Path, errors: list[str]):
    required = [
        output_dir / "REITERATE.md",
        output_dir / "reiterate-results.json",
        output_dir / "agents-md-patches.md",
        output_dir / "agents-md.patch.json",
    ]
    for path in required:
        require_file(path, errors)


def validate_foundation(output_dir: Path, errors: list[str]):
    required = [
        output_dir / "FOUNDATION.md",
        output_dir / "foundation-summary.json",
        output_dir / "discovery.graph.json",
        output_dir / "symbolic-batches.json",
        output_dir / "symbol-registry.json",
        output_dir / "migration-order.json",
    ]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    summary = load_json(output_dir / "foundation-summary.json")
    if not isinstance(summary.get("domains"), list) or not summary["domains"]:
        errors.append("foundation-summary.json must contain a non-empty 'domains' array")
    batches = load_json(output_dir / "symbolic-batches.json")
    if not isinstance(batches.get("batches"), list) or not batches["batches"]:
        errors.append("symbolic-batches.json must contain a non-empty 'batches' array")


def validate_module_discovery(output_dir: Path, errors: list[str]):
    required = [output_dir / "MODULE_DISCOVERY.md", output_dir / "module-discovery.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    payload = load_json(output_dir / "module-discovery.json")
    if not isinstance(payload.get("modules"), list) or not payload["modules"]:
        errors.append("module-discovery.json must contain a non-empty 'modules' array")


def validate_domain_discovery(output_dir: Path, errors: list[str]):
    required = [output_dir / "DOMAIN_DISCOVERY.md", output_dir / "domain-discovery-overview.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    overview = load_json(output_dir / "domain-discovery-overview.json")
    domains = overview.get("domains")
    if not isinstance(domains, list) or not domains:
        errors.append("domain-discovery-overview.json must contain a non-empty 'domains' array")
        return
    for domain in domains:
        if not isinstance(domain, dict):
            errors.append("domain-discovery-overview.json domains entries must be objects")
            continue
        for key in ("name", "discoveryJson", "summaryMd"):
            value = domain.get(key)
            if key == "name" and not isinstance(value, str):
                errors.append(f"domain discovery entry missing valid {key}: {domain}")
                continue
            if key != "name" and (not isinstance(value, str) or not Path(value).exists()):
                errors.append(f"domain discovery entry missing valid {key}: {domain}")
        discovery_json = domain.get("discoveryJson")
        if isinstance(discovery_json, str) and Path(discovery_json).exists():
            payload = load_json(Path(discovery_json))
            if not isinstance(payload.get("ownedFiles"), list):
                errors.append(f"{discovery_json} must contain an 'ownedFiles' array")
            if not isinstance(payload.get("ownedSymbols"), list):
                errors.append(f"{discovery_json} must contain an 'ownedSymbols' array")
            if not isinstance(payload.get("summary"), dict):
                errors.append(f"{discovery_json} must contain a 'summary' object")


def validate_conflict_resolution(output_dir: Path, errors: list[str]):
    required = [output_dir / "CONFLICT_RESOLUTION.md", output_dir / "conflict-resolution.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    payload = load_json(output_dir / "conflict-resolution.json")
    if "status" not in payload:
        errors.append("conflict-resolution.json must contain a 'status' field")
    for key in ("resolved", "shared", "unresolved"):
        if not isinstance(payload.get(key), list):
            errors.append(f"conflict-resolution.json must contain a '{key}' array")


def validate_domain_planning(output_dir: Path, errors: list[str]):
    required = [output_dir / "DOMAIN_PLANNING.md", output_dir / "domain-plan-overview.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    overview = load_json(output_dir / "domain-plan-overview.json")
    domains = overview.get("domains")
    if not isinstance(domains, list) or not domains:
        errors.append("domain-plan-overview.json must contain a non-empty 'domains' array")
        return
    for domain in domains:
        if not isinstance(domain, dict):
            errors.append("domain-plan-overview.json domains entries must be objects")
            continue
        for key in ("name", "executionOrder", "decoupledFilesPath", "rewiringImportsPath", "agentsPath", "summaryMd"):
            value = domain.get(key)
            if key == "name" and not isinstance(value, str):
                errors.append(f"domain planning entry missing valid {key}: {domain}")
                continue
            if key == "executionOrder" and not isinstance(value, int):
                errors.append(f"domain planning entry missing valid {key}: {domain}")
                continue
            if key not in {"name", "executionOrder"} and (not isinstance(value, str) or not Path(value).exists()):
                errors.append(f"domain planning entry missing valid {key}: {domain}")
        decoupled_path = domain.get("decoupledFilesPath")
        if isinstance(decoupled_path, str) and Path(decoupled_path).exists():
            payload = load_json(Path(decoupled_path))
            if not isinstance(payload.get("ownedFiles"), list):
                errors.append(f"{decoupled_path} must contain an 'ownedFiles' array")
            if not isinstance(payload.get("summary"), dict):
                errors.append(f"{decoupled_path} must contain a 'summary' object")
        rewiring_path = domain.get("rewiringImportsPath")
        if isinstance(rewiring_path, str) and Path(rewiring_path).exists():
            payload = load_json(Path(rewiring_path))
            if not isinstance(payload.get("plannedImports"), list):
                errors.append(f"{rewiring_path} must contain a 'plannedImports' array")


def validate_domain_execution(output_dir: Path, errors: list[str]):
    required = [output_dir / "DOMAIN_EXECUTION.md", output_dir / "domain-execution-overview.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    overview = load_json(output_dir / "domain-execution-overview.json")
    domains = overview.get("domains")
    if not isinstance(domains, list) or not domains:
        errors.append("domain-execution-overview.json must contain a non-empty 'domains' array")
        return
    for domain in domains:
        if not isinstance(domain, dict):
            errors.append("domain-execution-overview.json domains entries must be objects")
            continue
        for key in ("name", "status", "executionJson", "summaryMd"):
            value = domain.get(key)
            if key in {"name", "status"} and not isinstance(value, str):
                errors.append(f"domain execution entry missing valid {key}: {domain}")
                continue
            if key not in {"name", "status"} and (not isinstance(value, str) or not Path(value).exists()):
                errors.append(f"domain execution entry missing valid {key}: {domain}")
        execution_json = domain.get("executionJson")
        if isinstance(execution_json, str) and Path(execution_json).exists():
            payload = load_json(Path(execution_json))
            if not isinstance(payload.get("files"), list):
                errors.append(f"{execution_json} must contain a 'files' array")
            if not isinstance(payload.get("summary"), dict):
                errors.append(f"{execution_json} must contain a 'summary' object")


def validate_rewiring(output_dir: Path, errors: list[str]):
    required = [output_dir / "REWIRING.md", output_dir / "rewiring-summary.json", output_dir / "rewiring-batches.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    payload = load_json(output_dir / "rewiring-batches.json")
    if not isinstance(payload.get("batches"), list) or not payload["batches"]:
        errors.append("rewiring-batches.json must contain a non-empty 'batches' array")
    if not isinstance(payload.get("globalRewriteMap"), list):
        errors.append("rewiring-batches.json must contain a 'globalRewriteMap' array")
    summary = load_json(output_dir / "rewiring-summary.json")
    if "status" not in summary:
        errors.append("rewiring-summary.json must contain a 'status' field")


def validate_integration_review(output_dir: Path, errors: list[str]):
    required = [output_dir / "INTEGRATION_REVIEW.md", output_dir / "integration-review.json", output_dir / "parity-results.json"]
    for path in required:
        require_file(path, errors)
    if errors:
        return
    payload = load_json(output_dir / "integration-review.json")
    if not isinstance(payload.get("checks"), list) or not payload["checks"]:
        errors.append("integration-review.json must contain a non-empty 'checks' array")
    routing = payload.get("routing")
    if not isinstance(routing, dict):
        errors.append("integration-review.json must contain a 'routing' object")
    else:
        for key in ("pass", "fail", "human"):
            if not isinstance(routing.get(key), list):
                errors.append(f"integration-review.json routing must contain a '{key}' array")
    if not isinstance(payload.get("summary"), dict):
        errors.append("integration-review.json must contain a 'summary' object")


VALIDATORS = {
    "discovery": validate_discovery,
    "planning": validate_planning,
    "execution": validate_execution,
    "review": validate_review,
    "reiterate": validate_reiterate,
    "foundation": validate_foundation,
    "module_discovery": validate_module_discovery,
    "domain_discovery": validate_domain_discovery,
    "conflict_resolution": validate_conflict_resolution,
    "domain_planning": validate_domain_planning,
    "domain_execution": validate_domain_execution,
    "rewiring": validate_rewiring,
    "integration_review": validate_integration_review,
}


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: validate_artifacts.py <phase> <output-dir>", file=sys.stderr)
        return 1

    phase = sys.argv[1]
    output_dir = Path(sys.argv[2]).resolve()
    validator = VALIDATORS.get(phase)
    if validator is None:
        print(f"Unknown phase: {phase}", file=sys.stderr)
        return 1

    errors: list[str] = []
    validator(output_dir, errors)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Artifacts valid for phase {phase}: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

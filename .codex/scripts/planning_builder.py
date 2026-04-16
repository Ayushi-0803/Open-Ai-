#!/usr/bin/env python3
"""
Deterministic planning input builder.

Consumes discovery artifacts and produces the dependency-ordered planning
contract that the LLM planning phase must follow instead of recomputing order
and risk heuristically.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def is_test_entry(entry: dict[str, Any]) -> bool:
    return entry.get("type") == "test" or bool(entry.get("hasTests") and entry.get("path") == entry.get("testFile"))


def deterministic_risk_reasons(entry: dict[str, Any], circular_paths: set[str]) -> list[str]:
    reasons: list[str] = []
    if entry.get("path") in circular_paths:
        reasons.append("circular dependency")
    if not entry.get("hasTests"):
        reasons.append("no direct test coverage")
    if entry.get("complexity") == "high":
        reasons.append("high complexity")
    dependent_count = len(entry.get("dependents", []))
    if dependent_count >= 4:
        reasons.append(f"high fan-in ({dependent_count} dependents)")
    if not reasons:
        reasons.append("deterministic auto-tier baseline")
    return reasons


def build_non_test_graph(entries: list[dict[str, Any]]) -> tuple[dict[str, list[str]], dict[str, int]]:
    entry_map = {entry["path"]: entry for entry in entries}
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {entry["path"]: 0 for entry in entries}

    for entry in entries:
        current = entry["path"]
        for dep in entry.get("dependencies", []):
            if dep not in entry_map:
                continue
            adjacency[dep].append(current)
            indegree[current] += 1

    for node in adjacency:
        adjacency[node].sort()
    return adjacency, indegree


def layer_batches(entries: list[dict[str, Any]]) -> tuple[list[list[str]], list[str]]:
    adjacency, indegree = build_non_test_graph(entries)
    queue = deque(sorted(path for path, degree in indegree.items() if degree == 0))
    layers: list[list[str]] = []
    seen: set[str] = set()

    while queue:
        current_layer = list(queue)
        queue.clear()
        layers.append(current_layer)
        for node in current_layer:
            seen.add(node)
            for dependent in adjacency.get(node, []):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)
        queue = deque(sorted(queue))

    leftovers = sorted(path for path in indegree if path not in seen)
    return layers, leftovers


def build_batch_plan(file_manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    entries = sorted(file_manifest["files"], key=lambda entry: entry["path"])
    test_entries = [entry for entry in entries if is_test_entry(entry)]
    non_test_entries = [entry for entry in entries if not is_test_entry(entry)]

    layers, cycle_paths = layer_batches(non_test_entries)
    cycle_set = set(cycle_paths)
    entry_map = {entry["path"]: entry for entry in entries}

    batches: list[dict[str, Any]] = []
    risk_assignments: list[dict[str, Any]] = []
    batch_index = 1

    for depth, layer_paths in enumerate(layers):
        files = []
        for path in layer_paths:
            entry = entry_map[path]
            reasons = deterministic_risk_reasons(entry, cycle_set)
            risk_assignments.append(
                {
                    "path": path,
                    "riskTier": entry["riskTier"],
                    "reasons": reasons,
                    "complexity": entry["complexity"],
                    "hasTests": entry["hasTests"],
                    "dependencyDepth": depth,
                }
            )
            files.append(
                {
                    "path": path,
                    "riskTier": entry["riskTier"],
                    "dependencies": entry.get("dependencies", []),
                    "patterns": entry.get("patterns", []),
                    "hasTests": entry.get("hasTests", False),
                    "dependencyDepth": depth,
                }
            )

        batches.append(
            {
                "id": f"batch-{batch_index}",
                "name": f"Dependency depth {depth}",
                "category": "code",
                "parallelizable": True,
                "dependsOn": [] if batch_index == 1 else [f"batch-{batch_index - 1}"],
                "files": files,
            }
        )
        batch_index += 1

    if cycle_paths:
        files = []
        for path in cycle_paths:
            entry = entry_map[path]
            reasons = deterministic_risk_reasons(entry, cycle_set)
            risk_assignments.append(
                {
                    "path": path,
                    "riskTier": "human",
                    "reasons": reasons,
                    "complexity": entry["complexity"],
                    "hasTests": entry["hasTests"],
                    "dependencyDepth": None,
                }
            )
            files.append(
                {
                    "path": path,
                    "riskTier": "human",
                    "dependencies": entry.get("dependencies", []),
                    "patterns": entry.get("patterns", []),
                    "hasTests": entry.get("hasTests", False),
                    "dependencyDepth": None,
                }
            )

        batches.append(
            {
                "id": f"batch-{batch_index}",
                "name": "Cycle break / manual review",
                "category": "cycle-break",
                "parallelizable": False,
                "dependsOn": [batches[-1]["id"]] if batches else [],
                "files": files,
            }
        )
        batch_index += 1

    if test_entries:
        files = []
        for entry in test_entries:
            reasons = deterministic_risk_reasons(entry, cycle_set)
            risk_assignments.append(
                {
                    "path": entry["path"],
                    "riskTier": entry["riskTier"],
                    "reasons": reasons,
                    "complexity": entry["complexity"],
                    "hasTests": entry["hasTests"],
                    "dependencyDepth": "tests-last",
                }
            )
            files.append(
                {
                    "path": entry["path"],
                    "riskTier": entry["riskTier"],
                    "dependencies": entry.get("dependencies", []),
                    "patterns": entry.get("patterns", []),
                    "hasTests": entry.get("hasTests", False),
                    "dependencyDepth": "tests-last",
                }
            )

        batches.append(
            {
                "id": f"batch-{batch_index}",
                "name": "Tests",
                "category": "tests",
                "parallelizable": True,
                "dependsOn": [batches[-1]["id"]] if batches else [],
                "files": files,
            }
        )

    return batches, sorted(risk_assignments, key=lambda item: item["path"]), cycle_set


def build_planning_contract(discovery_dir: Path) -> dict[str, Any]:
    dep_graph = load_json(discovery_dir / "dep-graph.json")
    file_manifest = load_json(discovery_dir / "file-manifest.json")

    batches, risk_assignments, cycle_set = build_batch_plan(file_manifest)
    human_review_queue = [item for item in risk_assignments if item["riskTier"] == "human"]

    ordered_paths = [file["path"] for batch in batches for file in batch["files"]]

    return {
        "summary": {
            "totalFiles": file_manifest["summary"]["totalFiles"],
            "nonTestFiles": sum(1 for entry in file_manifest["files"] if not is_test_entry(entry)),
            "testFiles": sum(1 for entry in file_manifest["files"] if is_test_entry(entry)),
            "totalBatches": len(batches),
            "cyclePaths": sorted(cycle_set),
        },
        "policy": {
            "batchingStrategy": "dependency-depth with tests last",
            "riskStrategy": "deterministic baseline from complexity, test coverage, fan-in, and cycles",
            "llmContract": "Planning must preserve batch order and risk tiers unless it records an explicit exception.",
        },
        "orderedPaths": ordered_paths,
        "batchPlan": batches,
        "riskAssignments": risk_assignments,
        "humanReviewQueue": human_review_queue,
        "entryPoints": dep_graph.get("entryPoints", []),
        "leafNodes": dep_graph.get("leafNodes", []),
        "externalPackages": dep_graph.get("externalPackages", []),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: planning_builder.py <discovery-dir> <planning-dir>", file=sys.stderr)
        return 1

    discovery_dir = Path(sys.argv[1]).resolve()
    planning_dir = Path(sys.argv[2]).resolve()
    planning_dir.mkdir(parents=True, exist_ok=True)

    if not discovery_dir.exists():
        print(f"Discovery directory does not exist: {discovery_dir}", file=sys.stderr)
        return 1

    contract = build_planning_contract(discovery_dir)
    (planning_dir / "planning-input.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    (planning_dir / "risk-policy.json").write_text(json.dumps(contract["policy"], indent=2) + "\n", encoding="utf-8")
    print(f"Wrote planning contract to {planning_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

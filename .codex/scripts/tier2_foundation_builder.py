#!/usr/bin/env python3
"""
Deterministic Tier 2 foundation artifact builder.

Builds the shared symbol/file foundation required by the Tier 2 pipeline using
only stdlib-backed analysis so downstream agents start from stable artifacts.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from discovery_builder import build_artifacts


COMPLEXITY_WEIGHT = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def infer_domains(file_manifest: dict[str, Any]) -> list[str]:
    domains: set[str] = set()
    for entry in file_manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if isinstance(entry_type, str) and entry_type not in {"module", "test"}:
            domains.add(entry_type.replace("-", "_"))
        for pattern in entry.get("patterns", []):
            if pattern == "config-module":
                domains.add("config")
            elif pattern == "middleware":
                domains.add("middleware")
            elif pattern == "handler":
                domains.add("routes")
            elif pattern == "test-file":
                domains.add("tests")
    domains.add("core")
    return sorted(domains)


def build_symbolic_batches(symbols: list[dict[str, Any]]) -> dict[str, Any]:
    if not symbols:
        return {"summary": {"totalSymbols": 0, "totalBatches": 0}, "batches": []}

    batch_count = max(1, math.ceil(len(symbols) / 50))
    buckets = [{"weight": 0, "symbols": []} for _ in range(batch_count)]
    weighted_symbols = sorted(
        symbols,
        key=lambda symbol: (
            COMPLEXITY_WEIGHT.get(str(symbol.get("complexity", "low")), 1),
            str(symbol.get("path", "")),
            str(symbol.get("symbol", "")),
        ),
        reverse=True,
    )

    for symbol in weighted_symbols:
        weight = COMPLEXITY_WEIGHT.get(str(symbol.get("complexity", "low")), 1)
        target = min(buckets, key=lambda bucket: (bucket["weight"], len(bucket["symbols"])))
        target["symbols"].append(symbol)
        target["weight"] += weight

    batches = []
    for index, bucket in enumerate(buckets, start=1):
        if not bucket["symbols"]:
            continue
        batches.append(
            {
                "id": f"batch-{index}",
                "estimatedWeight": bucket["weight"],
                "symbolCount": len(bucket["symbols"]),
                "paths": sorted({str(symbol.get("path", "")) for symbol in bucket["symbols"]}),
                "symbols": sorted(
                    bucket["symbols"],
                    key=lambda symbol: (str(symbol.get("path", "")), str(symbol.get("symbol", ""))),
                ),
            }
        )

    return {
        "summary": {
            "totalSymbols": len(symbols),
            "totalBatches": len(batches),
            "batchingStrategy": "weighted round-robin by symbol complexity",
        },
        "batches": batches,
    }


def build_symbol_registry(symbols: list[dict[str, Any]], dep_graph: dict[str, Any]) -> dict[str, Any]:
    files = dep_graph.get("files", {})
    registry = []
    for symbol in sorted(symbols, key=lambda item: (str(item.get("path", "")), str(item.get("symbol", "")))):
        path = str(symbol.get("path", ""))
        file_entry = files.get(path, {})
        registry.append(
            {
                "symbolId": f"{path}::{symbol.get('symbol', '')}",
                "symbol": symbol.get("symbol"),
                "path": path,
                "complexity": symbol.get("complexity"),
                "claimedBy": None,
                "status": "unclaimed",
                "externalConsumers": file_entry.get("importedBy", []),
            }
        )
    return {
        "summary": {
            "totalSymbols": len(registry),
            "claimedSymbols": 0,
            "unclaimedSymbols": len(registry),
        },
        "symbols": registry,
    }


def layer_file_graph(file_manifest: dict[str, Any]) -> tuple[list[list[str]], list[str]]:
    entries = {
        entry["path"]: entry
        for entry in file_manifest.get("files", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {path: 0 for path in entries}

    for path, entry in entries.items():
        for dep in entry.get("dependencies", []):
            if dep not in entries:
                continue
            adjacency[dep].append(path)
            indegree[path] += 1

    queue = deque(sorted(path for path, degree in indegree.items() if degree == 0))
    layers: list[list[str]] = []
    seen: set[str] = set()

    while queue:
        current = list(queue)
        queue.clear()
        layers.append(current)
        for path in current:
            seen.add(path)
            for dependent in sorted(adjacency.get(path, [])):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)
        queue = deque(sorted(queue))

    cycles = sorted(path for path in indegree if path not in seen)
    return layers, cycles


def build_migration_order(file_manifest: dict[str, Any]) -> dict[str, Any]:
    layers, cycles = layer_file_graph(file_manifest)
    return {
        "summary": {
            "totalLayers": len(layers),
            "cycleCount": len(cycles),
        },
        "layers": [
            {
                "id": f"layer-{index + 1}",
                "paths": layer,
            }
            for index, layer in enumerate(layers)
        ],
        "cyclePaths": cycles,
    }


def build_foundation(source_path: Path) -> dict[str, Any]:
    base = build_artifacts(source_path)
    dep_graph = base["dep_graph"]
    file_manifest = base["file_manifest"]
    symbols = base["symbol_index"]["symbols"]
    domains = infer_domains(file_manifest)

    discovery_graph = {
        "summary": {
            "totalFiles": len(dep_graph.get("files", {})),
            "totalSymbols": len(symbols),
            "externalPackageCount": len(dep_graph.get("externalPackages", [])),
        },
        **dep_graph,
    }
    symbolic_batches = build_symbolic_batches(symbols)
    symbol_registry = build_symbol_registry(symbols, dep_graph)
    migration_order = build_migration_order(file_manifest)
    foundation_summary = {
        "domains": domains,
        "summary": {
            "totalFiles": len(dep_graph.get("files", {})),
            "totalSymbols": len(symbols),
            "totalBatches": symbolic_batches["summary"]["totalBatches"],
            "totalLayers": migration_order["summary"]["totalLayers"],
        },
        "hints": {
            "entryPoints": discovery_graph.get("entryPoints", []),
            "leafNodes": discovery_graph.get("leafNodes", []),
            "externalPackages": discovery_graph.get("externalPackages", []),
        },
    }
    return {
        "foundation_summary": foundation_summary,
        "discovery_graph": discovery_graph,
        "symbolic_batches": symbolic_batches,
        "symbol_registry": symbol_registry,
        "migration_order": migration_order,
    }


def write_markdown(output_dir: Path, foundation: dict[str, Any]):
    summary = foundation["foundation_summary"]
    lines = [
        "# FOUNDATION",
        "",
        f"- Domains: {', '.join(summary['domains'])}",
        f"- Files: {summary['summary']['totalFiles']}",
        f"- Symbols: {summary['summary']['totalSymbols']}",
        f"- Symbolic batches: {summary['summary']['totalBatches']}",
        f"- Migration layers: {summary['summary']['totalLayers']}",
        "",
        "## Entry Points",
    ]
    for path in summary["hints"]["entryPoints"][:10]:
        lines.append(f"- {path}")
    lines.extend(["", "## External Packages"])
    for package in summary["hints"]["externalPackages"][:20]:
        lines.append(f"- {package}")
    (output_dir / "FOUNDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tier2_foundation_builder.py <source-path> <output-dir>", file=sys.stderr)
        return 1

    source_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        print(f"Source path does not exist: {source_path}", file=sys.stderr)
        return 1

    foundation = build_foundation(source_path)
    (output_dir / "foundation-summary.json").write_text(json.dumps(foundation["foundation_summary"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "discovery.graph.json").write_text(json.dumps(foundation["discovery_graph"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "symbolic-batches.json").write_text(json.dumps(foundation["symbolic_batches"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "symbol-registry.json").write_text(json.dumps(foundation["symbol_registry"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "migration-order.json").write_text(json.dumps(foundation["migration_order"], indent=2) + "\n", encoding="utf-8")
    write_markdown(output_dir, foundation)
    print(f"Wrote Tier 2 foundation artifacts to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Deterministic Tier 2 module discovery builder.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from tier2_common import load_json, write_json, write_text


def bucket_name(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if len(parts) >= 2:
        return parts[0]
    if parts:
        return Path(parts[0]).stem
    return "root"


def build_modules(foundation_dir: Path) -> dict:
    graph = load_json(foundation_dir / "discovery.graph.json")
    files = graph.get("files", {})
    buckets: dict[str, list[dict]] = defaultdict(list)
    for rel_path, entry in files.items():
        if isinstance(entry, dict):
            buckets[bucket_name(rel_path)].append(entry)

    modules: list[dict] = []
    for name, entries in sorted(buckets.items()):
        paths = sorted(str(entry.get("path", "")) for entry in entries if entry.get("path"))
        internal_imports = sum(len(entry.get("imports", {}).get("internal", [])) for entry in entries)
        external_imports = sorted({pkg for entry in entries for pkg in entry.get("imports", {}).get("external", [])})
        risky_files = sorted(str(entry.get("path", "")) for entry in entries if entry.get("complexity") == "high")
        modules.append(
            {
                "name": name,
                "paths": paths,
                "summary": {
                    "fileCount": len(paths),
                    "highComplexityFiles": len(risky_files),
                    "internalImportEdges": internal_imports,
                    "externalPackages": external_imports,
                },
                "risks": [
                    f"High complexity files: {', '.join(risky_files[:5])}" if risky_files else "No high complexity files detected.",
                    "External package usage present." if external_imports else "No external package usage detected.",
                ],
            }
        )

    return {
        "summary": {
            "totalModules": len(modules),
            "totalFiles": len(files),
        },
        "modules": modules,
    }


def write_markdown(output_dir: Path, payload: dict):
    lines = [
        "# MODULE_DISCOVERY",
        "",
        f"- Modules: {payload['summary']['totalModules']}",
        f"- Files: {payload['summary']['totalFiles']}",
        "",
        "## Module Summary",
    ]
    for module in payload.get("modules", []):
        lines.append(
            f"- {module['name']}: {module['summary']['fileCount']} files, "
            f"{module['summary']['highComplexityFiles']} high-complexity files"
        )
    write_text(output_dir / "MODULE_DISCOVERY.md", "\n".join(lines))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tier2_module_discovery_builder.py <foundation-dir> <output-dir>", file=sys.stderr)
        return 1

    foundation_dir = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_modules(foundation_dir)
    write_json(output_dir / "module-discovery.json", payload)
    write_markdown(output_dir, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

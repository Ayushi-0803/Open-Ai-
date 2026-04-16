#!/usr/bin/env python3
"""
Deterministic Tier 2 conflict resolution builder.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tier2_common import (
    domain_priority_map,
    load_manifest_context,
    load_json,
    phase_output_dir,
    write_json,
    write_text,
)


FRAMEWORK_DIR = Path(__file__).resolve().parents[1]


def build_resolution(manifest_context: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    summaries_dir = manifest_context["summaries_dir"]
    overview = load_json(phase_output_dir(summaries_dir, "domain_discovery") / "domain-discovery-overview.json")
    priorities = domain_priority_map(
        manifest_context["domains"],
        manifest_context["domain_ordering"],
        manifest_context["recipe_manifest"],
    )

    path_claims: dict[str, dict[str, Any]] = {}
    for domain_entry in overview.get("domains", []):
        if not isinstance(domain_entry, dict):
            continue
        domain = domain_entry.get("name")
        discovery_json = domain_entry.get("discoveryJson")
        if not domain or not discovery_json:
            continue
        payload = load_json(Path(discovery_json))
        for rel_path in payload.get("ownedFiles", []):
            path_claims.setdefault(rel_path, {"owners": [], "sharedBy": []})
            path_claims[rel_path]["owners"].append(domain)
        for rel_path in payload.get("sharedCandidates", []):
            path_claims.setdefault(rel_path, {"owners": [], "sharedBy": []})
            if domain not in path_claims[rel_path]["sharedBy"]:
                path_claims[rel_path]["sharedBy"].append(domain)

    resolved = []
    shared = []
    unresolved = []

    for rel_path, claim in sorted(path_claims.items()):
        owners = sorted(set(claim["owners"]))
        shared_by = sorted(set(claim["sharedBy"]))
        if len(owners) == 1:
            resolved.append({"path": rel_path, "domain": owners[0], "reason": "single deterministic owner"})
            continue
        if len(owners) > 1:
            owners_sorted = sorted(owners, key=lambda domain: (priorities.get(domain, 999), domain))
            if priorities.get(owners_sorted[0], 999) != priorities.get(owners_sorted[1], 999):
                resolved.append(
                    {
                        "path": rel_path,
                        "domain": owners_sorted[0],
                        "reason": "resolved by configured domain priority",
                        "alternates": owners_sorted[1:],
                    }
                )
            else:
                unresolved.append(
                    {
                        "path": rel_path,
                        "candidateDomains": owners_sorted,
                        "reason": "multiple equal-priority domain owners",
                    }
                )
            continue
        if shared_by:
            shared.append(
                {
                    "path": rel_path,
                    "domains": shared_by,
                    "reason": "flagged as a shared candidate without a deterministic sole owner",
                }
            )
            continue
        unresolved.append(
            {
                "path": rel_path,
                "candidateDomains": [],
                "reason": "no domain ownership information found",
            }
        )

    status = "resolved" if not unresolved else "needs-human-review"
    return {
        "status": status,
        "summary": {
            "resolvedCount": len(resolved),
            "sharedCount": len(shared),
            "unresolvedCount": len(unresolved),
        },
        "resolved": resolved,
        "shared": shared,
        "unresolved": unresolved,
    }


def write_markdown(output_dir: Path, payload: dict):
    lines = [
        "# CONFLICT_RESOLUTION",
        "",
        f"- Status: {payload['status']}",
        f"- Resolved: {payload['summary']['resolvedCount']}",
        f"- Shared: {payload['summary']['sharedCount']}",
        f"- Unresolved: {payload['summary']['unresolvedCount']}",
    ]
    if payload["unresolved"]:
        lines.extend(["", "## Human Review Needed"])
        for item in payload["unresolved"][:20]:
            lines.append(f"- {item['path']}: {item['reason']}")
    write_text(output_dir / "CONFLICT_RESOLUTION.md", "\n".join(lines))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tier2_conflict_resolution_builder.py <manifest-path> <output-dir>", file=sys.stderr)
        return 1

    manifest_context = load_manifest_context(sys.argv[1], FRAMEWORK_DIR)
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_resolution(manifest_context, output_dir)
    write_json(output_dir / "conflict-resolution.json", payload)
    write_markdown(output_dir, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

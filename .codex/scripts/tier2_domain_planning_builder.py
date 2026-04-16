#!/usr/bin/env python3
"""
Deterministic Tier 2 domain planning prebuilder.
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
    render_template,
    resolve_existing_target_file,
    safe_domain_token,
    topo_sort_domains,
    write_json,
    write_text,
)


FRAMEWORK_DIR = Path(__file__).resolve().parents[1]


def load_templates(recipe_assets: dict[str, Any]) -> dict[str, Path]:
    recipe_root = recipe_assets.get("recipe_root")
    if not recipe_root:
        return {}
    root = Path(recipe_root)
    return {
        "discovery": root / "tier2-discovery.md.tmpl",
        "planning": root / "tier2-planning.md.tmpl",
        "execution": root / "tier2-execution.md.tmpl",
    }


def build_domain_payloads(manifest_context: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    summaries_dir = manifest_context["summaries_dir"]
    foundation_graph = load_json(phase_output_dir(summaries_dir, "foundation") / "discovery.graph.json")
    domain_overview = load_json(phase_output_dir(summaries_dir, "domain_discovery") / "domain-discovery-overview.json")
    conflict_resolution = load_json(phase_output_dir(summaries_dir, "conflict_resolution") / "conflict-resolution.json")
    domains = [entry["name"] for entry in domain_overview.get("domains", []) if isinstance(entry, dict) and entry.get("name")]
    ordered_domains = topo_sort_domains(domains, manifest_context["domain_ordering"])
    templates = load_templates(manifest_context["recipe_assets"])
    target_root = Path(manifest_context["meta"].get("targetPath", "")).resolve()

    ownership = {item["path"]: item["domain"] for item in conflict_resolution.get("resolved", []) if isinstance(item, dict) and item.get("domain")}
    shared_paths = {item["path"]: item.get("domains", []) for item in conflict_resolution.get("shared", []) if isinstance(item, dict)}
    files = foundation_graph.get("files", {})
    overview_domains: list[dict[str, Any]] = []

    for domain_entry in domain_overview.get("domains", []):
        if not isinstance(domain_entry, dict):
            continue
        domain = domain_entry.get("name")
        if not domain:
            continue
        token = safe_domain_token(domain)
        discovery_payload = load_json(Path(domain_entry["discoveryJson"]))
        planning_dir = output_dir / token / "planning"
        owned_files = discovery_payload.get("ownedFiles", [])
        cross_domain_imports = []
        target_candidates = []

        for rel_path in owned_files:
            entry = files.get(rel_path, {})
            if not isinstance(entry, dict):
                continue
            for dependency in entry.get("imports", {}).get("internal", []):
                dependency_domain = ownership.get(str(dependency))
                if not dependency_domain or dependency_domain == domain:
                    continue
                source_candidates = infer_target_candidate_paths(rel_path)
                dependency_candidates = infer_target_candidate_paths(str(dependency))
                cross_domain_imports.append(
                    {
                        "sourcePath": rel_path,
                        "sourceDomain": domain,
                        "dependencyPath": str(dependency),
                        "dependencyDomain": dependency_domain,
                        "rewriteKind": "cross-domain-import",
                        "targetFileCandidates": source_candidates,
                        "targetDependencyCandidates": dependency_candidates,
                        "resolvedTargetFile": resolve_existing_target_file(target_root, source_candidates) if target_root.exists() else None,
                        "resolvedDependencyTarget": resolve_existing_target_file(target_root, dependency_candidates) if target_root.exists() else None,
                        "safeRewrite": False,
                        "notes": [
                            "Verify import path after target generation.",
                            "Promote to safe rewrite only after target files exist unambiguously.",
                        ],
                    }
                )
            target_candidates.append(
                {
                    "sourcePath": rel_path,
                    "targetCandidates": infer_target_candidate_paths(rel_path),
                }
            )

        shared_file_entries = [{"path": path, "domains": shared_paths.get(path, [])} for path in owned_files if path in shared_paths]
        decoupled_payload = {
            "domain": domain,
            "executionOrder": ordered_domains.index(domain) + 1 if domain in ordered_domains else None,
            "dependsOnDomains": manifest_context["domain_ordering"].get(domain, []),
            "ownedFiles": owned_files,
            "sharedFiles": shared_file_entries,
            "targetCandidates": target_candidates,
            "summary": {
                "ownedFileCount": len(owned_files),
                "sharedFileCount": len(shared_file_entries),
                "crossDomainImportCount": len(cross_domain_imports),
            },
        }
        rewiring_payload = {
            "domain": domain,
            "dependsOnDomains": manifest_context["domain_ordering"].get(domain, []),
            "plannedImports": cross_domain_imports,
            "summary": {
                "totalRewrites": len(cross_domain_imports),
                "safeRewriteCandidates": sum(1 for item in cross_domain_imports if item["safeRewrite"]),
            },
        }

        template_values = {
            "domain": token,
            "domain_name": domain,
        }
        planning_template = render_template(templates.get("planning"), template_values)
        agents_lines = [
            f"# AGENTS.{domain}",
            "",
            f"- Domain: {domain}",
            f"- Execution order: {decoupled_payload['executionOrder']}",
            f"- Depends on: {', '.join(decoupled_payload['dependsOnDomains']) or 'none'}",
            f"- Owned files: {decoupled_payload['summary']['ownedFileCount']}",
            f"- Cross-domain imports: {decoupled_payload['summary']['crossDomainImportCount']}",
            "",
            "## Deterministic Rules",
            "",
            "- Preserve file ownership recorded in domain discovery unless conflict resolution says otherwise.",
            "- Record unresolved imports in execution artifacts instead of silently deleting them.",
            "- Do not change files outside the claimed domain unless the rewiring plan requires it.",
        ]
        if planning_template:
            agents_lines.extend(["", "## Recipe Template", "", planning_template])
        planning_lines = [
            f"# {domain} Planning",
            "",
            f"- Owned files: {decoupled_payload['summary']['ownedFileCount']}",
            f"- Shared files: {decoupled_payload['summary']['sharedFileCount']}",
            f"- Rewiring actions: {decoupled_payload['summary']['crossDomainImportCount']}",
        ]

        decoupled_path = (planning_dir / f"decoupled-files.{token}.json").resolve()
        rewiring_path = (planning_dir / f"rewiring-imports.{token}.json").resolve()
        agents_path = (planning_dir / f"AGENTS.{token}.md").resolve()
        planning_md_path = (planning_dir / f"planning.{token}.md").resolve()
        write_json(decoupled_path, decoupled_payload)
        write_json(rewiring_path, rewiring_payload)
        write_text(agents_path, "\n".join(agents_lines))
        write_text(planning_md_path, "\n".join(planning_lines))

        overview_domains.append(
            {
                "name": domain,
                "executionOrder": decoupled_payload["executionOrder"],
                "dependsOnDomains": decoupled_payload["dependsOnDomains"],
                "decoupledFilesPath": str(decoupled_path),
                "rewiringImportsPath": str(rewiring_path),
                "agentsPath": str(agents_path),
                "summaryMd": str(planning_md_path),
            }
        )

    return {
        "summary": {
            "totalDomains": len(overview_domains),
            "orderedDomains": ordered_domains,
        },
        "domains": sorted(overview_domains, key=lambda item: (item.get("executionOrder") or 999, item["name"])),
    }


def write_markdown(output_dir: Path, payload: dict):
    lines = [
        "# DOMAIN_PLANNING",
        "",
        f"- Domains: {payload['summary']['totalDomains']}",
        f"- Order: {', '.join(payload['summary']['orderedDomains'])}",
        "",
        "## Planned Domains",
    ]
    for domain in payload.get("domains", []):
        lines.append(
            f"- {domain['name']}: order={domain['executionOrder']}, depends on "
            f"{', '.join(domain['dependsOnDomains']) or 'none'}"
        )
    write_text(output_dir / "DOMAIN_PLANNING.md", "\n".join(lines))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tier2_domain_planning_builder.py <manifest-path> <output-dir>", file=sys.stderr)
        return 1

    manifest_context = load_manifest_context(sys.argv[1], FRAMEWORK_DIR)
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_domain_payloads(manifest_context, output_dir)
    write_json(output_dir / "domain-plan-overview.json", payload)
    write_markdown(output_dir, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

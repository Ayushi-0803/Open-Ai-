#!/usr/bin/env python3
"""
Deterministic Tier 2 domain discovery builder.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from tier2_common import (
    domain_priority_map,
    load_domain_pattern_rules,
    load_manifest_context,
    load_json,
    path_matches_any,
    phase_output_dir,
    safe_domain_token,
    write_json,
    write_text,
)


FRAMEWORK_DIR = Path(__file__).resolve().parents[1]

COMMON_PATTERN_DOMAIN_MAP = {
    "handler": ("interface", "routes"),
    "middleware": ("middleware", "interface"),
    "config-module": ("config", "infrastructure"),
    "test-file": ("tests",),
}


def score_entry(rel_path: str, entry: dict[str, Any], domain: str, rule: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    detection = rule.get("detection", {}) if isinstance(rule, dict) else {}
    file_patterns = detection.get("file_patterns", [])
    path_hints = detection.get("path_hints", [])
    import_hints = detection.get("import_hints", [])
    signal_tags = detection.get("signals", [])
    code_patterns = detection.get("code_patterns", [])

    if path_matches_any(rel_path, file_patterns if isinstance(file_patterns, list) else []):
        score += 10
        reasons.append("recipe file pattern match")
    if any(isinstance(hint, str) and hint.lower() in rel_path.lower() for hint in path_hints if isinstance(path_hints, list)):
        score += 6
        reasons.append("recipe path hint")
    external_imports = entry.get("imports", {}).get("external", [])
    if any(isinstance(hint, str) and hint in external_imports for hint in import_hints if isinstance(import_hints, list)):
        score += 3
        reasons.append("recipe import hint")
    entry_patterns = entry.get("patterns", [])
    if any(isinstance(signal, str) and signal in entry_patterns for signal in signal_tags if isinstance(signal_tags, list)):
        score += 4
        reasons.append("recipe signal match")
    exports = entry.get("exports", [])
    if any(isinstance(pattern, str) and any(pattern.lower() in export.lower() for export in exports) for pattern in code_patterns if isinstance(code_patterns, list)):
        score += 2
        reasons.append("recipe export hint")

    rel_lower = rel_path.lower()
    domain_lower = domain.lower()
    if domain_lower in rel_lower:
        score += 5
        reasons.append("domain token in path")
    for pattern in entry_patterns:
        for mapped_domain in COMMON_PATTERN_DOMAIN_MAP.get(pattern, ()):
            if mapped_domain == domain:
                score += 4
                reasons.append(f"heuristic pattern:{pattern}")
    return score, reasons


def classify_domains(manifest_context: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    summaries_dir = manifest_context["summaries_dir"]
    foundation_dir = phase_output_dir(summaries_dir, "foundation")
    graph = load_json(foundation_dir / "discovery.graph.json")
    symbol_registry = load_json(foundation_dir / "symbol-registry.json")
    domains = manifest_context["domains"] or load_json(foundation_dir / "foundation-summary.json").get("domains", [])
    ordering = manifest_context["domain_ordering"]
    priorities = domain_priority_map(domains, ordering, manifest_context["recipe_manifest"])
    rules = load_domain_pattern_rules(manifest_context["domain_patterns_map"])

    files = graph.get("files", {})
    claims_by_domain: dict[str, dict[str, list[Any]]] = {
        domain: {"ownedFiles": [], "sharedCandidates": [], "reasons": defaultdict(list)}
        for domain in domains
    }
    owner_by_path: dict[str, str] = {}
    shared_paths: dict[str, list[str]] = {}

    for rel_path, entry in sorted(files.items()):
        if not isinstance(entry, dict):
            continue
        scored: list[tuple[str, int, list[str]]] = []
        for domain in domains:
            score, reasons = score_entry(rel_path, entry, domain, rules.get(domain, {}))
            scored.append((domain, score, reasons))
        scored.sort(key=lambda item: (-item[1], priorities.get(item[0], 999), item[0]))
        best_domain, best_score, best_reasons = scored[0] if scored else ("core", 0, ["fallback"])
        close_matches = [domain for domain, score, _ in scored if score > 0 and best_score - score <= 2]
        if not close_matches:
            close_matches = [best_domain]
        owner_by_path[rel_path] = best_domain
        if len(close_matches) > 1:
            shared_paths[rel_path] = close_matches
        claims_by_domain[best_domain]["ownedFiles"].append(rel_path)
        claims_by_domain[best_domain]["reasons"][rel_path] = best_reasons or ["fallback ownership"]
        for shared_domain in close_matches:
            if rel_path not in claims_by_domain[shared_domain]["sharedCandidates"]:
                claims_by_domain[shared_domain]["sharedCandidates"].append(rel_path)

    symbols_by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for symbol in symbol_registry.get("symbols", []):
        if not isinstance(symbol, dict):
            continue
        domain = owner_by_path.get(str(symbol.get("path", "")))
        if domain:
            symbols_by_domain[domain].append(symbol)

    overview_domains: list[dict[str, Any]] = []
    cross_domain_edges = {
        domain: defaultdict(set) for domain in domains
    }
    for rel_path, entry in sorted(files.items()):
        source_domain = owner_by_path.get(rel_path)
        if not source_domain or not isinstance(entry, dict):
            continue
        for dependency in entry.get("imports", {}).get("internal", []):
            dependency_domain = owner_by_path.get(str(dependency))
            if dependency_domain and dependency_domain != source_domain:
                cross_domain_edges[source_domain][dependency_domain].add(str(dependency))

    updated_symbols = []
    for symbol in symbol_registry.get("symbols", []):
        if not isinstance(symbol, dict):
            continue
        domain = owner_by_path.get(str(symbol.get("path", "")))
        patched = dict(symbol)
        if domain:
            patched["claimedBy"] = domain
            patched["status"] = "claimed"
        updated_symbols.append(patched)
    symbol_registry["summary"]["claimedSymbols"] = sum(1 for item in updated_symbols if item.get("claimedBy"))
    symbol_registry["summary"]["unclaimedSymbols"] = max(0, len(updated_symbols) - symbol_registry["summary"]["claimedSymbols"])
    symbol_registry["symbols"] = updated_symbols
    write_json(foundation_dir / "symbol-registry.json", symbol_registry)

    for domain in domains:
        token = safe_domain_token(domain)
        domain_dir = output_dir / token / "discovery"
        owned_files = sorted(claims_by_domain[domain]["ownedFiles"])
        owned_symbols = sorted(
            (
                {
                    "symbol": symbol.get("symbol"),
                    "path": symbol.get("path"),
                    "complexity": symbol.get("complexity"),
                }
                for symbol in symbols_by_domain.get(domain, [])
            ),
            key=lambda item: (str(item["path"]), str(item["symbol"])),
        )
        risks = []
        if any(path in shared_paths for path in owned_files):
            risks.append("Contains files with multi-domain affinity that may need manual review.")
        if not owned_symbols:
            risks.append("No exportable symbols were assigned to this domain.")
        if not risks:
            risks.append("No deterministic discovery risks detected.")

        payload = {
            "domain": domain,
            "summary": {
                "ownedFileCount": len(owned_files),
                "sharedCandidateCount": len(claims_by_domain[domain]["sharedCandidates"]),
                "ownedSymbolCount": len(owned_symbols),
                "crossDomainDependencyCount": sum(len(paths) for paths in cross_domain_edges[domain].values()),
            },
            "ownedFiles": owned_files,
            "ownedSymbols": owned_symbols,
            "sharedCandidates": sorted(claims_by_domain[domain]["sharedCandidates"]),
            "crossDomainDependencies": [
                {
                    "targetDomain": other_domain,
                    "paths": sorted(paths),
                }
                for other_domain, paths in sorted(cross_domain_edges[domain].items())
                if paths
            ],
            "rationale": [
                {
                    "path": rel_path,
                    "reasons": claims_by_domain[domain]["reasons"].get(rel_path, ["fallback ownership"]),
                }
                for rel_path in owned_files
            ],
            "risks": risks,
        }
        json_path = (domain_dir / f"discovery.{token}.json").resolve()
        md_path = (domain_dir / f"discovery.{token}.md").resolve()
        write_json(json_path, payload)
        lines = [
            f"# {domain} Discovery",
            "",
            f"- Owned files: {payload['summary']['ownedFileCount']}",
            f"- Owned symbols: {payload['summary']['ownedSymbolCount']}",
            f"- Shared candidates: {payload['summary']['sharedCandidateCount']}",
            "",
            "## Risks",
        ]
        for risk in payload["risks"]:
            lines.append(f"- {risk}")
        write_text(md_path, "\n".join(lines))
        overview_domains.append(
            {
                "name": domain,
                "symbolCount": payload["summary"]["ownedSymbolCount"],
                "fileCount": payload["summary"]["ownedFileCount"],
                "sharedCandidateCount": payload["summary"]["sharedCandidateCount"],
                "discoveryJson": str(json_path),
                "summaryMd": str(md_path),
            }
        )

    return {
        "summary": {
            "totalDomains": len(overview_domains),
            "totalClaimedFiles": len(owner_by_path),
            "sharedFileCount": len(shared_paths),
        },
        "domains": overview_domains,
    }


def write_markdown(output_dir: Path, overview: dict[str, Any]):
    lines = [
        "# DOMAIN_DISCOVERY",
        "",
        f"- Domains: {overview['summary']['totalDomains']}",
        f"- Claimed files: {overview['summary']['totalClaimedFiles']}",
        f"- Shared candidates: {overview['summary']['sharedFileCount']}",
        "",
        "## Coverage",
    ]
    for domain in overview.get("domains", []):
        lines.append(
            f"- {domain['name']}: {domain['fileCount']} files, {domain['symbolCount']} symbols, "
            f"{domain['sharedCandidateCount']} shared candidates"
        )
    write_text(output_dir / "DOMAIN_DISCOVERY.md", "\n".join(lines))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: tier2_domain_discovery_builder.py <manifest-path> <output-dir>", file=sys.stderr)
        return 1

    manifest_context = load_manifest_context(sys.argv[1], FRAMEWORK_DIR)
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    overview = classify_domains(manifest_context, output_dir)
    write_json(output_dir / "domain-discovery-overview.json", overview)
    write_markdown(output_dir, overview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

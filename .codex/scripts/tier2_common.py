#!/usr/bin/env python3
"""
Shared Tier 2 helpers for deterministic artifact builders.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any

RECIPE_MANIFEST_NAMES = ("recipe.yaml", "recipe.yml", "recipe.json")

PHASE_OUTPUTS = {
    "foundation": "foundation",
    "module_discovery": "module-discovery",
    "domain_discovery": "domain-discovery",
    "conflict_resolution": "conflict-resolution",
    "domain_planning": "domain-planning",
    "domain_execution": "domain-execution",
    "rewiring": "rewiring",
    "integration_review": "integration-review",
}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def phase_output_dir(summaries_dir: str | Path, phase_name: str) -> Path:
    return Path(summaries_dir) / PHASE_OUTPUTS.get(phase_name, phase_name)


def resolve_recipe_assets(meta: dict[str, Any], framework_dir: Path) -> tuple[dict[str, str] | None, str | None]:
    recipe_path = meta.get("recipePath")
    recipe_id = meta.get("recipe")
    candidates: list[Path] = []

    if recipe_path:
        recipe_candidate = Path(recipe_path)
        if not recipe_candidate.is_absolute():
            recipe_candidate = (Path.cwd() / recipe_candidate).resolve()
        candidates.append(recipe_candidate)

    if recipe_id:
        candidates.append((framework_dir / "recipes" / recipe_id).resolve())

    for candidate in candidates:
        if candidate.is_file():
            return {
                "recipe_manifest_path": str(candidate),
                "recipe_root": str(candidate.parent),
                "recipe_patterns_dir": str(candidate.parent / "patterns"),
                "recipe_verify_dir": str(candidate.parent / "verify"),
            }, None
        if candidate.is_dir():
            for manifest_name in RECIPE_MANIFEST_NAMES:
                manifest_path = candidate / manifest_name
                if manifest_path.exists():
                    return {
                        "recipe_manifest_path": str(manifest_path),
                        "recipe_root": str(candidate),
                        "recipe_patterns_dir": str(candidate / "patterns"),
                        "recipe_verify_dir": str(candidate / "verify"),
                    }, None

    if not recipe_path and not recipe_id:
        return {}, None
    if recipe_path:
        return None, f"Recipe could not be resolved from recipePath={recipe_path}"
    return None, f"Recipe could not be resolved from recipe={recipe_id}"


def load_recipe_manifest_data(recipe_manifest_path: str | None) -> dict[str, Any] | None:
    if not recipe_manifest_path:
        return None
    path = Path(recipe_manifest_path)
    if not path.exists() or path.suffix.lower() != ".json":
        return None
    try:
        return load_json(path)
    except json.JSONDecodeError:
        return None


def normalize_domain_list(meta: dict[str, Any], recipe_manifest: dict[str, Any] | None) -> list[str]:
    if isinstance(meta.get("domains"), list):
        return [str(item) for item in meta["domains"]]
    if recipe_manifest and isinstance(recipe_manifest.get("domains"), list):
        result: list[str] = []
        for item in recipe_manifest["domains"]:
            if isinstance(item, dict) and item.get("name"):
                result.append(str(item["name"]))
            elif isinstance(item, str):
                result.append(str(item))
        return result
    return []


def normalize_domain_ordering(meta: dict[str, Any], recipe_manifest: dict[str, Any] | None) -> dict[str, list[str]]:
    ordering = meta.get("domainOrdering")
    if isinstance(ordering, dict):
        return {
            str(key): [str(dep) for dep in value]
            for key, value in ordering.items()
            if isinstance(value, list)
        }
    ordering = (recipe_manifest or {}).get("domain_ordering")
    if isinstance(ordering, dict):
        return {
            str(key): [str(dep) for dep in value]
            for key, value in ordering.items()
            if isinstance(value, list)
        }
    return {}


def build_recipe_domain_patterns(recipe_root: str | None, recipe_manifest: dict[str, Any] | None) -> dict[str, str]:
    if not recipe_root or not recipe_manifest or not isinstance(recipe_manifest.get("domains"), list):
        return {}
    root = Path(recipe_root)
    result: dict[str, str] = {}
    for item in recipe_manifest["domains"]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        patterns_file = item.get("patterns_file")
        if name and patterns_file:
            result[str(name)] = str((root / str(patterns_file)).resolve())
    return result


def load_manifest_context(manifest_path: str | Path, framework_dir: Path) -> dict[str, Any]:
    manifest = load_json(Path(manifest_path))
    meta = manifest.get("meta", {})
    summaries_dir = meta.get("summariesDir", "migration-summaries")
    recipe_assets, recipe_error = resolve_recipe_assets(meta, framework_dir)
    recipe_manifest = load_recipe_manifest_data((recipe_assets or {}).get("recipe_manifest_path"))
    return {
        "manifest": manifest,
        "meta": meta,
        "summaries_dir": summaries_dir,
        "recipe_assets": recipe_assets or {},
        "recipe_error": recipe_error,
        "recipe_manifest": recipe_manifest,
        "domains": normalize_domain_list(meta, recipe_manifest),
        "domain_ordering": normalize_domain_ordering(meta, recipe_manifest),
        "domain_patterns_map": build_recipe_domain_patterns((recipe_assets or {}).get("recipe_root"), recipe_manifest),
    }


def topo_sort_domains(domains: list[str], ordering: dict[str, list[str]]) -> list[str]:
    indegree = {domain: 0 for domain in domains}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for domain in domains:
        for dependency in ordering.get(domain, []):
            if dependency not in indegree:
                continue
            adjacency[dependency].append(domain)
            indegree[domain] += 1
    queue = deque(sorted(domain for domain, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for dependent in sorted(adjacency.get(current, [])):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(ordered) == len(domains):
        return ordered
    remaining = [domain for domain in domains if domain not in ordered]
    return ordered + sorted(remaining)


def safe_domain_token(domain: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in domain.strip()) or "domain"


def domain_priority_map(domains: list[str], ordering: dict[str, list[str]], recipe_manifest: dict[str, Any] | None) -> dict[str, int]:
    priorities: dict[str, int] = {}
    if recipe_manifest and isinstance(recipe_manifest.get("domains"), list):
        for item in recipe_manifest["domains"]:
            if isinstance(item, dict) and item.get("name"):
                try:
                    priorities[str(item["name"])] = int(item.get("priority", 0))
                except (TypeError, ValueError):
                    priorities[str(item["name"])] = 0
    ordered = topo_sort_domains(domains, ordering)
    for index, domain in enumerate(ordered):
        priorities.setdefault(domain, index + 1)
    return priorities


def render_template(template_path: str | Path | None, values: dict[str, str]) -> str:
    if not template_path:
        return ""
    path = Path(template_path)
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content.strip()


def load_domain_pattern_rules(pattern_map: dict[str, str]) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    for domain, path_str in pattern_map.items():
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            payload = load_json(path)
        except json.JSONDecodeError:
            continue
        rules[domain] = payload if isinstance(payload, dict) else {}
    return rules


def path_matches_any(rel_path: str, patterns: list[str]) -> bool:
    pure_path = PurePosixPath(rel_path)
    return any(pure_path.match(pattern) for pattern in patterns if isinstance(pattern, str) and pattern)


def infer_target_candidate_paths(source_rel_path: str) -> list[str]:
    source = Path(source_rel_path)
    candidates = [source_rel_path]
    parts = list(source.parts)
    if parts:
        remainder = Path(*parts[1:])
        if str(remainder) not in {"", "."}:
            candidates.append(str(remainder))
    if source.suffix == ".py":
        candidates.append(source_rel_path.replace(".py", ".ts"))
        if parts:
            remainder = Path(*parts[1:])
            if str(remainder) not in {"", "."}:
                candidates.append(str(remainder).replace(".py", ".ts"))
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def resolve_existing_target_file(target_root: Path, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = target_root / candidate
        if path.exists() and path.is_file():
            return str(path.resolve())
    return None

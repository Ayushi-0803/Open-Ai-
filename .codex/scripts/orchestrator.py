#!/usr/bin/env python3
from __future__ import annotations

"""
Migration Orchestrator — deterministic state machine.

This script IS the control plane. It:
  1. Reads the migration manifest
  2. Runs phases sequentially
  3. Spawns LLM agents as subprocesses (they do the work)
  4. Polls for completion markers on the filesystem
  5. Enforces approval gates (input() — blocking, unskippable)
  6. Updates the manifest after every state change
  7. Handles failures, retries, and resume

The orchestrator NEVER reads source code. It NEVER makes migration decisions.
It coordinates. The agents do the work.

Usage:
    python orchestrator.py migration-manifest.json
    python orchestrator.py migration-manifest.json --runtime codex
    python orchestrator.py migration-manifest.json --skip-approval   # for CI/testing only
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add scripts dir to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest as mf
from agent_runner import spawn_agent, poll_for_completion


def resolve_skill_path(skill_name: str) -> Path | None:
    """
    Resolve a phase skill against the Codex-native skill layout first:
      .codex/skills/<name>/SKILL.md

    Falls back to flat markdown files and then to the legacy .claude tree so
    incomplete migrations remain runnable while the framework is being ported.
    """
    relative = Path(skill_name)
    stem = relative.with_suffix("") if relative.suffix else relative

    candidates = [
        FRAMEWORK_DIR / "skills" / stem / "SKILL.md",
        FRAMEWORK_DIR / "skills" / relative,
        FRAMEWORK_DIR.parent / ".claude" / "skills" / stem / "SKILL.md",
        FRAMEWORK_DIR.parent / ".claude" / "skills" / relative,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_recipe_assets(meta: dict) -> tuple[dict[str, str] | None, str | None]:
    recipe_path = meta.get("recipePath")
    recipe_id = meta.get("recipe")
    candidates: list[Path] = []

    if recipe_path:
        recipe_candidate = Path(recipe_path)
        if not recipe_candidate.is_absolute():
            recipe_candidate = (Path.cwd() / recipe_candidate).resolve()
        candidates.append(recipe_candidate)

    if recipe_id:
        candidates.append((FRAMEWORK_DIR / "recipes" / recipe_id).resolve())

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


def load_recipe_manifest_data(recipe_manifest_path: str | None) -> dict | None:
    if not recipe_manifest_path:
        return None
    path = Path(recipe_manifest_path)
    if path.suffix.lower() != ".json" or not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return None


def normalize_domain_list(meta: dict, recipe_manifest: dict | None) -> list[str]:
    if isinstance(meta.get("domains"), list):
        return [str(item) for item in meta["domains"]]
    if recipe_manifest and isinstance(recipe_manifest.get("domains"), list):
        result: list[str] = []
        for item in recipe_manifest["domains"]:
            if isinstance(item, dict) and item.get("name"):
                result.append(str(item["name"]))
            elif isinstance(item, str):
                result.append(item)
        return result
    return []


def normalize_domain_ordering(meta: dict, recipe_manifest: dict | None) -> dict[str, list[str]]:
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


def build_recipe_domain_patterns(recipe_root: str | None, recipe_manifest: dict | None) -> dict[str, str]:
    if not recipe_root or not recipe_manifest or not isinstance(recipe_manifest.get("domains"), list):
        return {}
    root = Path(recipe_root)
    result: dict[str, str] = {}
    for item in recipe_manifest["domains"]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        patterns_file = item.get("patterns_file")
        if not name or not patterns_file:
            continue
        result[str(name)] = str((root / str(patterns_file)).resolve())
    return result


VALIDATION_REPORTS = {
    "discovery": ["dep-graph.json", "file-manifest.json", "symbol-index.json", "dynamic-risk-report.json", "dependency-shards/index.json", "DISCOVERY.md"],
    "planning": ["planning-input.json", "risk-policy.json", "AGENTS.md", "migration-batches.json", "planning-overview.json", "PLAN.md"],
    "execution": ["EXECUTION.md", "execution-summary.json"],
    "review": ["REVIEW.md", "review-results.json", "validation-report.json", "parity-results.json"],
    "reiterate": ["REITERATE.md", "reiterate-results.json", "agents-md-patches.md", "agents-md.patch.json"],
    "foundation": ["foundation-summary.json", "FOUNDATION.md", "discovery.graph.json", "symbolic-batches.json", "symbol-registry.json", "migration-order.json"],
    "module_discovery": ["module-discovery.json", "MODULE_DISCOVERY.md"],
    "domain_discovery": ["domain-discovery-overview.json", "DOMAIN_DISCOVERY.md"],
    "conflict_resolution": ["conflict-resolution.json", "CONFLICT_RESOLUTION.md"],
    "domain_planning": ["domain-plan-overview.json", "DOMAIN_PLANNING.md"],
    "domain_execution": ["domain-execution-overview.json", "DOMAIN_EXECUTION.md"],
    "rewiring": ["rewiring-summary.json", "rewiring-batches.json", "REWIRING.md"],
    "integration_review": ["integration-review.json", "parity-results.json", "INTEGRATION_REVIEW.md"],
}

SUCCESS_MARKERS = {
    "discovery": ["DISCOVERY.md"],
    "planning": ["PLAN.md"],
    "execution": ["EXECUTION.md", "execution-summary.json"],
    "review": ["REVIEW.md", "validation-report.json"],
    "reiterate": ["REITERATE.md", "reiterate-results.json"],
    "foundation": ["FOUNDATION.md", "foundation-summary.json"],
    "module_discovery": ["MODULE_DISCOVERY.md", "module-discovery.json"],
    "domain_discovery": ["DOMAIN_DISCOVERY.md", "domain-discovery-overview.json"],
    "conflict_resolution": ["CONFLICT_RESOLUTION.md", "conflict-resolution.json"],
    "domain_planning": ["DOMAIN_PLANNING.md", "domain-plan-overview.json"],
    "domain_execution": ["DOMAIN_EXECUTION.md", "domain-execution-overview.json"],
    "rewiring": ["REWIRING.md", "rewiring-summary.json", "rewiring-batches.json"],
    "integration_review": ["INTEGRATION_REVIEW.md", "integration-review.json", "parity-results.json"],
}

RECIPE_MANIFEST_NAMES = ("recipe.yaml", "recipe.yml", "recipe.json")

TIER1_PHASES = [
    {
        "name": "discovery",
        "skill": "discovery.md",
        "success_marker": "DISCOVERY.md",
        "needs_approval": True,
        "allowed_tools": "Read,Bash,Glob,Grep",
        "artifact_validator": "discovery",
        "supported": True,
    },
    {
        "name": "planning",
        "skill": "planning.md",
        "success_marker": "PLAN.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "planning",
        "supported": True,
    },
    {
        "name": "execution",
        "skill": "execution.md",
        "success_marker": "EXECUTION.md",
        "needs_approval": False,
        "allowed_tools": "Read,Write,Edit,Bash,Glob,Grep",
        "artifact_validator": "execution",
        "supported": True,
    },
    {
        "name": "review",
        "skill": "review.md",
        "success_marker": "REVIEW.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "review",
        "supported": True,
    },
    {
        "name": "reiterate",
        "skill": "reiterate.md",
        "success_marker": "REITERATE.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Edit,Bash,Glob,Grep",
        "artifact_validator": "reiterate",
        "supported": True,
    },
]

TIER2_PHASES = [
    {
        "name": "foundation",
        "skill": "tier2-foundation.md",
        "success_marker": "FOUNDATION.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "foundation",
        "supported": True,
    },
    {
        "name": "module_discovery",
        "skill": "tier2-module_discovery.md",
        "success_marker": "MODULE_DISCOVERY.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "module_discovery",
        "supported": True,
    },
    {
        "name": "domain_discovery",
        "skill": "tier2-domain_discovery.md",
        "success_marker": "DOMAIN_DISCOVERY.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "domain_discovery",
        "supported": True,
    },
    {
        "name": "conflict_resolution",
        "skill": "tier2-conflict_resolution.md",
        "success_marker": "CONFLICT_RESOLUTION.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "conflict_resolution",
        "supported": True,
    },
    {
        "name": "domain_planning",
        "skill": "tier2-domain_planning.md",
        "success_marker": "DOMAIN_PLANNING.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "domain_planning",
        "supported": True,
    },
    {
        "name": "domain_execution",
        "skill": "tier2-domain_execution.md",
        "success_marker": "DOMAIN_EXECUTION.md",
        "needs_approval": False,
        "allowed_tools": "Read,Write,Edit,Bash,Glob,Grep",
        "artifact_validator": "domain_execution",
        "supported": True,
    },
    {
        "name": "rewiring",
        "skill": "tier2-rewiring.md",
        "success_marker": "REWIRING.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "rewiring",
        "supported": True,
    },
    {
        "name": "integration_review",
        "skill": "tier2-integration_review.md",
        "success_marker": "INTEGRATION_REVIEW.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Bash,Glob,Grep",
        "artifact_validator": "integration_review",
        "supported": True,
    },
    {
        "name": "reiterate",
        "skill": "tier2-reiterate.md",
        "success_marker": "REITERATE.md",
        "needs_approval": True,
        "allowed_tools": "Read,Write,Edit,Bash,Glob,Grep",
        "artifact_validator": "reiterate",
        "supported": True,
    },
]

PHASE_SETS = {
    "tier-1": TIER1_PHASES,
    "tier-2": TIER2_PHASES,
}

APPROVAL_PHASES = sorted({phase["name"] for phases in PHASE_SETS.values() for phase in phases})


def get_phase_set(manifest_data: dict) -> list[dict]:
    framework_version = manifest_data.get("meta", {}).get("frameworkVersion")
    if framework_version in PHASE_SETS:
        return PHASE_SETS[framework_version]
    tier = manifest_data.get("meta", {}).get("tier", "medium")
    return TIER2_PHASES if tier == "high" else TIER1_PHASES


def build_phase_index(phases: list[dict]) -> dict[str, dict]:
    return {phase["name"]: phase for phase in phases}


def is_phase_supported(phase_config: dict) -> bool:
    return phase_config.get("supported", True)


def unsupported_phase_error(phase_config: dict) -> str:
    return phase_config.get("support_note", f"Phase {phase_config['name']} is not implemented yet.")


def phase_output_dir(sd: str, phase_name: str) -> str:
    return f"{sd}/{phase_name.replace('_', '-') if phase_name in {'module_discovery', 'domain_discovery', 'conflict_resolution', 'domain_planning', 'domain_execution', 'integration_review'} else phase_name}"


def phase_summary_path(sd: str, phase_config: dict) -> str:
    return str(Path(phase_output_dir(sd, phase_config["name"])) / phase_config["success_marker"])


def refresh_phase_constants(phases: list[dict]) -> dict[str, dict]:
    return build_phase_index(phases)

SUPPORTED_FRAMEWORKS = {name for name, phases in PHASE_SETS.items() if all(is_phase_supported(p) for p in phases)}
UNSUPPORTED_FRAMEWORKS = set(PHASE_SETS) - SUPPORTED_FRAMEWORKS

TIER2_PATH_PHASES = {
    'module_discovery', 'domain_discovery', 'conflict_resolution',
    'domain_planning', 'domain_execution', 'integration_review'
}

PHASE_OUTPUTS = {
    'foundation': 'foundation',
    'module_discovery': 'module-discovery',
    'domain_discovery': 'domain-discovery',
    'conflict_resolution': 'conflict-resolution',
    'domain_planning': 'domain-planning',
    'domain_execution': 'domain-execution',
    'rewiring': 'rewiring',
    'integration_review': 'integration-review',
}

PREBUILT_SUCCESS_PHASES = {
    "foundation",
    "module_discovery",
    "domain_discovery",
    "conflict_resolution",
    "domain_planning",
    "domain_execution",
    "rewiring",
    "integration_review",
}


def phase_dir_name(phase_name: str) -> str:
    return PHASE_OUTPUTS.get(phase_name, phase_name)


def is_tier2_manifest(manifest_data: dict) -> bool:
    return manifest_data.get('meta', {}).get('frameworkVersion') == 'tier-2' or manifest_data.get('meta', {}).get('tier') == 'high'


def require_supported_framework(manifest_data: dict) -> tuple[bool, str | None]:
    framework_version = manifest_data.get('meta', {}).get('frameworkVersion')
    if framework_version in SUPPORTED_FRAMEWORKS:
        return True, None
    if framework_version in UNSUPPORTED_FRAMEWORKS:
        return False, f"Framework {framework_version} is defined but not fully executable yet."
    return True, None


def get_phase_list_from_manifest(manifest_data: dict) -> list[dict]:
    return get_phase_set(manifest_data)


def get_phase_names(manifest_data: dict) -> list[str]:
    return [phase['name'] for phase in get_phase_set(manifest_data)]


def get_phase_config(manifest_data: dict, phase_name: str) -> dict | None:
    return build_phase_index(get_phase_set(manifest_data)).get(phase_name)


def tier2_context_fields(meta: dict) -> dict:
    fields: dict[str, object] = {}
    if meta.get('domains'):
        fields['domains'] = json.dumps(meta['domains'], indent=2)
    if meta.get('domainOrdering'):
        fields['domain_ordering'] = json.dumps(meta['domainOrdering'], indent=2)
    return fields


def tier2_artifact_contracts(phase_name: str) -> list[str]:
    return VALIDATION_REPORTS.get(phase_name, [])


def should_prebuild_discovery(phase_name: str, manifest_data: dict) -> bool:
    return phase_name == 'discovery' and not is_tier2_manifest(manifest_data)


def get_display_framework(manifest_data: dict) -> str:
    return manifest_data.get('meta', {}).get('frameworkVersion', 'tier-1')


def get_default_complete_paths(sd: str, manifest_data: dict) -> list[str]:
    if is_tier2_manifest(manifest_data):
        return [
            f"{sd}/foundation/FOUNDATION.md",
            f"{sd}/domain-planning/DOMAIN_PLANNING.md",
            f"{sd}/integration-review/INTEGRATION_REVIEW.md",
        ]
    return [
        f"{sd}/discovery/DISCOVERY.md",
        f"{sd}/planning/PLAN.md",
        f"{sd}/review/REVIEW.md",
    ]


def should_skip_reiterate(manifest_path: str, manifest_data: dict) -> bool:
    if is_tier2_manifest(manifest_data):
        review_path = f"{get_summaries_dir(manifest_path)}/integration-review/integration-review.json"
        if not os.path.exists(review_path):
            return False
        try:
            with open(review_path) as f:
                results = json.load(f)
            return not bool(results.get('routing', {}).get('fail', []))
        except (json.JSONDecodeError, KeyError):
            return False
    return should_run_reiterate(manifest_path)


def get_phase_output_dir_from_manifest(manifest_path: str, phase_name: str) -> str:
    return phase_output_dir(get_summaries_dir(manifest_path), phase_name)


def build_runtime_support_message(manifest_data: dict) -> str | None:
    supported, reason = require_supported_framework(manifest_data)
    if supported:
        return None
    return reason


def get_active_phase_list(manifest_path: str) -> list[dict]:
    return get_phase_set(mf.load(manifest_path))


def get_active_phase_index(manifest_path: str) -> dict[str, dict]:
    return build_phase_index(get_active_phase_list(manifest_path))


def get_approval_choices(manifest_data: dict) -> list[str]:
    return [phase['name'] for phase in get_phase_set(manifest_data)]


def compute_phase_configs(manifest_data: dict, phase_name: str | None = None) -> list[dict]:
    phases = get_phase_set(manifest_data)
    if phase_name:
        return [p for p in phases if p['name'] == phase_name]
    return phases


def get_resume_phase_configs(manifest_data: dict, approved_phase: str) -> list[dict]:
    phases = get_phase_set(manifest_data)
    phase_index = next(i for i, p in enumerate(phases) if p['name'] == approved_phase)
    return phases[phase_index + 1:]


def get_summary_output_path(manifest_path: str, phase_config: dict) -> str:
    return phase_summary_path(get_summaries_dir(manifest_path), phase_config)


def record_unsupported_phase(manifest_path: str, phase_config: dict) -> bool:
    phase_name = phase_config['name']
    output_dir = get_phase_output_dir_from_manifest(manifest_path, phase_name)
    os.makedirs(output_dir, exist_ok=True)
    error_msg = unsupported_phase_error(phase_config)
    error_path = Path(output_dir) / 'ERROR'
    error_path.write_text(error_msg + '\n', encoding='utf-8')
    mf.update_phase(manifest_path, phase_name, 'failed', extra={'error': error_msg})
    log_and_print(manifest_path, f"  ✗ {phase_name} not supported: {error_msg}")
    return False


def maybe_add_tier2_context(ctx: dict, manifest_data: dict):
    if is_tier2_manifest(manifest_data):
        ctx.update(tier2_context_fields(manifest_data.get('meta', {})))
        ctx['framework_version'] = get_display_framework(manifest_data)


def get_phase_success_markers(phase_name: str) -> list[str]:
    return SUCCESS_MARKERS.get(phase_name, [])


def get_phase_validation_contract(phase_name: str) -> list[str]:
    return VALIDATION_REPORTS.get(phase_name, [])


def get_framework_version(manifest_data: dict) -> str:
    return manifest_data.get('meta', {}).get('frameworkVersion', 'tier-1')


def get_phase_state_names(manifest_data: dict) -> list[str]:
    return list(manifest_data.get('phases', {}).keys())


def validate_manifest_phase_alignment(manifest_data: dict) -> tuple[bool, str | None]:
    expected = {phase['name'] for phase in get_phase_set(manifest_data)}
    actual = set(get_phase_state_names(manifest_data))
    if expected != actual:
        return False, f"Manifest phase set mismatch. Expected {sorted(expected)}, found {sorted(actual)}"
    return True, None


def get_planning_context_contracts(manifest_data: dict, phase_name: str) -> object:
    if is_tier2_manifest(manifest_data):
        return json.dumps(get_phase_validation_contract(phase_name), indent=2)
    if phase_name == 'planning':
        return json.dumps(PLANNING_ARTIFACT_CONTRACTS, indent=2)
    return VALIDATION_REPORTS.get(phase_name, [])


def maybe_update_phase_index(manifest_data: dict):
    global PHASES, PHASE_CONFIG_BY_NAME
    PHASES = get_phase_set(manifest_data)
    PHASE_CONFIG_BY_NAME = refresh_phase_constants(PHASES)


def get_phase_retry_error_path(manifest_path: str, phase_name: str) -> str:
    return f"{get_phase_output_dir_from_manifest(manifest_path, phase_name)}/ERROR"


def get_human_summary_paths(manifest_path: str, manifest_data: dict) -> list[str]:
    return get_default_complete_paths(get_summaries_dir(manifest_path), manifest_data)


def tier2_not_yet_supported(phase_config: dict) -> bool:
    return not is_phase_supported(phase_config)


def maybe_record_framework_warning(manifest_path: str, manifest_data: dict):
    message = build_runtime_support_message(manifest_data)
    if message:
        log_event(manifest_path, f"framework_warning {message}")


def get_phase_approval_summary(manifest_path: str, phase_config: dict) -> str:
    return get_summary_output_path(manifest_path, phase_config)


def get_manifest_framework_line(meta: dict) -> str:
    return meta.get('frameworkVersion', 'tier-1')


def get_runtime_phase_names(manifest_data: dict) -> list[str]:
    return [phase['name'] for phase in get_phase_set(manifest_data)]


def ensure_phase_supported_before_run(manifest_path: str, phase_config: dict) -> bool:
    if tier2_not_yet_supported(phase_config):
        return record_unsupported_phase(manifest_path, phase_config)
    return True


def maybe_get_tier2_support_note(phase_config: dict) -> str | None:
    if tier2_not_yet_supported(phase_config):
        return unsupported_phase_error(phase_config)
    return None


def get_framework_banner_label(meta: dict) -> str:
    return meta.get('frameworkVersion', 'tier-1')


def get_manifest_phase_configs(manifest_data: dict) -> list[dict]:
    return get_phase_set(manifest_data)


def get_phase_resume_index(phases: list[dict], phase_name: str) -> int:
    return next(i for i, p in enumerate(phases) if p['name'] == phase_name)


def get_phase_completion_reference(manifest_path: str, manifest_data: dict) -> list[str]:
    return get_default_complete_paths(get_summaries_dir(manifest_path), manifest_data)


def maybe_raise_manifest_alignment(manifest_data: dict):
    aligned, error = validate_manifest_phase_alignment(manifest_data)
    if not aligned:
        raise ValueError(error)


def maybe_get_tier2_domains(meta: dict) -> str:
    if meta.get('domains'):
        return ', '.join(meta['domains'])
    return 'none specified'


def maybe_get_tier2_ordering(meta: dict) -> str:
    if meta.get('domainOrdering'):
        return json.dumps(meta['domainOrdering'])
    return 'none specified'


def get_phase_name_choices(manifest_data: dict) -> list[str]:
    return [phase['name'] for phase in get_phase_set(manifest_data)]


def build_phase_metadata(manifest_data: dict) -> dict:
    return {
        'frameworkVersion': get_framework_version(manifest_data),
        'phaseNames': get_phase_name_choices(manifest_data),
    }


def get_summary_phase_path(manifest_path: str, phase_name: str) -> str:
    config = get_active_phase_index(manifest_path)[phase_name]
    return get_summary_output_path(manifest_path, config)


def is_runtime_supported_for_manifest(manifest_data: dict) -> bool:
    return build_runtime_support_message(manifest_data) is None


def get_current_phase_set(manifest_path: str) -> list[dict]:
    return get_active_phase_list(manifest_path)


def get_current_phase_index(manifest_path: str) -> dict[str, dict]:
    return get_active_phase_index(manifest_path)


def get_framework_status_line(meta: dict) -> str:
    return f"{meta.get('tier', 'medium')} / {meta.get('frameworkVersion', 'tier-1')}"


def should_show_partial_support_warning(manifest_data: dict) -> bool:
    return is_tier2_manifest(manifest_data) and not is_runtime_supported_for_manifest(manifest_data)


def maybe_print_framework_warning(manifest_data: dict):
    message = build_runtime_support_message(manifest_data)
    if message:
        print(f"  Warning: {message}")


def get_phase_output_root(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def build_phase_artifact_context(manifest_data: dict, phase_name: str) -> object:
    return get_planning_context_contracts(manifest_data, phase_name)


def get_phase_success_path_from_config(manifest_path: str, phase_config: dict) -> str:
    return get_summary_output_path(manifest_path, phase_config)


def get_supported_phase_choices(manifest_data: dict) -> list[str]:
    return [phase['name'] for phase in get_phase_set(manifest_data)]


def maybe_extend_context_for_framework(ctx: dict, manifest_data: dict, phase_name: str):
    maybe_add_tier2_context(ctx, manifest_data)
    ctx['framework_version'] = get_framework_version(manifest_data)
    ctx['artifact_contracts'] = get_phase_validation_contract(phase_name)
    ctx['phase_metadata'] = json.dumps(build_phase_metadata(manifest_data), indent=2)


def maybe_get_review_path(sd: str, manifest_data: dict) -> str:
    if is_tier2_manifest(manifest_data):
        return f"{sd}/integration-review/INTEGRATION_REVIEW.md"
    return f"{sd}/review/REVIEW.md"


def maybe_get_review_results_path(sd: str, manifest_data: dict) -> str:
    if is_tier2_manifest(manifest_data):
        return f"{sd}/integration-review/integration-review.json"
    return f"{sd}/review/review-results.json"


def get_framework_summary_lines(meta: dict) -> list[str]:
    lines = [f"  Tier:     {meta.get('tier', 'medium')}"]
    lines.append(f"  Framework:{' ' if len('Framework:') < 10 else ''}{meta.get('frameworkVersion', 'tier-1')}")
    if meta.get('frameworkVersion') == 'tier-2':
        lines.append(f"  Domains:  {maybe_get_tier2_domains(meta)}")
    return lines


def get_phase_dirname_for_phase(phase_name: str) -> str:
    return phase_dir_name(phase_name)


def get_manifest_complete_paths(manifest_path: str) -> list[str]:
    manifest_data = mf.load(manifest_path)
    return get_default_complete_paths(get_summaries_dir(manifest_path), manifest_data)


def get_phase_output_parent(manifest_path: str, phase_name: str) -> Path:
    return Path(get_phase_output_dir_from_manifest(manifest_path, phase_name))


def get_framework_support_state(manifest_data: dict) -> str:
    return 'full' if is_runtime_supported_for_manifest(manifest_data) else 'partial'


def get_resume_phase_choices(manifest_data: dict) -> list[str]:
    return get_phase_name_choices(manifest_data)


def maybe_get_domain_context(meta: dict) -> dict:
    result = {}
    if meta.get('domains'):
        result['domains'] = meta['domains']
    if meta.get('domainOrdering'):
        result['domainOrdering'] = meta['domainOrdering']
    return result


def maybe_add_domain_context(ctx: dict, meta: dict):
    domain_context = maybe_get_domain_context(meta)
    if domain_context:
        ctx['domain_context'] = json.dumps(domain_context, indent=2)


def get_manifest_phase_output_dir(manifest_data: dict, phase_name: str) -> str:
    sd = manifest_data.get('meta', {}).get('summariesDir', 'migration-summaries')
    return phase_output_dir(sd, phase_name)


def maybe_print_tier2_support_note(phase_config: dict):
    note = maybe_get_tier2_support_note(phase_config)
    if note:
        print(f"  Note: {note}")


def get_phase_summary_reference(manifest_path: str, phase_name: str) -> str:
    config = get_active_phase_index(manifest_path)[phase_name]
    return get_summary_output_path(manifest_path, config)


def get_manifest_phase_order(manifest_data: dict) -> list[str]:
    return [phase['name'] for phase in get_phase_set(manifest_data)]


def get_configured_phase_set_label(manifest_data: dict) -> str:
    return get_framework_version(manifest_data)


def maybe_get_phase_support_error(phase_config: dict) -> str | None:
    if not is_phase_supported(phase_config):
        return unsupported_phase_error(phase_config)
    return None


def get_phase_output_paths_for_run(manifest_path: str, phase_name: str) -> tuple[str, str]:
    output_dir = get_phase_output_dir_from_manifest(manifest_path, phase_name)
    success_marker = get_active_phase_index(manifest_path)[phase_name]['success_marker']
    return output_dir, str(Path(output_dir) / success_marker)


def is_tier2_phase(phase_name: str) -> bool:
    return phase_name in {phase['name'] for phase in TIER2_PHASES}


def maybe_get_framework_paths(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def get_manifest_phase_summary(manifest_data: dict) -> str:
    return ', '.join(get_manifest_phase_order(manifest_data))


def get_phase_allowed_tools(phase_config: dict) -> str:
    return phase_config.get('allowed_tools', 'Read,Write,Edit,Bash,Glob,Grep')


def get_phase_validator_name(phase_config: dict) -> str:
    return phase_config.get('artifact_validator', phase_config['name'])


def maybe_build_framework_context(manifest_data: dict, phase_name: str) -> dict:
    return {
        'frameworkVersion': get_framework_version(manifest_data),
        'phaseOrder': get_manifest_phase_order(manifest_data),
        'artifactContracts': get_phase_validation_contract(phase_name),
    }


def maybe_set_framework_context(ctx: dict, manifest_data: dict, phase_name: str):
    ctx['framework_context'] = json.dumps(maybe_build_framework_context(manifest_data, phase_name), indent=2)


def maybe_get_phase_dir_from_sd(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def get_phase_support_status(phase_config: dict) -> str:
    return 'supported' if is_phase_supported(phase_config) else 'unsupported'


def maybe_log_phase_support(manifest_path: str, phase_config: dict):
    log_event(manifest_path, f"phase_support {phase_config['name']}={get_phase_support_status(phase_config)}")


def get_phase_runtime_label(phase_config: dict) -> str:
    return get_phase_support_status(phase_config)


def maybe_get_framework_domains(meta: dict) -> str:
    return maybe_get_tier2_domains(meta)


def get_manifest_paths_summary(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def get_phase_dir_for_phase(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def maybe_get_framework_warning(manifest_data: dict) -> str | None:
    return build_runtime_support_message(manifest_data)


def is_phase_known(manifest_data: dict, phase_name: str) -> bool:
    return phase_name in get_phase_name_choices(manifest_data)


def maybe_get_phase_output_manifest(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def get_phase_review_output(sd: str, manifest_data: dict) -> str:
    return maybe_get_review_path(sd, manifest_data)


def get_phase_review_results(sd: str, manifest_data: dict) -> str:
    return maybe_get_review_results_path(sd, manifest_data)


def maybe_ensure_phase_index(manifest_data: dict):
    maybe_update_phase_index(manifest_data)


def get_framework_execution_support(meta: dict) -> str:
    return 'partial' if meta.get('frameworkVersion') == 'tier-2' else 'full'


def maybe_get_framework_phase_list(manifest_data: dict) -> str:
    return ', '.join(get_manifest_phase_order(manifest_data))


def maybe_get_phase_success_reference(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def get_phase_manifest_output_dir(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def get_framework_detail_lines(meta: dict) -> list[str]:
    lines = get_framework_summary_lines(meta)
    lines.append(f"  Support:  {get_framework_execution_support(meta)}")
    return lines


def maybe_print_framework_details(meta: dict):
    for line in get_framework_detail_lines(meta):
        print(line)


def get_current_framework_version(manifest_path: str) -> str:
    return get_framework_version(mf.load(manifest_path))


def get_supported_phase_configs(manifest_data: dict) -> list[dict]:
    return get_phase_set(manifest_data)


def maybe_get_phase_support_note(phase_name: str, manifest_data: dict) -> str | None:
    config = get_phase_config(manifest_data, phase_name)
    if config:
        return maybe_get_tier2_support_note(config)
    return None


def get_complete_summary_lines(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def get_phase_output_mapping(phase_name: str) -> str:
    return phase_dir_name(phase_name)


def maybe_get_framework_manifest_data(manifest_path: str) -> dict:
    return mf.load(manifest_path)


def maybe_get_framework_phase_configs(manifest_path: str) -> list[dict]:
    return get_active_phase_list(manifest_path)


def get_phase_success_basename(phase_config: dict) -> str:
    return phase_config['success_marker']


def maybe_get_tier2_warning(manifest_data: dict) -> str | None:
    if should_show_partial_support_warning(manifest_data):
        return build_runtime_support_message(manifest_data)
    return None


def maybe_log_framework_mode(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"framework_mode {get_framework_version(manifest_data)}")


def get_manifest_phase_dir(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def maybe_get_framework_phase_order(manifest_data: dict) -> str:
    return maybe_get_framework_phase_list(manifest_data)


def get_phase_config_by_manifest(manifest_data: dict, phase_name: str) -> dict:
    return build_phase_index(get_phase_set(manifest_data))[phase_name]


def get_manifest_phase_resume_configs(manifest_data: dict, approved_phase: str) -> list[dict]:
    return get_resume_phase_configs(manifest_data, approved_phase)


def get_framework_paths(sd: str, manifest_data: dict) -> list[str]:
    return get_default_complete_paths(sd, manifest_data)


def maybe_update_phase_globals(manifest_data: dict):
    maybe_update_phase_index(manifest_data)


def get_phase_retry_path(manifest_path: str, phase_name: str) -> str:
    return get_phase_retry_error_path(manifest_path, phase_name)


def maybe_get_phase_contracts(phase_name: str) -> list[str]:
    return get_phase_validation_contract(phase_name)


def get_framework_launch_state(manifest_data: dict) -> str:
    return get_framework_execution_support(manifest_data.get('meta', {}))


def maybe_get_framework_resume_choices(manifest_data: dict) -> list[str]:
    return get_resume_phase_choices(manifest_data)


def get_manifest_phase_directory(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_extend_context_with_domains(ctx: dict, manifest_data: dict):
    maybe_add_domain_context(ctx, manifest_data.get('meta', {}))


def get_framework_display_name(manifest_data: dict) -> str:
    return get_framework_version(manifest_data)


def maybe_log_phase_contracts(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_contracts {phase_name}={get_phase_validation_contract(phase_name)}")


def get_phase_success_files(phase_name: str) -> list[str]:
    return get_phase_success_markers(phase_name)


def get_framework_summary_targets(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def maybe_get_framework_support(manifest_data: dict) -> str:
    return get_framework_support_state(manifest_data)


def get_phase_summary_file(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def get_runtime_phase_configs(manifest_data: dict) -> list[dict]:
    return get_phase_set(manifest_data)


def maybe_get_phase_config(manifest_path: str, phase_name: str) -> dict:
    return get_active_phase_index(manifest_path)[phase_name]


def get_manifest_phase_outputs(manifest_path: str, phase_name: str) -> tuple[str, str]:
    return get_phase_output_paths_for_run(manifest_path, phase_name)


def maybe_get_framework_overview(meta: dict) -> str:
    return f"{meta.get('tier', 'medium')} ({meta.get('frameworkVersion', 'tier-1')})"


def get_phase_dir_basename(phase_name: str) -> str:
    return phase_dir_name(phase_name)


def maybe_add_framework_metadata(ctx: dict, manifest_data: dict, phase_name: str):
    maybe_extend_context_for_framework(ctx, manifest_data, phase_name)
    maybe_set_framework_context(ctx, manifest_data, phase_name)
    maybe_extend_context_with_domains(ctx, manifest_data)


def get_framework_success_paths(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def maybe_log_framework_summary(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"framework_summary {maybe_get_framework_phase_order(manifest_data)}")


def get_phase_configs_for_args(manifest_data: dict, args_phase: str | None) -> list[dict]:
    return compute_phase_configs(manifest_data, args_phase)


def get_phase_resume_configs_for_args(manifest_data: dict, approved_phase: str) -> list[dict]:
    return get_resume_phase_configs(manifest_data, approved_phase)


def maybe_validate_framework_runtime(manifest_data: dict) -> tuple[bool, str | None]:
    return require_supported_framework(manifest_data)


def get_framework_complete_paths(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def maybe_get_phase_output_dir(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def get_manifest_framework_version(manifest_path: str) -> str:
    return get_current_framework_version(manifest_path)


def maybe_get_phase_artifact_contracts(phase_name: str) -> list[str]:
    return get_phase_validation_contract(phase_name)


def maybe_should_prebuild_discovery(phase_name: str, manifest_data: dict) -> bool:
    return should_prebuild_discovery(phase_name, manifest_data)


def get_phase_display_dir(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def get_framework_support_message(manifest_data: dict) -> str | None:
    return build_runtime_support_message(manifest_data)


def maybe_log_framework_warning_message(manifest_path: str, manifest_data: dict):
    message = get_framework_support_message(manifest_data)
    if message:
        log_event(manifest_path, f"framework_support_warning {message}")


def get_framework_phase_count(manifest_data: dict) -> int:
    return len(get_phase_set(manifest_data))


def maybe_get_framework_warning_line(manifest_data: dict) -> str | None:
    return maybe_get_framework_warning(manifest_data)


def get_phase_support_note(phase_config: dict) -> str | None:
    return maybe_get_tier2_support_note(phase_config)


def maybe_print_phase_support_note(phase_config: dict):
    note = get_phase_support_note(phase_config)
    if note:
        print(f"  Note: {note}")


def get_framework_state(manifest_data: dict) -> str:
    return get_framework_support_state(manifest_data)


def get_phase_manifest_summary(manifest_data: dict) -> str:
    return get_manifest_phase_summary(manifest_data)


def maybe_record_framework_state(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"framework_state {get_framework_state(manifest_data)}")


def get_phase_config_map(manifest_data: dict) -> dict[str, dict]:
    return build_phase_index(get_phase_set(manifest_data))


def maybe_get_phase_summary_file(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def get_framework_manifest_support(meta: dict) -> str:
    return get_framework_execution_support(meta)


def maybe_get_framework_runtime_state(manifest_data: dict) -> str:
    return get_framework_execution_support(manifest_data.get('meta', {}))


def maybe_get_phase_output_paths(manifest_path: str, phase_name: str) -> tuple[str, str]:
    return get_manifest_phase_outputs(manifest_path, phase_name)


def get_framework_summary(meta: dict) -> str:
    return maybe_get_framework_overview(meta)


def maybe_add_framework_info_to_context(ctx: dict, manifest_data: dict, phase_name: str):
    maybe_add_framework_metadata(ctx, manifest_data, phase_name)


def get_phase_path_key(phase_name: str) -> str:
    return phase_dir_name(phase_name)


def maybe_log_framework_paths(manifest_path: str):
    log_event(manifest_path, f"framework_paths {get_framework_complete_paths(manifest_path)}")


def get_framework_phase_configs(manifest_data: dict) -> list[dict]:
    return get_phase_set(manifest_data)


def maybe_get_framework_phase_index(manifest_data: dict) -> dict[str, dict]:
    return build_phase_index(get_phase_set(manifest_data))


def get_manifest_phase_reference(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_get_phase_contract_info(phase_name: str) -> list[str]:
    return get_phase_validation_contract(phase_name)


def get_phase_summary_target(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_add_framework_warning(ctx: dict, manifest_data: dict):
    warning = maybe_get_framework_warning(manifest_data)
    if warning:
        ctx['framework_warning'] = warning


def get_phase_runtime_support(phase_config: dict) -> bool:
    return is_phase_supported(phase_config)


def maybe_get_phase_runtime_warning(phase_config: dict) -> str | None:
    return get_phase_support_note(phase_config)


def get_framework_phase_names(manifest_data: dict) -> list[str]:
    return get_manifest_phase_order(manifest_data)


def maybe_record_phase_runtime(manifest_path: str, phase_config: dict):
    log_event(manifest_path, f"phase_runtime {phase_config['name']}={get_phase_runtime_label(phase_config)}")


def get_phase_output_success_path(sd: str, phase_config: dict) -> str:
    return str(Path(phase_output_dir(sd, phase_config['name'])) / phase_config['success_marker'])


def maybe_get_framework_context(manifest_data: dict, phase_name: str) -> dict:
    return maybe_build_framework_context(manifest_data, phase_name)


def maybe_set_framework_warning(manifest_path: str, manifest_data: dict):
    maybe_log_framework_warning_message(manifest_path, manifest_data)


def get_phase_context_contracts(manifest_data: dict, phase_name: str) -> object:
    return get_planning_context_contracts(manifest_data, phase_name)


def maybe_get_framework_phase_summary(manifest_data: dict) -> str:
    return get_manifest_phase_summary(manifest_data)


def get_framework_runtime_support_message(manifest_data: dict) -> str | None:
    return build_runtime_support_message(manifest_data)


def maybe_record_phase_summary(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_summary_path {phase_name}={get_phase_summary_reference(manifest_path, phase_name)}")


def maybe_get_framework_complete_summary(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def get_runtime_phase_index(manifest_data: dict) -> dict[str, dict]:
    return build_phase_index(get_phase_set(manifest_data))


def maybe_get_framework_display(meta: dict) -> str:
    return get_framework_summary(meta)


def maybe_record_framework_display(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"framework_display {maybe_get_framework_phase_summary(manifest_data)}")


def get_phase_output_label(phase_name: str) -> str:
    return phase_dir_name(phase_name)


def maybe_record_phase_output(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_output_dir {phase_name}={get_phase_output_dir_from_manifest(manifest_path, phase_name)}")


def maybe_get_phase_output_label(phase_name: str) -> str:
    return get_phase_output_label(phase_name)


def maybe_get_framework_phase_support(manifest_data: dict) -> str:
    return get_framework_support_state(manifest_data)


def maybe_get_framework_support_paths(manifest_path: str) -> list[str]:
    return get_framework_complete_paths(manifest_path)


def get_framework_phase_output_dir(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_get_framework_runtime_warning(manifest_data: dict) -> str | None:
    return build_runtime_support_message(manifest_data)


def maybe_get_framework_launch_support(manifest_data: dict) -> str:
    return get_framework_launch_state(manifest_data)


def get_phase_output_identifier(phase_name: str) -> str:
    return phase_dir_name(phase_name)


def maybe_log_framework_identifiers(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"framework_identifiers {get_framework_phase_names(manifest_data)}")


def get_phase_support_display(phase_config: dict) -> str:
    return get_phase_support_status(phase_config)


def maybe_get_phase_support_display(phase_config: dict) -> str:
    return get_phase_support_display(phase_config)


def maybe_add_framework_support_message(ctx: dict, manifest_data: dict):
    message = build_runtime_support_message(manifest_data)
    if message:
        ctx['runtime_support'] = message


def get_framework_runtime_status(manifest_data: dict) -> str:
    return get_framework_state(manifest_data)


def maybe_record_runtime_status(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"runtime_status {get_framework_runtime_status(manifest_data)}")


def get_phase_success_marker(phase_name: str) -> list[str]:
    return SUCCESS_MARKERS.get(phase_name, [])


def maybe_add_phase_context_info(ctx: dict, manifest_data: dict, phase_name: str):
    ctx['phase_contracts'] = json.dumps(get_phase_validation_contract(phase_name), indent=2)
    maybe_add_framework_support_message(ctx, manifest_data)


def maybe_log_phase_context(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_context {phase_name}")


def get_framework_paths_for_manifest(manifest_path: str) -> list[str]:
    return get_manifest_complete_paths(manifest_path)


def maybe_get_framework_support_status(manifest_data: dict) -> str:
    return get_framework_runtime_status(manifest_data)


def maybe_add_framework_state(ctx: dict, manifest_data: dict):
    ctx['framework_state'] = get_framework_runtime_status(manifest_data)


def get_phase_contract_dump(phase_name: str) -> str:
    return json.dumps(get_phase_validation_contract(phase_name), indent=2)


def maybe_add_phase_contract_dump(ctx: dict, phase_name: str):
    ctx['artifact_contracts'] = get_phase_validation_contract(phase_name)
    ctx['artifact_contract_dump'] = get_phase_contract_dump(phase_name)


def maybe_log_manifest_alignment(manifest_path: str, manifest_data: dict):
    aligned, error = validate_manifest_phase_alignment(manifest_data)
    log_event(manifest_path, f"manifest_alignment aligned={aligned} error={error or ''}")


def maybe_get_framework_progression(manifest_data: dict) -> str:
    return ' -> '.join(get_phase_names(manifest_data))


def maybe_add_framework_progression(ctx: dict, manifest_data: dict):
    ctx['phase_progression'] = maybe_get_framework_progression(manifest_data)


def get_phase_context_dir(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_log_phase_dir(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_dir {phase_name}={get_phase_context_dir(manifest_path, phase_name)}")


def maybe_get_framework_targets(manifest_path: str) -> list[str]:
    return get_framework_paths_for_manifest(manifest_path)


def get_phase_summary_display(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_get_framework_domains_display(meta: dict) -> str:
    return maybe_get_tier2_domains(meta)


def maybe_add_domains_display(ctx: dict, manifest_data: dict):
    if is_tier2_manifest(manifest_data):
        ctx['domains_display'] = maybe_get_framework_domains_display(manifest_data.get('meta', {}))


def get_framework_paths_text(manifest_path: str) -> str:
    return json.dumps(get_framework_paths_for_manifest(manifest_path), indent=2)


def maybe_add_framework_paths(ctx: dict, manifest_path: str):
    ctx['framework_paths'] = get_framework_paths_text(manifest_path)


def maybe_prepare_framework_context(ctx: dict, manifest_path: str, manifest_data: dict, phase_name: str):
    maybe_add_framework_info_to_context(ctx, manifest_data, phase_name)
    maybe_add_phase_context_info(ctx, manifest_data, phase_name)
    maybe_add_framework_state(ctx, manifest_data)
    maybe_add_framework_progression(ctx, manifest_data)
    maybe_add_domains_display(ctx, manifest_data)
    maybe_add_framework_paths(ctx, manifest_path)


def get_runtime_phase_set(manifest_data: dict) -> list[dict]:
    return get_phase_set(manifest_data)


def get_runtime_phase_map(manifest_data: dict) -> dict[str, dict]:
    return build_phase_index(get_runtime_phase_set(manifest_data))


def get_phase_output_dir_for_manifest(manifest_data: dict, phase_name: str) -> str:
    return phase_output_dir(manifest_data.get('meta', {}).get('summariesDir', 'migration-summaries'), phase_name)


def maybe_record_framework_context(manifest_path: str, manifest_data: dict, phase_name: str):
    log_event(manifest_path, f"framework_context phase={phase_name} framework={get_framework_version(manifest_data)}")


def get_phase_run_summary(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_get_runtime_support(manifest_data: dict) -> str:
    return get_framework_support_state(manifest_data)


def maybe_add_runtime_support(ctx: dict, manifest_data: dict):
    ctx['runtime_support_state'] = maybe_get_runtime_support(manifest_data)


def maybe_prepare_context(ctx: dict, manifest_path: str, manifest_data: dict, phase_name: str):
    maybe_prepare_framework_context(ctx, manifest_path, manifest_data, phase_name)
    maybe_add_runtime_support(ctx, manifest_data)


def get_framework_success_files(manifest_path: str) -> list[str]:
    return get_framework_paths_for_manifest(manifest_path)


def maybe_record_framework_success_files(manifest_path: str):
    log_event(manifest_path, f"framework_success_files {get_framework_success_files(manifest_path)}")


def get_phase_contracts_json(phase_name: str) -> str:
    return json.dumps(get_phase_validation_contract(phase_name), indent=2)


def maybe_add_contracts_json(ctx: dict, phase_name: str):
    ctx['artifact_contracts_json'] = get_phase_contracts_json(phase_name)


def maybe_finalize_context(ctx: dict, manifest_path: str, manifest_data: dict, phase_name: str):
    maybe_prepare_context(ctx, manifest_path, manifest_data, phase_name)
    maybe_add_contracts_json(ctx, phase_name)


def get_framework_phase_state(manifest_data: dict) -> dict:
    return manifest_data.get('phases', {})


def maybe_get_phase_state(manifest_data: dict, phase_name: str) -> dict:
    return get_framework_phase_state(manifest_data).get(phase_name, {})


def get_phase_output_for_phase(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_log_phase_state(manifest_path: str, manifest_data: dict, phase_name: str):
    log_event(manifest_path, f"phase_state {phase_name}={maybe_get_phase_state(manifest_data, phase_name)}")


def get_framework_phase_state_names(manifest_data: dict) -> list[str]:
    return list(get_framework_phase_state(manifest_data).keys())


def maybe_get_framework_alignment(manifest_data: dict) -> tuple[bool, str | None]:
    return validate_manifest_phase_alignment(manifest_data)


def get_phase_contract_list(phase_name: str) -> list[str]:
    return get_phase_validation_contract(phase_name)


def maybe_log_phase_contract_list(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_contract_list {phase_name}={get_phase_contract_list(phase_name)}")


def get_framework_success_summary(manifest_path: str) -> str:
    return '\n'.join(get_framework_success_files(manifest_path))


def maybe_add_success_summary(ctx: dict, manifest_path: str):
    ctx['framework_success_summary'] = get_framework_success_summary(manifest_path)


def maybe_prepare_all_context(ctx: dict, manifest_path: str, manifest_data: dict, phase_name: str):
    maybe_finalize_context(ctx, manifest_path, manifest_data, phase_name)
    maybe_add_success_summary(ctx, manifest_path)


def get_manifest_phase_output_root(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_log_phase_output_root(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_output_root {phase_name}={get_manifest_phase_output_root(manifest_path, phase_name)}")


def get_framework_complete_summary_lines(manifest_path: str) -> list[str]:
    return get_framework_success_files(manifest_path)


def maybe_print_framework_warning_if_needed(manifest_data: dict):
    warning = maybe_get_framework_warning(manifest_data)
    if warning:
        print(f"  Warning: {warning}")


def get_phase_contract_details(phase_name: str) -> str:
    return ', '.join(get_phase_validation_contract(phase_name))


def maybe_log_phase_contract_details(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_contract_details {phase_name}={get_phase_contract_details(phase_name)}")


def maybe_prepare_before_phase(manifest_path: str, manifest_data: dict, phase_config: dict) -> None:
    maybe_log_phase_support(manifest_path, phase_config)
    maybe_record_phase_runtime(manifest_path, phase_config)
    maybe_record_phase_summary(manifest_path, phase_config['name'])
    maybe_record_phase_output(manifest_path, phase_config['name'])
    maybe_log_phase_contracts(manifest_path, phase_config['name'])
    maybe_log_phase_contract_list(manifest_path, phase_config['name'])
    maybe_log_phase_contract_details(manifest_path, phase_config['name'])
    maybe_log_phase_dir(manifest_path, phase_config['name'])
    maybe_log_phase_output_root(manifest_path, phase_config['name'])
    maybe_record_framework_context(manifest_path, manifest_data, phase_config['name'])
    maybe_log_phase_state(manifest_path, manifest_data, phase_config['name'])


def get_framework_display_paths(manifest_path: str) -> list[str]:
    return get_framework_complete_summary_lines(manifest_path)


def maybe_print_framework_paths(manifest_path: str):
    for path in get_framework_display_paths(manifest_path):
        print(f"    {path}")


def get_framework_phase_dir(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_prepare_phase_context(ctx: dict, manifest_path: str, manifest_data: dict, phase_name: str):
    maybe_prepare_all_context(ctx, manifest_path, manifest_data, phase_name)


def get_framework_phase_reference(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_get_framework_state_summary(manifest_data: dict) -> str:
    return f"support={get_framework_support_state(manifest_data)} phases={get_manifest_phase_summary(manifest_data)}"


def maybe_log_framework_state_summary(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"framework_state_summary {maybe_get_framework_state_summary(manifest_data)}")


def get_framework_review_reference(manifest_path: str) -> str:
    manifest_data = mf.load(manifest_path)
    return maybe_get_review_path(get_summaries_dir(manifest_path), manifest_data)


def get_framework_review_results_reference(manifest_path: str) -> str:
    manifest_data = mf.load(manifest_path)
    return maybe_get_review_results_path(get_summaries_dir(manifest_path), manifest_data)


def maybe_log_review_refs(manifest_path: str):
    log_event(manifest_path, f"review_ref {get_framework_review_reference(manifest_path)}")
    log_event(manifest_path, f"review_results_ref {get_framework_review_results_reference(manifest_path)}")


def maybe_prepare_framework_logging(manifest_path: str, manifest_data: dict):
    maybe_log_framework_mode(manifest_path, manifest_data)
    maybe_log_framework_warning(manifest_path, manifest_data)
    maybe_log_framework_summary(manifest_path, manifest_data)
    maybe_record_framework_display(manifest_path, manifest_data)
    maybe_record_framework_state(manifest_path, manifest_data)
    maybe_log_framework_state_summary(manifest_path, manifest_data)
    maybe_log_framework_paths(manifest_path)
    maybe_record_framework_success_files(manifest_path)
    maybe_log_review_refs(manifest_path)
    maybe_log_manifest_alignment(manifest_path, manifest_data)


def maybe_get_phase_planning_contracts(manifest_data: dict, phase_name: str) -> object:
    return get_planning_context_contracts(manifest_data, phase_name)


def get_framework_output_dir(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def maybe_update_globals_from_manifest(manifest_data: dict):
    maybe_update_phase_globals(manifest_data)


def maybe_get_framework_error(manifest_data: dict) -> str | None:
    aligned, error = validate_manifest_phase_alignment(manifest_data)
    if not aligned:
        return error
    return None


def maybe_fail_framework_alignment(manifest_data: dict):
    error = maybe_get_framework_error(manifest_data)
    if error:
        raise ValueError(error)


def get_phase_artifact_validator(phase_config: dict) -> str:
    return get_phase_validator_name(phase_config)


def maybe_get_phase_success_path(sd: str, phase_config: dict) -> str:
    return get_phase_output_success_path(sd, phase_config)


def maybe_get_framework_output_dir(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def maybe_should_skip_reiterate(manifest_path: str, manifest_data: dict) -> bool:
    return should_skip_reiterate(manifest_path, manifest_data)


def maybe_get_framework_review_path(manifest_path: str) -> str:
    return get_framework_review_reference(manifest_path)


def maybe_get_framework_review_results(manifest_path: str) -> str:
    return get_framework_review_results_reference(manifest_path)


def maybe_get_framework_complete_outputs(manifest_path: str) -> list[str]:
    return get_framework_complete_paths(manifest_path)


def maybe_log_framework_complete_outputs(manifest_path: str):
    log_event(manifest_path, f"framework_complete_outputs {get_framework_complete_paths(manifest_path)}")


def maybe_prepare_manifest_runtime(manifest_path: str, manifest_data: dict):
    maybe_update_globals_from_manifest(manifest_data)
    maybe_prepare_framework_logging(manifest_path, manifest_data)
    maybe_log_framework_complete_outputs(manifest_path)


def get_phase_context_output_dir(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_get_framework_phase_ref(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def get_phase_support_message(phase_config: dict) -> str | None:
    return maybe_get_phase_support_error(phase_config)


def maybe_add_phase_support(ctx: dict, phase_config: dict):
    support_message = get_phase_support_message(phase_config)
    if support_message:
        ctx['phase_support_message'] = support_message


def maybe_prepare_phase_context_all(ctx: dict, manifest_path: str, manifest_data: dict, phase_config: dict):
    maybe_prepare_phase_context(ctx, manifest_path, manifest_data, phase_config['name'])
    maybe_add_phase_support(ctx, phase_config)


def get_framework_paths_list(manifest_path: str) -> list[str]:
    return get_framework_complete_paths(manifest_path)


def maybe_get_framework_banner_lines(meta: dict) -> list[str]:
    return get_framework_detail_lines(meta)


def maybe_print_framework_banner(meta: dict):
    for line in maybe_get_framework_banner_lines(meta):
        print(line)


def get_phase_output_path(sd: str, phase_name: str, success_marker: str) -> str:
    return str(Path(phase_output_dir(sd, phase_name)) / success_marker)


def maybe_get_framework_manifest_support_state(manifest_data: dict) -> str:
    return get_framework_support_state(manifest_data)


def maybe_add_manifest_support(ctx: dict, manifest_data: dict):
    ctx['manifest_support_state'] = maybe_get_framework_manifest_support_state(manifest_data)


def maybe_complete_context(ctx: dict, manifest_path: str, manifest_data: dict, phase_config: dict):
    maybe_prepare_phase_context_all(ctx, manifest_path, manifest_data, phase_config)
    maybe_add_manifest_support(ctx, manifest_data)


def get_phase_success_reference(sd: str, phase_config: dict) -> str:
    return get_phase_output_path(sd, phase_config['name'], phase_config['success_marker'])


def maybe_log_phase_success_reference(manifest_path: str, sd: str, phase_config: dict):
    log_event(manifest_path, f"phase_success_reference {phase_config['name']}={get_phase_success_reference(sd, phase_config)}")


def maybe_prepare_phase_logging(manifest_path: str, sd: str, manifest_data: dict, phase_config: dict):
    maybe_prepare_before_phase(manifest_path, manifest_data, phase_config)
    maybe_log_phase_success_reference(manifest_path, sd, phase_config)


def get_phase_output_contracts(phase_name: str) -> list[str]:
    return get_phase_validation_contract(phase_name)


def maybe_get_framework_support_notice(manifest_data: dict) -> str | None:
    return maybe_get_framework_warning(manifest_data)


def maybe_add_support_notice(ctx: dict, manifest_data: dict):
    notice = maybe_get_framework_support_notice(manifest_data)
    if notice:
        ctx['support_notice'] = notice


def maybe_prepare_context_bundle(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_complete_context(ctx, manifest_path, manifest_data, phase_config)
    maybe_add_support_notice(ctx, manifest_data)
    maybe_log_phase_success_reference(manifest_path, sd, phase_config)


def get_framework_progression(manifest_data: dict) -> str:
    return maybe_get_framework_progression(manifest_data)


def maybe_get_framework_artifacts(phase_name: str) -> list[str]:
    return get_phase_validation_contract(phase_name)


def maybe_get_framework_success_path(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_log_framework_support_notice(manifest_path: str, manifest_data: dict):
    notice = maybe_get_framework_support_notice(manifest_data)
    if notice:
        log_event(manifest_path, f"framework_support_notice {notice}")


def maybe_prepare_startup(manifest_path: str, manifest_data: dict):
    maybe_prepare_manifest_runtime(manifest_path, manifest_data)
    maybe_log_framework_support_notice(manifest_path, manifest_data)


def get_phase_context_success_markers(phase_name: str) -> list[str]:
    return get_phase_success_markers(phase_name)


def maybe_get_phase_success_reference_for_manifest(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_print_framework_support_notice(manifest_data: dict):
    notice = maybe_get_framework_support_notice(manifest_data)
    if notice:
        print(f"  Support:  partial ({notice})")


def get_framework_summary_targets_text(manifest_path: str) -> str:
    return '\n'.join(get_framework_paths_for_manifest(manifest_path))


def maybe_add_summary_targets(ctx: dict, manifest_path: str):
    ctx['summary_targets'] = get_framework_summary_targets_text(manifest_path)


def maybe_prepare_phase_context_bundle(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_bundle(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_summary_targets(ctx, manifest_path)


def get_phase_supported_value(phase_config: dict) -> bool:
    return is_phase_supported(phase_config)


def maybe_get_phase_supported_value(phase_config: dict) -> bool:
    return get_phase_supported_value(phase_config)


def get_framework_manifest_warning(manifest_data: dict) -> str | None:
    return build_runtime_support_message(manifest_data)


def maybe_add_manifest_warning(ctx: dict, manifest_data: dict):
    warning = get_framework_manifest_warning(manifest_data)
    if warning:
        ctx['manifest_warning'] = warning


def maybe_prepare_phase_context_final(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_phase_context_bundle(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_manifest_warning(ctx, manifest_data)


def get_framework_status_notice(manifest_data: dict) -> str:
    warning = get_framework_manifest_warning(manifest_data)
    return warning or 'supported'


def maybe_log_framework_status_notice(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"framework_status_notice {get_framework_status_notice(manifest_data)}")


def maybe_prepare_bootstrap(manifest_path: str, manifest_data: dict):
    maybe_prepare_startup(manifest_path, manifest_data)
    maybe_log_framework_status_notice(manifest_path, manifest_data)


def maybe_get_phase_output_contracts(phase_name: str) -> list[str]:
    return get_phase_output_contracts(phase_name)


def get_framework_manifest_paths(manifest_path: str) -> list[str]:
    return get_framework_complete_paths(manifest_path)


def maybe_get_framework_manifest_paths(manifest_path: str) -> list[str]:
    return get_framework_manifest_paths(manifest_path)


def maybe_prepare_phase_contract_context(ctx: dict, phase_name: str):
    ctx['phase_output_contracts'] = json.dumps(get_phase_output_contracts(phase_name), indent=2)


def maybe_prepare_phase_context_complete(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_phase_context_final(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_prepare_phase_contract_context(ctx, phase_config['name'])


def get_framework_meta_notice(meta: dict) -> str:
    return f"framework={meta.get('frameworkVersion', 'tier-1')} support={get_framework_manifest_support(meta)}"


def maybe_print_framework_meta_notice(meta: dict):
    print(f"  Framework:{' ' if len('Framework:') < 10 else ''}{meta.get('frameworkVersion', 'tier-1')}")
    if meta.get('frameworkVersion') == 'tier-2':
        print(f"  Support:  {get_framework_manifest_support(meta)}")
        print(f"  Domains:  {maybe_get_tier2_domains(meta)}")


def maybe_log_framework_meta_notice(manifest_path: str, meta: dict):
    log_event(manifest_path, f"framework_meta_notice {get_framework_meta_notice(meta)}")


def get_phase_output_root_dir(sd: str, phase_name: str) -> str:
    return phase_output_dir(sd, phase_name)


def maybe_prepare_meta_notice(manifest_path: str, meta: dict):
    maybe_log_framework_meta_notice(manifest_path, meta)


def get_framework_tier(meta: dict) -> str:
    return meta.get('tier', 'medium')


def maybe_get_framework_tier(meta: dict) -> str:
    return get_framework_tier(meta)


def maybe_log_framework_tier(manifest_path: str, meta: dict):
    log_event(manifest_path, f"framework_tier {get_framework_tier(meta)}")


def maybe_prepare_meta(manifest_path: str, meta: dict):
    maybe_prepare_meta_notice(manifest_path, meta)
    maybe_log_framework_tier(manifest_path, meta)


def get_phase_success_files_for_phase(phase_name: str) -> list[str]:
    return get_phase_success_markers(phase_name)


def maybe_prepare_banner(manifest_path: str, manifest_data: dict):
    maybe_prepare_bootstrap(manifest_path, manifest_data)
    maybe_prepare_meta(manifest_path, manifest_data.get('meta', {}))


def get_phase_support_contracts(phase_name: str) -> list[str]:
    return get_phase_validation_contract(phase_name)


def maybe_add_phase_support_contracts(ctx: dict, phase_name: str):
    ctx['phase_support_contracts'] = json.dumps(get_phase_support_contracts(phase_name), indent=2)


def maybe_prepare_context_full(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_phase_context_complete(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_phase_support_contracts(ctx, phase_config['name'])


def get_framework_phase_dirname(phase_name: str) -> str:
    return phase_dir_name(phase_name)


def maybe_record_phase_dirname(manifest_path: str, phase_name: str):
    log_event(manifest_path, f"phase_dirname {phase_name}={get_framework_phase_dirname(phase_name)}")


def maybe_prepare_phase_dirname(manifest_path: str, phase_name: str):
    maybe_record_phase_dirname(manifest_path, phase_name)


def get_framework_summary_targets_joined(manifest_path: str) -> str:
    return '\n'.join(get_framework_manifest_paths(manifest_path))


def maybe_add_framework_summary_targets(ctx: dict, manifest_path: str):
    ctx['framework_summary_targets'] = get_framework_summary_targets_joined(manifest_path)


def maybe_prepare_context_everything(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_full(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_framework_summary_targets(ctx, manifest_path)


def get_framework_phase_marker(phase_config: dict) -> str:
    return phase_config['success_marker']


def maybe_get_framework_phase_marker(phase_config: dict) -> str:
    return get_framework_phase_marker(phase_config)


def maybe_prepare_phase_all(manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_phase_logging(manifest_path, sd, manifest_data, phase_config)


def maybe_prepare_context_and_phase(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_everything(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_prepare_phase_all(manifest_path, manifest_data, sd, phase_config)


def get_framework_complete_output_paths(manifest_path: str) -> list[str]:
    return get_framework_manifest_paths(manifest_path)


def maybe_prepare_framework(manifest_path: str, manifest_data: dict):
    maybe_prepare_banner(manifest_path, manifest_data)
    maybe_log_framework_identifiers(manifest_path, manifest_data)


def get_phase_context_support(phase_config: dict) -> str:
    return get_phase_support_status(phase_config)


def maybe_add_phase_context_support(ctx: dict, phase_config: dict):
    ctx['phase_context_support'] = get_phase_context_support(phase_config)


def maybe_prepare_context_last(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_and_phase(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_phase_context_support(ctx, phase_config)


def get_framework_warning_notice(manifest_data: dict) -> str | None:
    return maybe_get_framework_warning(manifest_data)


def maybe_prepare_warning_notice(manifest_path: str, manifest_data: dict):
    warning = get_framework_warning_notice(manifest_data)
    if warning:
        log_event(manifest_path, f"warning_notice {warning}")


def maybe_prepare_runtime(manifest_path: str, manifest_data: dict):
    maybe_prepare_framework(manifest_path, manifest_data)
    maybe_prepare_warning_notice(manifest_path, manifest_data)


def maybe_prepare_all(manifest_path: str, manifest_data: dict):
    maybe_prepare_runtime(manifest_path, manifest_data)


def get_phase_context_warning(phase_config: dict) -> str | None:
    return get_phase_support_note(phase_config)


def maybe_add_phase_context_warning(ctx: dict, phase_config: dict):
    warning = get_phase_context_warning(phase_config)
    if warning:
        ctx['phase_context_warning'] = warning


def maybe_prepare_context_max(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_last(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_phase_context_warning(ctx, phase_config)


def get_framework_complete_output_text(manifest_path: str) -> str:
    return '\n'.join(get_framework_complete_output_paths(manifest_path))


def maybe_add_complete_output_text(ctx: dict, manifest_path: str):
    ctx['complete_output_text'] = get_framework_complete_output_text(manifest_path)


def maybe_prepare_context_total(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_max(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_complete_output_text(ctx, manifest_path)


def get_phase_context_ready(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict) -> dict:
    maybe_prepare_context_total(ctx, manifest_path, manifest_data, sd, phase_config)
    return ctx


def maybe_prepare_manifest(manifest_path: str, manifest_data: dict):
    maybe_prepare_all(manifest_path, manifest_data)


def get_framework_phase_summary_paths(manifest_path: str) -> list[str]:
    return get_framework_complete_output_paths(manifest_path)


def maybe_log_framework_phase_summary_paths(manifest_path: str):
    log_event(manifest_path, f"framework_phase_summary_paths {get_framework_phase_summary_paths(manifest_path)}")


def maybe_prepare_manifest_summary_paths(manifest_path: str):
    maybe_log_framework_phase_summary_paths(manifest_path)


def maybe_prepare_orchestrator_runtime(manifest_path: str, manifest_data: dict):
    maybe_prepare_manifest(manifest_path, manifest_data)
    maybe_prepare_manifest_summary_paths(manifest_path)


def get_framework_phase_success_path(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_prepare_phase_support(manifest_path: str, phase_config: dict):
    maybe_print_phase_support_note(phase_config)
    maybe_log_phase_support(manifest_path, phase_config)


def maybe_prepare_phase_execution(manifest_path: str, manifest_data: dict, sd: str, phase_config: dict, ctx: dict):
    maybe_prepare_phase_support(manifest_path, phase_config)
    get_phase_context_ready(ctx, manifest_path, manifest_data, sd, phase_config)


def get_framework_phase_complete_refs(manifest_path: str) -> list[str]:
    return get_framework_phase_summary_paths(manifest_path)


def maybe_log_framework_phase_complete_refs(manifest_path: str):
    log_event(manifest_path, f"framework_phase_complete_refs {get_framework_phase_complete_refs(manifest_path)}")


def maybe_prepare_manifest_runtime_state(manifest_path: str, manifest_data: dict):
    maybe_prepare_orchestrator_runtime(manifest_path, manifest_data)
    maybe_log_framework_phase_complete_refs(manifest_path)


def get_phase_context_warning_message(phase_config: dict) -> str | None:
    return get_phase_support_note(phase_config)


def maybe_add_phase_context_warning_message(ctx: dict, phase_config: dict):
    warning = get_phase_context_warning_message(phase_config)
    if warning:
        ctx['phase_warning_message'] = warning


def maybe_prepare_context_runtime(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_phase_execution(manifest_path, manifest_data, sd, phase_config, ctx)
    maybe_add_phase_context_warning_message(ctx, phase_config)


def get_framework_paths_block(manifest_path: str) -> str:
    return get_framework_complete_output_text(manifest_path)


def maybe_add_paths_block(ctx: dict, manifest_path: str):
    ctx['paths_block'] = get_framework_paths_block(manifest_path)


def maybe_prepare_context_runtime_block(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_runtime(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_paths_block(ctx, manifest_path)


def get_context_for_phase(manifest_path: str, manifest_data: dict, phase_name: str) -> dict:
    sd = get_summaries_dir(manifest_path)
    phase_config = get_phase_config_by_manifest(manifest_data, phase_name)
    ctx = {
        'manifest_path': manifest_path,
        'source_path': manifest_data.get('meta', {}).get('sourcePath', ''),
        'target_path': manifest_data.get('meta', {}).get('targetPath', ''),
        'output_dir': phase_output_dir(sd, phase_name),
    }
    maybe_prepare_context_runtime_block(ctx, manifest_path, manifest_data, sd, phase_config)
    return ctx


def get_framework_runtime_summary(manifest_data: dict) -> str:
    return f"framework={get_framework_version(manifest_data)} support={get_framework_support_state(manifest_data)}"


def maybe_log_runtime_summary(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"runtime_summary {get_framework_runtime_summary(manifest_data)}")


def maybe_prepare_session(manifest_path: str, manifest_data: dict):
    maybe_prepare_manifest_runtime_state(manifest_path, manifest_data)
    maybe_log_runtime_summary(manifest_path, manifest_data)


def get_phase_output_display_dir(manifest_path: str, phase_name: str) -> str:
    return get_phase_output_dir_from_manifest(manifest_path, phase_name)


def maybe_print_phase_output_dir(manifest_path: str, phase_name: str):
    print(f"    Output dir: {get_phase_output_display_dir(manifest_path, phase_name)}")


def maybe_prepare_phase_runtime(manifest_path: str, manifest_data: dict, phase_config: dict):
    maybe_prepare_phase_support(manifest_path, phase_config)
    maybe_print_phase_output_dir(manifest_path, phase_config['name'])


def get_phase_artifact_contract_text(phase_name: str) -> str:
    return get_phase_contract_dump(phase_name)


def maybe_add_phase_artifact_contract_text(ctx: dict, phase_name: str):
    ctx['phase_artifact_contract_text'] = get_phase_artifact_contract_text(phase_name)


def maybe_prepare_context_ultra(ctx: dict, manifest_path: str, manifest_data: dict, sd: str, phase_config: dict):
    maybe_prepare_context_runtime_block(ctx, manifest_path, manifest_data, sd, phase_config)
    maybe_add_phase_artifact_contract_text(ctx, phase_config['name'])


def get_framework_start_paths(manifest_path: str) -> list[str]:
    return get_framework_complete_output_paths(manifest_path)


def maybe_print_framework_start_paths(manifest_path: str):
    for path in get_framework_start_paths(manifest_path):
        print(f"    {path}")


def maybe_prepare_start(manifest_path: str, manifest_data: dict):
    maybe_prepare_session(manifest_path, manifest_data)
    maybe_print_framework_start_paths(manifest_path)


def get_phase_configs(manifest_data: dict) -> list[dict]:
    return get_phase_set(manifest_data)


def maybe_get_phase_configs(manifest_data: dict) -> list[dict]:
    return get_phase_configs(manifest_data)


def maybe_prepare_preflight(manifest_path: str, manifest_data: dict):
    maybe_prepare_start(manifest_path, manifest_data)


def get_phase_summary_output(manifest_path: str, phase_name: str) -> str:
    return get_phase_summary_reference(manifest_path, phase_name)


def maybe_prepare_phase_ctx(ctx: dict, manifest_path: str, manifest_data: dict, phase_name: str):
    phase_config = get_phase_config_by_manifest(manifest_data, phase_name)
    sd = get_summaries_dir(manifest_path)
    maybe_prepare_context_ultra(ctx, manifest_path, manifest_data, sd, phase_config)


def maybe_prepare_run(manifest_path: str, manifest_data: dict):
    maybe_prepare_preflight(manifest_path, manifest_data)


def get_framework_manifest_summary_text(manifest_data: dict) -> str:
    return maybe_get_framework_phase_summary(manifest_data)


def maybe_log_manifest_summary_text(manifest_path: str, manifest_data: dict):
    log_event(manifest_path, f"manifest_summary_text {get_framework_manifest_summary_text(manifest_data)}")


def maybe_prepare_manifest_summary(manifest_path: str, manifest_data: dict):
    maybe_log_manifest_summary_text(manifest_path, manifest_data)


def maybe_prepare_orchestrator(manifest_path: str, manifest_data: dict):
    maybe_prepare_run(manifest_path, manifest_data)
    maybe_prepare_manifest_summary(manifest_path, manifest_data)


def get_framework_end_paths(manifest_path: str) -> list[str]:
    return get_framework_complete_output_paths(manifest_path)


def maybe_print_framework_end_paths(manifest_path: str):
    for path in get_framework_end_paths(manifest_path):
        print(f"    {path}")


def maybe_prepare_finish(manifest_path: str, manifest_data: dict):
    maybe_prepare_orchestrator(manifest_path, manifest_data)
    maybe_print_framework_end_paths(manifest_path)


def get_phase_output_contract_dump(phase_name: str) -> str:
    return json.dumps(get_phase_output_contracts(phase_name), indent=2)


def maybe_add_phase_output_contract_dump(ctx: dict, phase_name: str):
    ctx['phase_output_contract_dump'] = get_phase_output_contract_dump(phase_name)


def maybe_prepare_context_extreme(ctx: dict, manifest_path: str, manifest_data: dict, phase_name: str):
    maybe_prepare_phase_ctx(ctx, manifest_path, manifest_data, phase_name)
    maybe_add_phase_output_contract_dump(ctx, phase_name)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# The active phase set is always resolved from the manifest at runtime.
# Keep a tier-1 default here so older helpers still have a non-empty phase map
# before the manifest is loaded.
PHASES = TIER1_PHASES

# How many times to retry a failed phase
MAX_RETRIES = 2

# Agent timeout in seconds. Defaults aggressively trimmed: prebuilders already
# produced valid artifacts, codex only "refines" them. 5 min cap beats infinity.
DEFAULT_AGENT_TIMEOUT = int(os.environ.get("MIGRATION_TIMEOUT", "300"))
PHASE_TIMEOUT_DEFAULTS = {
    "domain_execution": int(os.environ.get("MIGRATION_TIMEOUT_DOMAIN_EXECUTION", "900")),
    "rewiring":         int(os.environ.get("MIGRATION_TIMEOUT_REWIRING", "360")),
    "integration_review": int(os.environ.get("MIGRATION_TIMEOUT_INTEGRATION_REVIEW", "360")),
}

# Fast mode: env override wins; CLI --fast sets it too.
FAST_MODE_DEFAULT = os.environ.get("MIGRATION_FAST", "").lower() in {"1", "true", "yes", "on"}

# Phases that can be fully skipped in fast mode when prebuilt markers exist.
FAST_MODE_SKIPPABLE_PHASES = {
    "foundation", "module_discovery", "domain_discovery",
    "conflict_resolution", "domain_planning", "rewiring",
    "integration_review",
}

# Polling interval in seconds
POLL_INTERVAL = int(os.environ.get("MIGRATION_POLL_INTERVAL", "15"))

# Framework root (where skills/ and scripts/ live)
FRAMEWORK_DIR = Path(__file__).parent.parent
DISCOVERY_BUILDER = FRAMEWORK_DIR / "scripts" / "discovery_builder.py"
FOUNDATION_BUILDER = FRAMEWORK_DIR / "scripts" / "tier2_foundation_builder.py"
TIER2_MODULE_DISCOVERY_BUILDER = FRAMEWORK_DIR / "scripts" / "tier2_module_discovery_builder.py"
TIER2_DOMAIN_DISCOVERY_BUILDER = FRAMEWORK_DIR / "scripts" / "tier2_domain_discovery_builder.py"
TIER2_CONFLICT_RESOLUTION_BUILDER = FRAMEWORK_DIR / "scripts" / "tier2_conflict_resolution_builder.py"
TIER2_DOMAIN_PLANNING_BUILDER = FRAMEWORK_DIR / "scripts" / "tier2_domain_planning_builder.py"
TIER2_DOMAIN_EXECUTION_BUILDER = FRAMEWORK_DIR / "scripts" / "tier2_domain_execution_builder.py"
TIER2_REWIRING_BUILDER = FRAMEWORK_DIR / "scripts" / "tier2_rewiring_builder.py"
TIER2_INTEGRATION_CHECKER = FRAMEWORK_DIR / "scripts" / "tier2_integration_checker.py"
PLANNING_BUILDER = FRAMEWORK_DIR / "scripts" / "planning_builder.py"
RECIPE_VERIFY_RUNNER = FRAMEWORK_DIR / "scripts" / "recipe_verify_runner.py"
ARTIFACT_VALIDATOR = FRAMEWORK_DIR / "scripts" / "validate_artifacts.py"
DEFAULT_EXECUTION_WORKERS = int(os.environ.get("MIGRATION_EXECUTION_WORKERS", "3"))
MAX_BATCH_WORKERS = max(1, DEFAULT_EXECUTION_WORKERS)


def get_agent_timeout_seconds(phase_name: str) -> int:
    env_key = f"MIGRATION_TIMEOUT_{phase_name.upper()}"
    raw = os.environ.get(env_key)
    if raw is None and phase_name in PHASE_TIMEOUT_DEFAULTS:
        raw = os.environ.get("MIGRATION_TIMEOUT_LONG_PHASES") or str(PHASE_TIMEOUT_DEFAULTS[phase_name])
    fallback = int(os.environ.get("MIGRATION_TIMEOUT", str(DEFAULT_AGENT_TIMEOUT)))
    if raw is None:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return value if value > 0 else fallback

PLANNING_ARTIFACT_CONTRACTS = [
    {"name": "AGENTS.md", "purpose": "Transformation rules for execution workers"},
    {"name": "migration-batches.json", "purpose": "Dependency-ordered execution batches"},
    {"name": "planning-overview.json", "purpose": "Machine-readable stage outputs and validation contracts"},
    {"name": "PLAN.md", "purpose": "Human-readable approval summary"},
]

REVIEW_CHECKS = ["build", "tests", "lint", "diff"]

EXECUTION_BATCH_SUCCESS_MARKER = "batch-{batch_id}-results.json"
PHASE_CONFIG_BY_NAME = refresh_phase_constants(PHASES)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Logging + display helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_log_path(manifest_path: str) -> Path:
    meta = mf.load(manifest_path)["meta"]
    return Path(meta.get("artifactsDir", ".")) / "migration.log"


def log_event(manifest_path: str, message: str):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    log_path = get_log_path(manifest_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def banner(msg: str, char="━"):
    width = 64
    print(f"\n{char * width}")
    print(f"  {msg}")
    print(f"{char * width}")


def log_and_print(manifest_path: str, message: str):
    print(message)
    log_event(manifest_path, message)


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_run_control_dir(manifest_path: str) -> Path:
    meta = mf.load(manifest_path)["meta"]
    artifacts_dir = Path(meta.get("artifactsDir", "."))
    return Path(meta.get("runControlDir", artifacts_dir / "run-control"))


def get_issue_ledger_paths(manifest_path: str) -> tuple[Path, Path]:
    meta = mf.load(manifest_path)["meta"]
    run_control_dir = get_run_control_dir(manifest_path)
    markdown_path = Path(meta.get("issueLedgerPath", run_control_dir / "ISSUE_LEDGER.md"))
    json_path = Path(meta.get("issueLedgerJsonPath", run_control_dir / "issue-ledger.json"))
    return markdown_path, json_path


def get_phase_issue_report_path(manifest_path: str, phase_name: str) -> Path:
    return get_run_control_dir(manifest_path) / "phase-issues" / f"{phase_name}.md"


def build_issue_ledger(manifest_path: str, manifest_data: dict | None = None) -> dict:
    if manifest_data is None:
        manifest_data = mf.load(manifest_path)
    meta = manifest_data.get("meta", {})
    return {
        "sessionId": meta.get("sessionId", "unknown"),
        "manifestPath": str(Path(manifest_path).resolve()),
        "frameworkVersion": meta.get("frameworkVersion", "tier-1"),
        "tier": meta.get("tier", "medium"),
        "sourcePath": meta.get("sourcePath", ""),
        "targetPath": meta.get("targetPath", ""),
        "status": meta.get("status", "pending"),
        "currentPhase": None,
        "currentAttempt": None,
        "progress": build_progress_snapshot(manifest_data),
        "issues": [],
        "events": [],
        "lastUpdatedAt": utc_timestamp(),
    }


def render_issue_ledger_markdown(ledger: dict) -> str:
    progress = ledger.get("progress", {})
    progress_bar = progress.get("bar", "[]")
    progress_done = progress.get("completedPhases", 0)
    progress_total = progress.get("totalPhases", 0)
    progress_percent = progress.get("percent", 0)
    progress_summary = progress.get("summary", "pending")
    lines = [
        "# Issue Ledger",
        "",
        "This file is the run-level source of truth for blockers, repairs, retries, and approvals.",
        "Use this file instead of chat history when the run state looks ambiguous.",
        "",
        "## Current State",
        "",
        f"- Session: `{ledger.get('sessionId', 'unknown')}`",
        f"- Status: `{ledger.get('status', 'pending')}`",
        f"- Framework: `{ledger.get('frameworkVersion', 'tier-1')}`",
        f"- Current phase: `{ledger.get('currentPhase') or 'none'}`",
        f"- Current attempt: `{ledger.get('currentAttempt') or 0}`",
        f"- Progress: `{progress_bar} {progress_done}/{progress_total} done ({progress_percent}%)`",
        f"- Progress state: `{progress_summary}`",
        f"- Manifest: `{ledger.get('manifestPath', '')}`",
        "",
        "## Open Issues",
        "",
    ]

    issues = [item for item in ledger.get("issues", []) if item.get("status") == "open"]
    if issues:
        for issue in issues:
            lines.append(
                f"- `{issue.get('id', 'issue')}` [{issue.get('phase') or 'run'} / {issue.get('category', 'issue')}] {issue.get('summary', '')}"
            )
            if issue.get("details"):
                lines.append(f"  Details: {issue['details']}")
            if issue.get("evidence"):
                lines.append(f"  Evidence: {', '.join(issue['evidence'])}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Resolved Issues", ""])
    resolved = [item for item in ledger.get("issues", []) if item.get("status") != "open"]
    if resolved:
        for issue in resolved:
            lines.append(
                f"- `{issue.get('id', 'issue')}` [{issue.get('phase') or 'run'} / {issue.get('category', 'issue')}] {issue.get('summary', '')}"
            )
            if issue.get("details"):
                lines.append(f"  Details: {issue['details']}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Iteration History", ""])
    events = ledger.get("events", [])
    if events:
        for event in events:
            phase = event.get("phase") or "run"
            attempt = event.get("attempt")
            attempt_text = f" attempt={attempt}" if attempt is not None else ""
            lines.append(
                f"- `{event.get('timestamp', '')}` [{event.get('type', 'event')}] phase={phase}{attempt_text} {event.get('message', '')}".rstrip()
            )
            if event.get("evidence"):
                lines.append(f"  Evidence: {', '.join(event['evidence'])}")
    else:
        lines.append("- No events recorded yet.")

    lines.append("")
    return "\n".join(lines)


def load_issue_ledger(manifest_path: str, manifest_data: dict | None = None) -> dict:
    manifest_snapshot = manifest_data or mf.load(manifest_path)
    markdown_path, json_path = get_issue_ledger_paths(manifest_path)
    if json_path.exists():
        try:
            ledger = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ledger = build_issue_ledger(manifest_path, manifest_snapshot)
    else:
        ledger = build_issue_ledger(manifest_path, manifest_snapshot)

    ledger.setdefault("issues", [])
    ledger.setdefault("events", [])
    ledger.setdefault("status", manifest_snapshot.get("meta", {}).get("status", "pending"))
    ledger.setdefault("currentPhase", None)
    ledger.setdefault("currentAttempt", None)
    ledger["progress"] = build_progress_snapshot(manifest_snapshot)
    ledger["lastUpdatedAt"] = utc_timestamp()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    return ledger


def save_issue_ledger(manifest_path: str, ledger: dict):
    markdown_path, json_path = get_issue_ledger_paths(manifest_path)
    ledger["lastUpdatedAt"] = utc_timestamp()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_issue_ledger_markdown(ledger), encoding="utf-8")


def initialize_run_control(manifest_path: str, manifest_data: dict | None = None):
    run_control_dir = get_run_control_dir(manifest_path)
    run_control_dir.mkdir(parents=True, exist_ok=True)
    (run_control_dir / "phase-issues").mkdir(parents=True, exist_ok=True)
    ledger = load_issue_ledger(manifest_path, manifest_data)
    save_issue_ledger(manifest_path, ledger)


def update_issue_ledger_state(
    manifest_path: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    attempt: int | None = None,
):
    ledger = load_issue_ledger(manifest_path)
    if status is not None:
        ledger["status"] = status
    if phase is not None:
        ledger["currentPhase"] = phase
    if attempt is not None:
        ledger["currentAttempt"] = attempt
    save_issue_ledger(manifest_path, ledger)


def append_issue_ledger_event(
    manifest_path: str,
    event_type: str,
    message: str,
    *,
    phase: str | None = None,
    attempt: int | None = None,
    evidence: list[str] | None = None,
):
    ledger = load_issue_ledger(manifest_path)
    ledger["events"].append(
        {
            "timestamp": utc_timestamp(),
            "type": event_type,
            "phase": phase,
            "attempt": attempt,
            "message": message,
            "evidence": evidence or [],
        }
    )
    save_issue_ledger(manifest_path, ledger)


def record_issue(
    manifest_path: str,
    *,
    category: str,
    summary: str,
    details: str = "",
    phase: str | None = None,
    attempt: int | None = None,
    evidence: list[str] | None = None,
    status: str = "open",
):
    ledger = load_issue_ledger(manifest_path)
    issue_id = f"issue-{len(ledger['issues']) + 1:04d}"
    ledger["issues"].append(
        {
            "id": issue_id,
            "timestamp": utc_timestamp(),
            "status": status,
            "category": category,
            "phase": phase,
            "attempt": attempt,
            "summary": summary,
            "details": details,
            "evidence": evidence or [],
        }
    )
    save_issue_ledger(manifest_path, ledger)
    return issue_id


def ensure_phase_issue_report(manifest_path: str, phase_name: str):
    phase_issue_path = get_phase_issue_report_path(manifest_path, phase_name)
    if phase_issue_path.exists():
        return
    phase_issue_path.parent.mkdir(parents=True, exist_ok=True)
    phase_issue_path.write_text(
        "\n".join(
            [
                f"# Phase Issue Report: {phase_name}",
                "",
                "Use this file to capture blockers, contradictions, or evidence that does not fit the main summary artifact.",
                "If the phase succeeds cleanly, this file may remain unchanged.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def mark_phase_failure(
    manifest_path: str,
    phase_name: str,
    error_msg: str,
    *,
    attempt: int | None = None,
    evidence: list[str] | None = None,
) -> bool:
    cleaned_evidence = [item for item in (evidence or []) if item]
    append_issue_ledger_event(
        manifest_path,
        "phase_failed",
        f"{phase_name} failed: {error_msg}",
        phase=phase_name,
        attempt=attempt,
        evidence=cleaned_evidence,
    )
    record_issue(
        manifest_path,
        category="phase_failure",
        summary=f"{phase_name} failed",
        details=error_msg,
        phase=phase_name,
        attempt=attempt,
        evidence=cleaned_evidence,
        status="open",
    )
    update_issue_ledger_state(manifest_path, status="failed", phase=phase_name, attempt=attempt)
    manifest_data = mf.update_phase(manifest_path, phase_name, "failed", extra={"error": error_msg})
    log_progress(manifest_path, manifest_data=manifest_data)
    return False


def reconcile_manifest_phase_set(manifest_path: str) -> tuple[dict, dict | None]:
    manifest_data = mf.load(manifest_path)
    expected_phase_names = get_phase_names(manifest_data)
    actual_phases = manifest_data.get("phases", {})
    expected_set = set(expected_phase_names)
    actual_set = set(actual_phases)
    if expected_set == actual_set:
        return manifest_data, None

    repaired_phases: dict[str, dict] = {}
    missing = [name for name in expected_phase_names if name not in actual_phases]
    unexpected = [name for name in actual_phases if name not in expected_set]
    for phase_name in expected_phase_names:
        repaired_phases[phase_name] = actual_phases.get(phase_name, {"status": "pending"})
    manifest_data["phases"] = repaired_phases
    repairs = manifest_data.setdefault("meta", {}).setdefault("phaseAlignmentRepairs", [])
    repairs.append(
        {
            "timestamp": utc_timestamp(),
            "missing": missing,
            "unexpected": unexpected,
        }
    )
    mf.save(manifest_path, manifest_data)
    return manifest_data, {"missing": missing, "unexpected": unexpected}


def restart_from_phase(manifest_path: str, manifest_data: dict, phase_name: str) -> dict:
    phases = get_phase_set(manifest_data)
    restart_index = get_phase_resume_index(phases, phase_name)
    manifest = mf.load(manifest_path)
    for phase in phases[restart_index:]:
        phase_state = manifest.setdefault("phases", {}).setdefault(phase["name"], {})
        phase_state["status"] = "pending"
        for key in ("completedAt", "approvedAt", "failedAt", "awaitingApprovalAt", "error"):
            phase_state.pop(key, None)
    manifest.setdefault("meta", {})["status"] = "pending"
    mf.save(manifest_path, manifest)
    return manifest


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Display helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def phase_header(phase_name: str, status: str = "starting"):
    print(f"\n{'─' * 64}")
    print(f"  Phase: {phase_name.upper()}  [{status}]")
    print(f"{'─' * 64}")


PHASE_STATUS_SYMBOLS = {
    "done": "#",
    "approved": "#",
    "in_progress": ">",
    "awaiting_approval": "!",
    "failed": "x",
    "pending": ".",
}

PHASE_STATUS_LABELS = {
    "done": "done",
    "approved": "approved",
    "in_progress": "in progress",
    "awaiting_approval": "awaiting approval",
    "failed": "failed",
    "pending": "pending",
    "complete": "complete",
}

# Rich progress bar glyphs (block cells). Falls back to ASCII if NO_COLOR/MIGRATION_ASCII set.
_ASCII_BAR = bool(os.environ.get("NO_COLOR") or os.environ.get("MIGRATION_ASCII"))
PHASE_STATUS_GLYPHS = {
    "done":               ("█", "\033[32m"),
    "approved":           ("█", "\033[32m"),
    "in_progress":        ("▓", "\033[33m"),
    "awaiting_approval":  ("▒", "\033[35m"),
    "failed":             ("✗", "\033[31m"),
    "pending":            ("░", "\033[90m"),
}
_RESET = "\033[0m"


def _render_bar_cells(phase_states: dict, phase_names: list[str]) -> str:
    """Build a colorized block-char bar for the manifest phases."""
    cells = []
    for name in phase_names:
        status = phase_states.get(name, {}).get("status", "pending")
        if _ASCII_BAR:
            cells.append(PHASE_STATUS_SYMBOLS.get(status, "?"))
        else:
            glyph, color = PHASE_STATUS_GLYPHS.get(status, ("?", ""))
            cells.append(f"{color}{glyph}{_RESET}" if color else glyph)
    if _ASCII_BAR:
        return f"[{''.join(cells)}]"
    return f"│{''.join(cells)}│"


def render_status_banner(manifest_data: dict) -> str:
    """Multi-line visual status card for end-of-phase / run completion."""
    snapshot = build_progress_snapshot(manifest_data)
    phase_names = get_phase_names(manifest_data)
    phase_states = manifest_data.get("phases", {})
    lines = []
    width = max(64, len(phase_names) * 4 + 20)
    title = f" MIGRATION PROGRESS — {snapshot['percent']}% "
    lines.append("╭" + "─" * (width - 2) + "╮")
    lines.append("│" + title.center(width - 2) + "│")
    lines.append("├" + "─" * (width - 2) + "┤")
    filled = int((snapshot["percent"] / 100) * (width - 10))
    track = "█" * filled + "░" * (width - 10 - filled)
    lines.append(f"│  {track}  │")
    lines.append("├" + "─" * (width - 2) + "┤")
    for idx, name in enumerate(phase_names, start=1):
        status = phase_states.get(name, {}).get("status", "pending")
        glyph, color = PHASE_STATUS_GLYPHS.get(status, ("?", ""))
        label = PHASE_STATUS_LABELS.get(status, status)
        if _ASCII_BAR:
            row = f"  {idx:>2}. [{PHASE_STATUS_SYMBOLS.get(status,'?')}] {name:<22} {label}"
        else:
            row = f"  {idx:>2}. {color}{glyph}{_RESET} {name:<22} {color}{label}{_RESET}"
        pad = width - 2 - _visual_len(row)
        lines.append("│" + row + " " * max(0, pad) + "│")
    lines.append("╰" + "─" * (width - 2) + "╯")
    return "\n".join(lines)


def _visual_len(text: str) -> int:
    """Count visible characters, ignoring ANSI escape sequences."""
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def build_progress_snapshot(manifest_data: dict) -> dict:
    phase_names = get_phase_names(manifest_data)
    phase_states = manifest_data.get("phases", {})
    total_phases = len(phase_names)
    completed_phases = 0
    current_phase = None
    current_status = None

    for phase_name in phase_names:
        status = phase_states.get(phase_name, {}).get("status", "pending")
        if status == "done":
            completed_phases += 1
        if current_phase is None and status in {"in_progress", "awaiting_approval", "failed", "approved"}:
            current_phase = phase_name
            current_status = status

    if current_phase is None:
        if completed_phases == total_phases:
            current_status = "complete"
        else:
            next_pending = next(
                (
                    phase_name
                    for phase_name in phase_names
                    if phase_states.get(phase_name, {}).get("status", "pending") == "pending"
                ),
                None,
            )
            current_phase = next_pending
            current_status = "pending" if next_pending else None

    current_index = phase_names.index(current_phase) + 1 if current_phase in phase_names else None
    percent = 100 if total_phases == 0 else int((completed_phases / total_phases) * 100)
    summary = PHASE_STATUS_LABELS.get(current_status, "pending")
    if current_phase and current_status != "complete":
        if current_index is not None:
            summary = f"{summary}: {current_phase} ({current_index}/{total_phases})"
        else:
            summary = f"{summary}: {current_phase}"

    return {
        "bar": _render_bar_cells(phase_states, phase_names),
        "completedPhases": completed_phases,
        "totalPhases": total_phases,
        "percent": percent,
        "currentPhase": current_phase,
        "currentStatus": current_status,
        "currentIndex": current_index,
        "summary": summary,
    }


def render_progress_line(manifest_data: dict, prefix: str = "  Progress: ") -> str:
    snapshot = build_progress_snapshot(manifest_data)
    return (
        f"{prefix}{snapshot['bar']} "
        f"{snapshot['completedPhases']}/{snapshot['totalPhases']} done "
        f"({snapshot['percent']}%) | {snapshot['summary']}"
    )


def log_progress(manifest_path: str, *, prefix: str = "  Progress: ", manifest_data: dict | None = None):
    snapshot = manifest_data or mf.load(manifest_path)
    log_and_print(manifest_path, render_progress_line(snapshot, prefix=prefix))


def show_summary(filepath: str, max_lines: int = 40):
    """Print the first N lines of a summary file."""
    if not os.path.exists(filepath):
        print(f"  (summary file not found: {filepath})")
        return
    with open(filepath) as f:
        lines = f.readlines()
    print()
    for line in lines[:max_lines]:
        print(f"  │ {line.rstrip()}")
    if len(lines) > max_lines:
        print(f"  │ ... ({len(lines) - max_lines} more lines)")
        print(f"  │ Full file: {filepath}")
    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Approval gate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def request_approval(phase_name: str, summary_path: str,
                     skip_approval: bool = False,
                     non_interactive: bool = False) -> str:
    """
    Handle approval gates.
    Returns one of: 'approved', 'aborted', 'deferred'.
    """
    if skip_approval:
        print(f"  [auto-approve: --skip-approval flag is set]")
        return "approved"

    banner(f"APPROVAL GATE: {phase_name.upper()}", char="═")
    print(f"  Review the output: {summary_path}")
    show_summary(summary_path)

    if non_interactive:
        print("  Non-interactive mode: approval deferred.")
        manifest_path = os.environ.get("MIGRATION_MANIFEST_PATH", "migration-manifest.json")
        print(f"  Review the summary, then resume with: python {__file__} {manifest_path} --approve {phase_name}")
        return "deferred"

    while True:
        try:
            response = input("  [approve / abort / open] → ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Interrupted. Deferring approval.")
            return "deferred"

        if response in ("approve", "a", "yes", "y"):
            print(f"  ✓ {phase_name} approved")
            return "approved"
        elif response in ("abort", "x", "no", "n"):
            return "aborted"
        elif response in ("open", "o"):
            editor = os.environ.get("EDITOR", "less")
            os.system(f"{editor} {summary_path}")
        else:
            print("  Type 'approve', 'abort', or 'open'")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Git checkpointing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def git_checkpoint(manifest_path: str, phase_name: str):
    """Create a git checkpoint for rollback support."""
    try:
        # Check if we're in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            git_ref = result.stdout.strip()
            sd = get_summaries_dir(manifest_path)
            # Stage and commit migration artifacts
            subprocess.run(["git", "add", f"{sd}/", manifest_path],
                           capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"migration checkpoint: {phase_name} complete",
                 "--allow-empty"],
                capture_output=True
            )
            new_ref = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True
            ).stdout.strip()
            mf.add_checkpoint(manifest_path, phase_name, new_ref)
            print(f"  [checkpoint] git: {new_ref}")
    except FileNotFoundError:
        pass  # git not available, skip


def apply_reiterate_patch_if_present(manifest_path: str, output_dir: str) -> dict:
    """
    Apply learned AGENTS.md patches proposed by reiterate only after approval.

    Expected agents-md.patch.json shape:
    {
      "mode": "append",
      "proposals": [
        {"title": "LEARNED PATTERN: ...", "content": "...", "apply": true}
      ]
    }
    """
    patch_path = Path(output_dir) / "agents-md.patch.json"
    if not patch_path.exists():
        return {"applied": False, "reason": "no patch proposal"}

    try:
        payload = json.loads(patch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"applied": False, "reason": f"invalid patch proposal json: {exc}"}

    proposals = payload.get("proposals", [])
    if not isinstance(proposals, list) or not proposals:
        return {"applied": False, "reason": "empty patch proposal"}

    summaries_dir = get_summaries_dir(manifest_path)
    target_paths = [str(Path(summaries_dir) / "planning" / "AGENTS.md")]
    target_paths.extend(tier2_agents_paths(summaries_dir))
    target_paths = [path for path in target_paths if Path(path).exists()]
    if not target_paths:
        return {"applied": False, "reason": "no AGENTS files found for patch application"}

    applied_by_path: dict[str, list[str]] = {}
    for target_path in target_paths:
        agents_path = Path(target_path)
        agents_text = agents_path.read_text(encoding="utf-8")
        appended_sections: list[str] = []
        applied_titles: list[str] = []
        domain_name = agents_path.stem.split(".", 1)[1] if agents_path.stem.startswith("AGENTS.") else None

        for proposal in proposals:
            if not isinstance(proposal, dict):
                continue
            if proposal.get("apply", True) is False:
                continue
            proposal_domain = proposal.get("domain")
            if domain_name and proposal_domain and proposal_domain != domain_name:
                continue
            if not domain_name and proposal_domain:
                continue
            title = str(proposal.get("title", "")).strip()
            content = str(proposal.get("content", "")).strip()
            if not title or not content:
                continue
            section = f"\n\n## {title}\n\n{content}\n"
            if title in agents_text or section.strip() in agents_text:
                continue
            appended_sections.append(section)
            applied_titles.append(title)

        if not appended_sections:
            continue
        agents_path.write_text(agents_text.rstrip() + "".join(appended_sections) + "\n", encoding="utf-8")
        applied_by_path[str(agents_path)] = applied_titles

    if not applied_by_path:
        return {"applied": False, "reason": "no new sections to append"}

    summary = ", ".join(f"{Path(path).name}: {', '.join(titles)}" for path, titles in applied_by_path.items())
    log_and_print(manifest_path, f"  [agents-md] appended learned patterns: {summary}")
    return {"applied": True, "appliedByPath": applied_by_path}


def run_recipe_verify_if_available(manifest_path: str, context: dict, output_dir: str) -> dict:
    parity_results_path = Path(output_dir) / "parity-results.json"
    recipe_root = context.get("recipe_root")
    verify_dir = context.get("recipe_verify_dir")
    if not recipe_root or not verify_dir:
        report = {
            "status": "skipped",
            "reason": "recipe context unavailable",
            "hooks": [],
            "summary": {"total": 0, "passed": 0, "failed": 0},
        }
        parity_results_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    verify_cmd = [
        sys.executable,
        str(RECIPE_VERIFY_RUNNER),
        context.get("source_path", ""),
        context.get("target_path", ""),
        recipe_root,
        verify_dir,
        str(parity_results_path),
        manifest_path,
    ]
    result = subprocess.run(verify_cmd, capture_output=True, text=True)
    if result.stdout.strip():
        log_and_print(manifest_path, f"    {result.stdout.strip()}")
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "recipe verify runner failed"
        raise RuntimeError(error_msg)

    try:
        return json.loads(parity_results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid parity-results.json: {exc}") from exc


def run_python_builder(manifest_path: str, label: str, script_path: Path, cmd_args: list[str]) -> tuple[bool, str]:
    if not script_path.exists():
        return True, ""
    log_and_print(manifest_path, f"  → {label}...")
    cmd = [sys.executable, str(script_path), *cmd_args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        log_and_print(manifest_path, f"    {result.stdout.strip()}")
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or f"{label} failed"
        log_and_print(manifest_path, f"  ✗ {label} failed: {error_msg}")
        return False, error_msg
    return True, ""


def collect_overview_domain_artifacts(overview_path: Path) -> list[dict]:
    if not overview_path.exists():
        return []
    try:
        overview = json.loads(overview_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in overview.get("domains", []) if isinstance(item, dict)]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Context builders — produce the context dict for each phase's agent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_summaries_dir(manifest_path: str) -> str:
    """
    Return the summaries root directory for this migration.
    Reads summariesDir from the manifest if present; falls back to
    the legacy project-root location so old manifests still work.
    """
    meta = mf.load(manifest_path)["meta"]
    return meta.get("summariesDir", "migration-summaries")


def build_context(manifest_path: str, phase_name: str) -> dict:
    """
    Build the context dict that gets injected into the agent's prompt.
    Each phase gets the manifest meta + references to upstream outputs.
    """
    manifest_data = mf.load(manifest_path)
    meta = manifest_data["meta"]
    sd = meta.get("summariesDir", "migration-summaries")  # summaries root
    recipe_assets, recipe_error = resolve_recipe_assets(meta)
    recipe_manifest = load_recipe_manifest_data((recipe_assets or {}).get("recipe_manifest_path"))
    domains = normalize_domain_list(meta, recipe_manifest)
    domain_ordering = normalize_domain_ordering(meta, recipe_manifest)
    domain_patterns = build_recipe_domain_patterns((recipe_assets or {}).get("recipe_root"), recipe_manifest)
    output_dir = phase_output_dir(sd, phase_name)

    ctx = {
        "manifest_path": manifest_path,
        "source_path": meta.get("sourcePath", ""),
        "target_path": meta.get("targetPath", ""),
        "source_description": meta.get("sourceDescription", ""),
        "target_description": meta.get("targetDescription", ""),
        "output_dir": output_dir,
        "working_dir": os.getcwd(),
        "artifact_contracts": VALIDATION_REPORTS.get(phase_name, []),
        "run_control_dir": str(get_run_control_dir(manifest_path)),
        "issue_ledger_path": str(get_issue_ledger_paths(manifest_path)[0]),
        "issue_ledger_json_path": str(get_issue_ledger_paths(manifest_path)[1]),
        "phase_issue_report_path": str(get_phase_issue_report_path(manifest_path, phase_name)),
    }
    if recipe_assets:
        ctx.update(recipe_assets)
    if recipe_error:
        ctx["recipe_required_error"] = recipe_error
    if domains:
        ctx["domains"] = json.dumps(domains, indent=2)
    if domain_ordering:
        ctx["domain_ordering"] = json.dumps(domain_ordering, indent=2)
    if domain_patterns:
        ctx["domain_patterns_map"] = json.dumps(domain_patterns, indent=2)
    if recipe_assets and recipe_assets.get("recipe_root"):
        recipe_template_dir = Path(recipe_assets["recipe_root"]) / "skills" / "templates"
        if recipe_template_dir.exists():
            ctx["recipe_skill_templates_dir"] = str(recipe_template_dir)
        legacy_templates = {
            "discovery": Path(recipe_assets["recipe_root"]) / "tier2-discovery.md.tmpl",
            "planning": Path(recipe_assets["recipe_root"]) / "tier2-planning.md.tmpl",
            "execution": Path(recipe_assets["recipe_root"]) / "tier2-execution.md.tmpl",
        }
        available_legacy = {name: str(path) for name, path in legacy_templates.items() if path.exists()}
        if available_legacy:
            ctx["recipe_skill_template_files"] = json.dumps(available_legacy, indent=2)
    if recipe_manifest is not None:
        ctx["recipe_manifest_data"] = json.dumps(recipe_manifest, indent=2)

    if phase_name == "planning":
        ctx["planning_artifact_contracts"] = json.dumps(PLANNING_ARTIFACT_CONTRACTS, indent=2)
    elif phase_name == "review":
        ctx["review_checks"] = ", ".join(REVIEW_CHECKS)
    elif phase_name == "execution":
        ctx["max_batch_workers"] = str(MAX_BATCH_WORKERS)
    elif phase_name == "integration_review":
        ctx["review_checks"] = ", ".join(REVIEW_CHECKS + ["recipe-parity", "cross-domain-imports"])

    execution_phase = manifest_data.get("phases", {}).get("execution", {})
    if execution_phase.get("artifacts", {}).get("batchResults"):
        ctx["batch_results"] = json.dumps(execution_phase["artifacts"]["batchResults"], indent=2)

    # Add reference path if available
    if meta.get("referencePath"):
        ctx["reference_path"] = meta["referencePath"]

    # Add non-negotiables
    if meta.get("nonNegotiables"):
        ctx["non_negotiables"] = " | ".join(meta["nonNegotiables"])
    if meta.get("styleGuides"):
        ctx["style_guides"] = json.dumps(meta["styleGuides"], indent=2)
    if meta.get("namingConventions"):
        ctx["naming_conventions"] = json.dumps(meta["namingConventions"], indent=2)

    # Add test/build/lint commands
    for key in ("testCommand", "buildCommand", "lintCommand"):
        if meta.get(key):
            ctx[key] = meta[key]

    # ── Phase-specific upstream references ──

    if phase_name == "planning":
        ctx["discovery_output"] = f"{sd}/discovery/DISCOVERY.md"
        ctx["dep_graph_path"] = f"{sd}/discovery/dep-graph.json"
        ctx["file_manifest_path"] = f"{sd}/discovery/file-manifest.json"
        ctx["symbol_index_path"] = f"{sd}/discovery/symbol-index.json"
        ctx["dynamic_risk_report_path"] = f"{sd}/discovery/dynamic-risk-report.json"
        ctx["dependency_shards_dir"] = f"{sd}/discovery/dependency-shards"
        ctx["planning_input_path"] = f"{sd}/planning/planning-input.json"
        ctx["risk_policy_path"] = f"{sd}/planning/risk-policy.json"

    elif phase_name == "discovery":
        ctx["dep_graph_path"] = f"{sd}/discovery/dep-graph.json"
        ctx["file_manifest_path"] = f"{sd}/discovery/file-manifest.json"
        ctx["symbol_index_path"] = f"{sd}/discovery/symbol-index.json"
        ctx["dynamic_risk_report_path"] = f"{sd}/discovery/dynamic-risk-report.json"
        ctx["dependency_shards_dir"] = f"{sd}/discovery/dependency-shards"

    elif phase_name == "execution":
        ctx["agents_md_path"] = f"{sd}/planning/AGENTS.md"
        ctx["plan_path"] = f"{sd}/planning/PLAN.md"
        ctx["batches_path"] = f"{sd}/planning/migration-batches.json"
        ctx["discovery_output"] = f"{sd}/discovery/DISCOVERY.md"
        ctx["planning_input_path"] = f"{sd}/planning/planning-input.json"

    elif phase_name == "review":
        ctx["execution_output"] = f"{sd}/execution"
        ctx["agents_md_path"] = f"{sd}/planning/AGENTS.md"
        ctx["plan_path"] = f"{sd}/planning/PLAN.md"
        ctx["planning_input_path"] = f"{sd}/planning/planning-input.json"
        ctx["parity_results_path"] = f"{sd}/review/parity-results.json"
        # Pass the diff scorer script path so the review agent can run it
        ctx["diff_scorer_script"] = str(FRAMEWORK_DIR / "scripts" / "diff_scorer.py")

    elif phase_name == "reiterate":
        if is_tier2_manifest(manifest_data):
            ctx["review_output"] = f"{phase_output_dir(sd, 'integration_review')}/INTEGRATION_REVIEW.md"
            ctx["review_results"] = f"{phase_output_dir(sd, 'integration_review')}/integration-review.json"
            ctx["execution_output"] = phase_output_dir(sd, "domain_execution")
            ctx["planning_output"] = phase_output_dir(sd, "domain_planning")
        else:
            ctx["review_output"] = f"{sd}/review/REVIEW.md"
            ctx["review_results"] = f"{sd}/review/review-results.json"
            ctx["agents_md_path"] = f"{sd}/planning/AGENTS.md"
            ctx["execution_output"] = f"{sd}/execution"
            ctx["planning_input_path"] = f"{sd}/planning/planning-input.json"
        ctx["agents_patch_proposal_path"] = f"{sd}/reiterate/agents-md.patch.json"
        ctx["agents_patch_summary_path"] = f"{sd}/reiterate/agents-md-patches.md"
    elif phase_name == "foundation":
        ctx["foundation_output_dir"] = output_dir
    elif phase_name == "module_discovery":
        foundation_dir = phase_output_dir(sd, "foundation")
        ctx["foundation_output"] = foundation_dir
        ctx["discovery_graph_path"] = f"{foundation_dir}/discovery.graph.json"
        ctx["symbolic_batches_path"] = f"{foundation_dir}/symbolic-batches.json"
        ctx["symbol_registry_path"] = f"{foundation_dir}/symbol-registry.json"
        ctx["migration_order_path"] = f"{foundation_dir}/migration-order.json"
        ctx["foundation_summary_path"] = f"{foundation_dir}/foundation-summary.json"
    elif phase_name == "domain_discovery":
        foundation_dir = phase_output_dir(sd, "foundation")
        module_dir = phase_output_dir(sd, "module_discovery")
        ctx["foundation_output"] = foundation_dir
        ctx["module_discovery_output"] = module_dir
        ctx["discovery_graph_path"] = f"{foundation_dir}/discovery.graph.json"
        ctx["symbolic_batches_path"] = f"{foundation_dir}/symbolic-batches.json"
        ctx["symbol_registry_path"] = f"{foundation_dir}/symbol-registry.json"
        ctx["migration_order_path"] = f"{foundation_dir}/migration-order.json"
        ctx["module_discovery_path"] = f"{module_dir}/module-discovery.json"
    elif phase_name == "conflict_resolution":
        foundation_dir = phase_output_dir(sd, "foundation")
        domain_discovery_dir = phase_output_dir(sd, "domain_discovery")
        ctx["foundation_output"] = foundation_dir
        ctx["domain_discovery_output"] = domain_discovery_dir
        ctx["symbol_registry_path"] = f"{foundation_dir}/symbol-registry.json"
        ctx["domain_discovery_overview_path"] = f"{domain_discovery_dir}/domain-discovery-overview.json"
    elif phase_name == "domain_planning":
        foundation_dir = phase_output_dir(sd, "foundation")
        domain_discovery_dir = phase_output_dir(sd, "domain_discovery")
        conflict_dir = phase_output_dir(sd, "conflict_resolution")
        ctx["foundation_output"] = foundation_dir
        ctx["domain_discovery_output"] = domain_discovery_dir
        ctx["conflict_resolution_output"] = conflict_dir
        ctx["discovery_graph_path"] = f"{foundation_dir}/discovery.graph.json"
        ctx["migration_order_path"] = f"{foundation_dir}/migration-order.json"
        ctx["domain_discovery_overview_path"] = f"{domain_discovery_dir}/domain-discovery-overview.json"
        ctx["conflict_resolution_path"] = f"{conflict_dir}/conflict-resolution.json"
    elif phase_name == "domain_execution":
        domain_planning_dir = phase_output_dir(sd, "domain_planning")
        ctx["domain_planning_output"] = domain_planning_dir
        ctx["domain_plan_overview_path"] = f"{domain_planning_dir}/domain-plan-overview.json"
    elif phase_name == "rewiring":
        domain_planning_dir = phase_output_dir(sd, "domain_planning")
        domain_execution_dir = phase_output_dir(sd, "domain_execution")
        ctx["domain_planning_output"] = domain_planning_dir
        ctx["domain_execution_output"] = domain_execution_dir
        ctx["domain_plan_overview_path"] = f"{domain_planning_dir}/domain-plan-overview.json"
        ctx["domain_execution_overview_path"] = f"{domain_execution_dir}/domain-execution-overview.json"
    elif phase_name == "integration_review":
        domain_execution_dir = phase_output_dir(sd, "domain_execution")
        rewiring_dir = phase_output_dir(sd, "rewiring")
        ctx["domain_execution_output"] = domain_execution_dir
        ctx["rewiring_output"] = rewiring_dir
        ctx["domain_execution_overview_path"] = f"{domain_execution_dir}/domain-execution-overview.json"
        ctx["rewiring_summary_path"] = f"{rewiring_dir}/rewiring-summary.json"
        ctx["parity_results_path"] = f"{output_dir}/parity-results.json"
        ctx["diff_scorer_script"] = str(FRAMEWORK_DIR / "scripts" / "diff_scorer.py")

    return ctx


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase runner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def should_run_reiterate(manifest_path: str) -> bool:
    """Check if reiterate phase is needed based on review results."""
    sd = get_summaries_dir(manifest_path)
    review_results_path = f"{sd}/review/review-results.json"
    if not os.path.exists(review_results_path):
        return False
    try:
        with open(review_results_path) as f:
            results = json.load(f)
        failed = results.get("routing", {}).get("fail", [])
        return len(failed) > 0
    except (json.JSONDecodeError, KeyError):
        return False


def tier2_agents_paths(sd: str) -> list[str]:
    overview_path = Path(phase_output_dir(sd, "domain_planning")) / "domain-plan-overview.json"
    if not overview_path.exists():
        return []
    try:
        overview = json.loads(overview_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    agents_paths: list[str] = []
    for domain in overview.get("domains", []):
        if not isinstance(domain, dict):
            continue
        agents_path = domain.get("agentsPath")
        if isinstance(agents_path, str) and agents_path:
            agents_paths.append(agents_path)
    return agents_paths


def validate_phase_artifacts(manifest_path: str, phase_name: str, output_dir: str) -> dict:
    validator_cmd = [
        sys.executable,
        str(ARTIFACT_VALIDATOR),
        phase_name,
        output_dir,
    ]
    result = subprocess.run(validator_cmd, capture_output=True, text=True)
    report = {
        "phase": phase_name,
        "validator": str(ARTIFACT_VALIDATOR),
        "command": validator_cmd,
        "passed": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "requiredArtifacts": VALIDATION_REPORTS.get(phase_name, []),
    }
    mf.update_phase_artifacts(manifest_path, phase_name, report)
    return report


def collect_phase_artifacts(phase_name: str, output_dir: str) -> dict:
    output_path = Path(output_dir)
    artifacts: dict[str, object] = {
        "outputDir": str(output_path),
        "successMarker": str(output_path / PHASE_CONFIG_BY_NAME[phase_name]["success_marker"]),
    }

    if phase_name == "execution":
        batch_results = sorted(
            path.name for path in output_path.glob("batch-*-results.json") if path.is_file()
        )
        artifacts["batchResults"] = batch_results
        artifacts["executionSummary"] = str(output_path / "execution-summary.json")
    elif phase_name == "discovery":
        artifacts["depGraph"] = str(output_path / "dep-graph.json")
        artifacts["fileManifest"] = str(output_path / "file-manifest.json")
        artifacts["symbolIndex"] = str(output_path / "symbol-index.json")
        artifacts["dynamicRiskReport"] = str(output_path / "dynamic-risk-report.json")
        artifacts["dependencyShardsDir"] = str(output_path / "dependency-shards")
    elif phase_name == "planning":
        artifacts["planningInput"] = str(output_path / "planning-input.json")
        artifacts["riskPolicy"] = str(output_path / "risk-policy.json")
        artifacts["planningOverview"] = str(output_path / "planning-overview.json")
        artifacts["batches"] = str(output_path / "migration-batches.json")
        artifacts["agentsRules"] = str(output_path / "AGENTS.md")
    elif phase_name == "review":
        artifacts["reviewResults"] = str(output_path / "review-results.json")
        artifacts["validationReport"] = str(output_path / "validation-report.json")
        artifacts["parityResults"] = str(output_path / "parity-results.json")
    elif phase_name == "reiterate":
        artifacts["reiterateResults"] = str(output_path / "reiterate-results.json")
        artifacts["agentsMdPatchProposal"] = str(output_path / "agents-md.patch.json")
        artifacts["agentsMdPatchSummary"] = str(output_path / "agents-md-patches.md")
    elif phase_name == "foundation":
        artifacts["foundationSummary"] = str(output_path / "foundation-summary.json")
        artifacts["discoveryGraph"] = str(output_path / "discovery.graph.json")
        artifacts["symbolicBatches"] = str(output_path / "symbolic-batches.json")
        artifacts["symbolRegistry"] = str(output_path / "symbol-registry.json")
        artifacts["migrationOrder"] = str(output_path / "migration-order.json")
    elif phase_name == "module_discovery":
        artifacts["moduleDiscovery"] = str(output_path / "module-discovery.json")
    elif phase_name == "domain_discovery":
        artifacts["domainDiscoveryOverview"] = str(output_path / "domain-discovery-overview.json")
        artifacts["domains"] = collect_overview_domain_artifacts(output_path / "domain-discovery-overview.json")
    elif phase_name == "conflict_resolution":
        artifacts["conflictResolution"] = str(output_path / "conflict-resolution.json")
    elif phase_name == "domain_planning":
        artifacts["domainPlanOverview"] = str(output_path / "domain-plan-overview.json")
        artifacts["domains"] = collect_overview_domain_artifacts(output_path / "domain-plan-overview.json")
    elif phase_name == "domain_execution":
        artifacts["domainExecutionOverview"] = str(output_path / "domain-execution-overview.json")
        artifacts["domains"] = collect_overview_domain_artifacts(output_path / "domain-execution-overview.json")
    elif phase_name == "rewiring":
        artifacts["rewiringSummary"] = str(output_path / "rewiring-summary.json")
        artifacts["rewiringBatches"] = str(output_path / "rewiring-batches.json")
    elif phase_name == "integration_review":
        artifacts["integrationReview"] = str(output_path / "integration-review.json")
        artifacts["parityResults"] = str(output_path / "parity-results.json")

    return artifacts


def run_phase(manifest_path: str, phase_config: dict,
              runtime: str = None, model: str = None,
              skip_approval: bool = False,
              non_interactive: bool = False,
              attempt: int = 1,
              fast_mode: bool = False) -> bool:
    """
    Run a single migration phase:
      1. Create output directory
      2. Update manifest → in_progress
      3. Spawn agent subprocess
      4. Poll for completion
      5. Handle success/failure
      6. Approval gate (if required)
      7. Update manifest → done
      8. Git checkpoint
    
    Returns True if phase completed successfully, False otherwise.
    """
    phase_name = phase_config["name"]
    skill_file = phase_config["skill"]
    success_marker = phase_config["success_marker"]
    needs_approval = phase_config["needs_approval"]

    # Special case: skip reiterate if review passed everything
    manifest_data = mf.load(manifest_path)
    maybe_update_phase_index(manifest_data)
    if phase_name == "reiterate" and should_skip_reiterate(manifest_path, manifest_data):
        print(f"\n  → {phase_name}: no failures to reiterate, skipping")
        mf.update_phase(manifest_path, phase_name, "done",
                        extra={"skipped": True, "reason": "no failures in review"})
        update_issue_ledger_state(manifest_path, status="in_progress", phase=phase_name, attempt=attempt)
        append_issue_ledger_event(
            manifest_path,
            "phase_skipped",
            f"{phase_name} skipped because review found no failures.",
            phase=phase_name,
            attempt=attempt,
        )
        return True

    phase_header(phase_name)
    log_event(manifest_path, f"phase={phase_name} status=starting")
    ensure_phase_issue_report(manifest_path, phase_name)
    update_issue_ledger_state(manifest_path, status="in_progress", phase=phase_name, attempt=attempt)
    append_issue_ledger_event(
        manifest_path,
        "phase_started",
        f"{phase_name} started.",
        phase=phase_name,
        attempt=attempt,
        evidence=[str(get_phase_issue_report_path(manifest_path, phase_name))],
    )

    sd = get_summaries_dir(manifest_path)
    output_dir = phase_output_dir(sd, phase_name)
    os.makedirs(output_dir, exist_ok=True)
    if not ensure_phase_supported_before_run(manifest_path, phase_config):
        return False

    context = build_context(manifest_path, phase_name)
    if phase_name not in {"discovery", "foundation", "module_discovery"} and context.get("recipe_required_error"):
        error_msg = context["recipe_required_error"]
        log_and_print(manifest_path, f"  ✗ {phase_name} requires a recipe: {error_msg}")
        return mark_phase_failure(
            manifest_path,
            phase_name,
            error_msg,
            attempt=attempt,
            evidence=[context.get("issue_ledger_path"), context.get("phase_issue_report_path")],
        )

    success_path = os.path.join(output_dir, success_marker)
    error_path = os.path.join(output_dir, "ERROR")
    stale_paths = [success_path, error_path]
    for marker in SUCCESS_MARKERS.get(phase_name, []):
        marker_path = os.path.join(output_dir, marker)
        if marker_path not in stale_paths:
            stale_paths.append(marker_path)
    for stale_path in stale_paths:
        if os.path.exists(stale_path):
            os.remove(stale_path)

    if phase_name == "foundation":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 foundation artifacts",
            FOUNDATION_BUILDER,
            [context["source_path"], output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir],
            )
    if phase_name == "discovery":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic discovery artifacts",
            DISCOVERY_BUILDER,
            [context["source_path"], output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir],
            )
    if phase_name == "planning":
        discovery_dir = str(Path(sd) / "discovery")
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic planning inputs",
            PLANNING_BUILDER,
            [discovery_dir, output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, discovery_dir],
            )
    if phase_name == "module_discovery":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 module discovery artifacts",
            TIER2_MODULE_DISCOVERY_BUILDER,
            [phase_output_dir(sd, "foundation"), output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, phase_output_dir(sd, "foundation")],
            )
    if phase_name == "domain_discovery":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 domain discovery artifacts",
            TIER2_DOMAIN_DISCOVERY_BUILDER,
            [manifest_path, output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, manifest_path],
            )
    if phase_name == "conflict_resolution":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 conflict resolution artifacts",
            TIER2_CONFLICT_RESOLUTION_BUILDER,
            [manifest_path, output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, manifest_path],
            )
    if phase_name == "domain_planning":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 domain planning artifacts",
            TIER2_DOMAIN_PLANNING_BUILDER,
            [manifest_path, output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, manifest_path],
            )
    if phase_name == "domain_execution":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 domain execution artifacts",
            TIER2_DOMAIN_EXECUTION_BUILDER,
            [manifest_path, output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, manifest_path],
            )
    if phase_name == "rewiring":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 rewiring artifacts",
            TIER2_REWIRING_BUILDER,
            [manifest_path, output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, manifest_path],
            )
    if phase_name in {"review", "integration_review"} and RECIPE_VERIFY_RUNNER.exists():
        log_and_print(manifest_path, "  → Running deterministic recipe parity checks...")
        try:
            parity_report = run_recipe_verify_if_available(manifest_path, context, output_dir)
            log_and_print(
                manifest_path,
                f"    Parity status: {parity_report.get('status', 'unknown')} | hooks={parity_report.get('summary', {}).get('total', 0)}",
            )
        except RuntimeError as exc:
            error_msg = str(exc)
            log_and_print(manifest_path, f"  ✗ deterministic recipe verification failed: {error_msg}")
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir],
            )
    if phase_name == "integration_review":
        ok, error_msg = run_python_builder(
            manifest_path,
            "Building deterministic Tier 2 integration review checks",
            TIER2_INTEGRATION_CHECKER,
            [manifest_path, output_dir],
        )
        if not ok:
            return mark_phase_failure(
                manifest_path,
                phase_name,
                error_msg,
                attempt=attempt,
                evidence=[output_dir, manifest_path],
            )

    # ── 1. Update manifest: starting ──
    manifest_data = mf.update_phase(manifest_path, phase_name, "in_progress")
    log_and_print(manifest_path, f"  [manifest] {phase_name} → in_progress")
    log_progress(manifest_path, manifest_data=manifest_data)
    append_issue_ledger_event(
        manifest_path,
        "phase_manifest_in_progress",
        f"{phase_name} marked in_progress in the manifest.",
        phase=phase_name,
        attempt=attempt,
        evidence=[manifest_path],
    )

    # ── 1a. Fast mode short-circuit ──
    # Prebuilders already wrote valid artifacts. If --fast and markers present
    # and validation passes, skip the codex refinement agent entirely.
    if fast_mode and phase_name in FAST_MODE_SKIPPABLE_PHASES:
        fast_markers_ok = all(
            os.path.exists(os.path.join(output_dir, marker))
            for marker in SUCCESS_MARKERS.get(phase_name, [success_marker])
        )
        if fast_markers_ok:
            fast_validation = validate_phase_artifacts(manifest_path, phase_name, output_dir)
            if fast_validation["passed"]:
                log_and_print(
                    manifest_path,
                    f"  ⚡ fast mode: prebuilt artifacts valid — skipping codex agent for {phase_name}",
                )
                phase_artifacts = collect_phase_artifacts(phase_name, output_dir)
                phase_artifacts["validation"] = fast_validation
                phase_artifacts["fastMode"] = True
                mf.update_phase_artifacts(manifest_path, phase_name, phase_artifacts)
                success_path = os.path.join(
                    output_dir,
                    SUCCESS_MARKERS.get(phase_name, [success_marker])[0],
                )
                append_issue_ledger_event(
                    manifest_path,
                    "phase_fast_skip",
                    f"{phase_name} completed via fast mode (agent skipped).",
                    phase=phase_name,
                    attempt=attempt,
                    evidence=[success_path],
                )
                # In fast mode, skip approval gates for deterministic phases.
                manifest_data = mf.update_phase(manifest_path, phase_name, "done")
                log_progress(manifest_path, manifest_data=manifest_data)
                git_checkpoint(manifest_path, phase_name)
                return True

    # ── 2. Build context for this phase ──
    context["allowed_tools"] = phase_config.get("allowed_tools", "Read,Write,Edit,Bash,Glob,Grep")
    context["phase_attempt"] = str(attempt)
    context["max_phase_retries"] = str(MAX_RETRIES)

    # ── 3. Resolve skill file path ──
    resolved_skill_path = resolve_skill_path(skill_file)
    if resolved_skill_path is None:
        skill_path = str(FRAMEWORK_DIR / "skills" / skill_file)
        print(f"  ✗ Skill file not found: {skill_path}")
        return mark_phase_failure(
            manifest_path,
            phase_name,
            f"Skill file not found: {skill_path}",
            attempt=attempt,
            evidence=[skill_path],
        )
    skill_path = str(resolved_skill_path)

    # ── 4. Spawn the agent ──
    log_and_print(manifest_path, f"  → Spawning {phase_name} agent...")
    log_and_print(manifest_path, f"    Skill:   {skill_path}")
    log_and_print(manifest_path, f"    Output:  {output_dir}")
    log_and_print(manifest_path, f"    Runtime: {runtime or 'auto-detect'}")
    agent_timeout = get_agent_timeout_seconds(phase_name)
    log_and_print(manifest_path, f"    Timeout: {agent_timeout}s")

    def _heartbeat_callback(elapsed_seconds: int):
        message = f"{phase_name} agent still running after {elapsed_seconds}s."
        log_and_print(manifest_path, f"    [heartbeat] {message}")
        log_progress(manifest_path, prefix="    [progress] ")
        append_issue_ledger_event(
            manifest_path,
            "phase_heartbeat",
            message,
            phase=phase_name,
            attempt=attempt,
            evidence=[skill_path, output_dir],
        )

    result = spawn_agent(
        skill_path=skill_path,
        context=context,
        runtime=runtime,
        model=model,
        timeout=agent_timeout,
        on_heartbeat=_heartbeat_callback,
    )

    log_and_print(manifest_path, f"    Exit code: {result['exit_code']}")
    log_and_print(manifest_path, f"    Runtime used: {result['runtime']}")
    if result.get("stdout"):
        stdout_text = result["stdout"].rstrip()
        print(stdout_text)
        log_event(manifest_path, f"agent_stdout:\n{stdout_text}")
    if result.get("stderr"):
        stderr_text = result["stderr"].rstrip()
        print(stderr_text, file=sys.stderr)
        log_event(manifest_path, f"agent_stderr:\n{stderr_text}")

    # ── 5. Check for output ──
    # The agent may have written files even if exit code is non-zero.
    # Check the filesystem for the definitive success marker.
    markers_complete = all(
        os.path.exists(os.path.join(output_dir, marker))
        for marker in SUCCESS_MARKERS.get(phase_name, [success_marker])
    )

    if os.path.exists(error_path):
        status = "failure"
    elif result["exit_code"] != 0 and (phase_name in PREBUILT_SUCCESS_PHASES or not markers_complete):
        # Agent crashed without writing ERROR file — create one
        with open(error_path, 'w') as f:
            f.write(f"Agent exited with code {result['exit_code']}\n")
            if result["stderr"]:
                f.write(f"\nStderr:\n{result['stderr'][-2000:]}\n")
        status = "failure"
    elif markers_complete:
        status = "success"
    else:
        # Agent exited 0 but expected artifacts may still be flushing.
        log_and_print(manifest_path, f"  → Agent exited but expected artifacts are incomplete. Polling briefly...")
        poll_result = poll_for_completion(
            output_dir, SUCCESS_MARKERS.get(phase_name, [success_marker]),
            timeout=60, interval=5
        )
        status = poll_result  # 'success', 'failure', or 'timeout'

    if status == "success":
        validation = validate_phase_artifacts(manifest_path, phase_name, output_dir)
        if not validation["passed"]:
            error_msg = validation["stderr"] or validation["stdout"] or "artifact validation failed"
            with open(error_path, 'w') as f:
                f.write(error_msg + "\n")
            status = "failure"
        else:
            phase_artifacts = collect_phase_artifacts(phase_name, output_dir)
            phase_artifacts["validation"] = validation
            mf.update_phase_artifacts(manifest_path, phase_name, phase_artifacts)

            if phase_name == "execution" and phase_artifacts.get("batchResults"):
                planning_overview_path = Path(sd) / "planning" / "planning-overview.json"
                if planning_overview_path.exists():
                    try:
                        planning_overview = json.loads(planning_overview_path.read_text())
                        planning_overview["executionWorkers"] = {
                            "configuredMax": MAX_BATCH_WORKERS,
                            "mode": "sequential-agent-batches",
                        }
                        planning_overview_path.write_text(json.dumps(planning_overview, indent=2) + "\n", encoding="utf-8")
                    except json.JSONDecodeError:
                        pass
            if phase_name == "domain_execution":
                overview_path = Path(output_dir) / "domain-execution-overview.json"
                if overview_path.exists():
                    try:
                        overview = json.loads(overview_path.read_text())
                        overview["executionWorkers"] = {
                            "configuredMax": MAX_BATCH_WORKERS,
                            "mode": "sequential-domain-workers",
                        }
                        overview_path.write_text(json.dumps(overview, indent=2) + "\n", encoding="utf-8")
                    except json.JSONDecodeError:
                        pass

            success_path = str(Path(output_dir) / SUCCESS_MARKERS.get(phase_name, [success_marker])[0])

    manifest_artifacts = mf.load(manifest_path).get("phases", {}).get(phase_name, {}).get("artifacts", {})
    if manifest_artifacts.get("successMarker"):
        success_path = manifest_artifacts["successMarker"]
    elif manifest_artifacts.get("outputDir"):
        success_path = str(Path(manifest_artifacts["outputDir"]) / success_marker)

    validation = manifest_artifacts.get("validation", {})
    validation_error = validation.get("stderr") or validation.get("stdout")

    if status == "failure" and validation_error and not os.path.exists(error_path):
        with open(error_path, 'w') as f:
            f.write(validation_error + "\n")

    # ── 6. Handle result ──

    if status == "success":
        log_and_print(manifest_path, f"  ✓ {phase_name} agent completed successfully")
        log_and_print(manifest_path, f"    Output: {success_path}")
        append_issue_ledger_event(
            manifest_path,
            "phase_agent_success",
            f"{phase_name} completed successfully.",
            phase=phase_name,
            attempt=attempt,
            evidence=[success_path],
        )
    else:
        # Read error details
        error_msg = "(no error details)"
        if os.path.exists(error_path):
            with open(error_path) as f:
                error_msg = f.read().strip()[:500]

        log_and_print(manifest_path, f"  ✗ {phase_name} agent failed")
        log_and_print(manifest_path, f"    Error: {error_msg}")
        return mark_phase_failure(
            manifest_path,
            phase_name,
            error_msg,
            attempt=attempt,
            evidence=[error_path, context.get("phase_issue_report_path")],
        )

    # ── 7. Approval gate ──
    if needs_approval:
        manifest_data = mf.update_phase(manifest_path, phase_name, "awaiting_approval")
        update_issue_ledger_state(manifest_path, status="awaiting_approval", phase=phase_name, attempt=attempt)
        log_progress(manifest_path, manifest_data=manifest_data)
        append_issue_ledger_event(
            manifest_path,
            "approval_required",
            f"{phase_name} is awaiting approval.",
            phase=phase_name,
            attempt=attempt,
            evidence=[success_path],
        )
        approval_status = request_approval(
            phase_name,
            success_path,
            skip_approval=skip_approval,
            non_interactive=non_interactive,
        )

        if approval_status == "deferred":
            log_and_print(manifest_path, f"\n  ⏸ {phase_name} awaiting approval")
            append_issue_ledger_event(
                manifest_path,
                "approval_deferred",
                f"{phase_name} approval deferred.",
                phase=phase_name,
                attempt=attempt,
                evidence=[success_path],
            )
            return True

        if approval_status == "aborted":
            log_and_print(manifest_path, f"\n  ✗ {phase_name} rejected by user")
            record_issue(
                manifest_path,
                category="approval_rejected",
                summary=f"{phase_name} rejected at approval gate",
                details="Rejected by user at approval gate",
                phase=phase_name,
                attempt=attempt,
                evidence=[success_path],
                status="open",
            )
            append_issue_ledger_event(
                manifest_path,
                "approval_rejected",
                f"{phase_name} rejected at approval gate.",
                phase=phase_name,
                attempt=attempt,
                evidence=[success_path],
            )
            update_issue_ledger_state(manifest_path, status="failed", phase=phase_name, attempt=attempt)
            mf.update_phase(manifest_path, phase_name, "failed",
                            extra={"error": "Rejected by user at approval gate"})
            return False

        if phase_name == "reiterate":
            patch_result = apply_reiterate_patch_if_present(manifest_path, output_dir)
            if patch_result.get("applied"):
                phase_artifacts = mf.load(manifest_path).get("phases", {}).get(phase_name, {}).get("artifacts", {})
                phase_artifacts["agentsMdAppliedPatch"] = patch_result
                mf.update_phase_artifacts(manifest_path, phase_name, phase_artifacts)

        mf.update_phase(manifest_path, phase_name, "approved")
        manifest_data = mf.update_phase(manifest_path, phase_name, "done")
        update_issue_ledger_state(manifest_path, status="in_progress", phase=phase_name, attempt=attempt)
        append_issue_ledger_event(
            manifest_path,
            "phase_approved",
            f"{phase_name} approved and marked done.",
            phase=phase_name,
            attempt=attempt,
            evidence=[success_path],
        )
        log_and_print(manifest_path, f"  [manifest] {phase_name} → done")
        log_progress(manifest_path, manifest_data=manifest_data)
        git_checkpoint(manifest_path, phase_name)
        return True

    manifest_data = mf.update_phase(manifest_path, phase_name, "done")
    update_issue_ledger_state(manifest_path, status="in_progress", phase=phase_name, attempt=attempt)
    append_issue_ledger_event(
        manifest_path,
        "phase_done",
        f"{phase_name} marked done.",
        phase=phase_name,
        attempt=attempt,
        evidence=[success_path],
    )
    log_and_print(manifest_path, f"  [manifest] {phase_name} → done")
    log_progress(manifest_path, manifest_data=manifest_data)

    git_checkpoint(manifest_path, phase_name)

    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    parser = argparse.ArgumentParser(
        description="Migration Orchestrator — deterministic state machine"
    )
    parser.add_argument(
        "manifest", nargs="?", default="migration-manifest.json",
        help="Path to migration-manifest.json"
    )
    parser.add_argument(
        "--runtime", choices=["claude-code", "codex", "cursor"],
        help="Override auto-detected runtime"
    )
    parser.add_argument(
        "--model", help="Override model (e.g., claude-sonnet-4-20250514, gpt-4.1)"
    )
    parser.add_argument(
        "--skip-approval", action="store_true",
        help="Skip approval gates (for CI/testing only — NOT for real migrations)"
    )
    parser.add_argument(
        "--phase", help="Run only a specific phase (e.g., 'discovery')"
    )
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="Stop cleanly at approval gates without waiting for stdin"
    )
    parser.add_argument(
        "--approve", choices=APPROVAL_PHASES,
        help="Mark a phase awaiting approval as approved, then continue"
    )
    parser.add_argument(
        "--restart-phase", choices=APPROVAL_PHASES,
        help="Reset the named phase and everything after it back to pending, then continue from there"
    )
    parser.add_argument(
        "--fast", action="store_true", default=FAST_MODE_DEFAULT,
        help="Fast mode: skip codex refinement when deterministic prebuilders produce valid artifacts"
    )
    parser.add_argument(
        "--agent-timeout", type=int, default=None,
        help="Override per-agent timeout in seconds (applies to all phases; fast mode still honors phase defaults)"
    )
    parser.add_argument(
        "--parallel-domains", type=int, default=None,
        help="Max concurrent domain workers during domain_execution (default: 4)"
    )
    args = parser.parse_args()

    if args.agent_timeout and args.agent_timeout > 0:
        os.environ["MIGRATION_TIMEOUT"] = str(args.agent_timeout)
    if args.parallel_domains and args.parallel_domains > 0:
        os.environ["MIGRATION_PARALLEL_DOMAINS"] = str(args.parallel_domains)

    manifest_path = args.manifest
    if args.approve and args.restart_phase:
        print("Error: --approve and --restart-phase cannot be used together.")
        sys.exit(1)

    # ── Validate manifest ──
    if not os.path.exists(manifest_path):
        print(f"Error: manifest not found: {manifest_path}")
        print(f"Run /migrate first, or create the manifest manually.")
        sys.exit(1)

    os.environ["MIGRATION_MANIFEST_PATH"] = manifest_path
    manifest_data = mf.load(manifest_path)
    initialize_run_control(manifest_path, manifest_data)
    manifest_data, phase_repair = reconcile_manifest_phase_set(manifest_path)
    if phase_repair:
        repair_summary = (
            f"Manifest phase set repaired. Missing={phase_repair['missing']} "
            f"Unexpected={phase_repair['unexpected']}"
        )
        log_event(manifest_path, repair_summary)
        append_issue_ledger_event(
            manifest_path,
            "manifest_phase_repaired",
            repair_summary,
            evidence=[manifest_path],
        )
        record_issue(
            manifest_path,
            category="manifest_phase_alignment",
            summary="Manifest phase set was repaired to match the selected framework.",
            details=repair_summary,
            evidence=[manifest_path],
            status="resolved",
        )
        manifest_data = mf.load(manifest_path)

    maybe_update_phase_index(manifest_data)
    maybe_raise_manifest_alignment(manifest_data)
    log_event(manifest_path, f"orchestrator_start manifest={manifest_path} runtime={args.runtime or 'auto-detect'} non_interactive={args.non_interactive} approve={args.approve or ''}")
    append_issue_ledger_event(
        manifest_path,
        "run_started",
        f"Orchestrator started with runtime={args.runtime or 'auto-detect'} non_interactive={args.non_interactive}.",
        evidence=[manifest_path, str(get_issue_ledger_paths(manifest_path)[0])],
    )
    update_issue_ledger_state(
        manifest_path,
        status=manifest_data.get("meta", {}).get("status", "pending"),
    )

    # ── Print banner ──
    meta = manifest_data["meta"]
    banner("MIGRATION ORCHESTRATOR")
    print(f"  Session:  {meta.get('sessionId', 'unknown')}")
    print(f"  Source:   {meta.get('sourceDescription', meta.get('sourcePath', '?'))}")
    print(f"  Target:   {meta.get('targetDescription', meta.get('targetPath', '?'))}")
    print(f"  Tier:     {meta.get('tier', 'medium')}")
    print(f"  Runtime:  {args.runtime or 'auto-detect'}")
    if args.fast:
        print(f"  Mode:     ⚡ FAST (codex refinement skipped for deterministic phases)")
    if meta.get("nonNegotiables"):
        print(f"  Rules:    {len(meta['nonNegotiables'])} non-negotiables")
    print(render_progress_line(manifest_data))
    print()
    print(render_status_banner(manifest_data))
    print()

    phase_set = get_phase_set(manifest_data)
    phase_names = [phase["name"] for phase in phase_set]

    if args.restart_phase:
        if args.restart_phase not in phase_names:
            print(f"Error: phase '{args.restart_phase}' is not valid for framework {meta.get('frameworkVersion', 'tier-1')}.")
            print(f"Available: {phase_names}")
            sys.exit(1)
        manifest_data = restart_from_phase(manifest_path, manifest_data, args.restart_phase)
        append_issue_ledger_event(
            manifest_path,
            "phase_restart_requested",
            f"Restart requested from {args.restart_phase}.",
            phase=args.restart_phase,
            evidence=[manifest_path],
        )
        phase_set = get_phase_set(manifest_data)
        phase_names = [phase["name"] for phase in phase_set]
        restart_index = get_phase_resume_index(phase_set, args.restart_phase)
        phase_configs = phase_set[restart_index:]
    else:
        phase_configs = None

    if args.approve:
        if args.approve not in phase_names:
            print(f"Error: phase '{args.approve}' is not valid for framework {meta.get('frameworkVersion', 'tier-1')}.")
            print(f"Available: {phase_names}")
            sys.exit(1)

        approved_index = get_phase_resume_index(phase_set, args.approve)

        for earlier_phase in phase_set[:approved_index]:
            earlier_name = earlier_phase["name"]
            earlier_status = manifest_data["phases"].get(earlier_name, {}).get("status", "pending")
            if earlier_status != "done":
                mf.update_phase(manifest_path, earlier_name, "done")

        if args.approve == "reiterate":
            reiterate_output_dir = Path(get_phase_output_dir_from_manifest(manifest_path, "reiterate"))
            patch_result = apply_reiterate_patch_if_present(manifest_path, str(reiterate_output_dir))
            if patch_result.get("applied"):
                phase_artifacts = manifest_data.get("phases", {}).get("reiterate", {}).get("artifacts", {})
                phase_artifacts["agentsMdAppliedPatch"] = patch_result
                mf.update_phase_artifacts(manifest_path, "reiterate", phase_artifacts)

        mf.update_phase(manifest_path, args.approve, "approved")
        mf.update_phase(manifest_path, args.approve, "done")
        append_issue_ledger_event(
            manifest_path,
            "approval_applied",
            f"{args.approve} approved from CLI resume.",
            phase=args.approve,
            evidence=[manifest_path],
        )

        manifest_data = mf.load(manifest_path)
        phase_set = get_phase_set(manifest_data)

        for later_phase in phase_set[approved_index + 1:]:
            later_name = later_phase["name"]
            later_status = manifest_data["phases"].get(later_name, {}).get("status", "pending")
            if later_status == "awaiting_approval":
                break
            if later_status in {"in_progress", "approved", "failed"}:
                mf.update_phase(manifest_path, later_name, "pending")

        print(f"Approved phase: {args.approve}")
        print(render_progress_line(mf.load(manifest_path)))
        manifest_data = mf.load(manifest_path)
        phase_set = get_phase_set(manifest_data)
        phase_configs = phase_set[approved_index + 1:]

    # ── Determine which phases to run ──
    if phase_configs is None:
        if args.phase:
            phase_configs = [p for p in phase_set if p["name"] == args.phase]
            if not phase_configs:
                print(f"Error: unknown phase '{args.phase}'. "
                      f"Available: {[p['name'] for p in phase_set]}")
                sys.exit(1)
        else:
            phase_configs = phase_set

    if not phase_configs:
        banner("MIGRATION COMPLETE", char="✓")
        print(render_progress_line(mf.load(manifest_path)))
        print("\n  No remaining phases to run.\n")
        append_issue_ledger_event(
            manifest_path,
            "run_noop",
            "No remaining phases to run.",
            evidence=[manifest_path],
        )
        sys.exit(0)

    # ── Run phases ──
    # Fast mode also drops `reiterate` entirely (prebuilders already write valid
    # artifacts — reiterate just re-reads them).
    if args.fast:
        fast_drop = {"reiterate"}
        original_count = len(phase_configs)
        phase_configs = [p for p in phase_configs if p["name"] not in fast_drop]
        dropped = original_count - len(phase_configs)
        if dropped:
            print(f"  ⚡ fast mode: skipping {dropped} redundant phase(s): {sorted(fast_drop)}")
            for dropped_name in fast_drop:
                if dropped_name in {p["name"] for p in phase_set}:
                    cur = mf.get_phase_status(manifest_path, dropped_name)
                    if cur != "done":
                        mf.update_phase(manifest_path, dropped_name, "done",
                                        extra={"skipped": True, "reason": "fast mode"})

    for phase_config in phase_configs:
        phase_name = phase_config["name"]

        # Check if already completed (for resume support)
        current_status = mf.get_phase_status(manifest_path, phase_name)
        if current_status == "done":
            print(f"\n  → {phase_name}: already done, skipping")
            append_issue_ledger_event(
                manifest_path,
                "phase_already_done",
                f"{phase_name} already done; skipped.",
                phase=phase_name,
                evidence=[manifest_path],
            )
            continue

        # Run the phase
        retries = 0
        success = False

        while retries <= MAX_RETRIES and not success:
            attempt = retries + 1
            if retries > 0:
                print(f"\n  → Retry {retries}/{MAX_RETRIES} for {phase_name}...")
                # Clean up error marker from previous attempt
                error_path = get_phase_retry_path(manifest_path, phase_name)
                if os.path.exists(error_path):
                    os.remove(error_path)
                append_issue_ledger_event(
                    manifest_path,
                    "phase_retry",
                    f"Retrying {phase_name}.",
                    phase=phase_name,
                    attempt=attempt,
                    evidence=[error_path, manifest_path],
                )
                update_issue_ledger_state(
                    manifest_path,
                    status="in_progress",
                    phase=phase_name,
                    attempt=attempt,
                )

            success = run_phase(
                manifest_path=manifest_path,
                phase_config=phase_config,
                runtime=args.runtime,
                model=args.model,
                skip_approval=args.skip_approval,
                non_interactive=args.non_interactive,
                attempt=attempt,
                fast_mode=args.fast,
            )

            if not success:
                retries += 1
                if retries <= MAX_RETRIES:
                    if args.non_interactive:
                        append_issue_ledger_event(
                            manifest_path,
                            "retry_skipped_non_interactive",
                            f"{phase_name} failed and non-interactive mode stopped further retries.",
                            phase=phase_name,
                            attempt=attempt,
                            evidence=[manifest_path],
                        )
                        break
                    try:
                        retry = input(f"\n  {phase_name} failed. Retry? [y/n] → ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        retry = "n"
                    if retry not in ("y", "yes"):
                        break

        current_status = mf.get_phase_status(manifest_path, phase_name)
        if current_status == "awaiting_approval":
            banner(f"MIGRATION PAUSED AT: {phase_name}", char="⏸")
            print(render_progress_line(mf.load(manifest_path)))
            print(f"\n  The migration is waiting for your review and approval.")
            print(f"  Summary: {get_summary_output_path(manifest_path, phase_config)}")
            print(f"  Approve and continue later with:")
            print(f"    python {__file__} {manifest_path} --approve {phase_name}")
            print()
            append_issue_ledger_event(
                manifest_path,
                "run_paused_for_approval",
                f"Run paused at {phase_name} awaiting approval.",
                phase=phase_name,
                evidence=[get_summary_output_path(manifest_path, phase_config)],
            )
            sys.exit(0)

        if not success:
            banner(f"MIGRATION STOPPED AT: {phase_name}", char="✗")
            print(render_progress_line(mf.load(manifest_path)))
            print(f"\n  The migration stopped at the {phase_name} phase.")
            print(f"  To resume, re-run: python {__file__} {manifest_path}")
            print(f"  Completed phases will be skipped automatically.\n")
            update_issue_ledger_state(manifest_path, status="failed", phase=phase_name, attempt=attempt)
            append_issue_ledger_event(
                manifest_path,
                "run_stopped",
                f"Run stopped at {phase_name}.",
                phase=phase_name,
                attempt=attempt,
                evidence=[manifest_path, str(get_issue_ledger_paths(manifest_path)[0])],
            )
            sys.exit(1)

    # ── All phases complete ──
    manifest_data = mf.load(manifest_path)
    sd = get_summaries_dir(manifest_path)
    ledger = load_issue_ledger(manifest_path, manifest_data)
    ledger["status"] = manifest_data.get("meta", {}).get("status", "complete")
    ledger["currentPhase"] = None
    ledger["currentAttempt"] = None
    ledger["events"].append(
        {
            "timestamp": utc_timestamp(),
            "type": "run_complete",
            "phase": None,
            "attempt": None,
            "message": "All phases completed successfully.",
            "evidence": [manifest_path],
        }
    )
    save_issue_ledger(manifest_path, ledger)
    banner("MIGRATION COMPLETE", char="✓")
    print(render_progress_line(manifest_data))
    print()
    print(render_status_banner(manifest_data))
    print(f"\n  All phases completed successfully.")
    print(f"  Review the final state:")
    print(f"    Manifest:  {manifest_path}")
    for path in get_default_complete_paths(sd, manifest_data):
        print(f"    Output:    {path}")
    print(f"    Ledger:    {get_issue_ledger_paths(manifest_path)[0]}")
    print()


if __name__ == "__main__":
    main()

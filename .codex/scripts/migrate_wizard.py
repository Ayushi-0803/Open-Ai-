#!/usr/bin/env python3
"""
Interactive migration setup wizard.

This script collects migration intent in a terminal-friendly flow, writes a
manifest, creates the summary directory structure, and can optionally launch
the orchestrator. The non-negotiables step is backed by repo style guides so
users can choose prewritten style/naming guidance instead of typing everything
free-form.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex
from typing import Callable

import manifest as mf


SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_DIR = SCRIPT_PATH.parent
FRAMEWORK_DIR = SCRIPTS_DIR.parent
REPO_ROOT = FRAMEWORK_DIR.parent
STYLEGUIDE_DIR = REPO_ROOT / "styleguide"
RECIPE_DIR = FRAMEWORK_DIR / "recipes"
ORCHESTRATOR_PATH = FRAMEWORK_DIR / "scripts" / "orchestrator.py"
RECIPE_MANIFEST_NAMES = ("recipe.yaml", "recipe.yml", "recipe.json")

TIER1_PHASES = ["discovery", "planning", "execution", "review", "reiterate"]
TIER2_PHASES = [
    "foundation",
    "module_discovery",
    "domain_discovery",
    "conflict_resolution",
    "domain_planning",
    "domain_execution",
    "rewiring",
    "integration_review",
    "reiterate",
]

PHASE_DIR_NAMES = {
    "module_discovery": "module-discovery",
    "domain_discovery": "domain-discovery",
    "conflict_resolution": "conflict-resolution",
    "domain_planning": "domain-planning",
    "domain_execution": "domain-execution",
    "integration_review": "integration-review",
}

LANGUAGE_TOKENS = (
    "python",
    "typescript",
    "javascript",
    "rust",
    "go",
    "java",
    "kotlin",
    "swift",
    "ruby",
    "php",
    "c#",
    "c++",
)


@dataclass(frozen=True)
class StyleGuideOption:
    language: str
    title: str
    style_path: str
    naming_path: str | None
    naming_preview: list[str]


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def read_first_heading(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
    except FileNotFoundError:
        return ""
    return ""


def extract_markdown_bullets(path: Path, heading_terms: tuple[str, ...]) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []

    normalized_terms = tuple(term.lower() for term in heading_terms)
    items: list[str] = []
    capture = False
    heading_level = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped[level:].strip().lower()
            if not capture and any(term in heading for term in normalized_terms):
                capture = True
                heading_level = level
                continue
            if capture and level <= heading_level:
                break
            continue
        if capture and re.match(r"^[-*]\s+", stripped):
            items.append(re.sub(r"^[-*]\s+", "", stripped))
    return items


def discover_style_guides(styleguide_root: Path = STYLEGUIDE_DIR) -> list[StyleGuideOption]:
    if not styleguide_root.exists():
        return []

    options: list[StyleGuideOption] = []
    for language_dir in sorted(path for path in styleguide_root.iterdir() if path.is_dir()):
        style_path = language_dir / "style.md"
        if not style_path.exists():
            continue

        title = read_first_heading(style_path) or f"{language_dir.name.title()} Style Guide"
        sections_dir = language_dir / "sections"
        naming_candidates = [
            sections_dir / "code-formatting-and-naming.md",
            *sorted(sections_dir.glob("*naming*.md")),
        ]
        naming_path = next((candidate for candidate in naming_candidates if candidate.exists()), None)
        naming_source = naming_path or style_path
        naming_preview = extract_markdown_bullets(
            naming_source,
            ("naming conventions", "naming and api shape"),
        )

        options.append(
            StyleGuideOption(
                language=language_dir.name,
                title=title,
                style_path=repo_relative(style_path),
                naming_path=repo_relative(naming_path) if naming_path else None,
                naming_preview=naming_preview[:4],
            )
        )
    return options


def format_sentence(text: str, prefix: str | None = None) -> str:
    value = text.strip()
    if prefix:
        value = f"{prefix}{value}"
    if not value:
        return value
    if value[-1] not in ".!?":
        value += "."
    return value


def append_unique(items: list[str], value: str):
    if value and value not in items:
        items.append(value)


def prompt_text(
    label: str,
    default: str | None = None,
    required: bool = False,
    input_fn: Callable[[str], str] = input,
) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input_fn(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("This value is required.")


def prompt_yes_no(
    label: str,
    default: bool = True,
    input_fn: Callable[[str], str] = input,
) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        value = input_fn(f"{label}{suffix}: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Enter y or n.")


def prompt_choice(
    label: str,
    options: list[str],
    default_index: int = 0,
    input_fn: Callable[[str], str] = input,
) -> int:
    print(label)
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")

    default_value = str(default_index + 1)
    while True:
        raw = input_fn(f"Choose [{default_value}]: ").strip()
        if not raw:
            return default_index
        if raw.isdigit():
            selected = int(raw) - 1
            if 0 <= selected < len(options):
                return selected
        print("Enter one of the option numbers.")


def prompt_multi_choice(
    label: str,
    options: list[str],
    default: list[int] | None = None,
    input_fn: Callable[[str], str] = input,
) -> list[int]:
    print(label)
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")

    default_text = ",".join(str(item + 1) for item in default) if default else ""
    prompt = f"Choose comma-separated values [{default_text or 'none'}]: "

    while True:
        raw = input_fn(prompt).strip()
        if not raw:
            return default or []
        try:
            selected = sorted({int(part.strip()) - 1 for part in raw.split(",") if part.strip()})
        except ValueError:
            print("Use comma-separated numbers.")
            continue
        if all(0 <= value < len(options) for value in selected):
            return selected
        print("One or more option numbers are out of range.")


def prompt_multiline(
    label: str,
    input_fn: Callable[[str], str] = input,
) -> list[str]:
    print(f"{label} Enter one line at a time. Submit an empty line to finish.")
    lines: list[str] = []
    while True:
        value = input_fn("> ").strip()
        if not value:
            return lines
        lines.append(value)


def available_recipe_ids(recipe_root: Path = RECIPE_DIR) -> list[str]:
    if not recipe_root.exists():
        return []
    result: list[str] = []
    for candidate in sorted(path for path in recipe_root.iterdir() if path.is_dir()):
        if any((candidate / manifest_name).exists() for manifest_name in RECIPE_MANIFEST_NAMES):
            result.append(candidate.name)
    return result


def resolve_recipe(recipe_value: str) -> tuple[str, str | None, Path]:
    raw = recipe_value.strip()
    if not raw:
        raise ValueError("Recipe is required.")

    explicit = Path(raw).expanduser()
    if explicit.exists():
        resolved = explicit.resolve()
        if resolved.is_dir():
            for manifest_name in RECIPE_MANIFEST_NAMES:
                manifest_path = resolved / manifest_name
                if manifest_path.exists():
                    return resolved.name, str(resolved), manifest_path
            raise ValueError(f"No recipe manifest found in {resolved}")
        if resolved.is_file():
            return resolved.parent.name, str(resolved), resolved

    candidate = RECIPE_DIR / raw
    if candidate.exists():
        for manifest_name in RECIPE_MANIFEST_NAMES:
            manifest_path = candidate / manifest_name
            if manifest_path.exists():
                return raw, None, manifest_path
        raise ValueError(f"No recipe manifest found in {candidate}")

    raise ValueError(f"Recipe could not be resolved from {raw}")


def load_recipe_manifest(recipe_manifest_path: Path) -> dict | None:
    if recipe_manifest_path.suffix.lower() != ".json":
        return None
    try:
        return json.loads(recipe_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def normalize_domain_ordering(raw_lines: list[str]) -> dict[str, list[str]]:
    ordering: dict[str, list[str]] = {}
    for line in raw_lines:
        if ":" not in line:
            continue
        domain, dependencies = line.split(":", 1)
        ordering[domain.strip()] = [item.strip() for item in dependencies.split(",") if item.strip()]
    return ordering


def count_files(path: Path) -> int:
    return sum(1 for candidate in path.rglob("*") if candidate.is_file())


def infer_language(text: str) -> str | None:
    lowered = text.lower()
    for token in LANGUAGE_TOKENS:
        if token in lowered:
            return token
    return None


def recommend_tier(
    source_path: Path,
    source_description: str,
    target_description: str,
    domain_hints: list[str],
    domain_ordering: dict[str, list[str]],
    recipe_manifest: dict | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    source_language = infer_language(source_description)
    target_language = infer_language(target_description)
    if source_language and target_language and source_language != target_language:
        reasons.append(f"source/target descriptions suggest a shift from {source_language} to {target_language}")

    file_count = count_files(source_path)
    if file_count > 300:
        reasons.append(f"source tree has {file_count} files")

    recipe_domains = recipe_manifest.get("domains", []) if isinstance(recipe_manifest, dict) else []
    if len(domain_hints) >= 3 or len(domain_ordering) >= 2 or len(recipe_domains) >= 4:
        reasons.append("domain decomposition looks useful")

    if reasons:
        return "high", reasons
    return "medium", ["single-rulebook flow looks sufficient"]


def phase_names_for_tier(tier: str) -> list[str]:
    return TIER2_PHASES if tier == "high" else TIER1_PHASES


def phase_dir_name(phase_name: str) -> str:
    return PHASE_DIR_NAMES.get(phase_name, phase_name)


def build_non_negotiables(
    style_guides: list[dict],
    naming_conventions: list[dict],
    custom_items: list[str],
) -> list[str]:
    result: list[str] = []
    for guide in style_guides:
        source = guide.get("source")
        if source == "repo":
            append_unique(
                result,
                format_sentence(f"Follow the {guide['label']} at {guide['path']}"),
            )
        elif source == "custom-path":
            append_unique(
                result,
                format_sentence(f"Follow the custom style guide at {guide['path']}"),
            )
        elif source == "custom-text":
            append_unique(result, format_sentence(guide["text"]))

    for naming in naming_conventions:
        source = naming.get("source")
        if source == "repo":
            append_unique(
                result,
                format_sentence(f"Use the naming conventions in {naming['path']}"),
            )
        elif source == "custom-text":
            append_unique(
                result,
                format_sentence(naming["text"], prefix="Naming conventions: "),
            )

    for item in custom_items:
        append_unique(result, format_sentence(item))
    return result


def build_manifest(config: dict) -> dict:
    source_path = Path(config["sourcePath"]).expanduser().resolve()
    experiment_dir = source_path.parent
    artifacts_dir = experiment_dir / "artifacts"
    summaries_dir = artifacts_dir / "migration-summaries"
    tier = config["tier"]
    framework_version = "tier-2" if tier == "high" else "tier-1"
    phases = {
        phase_name: {"status": "pending"}
        for phase_name in phase_names_for_tier(tier)
    }

    meta = {
        "sessionId": f"migrate-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{token_hex(3)}",
        "recipe": config["recipe"],
        "sourcePath": str(source_path),
        "targetPath": str(Path(config["targetPath"]).expanduser().resolve()),
        "artifactsDir": str(artifacts_dir),
        "summariesDir": str(summaries_dir),
        "referencePath": (
            str(Path(config["referencePath"]).expanduser().resolve())
            if config.get("referencePath")
            else None
        ),
        "sourceDescription": config["sourceDescription"],
        "targetDescription": config["targetDescription"],
        "testCommand": config.get("testCommand") or None,
        "buildCommand": config.get("buildCommand") or None,
        "lintCommand": config.get("lintCommand") or None,
        "nonNegotiables": config["nonNegotiables"],
        "status": "pending",
        "tier": tier,
        "frameworkVersion": framework_version,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if config.get("recipePath"):
        meta["recipePath"] = config["recipePath"]
    if config.get("domains"):
        meta["domains"] = config["domains"]
    if config.get("domainOrdering"):
        meta["domainOrdering"] = config["domainOrdering"]
    if config.get("styleGuides"):
        meta["styleGuides"] = config["styleGuides"]
    if config.get("namingConventions"):
        meta["namingConventions"] = config["namingConventions"]

    return {
        "meta": meta,
        "phases": phases,
        "checkpoints": [],
    }


def validate_paths(config: dict) -> list[str]:
    errors: list[str] = []
    source_path = Path(config["sourcePath"]).expanduser()
    if not source_path.exists() or not source_path.is_dir():
        errors.append(f"Source directory does not exist: {source_path}")
    elif not any(source_path.iterdir()):
        errors.append(f"Source directory is empty: {source_path}")

    target_path = Path(config["targetPath"]).expanduser()
    if target_path.exists() and not target_path.is_dir():
        errors.append(f"Target path exists but is not a directory: {target_path}")

    reference_path_value = config.get("referencePath")
    if reference_path_value:
        reference_path = Path(reference_path_value).expanduser()
        if not reference_path.exists():
            errors.append(f"Reference path does not exist: {reference_path}")
        elif reference_path.is_dir() and not any(reference_path.iterdir()):
            errors.append(f"Reference directory is empty: {reference_path}")

    try:
        resolve_recipe(config["recipeInput"])
    except ValueError as exc:
        errors.append(str(exc))

    if not ORCHESTRATOR_PATH.exists():
        errors.append(f"Missing orchestrator: {ORCHESTRATOR_PATH}")
    if not (sys.executable or shutil.which("python3")):
        errors.append("python3 is not available")
    return errors


def create_output_dirs(manifest_data: dict):
    meta = manifest_data["meta"]
    artifacts_dir = Path(meta["artifactsDir"])
    summaries_dir = Path(meta["summariesDir"])
    target_dir = Path(meta["targetPath"])

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    for phase_name in manifest_data["phases"]:
        (summaries_dir / phase_dir_name(phase_name)).mkdir(parents=True, exist_ok=True)


def print_summary(manifest_data: dict):
    meta = manifest_data["meta"]
    print("\nMigration Summary")
    print(f"  Source:   {meta['sourceDescription']}")
    print(f"            {meta['sourcePath']}")
    print(f"  Target:   {meta['targetDescription']}")
    print(f"            {meta['targetPath']}")
    print(f"  Recipe:   {meta['recipe']}")
    if meta.get("recipePath"):
        print(f"            {meta['recipePath']}")
    print(f"  Tier:     {meta['tier']} ({meta['frameworkVersion']})")
    print(f"  Artifacts:{meta['artifactsDir']}")
    print(f"  Manifest: {Path(meta['sourcePath']).parent / 'migration-manifest.json'}")
    if meta.get("referencePath"):
        print(f"  Reference:{meta['referencePath']}")
    if meta.get("testCommand"):
        print(f"  Test:     {meta['testCommand']}")
    if meta.get("buildCommand"):
        print(f"  Build:    {meta['buildCommand']}")
    if meta.get("lintCommand"):
        print(f"  Lint:     {meta['lintCommand']}")
    if meta.get("nonNegotiables"):
        print("  Rules:")
        for item in meta["nonNegotiables"]:
            print(f"    - {item}")
    if meta.get("domains"):
        print(f"  Domains:  {', '.join(meta['domains'])}")
    if meta.get("domainOrdering"):
        print("  Ordering:")
        for domain, dependencies in meta["domainOrdering"].items():
            joined = ", ".join(dependencies) if dependencies else "(none)"
            print(f"    - {domain}: {joined}")


def detect_runtime_label(runtime: str | None) -> str:
    if runtime:
        return runtime
    if shutil.which("codex"):
        return "codex"
    if shutil.which("claude"):
        return "claude-code"
    if shutil.which("cursor-agent"):
        return "cursor"
    return "auto-detect"


def launch_orchestrator(manifest_path: Path, runtime: str | None = None, model: str | None = None) -> tuple[int, Path]:
    python_exec = sys.executable or shutil.which("python3")
    if not python_exec:
        raise RuntimeError("python3 is not available")

    meta = mf.load(str(manifest_path))["meta"]
    artifacts_dir = Path(meta["artifactsDir"])
    log_path = artifacts_dir / "wizard-launch.log"
    cmd = [python_exec, str(ORCHESTRATOR_PATH), str(manifest_path), "--non-interactive"]
    if runtime:
        cmd.extend(["--runtime", runtime])
    if model:
        cmd.extend(["--model", model])

    with log_path.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return process.pid, log_path


def collect_non_negotiables(
    style_guides: list[StyleGuideOption],
    input_fn: Callable[[str], str] = input,
) -> tuple[list[dict], list[dict], list[str]]:
    selected_style_guides: list[dict] = []
    selected_naming: list[dict] = []
    custom_items: list[str] = []

    print("\nNon-Negotiables")
    print("Choose repo style guides, naming conventions, or add custom rules.")

    if style_guides:
        options: list[str] = []
        for guide in style_guides:
            line = f"{guide.title} [{guide.style_path}]"
            if guide.naming_preview:
                line += f" | naming: {guide.naming_preview[0]}"
            options.append(line)

        selected_indexes = prompt_multi_choice(
            "Select repo style guide presets:",
            options,
            input_fn=input_fn,
        )
        for index in selected_indexes:
            guide = style_guides[index]
            selected_style_guides.append(
                {
                    "source": "repo",
                    "language": guide.language,
                    "label": guide.title,
                    "path": guide.style_path,
                }
            )

        if selected_indexes and prompt_yes_no("Use naming conventions from the selected style guide(s)?", True, input_fn):
            for index in selected_indexes:
                guide = style_guides[index]
                if guide.naming_path:
                    selected_naming.append(
                        {
                            "source": "repo",
                            "language": guide.language,
                            "label": f"{guide.title} naming conventions",
                            "path": guide.naming_path,
                            "preview": guide.naming_preview,
                        }
                    )
    else:
        print("No repo style guides were discovered under styleguide/.")

    if prompt_yes_no("Add a custom style guide path?", False, input_fn):
        while True:
            path_value = prompt_text("Custom style guide path", required=True, input_fn=input_fn)
            path = Path(path_value).expanduser()
            if path.exists():
                selected_style_guides.append(
                    {
                        "source": "custom-path",
                        "label": "Custom style guide",
                        "path": str(path.resolve()),
                    }
                )
                break
            print("That path does not exist.")

    if prompt_yes_no("Add custom style-guide instructions?", False, input_fn):
        for line in prompt_multiline("Custom style-guide rules.", input_fn):
            selected_style_guides.append(
                {
                    "source": "custom-text",
                    "text": line,
                }
            )

    if prompt_yes_no("Add custom naming conventions?", False, input_fn):
        for line in prompt_multiline("Custom naming conventions.", input_fn):
            selected_naming.append(
                {
                    "source": "custom-text",
                    "text": line,
                }
            )

    if prompt_yes_no("Add any other non-negotiables?", False, input_fn):
        custom_items.extend(prompt_multiline("Additional non-negotiables.", input_fn))

    return selected_style_guides, selected_naming, custom_items


def collect_inputs(args: argparse.Namespace, input_fn: Callable[[str], str] = input) -> dict:
    print("Migration Wizard")
    print(f"Repository root: {REPO_ROOT}")
    print(f"Detected runtime: {detect_runtime_label(args.runtime)}")

    recipe_ids = available_recipe_ids()
    default_recipe = args.recipe or (recipe_ids[0] if len(recipe_ids) == 1 else None)
    source_path_value = prompt_text("Source path", args.source_path, required=True, input_fn=input_fn)
    source_path = Path(source_path_value).expanduser().resolve()
    default_target_path = args.target_path or str(source_path.parent / f"{source_path.name}-migrated")
    source_description = prompt_text("Source description", args.source_description, required=True, input_fn=input_fn)
    target_description = prompt_text("Target description", args.target_description, required=True, input_fn=input_fn)
    target_path = prompt_text("Target path", default_target_path, required=True, input_fn=input_fn)
    recipe_input = prompt_text("Recipe", default_recipe, required=True, input_fn=input_fn)
    reference_path = prompt_text("Reference path", args.reference_path, input_fn=input_fn)
    test_command = prompt_text("Test command", args.test_command, input_fn=input_fn)
    build_command = prompt_text("Build command", args.build_command, input_fn=input_fn)
    lint_command = prompt_text("Lint command", args.lint_command, input_fn=input_fn)

    style_guides = discover_style_guides()
    selected_style_guides, selected_naming, custom_items = collect_non_negotiables(style_guides, input_fn=input_fn)

    domain_hints: list[str] = []
    if prompt_yes_no("Add domain hints for a Tier 2 run?", False, input_fn):
        domain_hints = prompt_multiline("Domains (for example: routes, models, services).", input_fn)

    domain_ordering_lines: list[str] = []
    if prompt_yes_no("Add domain ordering constraints?", False, input_fn):
        domain_ordering_lines = prompt_multiline("Domain ordering as 'domain: dep1, dep2'.", input_fn)

    config = {
        "sourceDescription": source_description,
        "targetDescription": target_description,
        "sourcePath": str(source_path),
        "targetPath": target_path,
        "recipeInput": recipe_input,
        "referencePath": reference_path or None,
        "testCommand": test_command or None,
        "buildCommand": build_command or None,
        "lintCommand": lint_command or None,
        "styleGuides": selected_style_guides,
        "namingConventions": selected_naming,
    }

    recipe_manifest = None
    try:
        recipe_name, recipe_path, recipe_manifest_path = resolve_recipe(recipe_input)
        recipe_manifest = load_recipe_manifest(recipe_manifest_path)
        config["recipe"] = recipe_name
        if recipe_path:
            config["recipePath"] = recipe_path
    except ValueError:
        config["recipe"] = recipe_input

    domain_ordering = normalize_domain_ordering(domain_ordering_lines)
    recommended_tier, tier_reasons = recommend_tier(
        source_path,
        source_description,
        target_description,
        domain_hints,
        domain_ordering,
        recipe_manifest,
    )
    print("\nTier Recommendation")
    print(f"  Recommended: {'Tier 2' if recommended_tier == 'high' else 'Tier 1'}")
    for reason in tier_reasons:
        print(f"    - {reason}")

    tier_choice = prompt_choice(
        "Select tier:",
        [
            f"Use recommendation ({'Tier 2' if recommended_tier == 'high' else 'Tier 1'})",
            "Tier 1 / medium",
            "Tier 2 / high",
        ],
        default_index=0,
        input_fn=input_fn,
    )
    if tier_choice == 1:
        config["tier"] = "medium"
    elif tier_choice == 2:
        config["tier"] = "high"
    else:
        config["tier"] = recommended_tier

    if config["tier"] == "high":
        if not domain_hints and recipe_manifest and isinstance(recipe_manifest.get("domains"), list):
            domain_hints = [
                item["name"] if isinstance(item, dict) else str(item)
                for item in recipe_manifest["domains"]
                if (isinstance(item, dict) and item.get("name")) or isinstance(item, str)
            ]
        if not domain_ordering and recipe_manifest and isinstance(recipe_manifest.get("domain_ordering"), dict):
            domain_ordering = {
                str(key): [str(value) for value in values]
                for key, values in recipe_manifest["domain_ordering"].items()
                if isinstance(values, list)
            }
        config["domains"] = domain_hints
        config["domainOrdering"] = domain_ordering

    config["nonNegotiables"] = build_non_negotiables(
        selected_style_guides,
        selected_naming,
        custom_items,
    )
    return config


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive migrate wizard")
    parser.add_argument("--source-path")
    parser.add_argument("--source-description")
    parser.add_argument("--target-path")
    parser.add_argument("--target-description")
    parser.add_argument("--recipe")
    parser.add_argument("--reference-path")
    parser.add_argument("--test-command")
    parser.add_argument("--build-command")
    parser.add_argument("--lint-command")
    parser.add_argument("--runtime", choices=["codex", "claude-code", "cursor"])
    parser.add_argument("--model")
    parser.add_argument("--no-launch", action="store_true", help="Write the manifest but do not launch the orchestrator")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = collect_inputs(args)

    errors = validate_paths(config)
    if errors:
        print("\nValidation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    manifest_data = build_manifest(config)
    manifest_path = Path(manifest_data["meta"]["sourcePath"]).parent / "migration-manifest.json"
    print_summary(manifest_data)

    if not prompt_yes_no("\nWrite the manifest and create directories?", True):
        print("Aborted before writing files.")
        return 0

    create_output_dirs(manifest_data)
    mf.save(str(manifest_path), manifest_data)
    print(f"Manifest written to {manifest_path}")

    if args.no_launch:
        print("Launch skipped by --no-launch.")
        return 0

    if not prompt_yes_no("Launch the orchestrator now?", True):
        print("Manifest written. Launch skipped.")
        return 0

    try:
        pid, log_path = launch_orchestrator(manifest_path, runtime=args.runtime, model=args.model)
    except Exception as exc:  # pragma: no cover - surfaced to terminal users
        print(f"Failed to launch orchestrator: {exc}")
        return 1

    print(f"Orchestrator started with pid {pid}.")
    print(f"Launch log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

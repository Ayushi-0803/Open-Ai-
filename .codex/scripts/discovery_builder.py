#!/usr/bin/env python3
"""
Deterministic discovery artifact builder.

Builds a file inventory plus a lightweight dependency graph for the source tree.
The output is intentionally machine-readable and conservative; LLM discovery can
layer richer semantic descriptions on top of it.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SOURCE_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".rb": "ruby",
    ".rs": "rust",
    ".php": "php",
}

TEST_PATTERNS = (
    "test_",
    "_test",
    ".test.",
    ".spec.",
)

IGNORE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}

SHARD_SIZE = 50


def is_test_file(rel_path: str) -> bool:
    name = Path(rel_path).name
    if any(part in {"test", "tests", "__tests__"} for part in Path(rel_path).parts):
        return True
    return any(token in name for token in TEST_PATTERNS)


def list_source_files(source_path: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(source_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for filename in filenames:
            path = Path(root) / filename
            if path.suffix.lower() in SOURCE_EXTENSIONS:
                files.append(path)
    return sorted(files)


def language_for(path: Path) -> str:
    return SOURCE_EXTENSIONS.get(path.suffix.lower(), "unknown")


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def python_module_candidates(rel_path: str) -> set[str]:
    path = Path(rel_path)
    without_suffix = path.with_suffix("")
    parts = without_suffix.parts
    if not parts:
        return set()
    candidates = {".".join(parts)}
    if parts[-1] == "__init__":
        candidates.add(".".join(parts[:-1]))
    return {c for c in candidates if c}


def build_python_module_index(rel_paths: list[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for rel_path in rel_paths:
        if not rel_path.endswith(".py"):
            continue
        for candidate in python_module_candidates(rel_path):
            index[candidate] = rel_path
    return index


def resolve_python_relative_module(module: str | None, level: int, rel_path: str) -> str | None:
    current = Path(rel_path).with_suffix("")
    package_parts = list(current.parts[:-1])
    if Path(rel_path).name == "__init__.py":
        package_parts = list(current.parts[:-1])
    if level > 0:
        if level - 1 > len(package_parts):
            package_parts = []
        else:
            package_parts = package_parts[: len(package_parts) - (level - 1)]
    module_parts = module.split(".") if module else []
    parts = package_parts + module_parts
    return ".".join(part for part in parts if part)


def extract_python_imports(rel_path: str, content: str, module_index: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    internal: set[str] = set()
    external: set[str] = set()
    exports: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [], [], []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                target = module_index.get(module_name)
                if target:
                    internal.add(target)
                else:
                    external.add(module_name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            module_name = resolve_python_relative_module(node.module, node.level, rel_path) if node.level else node.module
            if module_name:
                target = module_index.get(module_name)
                if target:
                    internal.add(target)
                else:
                    external.add(module_name.split(".")[0])
            elif node.module:
                external.add(node.module.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if getattr(node, "col_offset", 0) == 0:
                exports.add(node.name)
        elif isinstance(node, ast.Assign) and getattr(node, "col_offset", 0) == 0:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exports.add(target.id)
    return sorted(internal), sorted(external), sorted(exports)


def infer_description(rel_path: str, has_tests: bool) -> str:
    if has_tests:
        return "Test module"
    name = Path(rel_path).stem.replace("_", " ").replace("-", " ")
    return f"Source file for {name}".strip()


def infer_complexity(loc: int, internal_imports: int) -> str:
    if loc >= 300 or internal_imports >= 8:
        return "high"
    if loc >= 120 or internal_imports >= 4:
        return "medium"
    return "low"


def infer_type(rel_path: str, has_tests: bool) -> str:
    path = rel_path.lower()
    if has_tests:
        return "test"
    if "route" in path or "handler" in path:
        return "route-handler"
    if "service" in path:
        return "service"
    if "middleware" in path:
        return "middleware"
    if "config" in path:
        return "config"
    if "model" in path:
        return "model"
    return "module"


def infer_test_target(rel_path: str, source_files: list[str]) -> str | None:
    source_stem = Path(rel_path).stem
    for candidate in source_files:
        candidate_name = Path(candidate).name
        if source_stem.replace("test_", "") in candidate_name or source_stem.replace("_test", "") in candidate_name:
            return candidate
    return None


def risk_tier(complexity: str, has_tests: bool, dependent_count: int) -> str:
    if not has_tests and (complexity == "high" or dependent_count >= 4):
        return "human"
    if complexity == "medium" or not has_tests:
        return "supervised"
    return "auto"


def detect_dynamic_risks(rel_path: str, content: str, language: str) -> list[str]:
    risks: list[str] = []
    lowered = rel_path.lower()
    if language == "python":
        if "__import__(" in content:
            risks.append("python-dynamic-import")
        if "importlib.import_module" in content:
            risks.append("python-importlib-dynamic-import")
        if "exec(" in content or "eval(" in content:
            risks.append("python-dynamic-eval")
    if language in {"javascript", "typescript"}:
        if "import(" in content:
            risks.append("js-dynamic-import")
        if "require(" in content and ("+" in content or "`" in content):
            risks.append("js-dynamic-require")
        if "eval(" in content:
            risks.append("js-eval")
    if any(token in lowered for token in ("plugin", "extension", "registry")):
        risks.append("convention-based-runtime-loading")
    return risks


def shard_symbol_index(dep_graph_files: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    for rel_path, entry in sorted(dep_graph_files.items()):
        for export in entry.get("exports", []):
            symbols.append(
                {
                    "symbol": export,
                    "path": rel_path,
                    "language": entry.get("language"),
                    "complexity": entry.get("complexity"),
                }
            )

    shards: list[dict[str, Any]] = []
    for index in range(0, len(symbols), SHARD_SIZE):
        shard_symbols = symbols[index:index + SHARD_SIZE]
        shards.append(
            {
                "name": f"shard-{(index // SHARD_SIZE) + 1}.json",
                "symbolCount": len(shard_symbols),
                "paths": sorted({item["path"] for item in shard_symbols}),
                "symbols": shard_symbols,
            }
        )
    return symbols, shards


def shard_dependency_graph(dep_graph_files: dict[str, Any]) -> list[dict[str, Any]]:
    files = []
    for rel_path, entry in sorted(dep_graph_files.items()):
        files.append(
            {
                "path": rel_path,
                "language": entry.get("language"),
                "loc": entry.get("loc"),
                "complexity": entry.get("complexity"),
                "imports": {
                    "internal": entry.get("imports", {}).get("internal", []),
                    "external": entry.get("imports", {}).get("external", []),
                },
                "importedBy": entry.get("importedBy", []),
                "patterns": entry.get("patterns", []),
                "hasTests": entry.get("hasTests", False),
            }
        )

    shards: list[dict[str, Any]] = []
    for index in range(0, len(files), SHARD_SIZE):
        shard_files = files[index:index + SHARD_SIZE]
        shards.append(
            {
                "name": f"shard-{(index // SHARD_SIZE) + 1}.json",
                "fileCount": len(shard_files),
                "files": shard_files,
            }
        )
    return shards


def build_artifacts(source_path: Path) -> dict[str, Any]:
    files = list_source_files(source_path)
    rel_paths = [str(path.relative_to(source_path)) for path in files]
    module_index = build_python_module_index(rel_paths)

    dep_graph_files: dict[str, Any] = {}
    imported_by: dict[str, list[str]] = defaultdict(list)
    manifest_entries: list[dict[str, Any]] = []
    external_packages: set[str] = set()
    pattern_counter: Counter[str] = Counter()
    dynamic_risks: list[dict[str, Any]] = []

    for path in files:
        rel_path = str(path.relative_to(source_path))
        content = safe_read(path)
        lines = content.splitlines()
        loc = len(lines)
        language = language_for(path)
        has_tests = is_test_file(rel_path)
        internal_imports: list[str] = []
        external_imports: list[str] = []
        exports: list[str] = []
        patterns: list[str] = []

        if language == "python":
            internal_imports, external_imports, exports = extract_python_imports(rel_path, content, module_index)
            if any("fastapi" in pkg for pkg in external_imports):
                patterns.append("fastapi-router")
            if any("pydantic" in pkg for pkg in external_imports):
                patterns.append("pydantic-model")
            if any("sqlalchemy" in pkg for pkg in external_imports):
                patterns.append("sqlalchemy-model")
        if has_tests:
            patterns.append("test-file")
        if "config" in rel_path.lower():
            patterns.append("config-module")
        if "middleware" in rel_path.lower():
            patterns.append("middleware")
        if "handler" in rel_path.lower() or "route" in rel_path.lower():
            patterns.append("handler")

        dynamic_signals = detect_dynamic_risks(rel_path, content, language)
        if dynamic_signals:
            dynamic_risks.append(
                {
                    "path": rel_path,
                    "language": language,
                    "signals": dynamic_signals,
                }
            )

        for dep in internal_imports:
            imported_by[dep].append(rel_path)
        for pkg in external_imports:
            external_packages.add(pkg)
        for pattern in patterns:
            pattern_counter[pattern] += 1

        description = infer_description(rel_path, has_tests)
        complexity = infer_complexity(loc, len(internal_imports))

        dep_graph_files[rel_path] = {
            "path": rel_path,
            "language": language,
            "loc": loc,
            "description": description,
            "exports": exports,
            "imports": {
                "internal": internal_imports,
                "external": external_imports,
            },
            "importedBy": [],
            "patterns": patterns,
            "complexity": complexity,
            "hasTests": has_tests,
            "testFile": rel_path if has_tests else None,
        }

    for rel_path, entry in dep_graph_files.items():
        entry["importedBy"] = sorted(imported_by.get(rel_path, []))

    source_only_files = [path for path in rel_paths if not is_test_file(path)]
    for rel_path in rel_paths:
        entry = dep_graph_files[rel_path]
        test_target = None if is_test_file(rel_path) else next(
            (candidate for candidate, candidate_entry in dep_graph_files.items() if candidate_entry["hasTests"] and infer_test_target(candidate, [rel_path]) == rel_path),
            None,
        )
        manifest_entries.append(
            {
                "path": rel_path,
                "type": infer_type(rel_path, entry["hasTests"]),
                "complexity": entry["complexity"],
                "loc": entry["loc"],
                "dependencies": entry["imports"]["internal"],
                "dependents": entry["importedBy"],
                "hasTests": entry["hasTests"],
                "testFile": rel_path if entry["hasTests"] else test_target,
                "patterns": entry["patterns"],
                "riskTier": risk_tier(entry["complexity"], entry["hasTests"], len(entry["importedBy"])),
            }
        )

    entry_points = sorted(
        rel_paths,
        key=lambda rel: len(dep_graph_files[rel]["importedBy"]),
        reverse=True,
    )
    leaf_nodes = sorted(
        [rel for rel, entry in dep_graph_files.items() if not entry["imports"]["internal"]],
        key=lambda rel: rel,
    )

    dep_graph = {
        "files": dep_graph_files,
        "entryPoints": [rel for rel in entry_points if dep_graph_files[rel]["importedBy"]][:10],
        "leafNodes": leaf_nodes,
        "circularDeps": [],
        "externalPackages": sorted(external_packages),
    }

    file_manifest = {
        "files": manifest_entries,
        "summary": {
            "totalFiles": len(rel_paths),
            "totalLoc": sum(entry["loc"] for entry in dep_graph_files.values()),
            "filesWithTests": sum(1 for entry in dep_graph_files.values() if entry["hasTests"]),
            "filesWithoutTests": sum(1 for entry in dep_graph_files.values() if not entry["hasTests"]),
            "patternDistribution": dict(sorted(pattern_counter.items())),
        },
    }

    symbols, symbol_shards = shard_symbol_index(dep_graph_files)
    dependency_shards = shard_dependency_graph(dep_graph_files)
    dynamic_risk_report = {
        "summary": {
            "flaggedFiles": len(dynamic_risks),
            "signals": sorted({signal for entry in dynamic_risks for signal in entry["signals"]}),
        },
        "files": dynamic_risks,
    }

    return {
        "dep_graph": dep_graph,
        "file_manifest": file_manifest,
        "symbol_index": {
            "summary": {
                "totalSymbols": len(symbols),
                "totalShards": len(symbol_shards),
            },
            "symbols": symbols,
        },
        "dependency_shards": {
            "summary": {
                "totalFiles": len(dep_graph_files),
                "totalShards": len(dependency_shards),
            },
            "shards": dependency_shards,
        },
        "dynamic_risk_report": dynamic_risk_report,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discovery_builder.py <source-path> <output-dir>", file=sys.stderr)
        return 1

    source_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        print(f"Source path does not exist: {source_path}", file=sys.stderr)
        return 1

    artifacts = build_artifacts(source_path)
    (output_dir / "dep-graph.json").write_text(json.dumps(artifacts["dep_graph"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "file-manifest.json").write_text(json.dumps(artifacts["file_manifest"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "symbol-index.json").write_text(json.dumps(artifacts["symbol_index"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "dynamic-risk-report.json").write_text(json.dumps(artifacts["dynamic_risk_report"], indent=2) + "\n", encoding="utf-8")
    shard_dir = output_dir / "dependency-shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_index = {
        "summary": artifacts["dependency_shards"]["summary"],
        "shards": [
            {
                "name": shard["name"],
                "fileCount": shard["fileCount"],
            }
            for shard in artifacts["dependency_shards"]["shards"]
        ],
    }
    (shard_dir / "index.json").write_text(json.dumps(shard_index, indent=2) + "\n", encoding="utf-8")
    for shard in artifacts["dependency_shards"]["shards"]:
        (shard_dir / shard["name"]).write_text(json.dumps(shard, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote discovery artifacts to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

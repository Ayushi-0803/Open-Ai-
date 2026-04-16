"""
Diff Scorer — deterministic heuristics for evaluating migration quality.
Used by the review agent to score diffs without needing an LLM.

Usage:
    python diff_scorer.py --source-dir ./src --target-dir ./target --output results.json

Scores each file on:
  1. Size ratio    — is the output roughly the same size as the input?
  2. Structure     — are function/class counts preserved?
  3. Dependencies  — were unexpected new imports added?
  4. Test results  — did tests pass?
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


def count_functions(content: str, language: str) -> int:
    """Count function/method definitions in source code."""
    patterns = {
        "python": r'^\s*(?:async\s+)?def\s+\w+',
        "javascript": r'(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>|(?:async\s+)?\w+\s*\([^)]*\)\s*\{)',
        "typescript": r'(?:function\s+\w+|(?:const|let|var)\s+\w+\s*(?::\s*\w+)?\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>|(?:async\s+)?\w+\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{)',
        "go": r'^\s*func\s+',
        "java": r'(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*(?:throws\s+\w+)?\s*\{',
    }
    pattern = patterns.get(language, patterns["python"])
    return len(re.findall(pattern, content, re.MULTILINE))


def count_imports(content: str, language: str) -> list[str]:
    """Extract import statements from source code."""
    patterns = {
        "python": r'^(?:import|from)\s+(\S+)',
        "javascript": r'(?:import\s+.*?from\s+["\'](.+?)["\']|require\(["\'](.+?)["\']\))',
        "typescript": r'(?:import\s+.*?from\s+["\'](.+?)["\']|require\(["\'](.+?)["\']\))',
        "go": r'^\s*(?:import\s+)?"(.+?)"',
        "java": r'^import\s+([\w.]+)',
    }
    pattern = patterns.get(language, patterns["python"])
    matches = re.findall(pattern, content, re.MULTILINE)
    # Flatten tuples for JS/TS patterns
    flat = []
    for m in matches:
        if isinstance(m, tuple):
            flat.extend(x for x in m if x)
        else:
            flat.append(m)
    return flat


def detect_language(filepath: str) -> str:
    """Detect language from file extension."""
    ext = Path(filepath).suffix.lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".java": "java",
        ".rs": "rust",
        ".rb": "ruby",
    }
    return mapping.get(ext, "unknown")


def score_file(source_path: str, target_path: str) -> dict:
    """
    Score a single file migration.
    
    Returns dict with:
        - size_ratio:   target LOC / source LOC (ideal: 0.5 - 2.0)
        - func_delta:   difference in function count (ideal: 0)
        - new_imports:   imports in target not in source
        - scores:       per-dimension 0.0-1.0 scores
        - overall:      weighted overall score 0.0-1.0
    """
    try:
        with open(source_path) as f:
            source = f.read()
        with open(target_path) as f:
            target = f.read()
    except FileNotFoundError as e:
        return {
            "source": source_path,
            "target": target_path,
            "error": str(e),
            "overall": 0.0,
        }

    source_lang = detect_language(source_path)
    target_lang = detect_language(target_path)

    source_loc = len([l for l in source.splitlines() if l.strip()])
    target_loc = len([l for l in target.splitlines() if l.strip()])

    source_funcs = count_functions(source, source_lang)
    target_funcs = count_functions(target, target_lang)

    source_imports = set(count_imports(source, source_lang))
    target_imports = set(count_imports(target, target_lang))
    new_imports = target_imports - source_imports

    # ── Scoring ──

    # Size ratio: penalize if target is >3x or <0.2x the source
    if source_loc == 0:
        size_score = 0.5
    else:
        ratio = target_loc / source_loc
        if 0.3 <= ratio <= 3.0:
            size_score = 1.0
        elif 0.1 <= ratio <= 5.0:
            size_score = 0.6
        else:
            size_score = 0.2

    # Function count preservation: penalize large deltas
    if source_funcs == 0 and target_funcs == 0:
        func_score = 1.0
    elif source_funcs == 0:
        func_score = 0.5
    else:
        delta_ratio = abs(target_funcs - source_funcs) / max(source_funcs, 1)
        if delta_ratio <= 0.2:
            func_score = 1.0
        elif delta_ratio <= 0.5:
            func_score = 0.7
        else:
            func_score = 0.3

    # New imports: a few new ones are fine (framework change), many is suspicious
    if len(new_imports) <= 3:
        import_score = 1.0
    elif len(new_imports) <= 8:
        import_score = 0.7
    else:
        import_score = 0.3

    # Weighted overall
    overall = (size_score * 0.3) + (func_score * 0.4) + (import_score * 0.3)

    return {
        "source": source_path,
        "target": target_path,
        "source_loc": source_loc,
        "target_loc": target_loc,
        "size_ratio": round(target_loc / max(source_loc, 1), 2),
        "source_functions": source_funcs,
        "target_functions": target_funcs,
        "func_delta": target_funcs - source_funcs,
        "new_imports": sorted(new_imports),
        "scores": {
            "size": round(size_score, 2),
            "structure": round(func_score, 2),
            "imports": round(import_score, 2),
        },
        "overall": round(overall, 2),
    }


def run_tests(test_command: str, cwd: Optional[str] = None) -> dict:
    """Run the test command and capture results."""
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=cwd,
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit_code": -1, "stdout": "", "stderr": "TIMEOUT"}
    except Exception as e:
        return {"passed": False, "exit_code": -1, "stdout": "", "stderr": str(e)}


def score_migration(file_pairs: list[dict], test_command: Optional[str] = None,
                    test_cwd: Optional[str] = None) -> dict:
    """
    Score an entire migration.
    
    Args:
        file_pairs: List of {"source": path, "target": path} dicts
        test_command: Command to run tests (optional)
        test_cwd: Working directory for test command
    
    Returns:
        Full scoring report with per-file and aggregate scores.
    """
    file_scores = []
    for pair in file_pairs:
        score = score_file(pair["source"], pair["target"])
        file_scores.append(score)

    # Aggregate
    valid_scores = [s for s in file_scores if "error" not in s]
    avg_overall = sum(s["overall"] for s in valid_scores) / max(len(valid_scores), 1)
    
    # Test results
    test_results = None
    if test_command:
        test_results = run_tests(test_command, cwd=test_cwd)

    # Routing decisions
    routing = {"pass": [], "fail": [], "human": []}
    for s in file_scores:
        if "error" in s:
            routing["fail"].append(s["source"])
        elif s["overall"] >= 0.7:
            routing["pass"].append(s["source"])
        elif s["overall"] >= 0.4:
            routing["human"].append(s["source"])
        else:
            routing["fail"].append(s["source"])

    return {
        "summary": {
            "total_files": len(file_scores),
            "passed": len(routing["pass"]),
            "failed": len(routing["fail"]),
            "human_review": len(routing["human"]),
            "avg_score": round(avg_overall, 2),
        },
        "test_results": test_results,
        "routing": routing,
        "files": file_scores,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score migration diff quality")
    parser.add_argument("--pairs-json", required=True, help="JSON file with source/target pairs")
    parser.add_argument("--test-command", help="Test command to run")
    parser.add_argument("--test-cwd", help="Working directory for tests")
    parser.add_argument("--output", default="diff-scores.json", help="Output file")
    args = parser.parse_args()

    with open(args.pairs_json) as f:
        pairs = json.load(f)

    report = score_migration(pairs, args.test_command, args.test_cwd)

    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"Scored {report['summary']['total_files']} files. "
          f"Avg score: {report['summary']['avg_score']}")
    print(f"  Pass: {report['summary']['passed']}, "
          f"Fail: {report['summary']['failed']}, "
          f"Human: {report['summary']['human_review']}")

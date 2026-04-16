import json
from pathlib import Path

import pytest

import validate_artifacts


def _write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_planning_dir(tmp_path: Path) -> Path:
    planning_dir = tmp_path / "planning"
    planning_dir.mkdir()
    _write_json(planning_dir / "planning-input.json", {"batchPlan": [{"id": 1}]})
    _write_json(planning_dir / "risk-policy.json", {"rules": ["a"]})
    _write_json(planning_dir / "migration-batches.json", {"batches": [{"id": 1}]})
    _write_json(planning_dir / "planning-overview.json", {"artifactContracts": ["foo"]})
    (planning_dir / "PLAN.md").write_text("# plan", encoding="utf-8")
    (planning_dir / "AGENTS.md").write_text("# agents", encoding="utf-8")
    return planning_dir


@pytest.mark.integration
def test_validate_planning_success(tmp_path):
    planning_dir = _build_planning_dir(tmp_path)
    errors: list[str] = []

    validate_artifacts.validate_planning(planning_dir, errors)

    assert errors == []


@pytest.mark.integration
def test_validate_planning_missing_file(tmp_path):
    planning_dir = _build_planning_dir(tmp_path)
    (planning_dir / "PLAN.md").unlink()
    errors: list[str] = []

    validate_artifacts.validate_planning(planning_dir, errors)

    assert any("PLAN.md" in err for err in errors)

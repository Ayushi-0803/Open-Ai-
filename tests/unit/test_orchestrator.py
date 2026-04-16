import json
from pathlib import Path

import orchestrator


def _write_manifest(path: Path, *, framework_version: str = "tier-2", tier: str = "high", phases: dict | None = None):
    source_path = path.parent / "source"
    target_path = path.parent / "target"
    artifacts_dir = path.parent / "artifacts"
    summaries_dir = artifacts_dir / "migration-summaries"
    source_path.mkdir()
    target_path.mkdir()
    payload = {
        "meta": {
            "sessionId": "migrate-20260416-a1b2c3",
            "recipe": "example-generic",
            "sourcePath": str(source_path),
            "targetPath": str(target_path),
            "artifactsDir": str(artifacts_dir),
            "summariesDir": str(summaries_dir),
            "sourceDescription": "Python service",
            "targetDescription": "Rust service",
            "nonNegotiables": [],
            "status": "pending",
            "tier": tier,
            "frameworkVersion": framework_version,
        },
        "phases": phases
        or {
            phase["name"]: {"status": "pending"}
            for phase in orchestrator.get_phase_set({"meta": {"frameworkVersion": framework_version, "tier": tier}})
        },
        "checkpoints": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_reconcile_manifest_phase_set_repairs_stray_tier1_phase(tmp_path):
    manifest_path = tmp_path / "migration-manifest.json"
    phases = {
        "foundation": {"status": "pending"},
        "module_discovery": {"status": "pending"},
        "domain_discovery": {"status": "pending"},
        "conflict_resolution": {"status": "pending"},
        "domain_planning": {"status": "pending"},
        "domain_execution": {"status": "pending"},
        "rewiring": {"status": "pending"},
        "integration_review": {"status": "pending"},
        "reiterate": {"status": "pending"},
        "discovery": {"status": "in_progress"},
    }
    _write_manifest(manifest_path, phases=phases)

    repaired, repair = orchestrator.reconcile_manifest_phase_set(str(manifest_path))

    assert repair == {"missing": [], "unexpected": ["discovery"]}
    assert list(repaired["phases"]) == [
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
    assert "discovery" not in repaired["phases"]
    assert repaired["meta"]["phaseAlignmentRepairs"][0]["unexpected"] == ["discovery"]


def test_initialize_run_control_creates_issue_ledger_files(tmp_path):
    manifest_path = tmp_path / "migration-manifest.json"
    manifest = _write_manifest(manifest_path, framework_version="tier-1", tier="medium")

    orchestrator.initialize_run_control(str(manifest_path), manifest)

    markdown_path, json_path = orchestrator.get_issue_ledger_paths(str(manifest_path))
    assert markdown_path.is_file()
    assert json_path.is_file()
    ledger = json.loads(json_path.read_text(encoding="utf-8"))
    assert ledger["manifestPath"] == str(manifest_path.resolve())
    assert ledger["frameworkVersion"] == "tier-1"
    assert "Issue Ledger" in markdown_path.read_text(encoding="utf-8")


def test_build_context_includes_run_control_paths(tmp_path):
    manifest_path = tmp_path / "migration-manifest.json"
    manifest = _write_manifest(manifest_path, framework_version="tier-1", tier="medium")
    orchestrator.initialize_run_control(str(manifest_path), manifest)

    context = orchestrator.build_context(str(manifest_path), "discovery")

    assert context["run_control_dir"].endswith("artifacts/run-control")
    assert context["issue_ledger_path"].endswith("ISSUE_LEDGER.md")
    assert context["issue_ledger_json_path"].endswith("issue-ledger.json")
    assert context["phase_issue_report_path"].endswith("phase-issues/discovery.md")


def test_run_phase_fails_when_prebuilt_success_marker_exists_but_agent_crashes(tmp_path, monkeypatch):
    manifest_path = tmp_path / "migration-manifest.json"
    manifest = _write_manifest(manifest_path)
    orchestrator.initialize_run_control(str(manifest_path), manifest)

    skill_path = tmp_path / "tier2-foundation.md"
    skill_path.write_text("foundation skill\n", encoding="utf-8")

    def _fake_builder(_manifest_path, _label, _script_path, _cmd_args):
        output_dir = Path(_cmd_args[-1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "FOUNDATION.md").write_text("# FOUNDATION\n", encoding="utf-8")
        return True, ""

    monkeypatch.setattr(orchestrator, "run_python_builder", _fake_builder)
    monkeypatch.setattr(orchestrator, "resolve_skill_path", lambda _skill_name: skill_path)
    monkeypatch.setattr(
        orchestrator,
        "spawn_agent",
        lambda **kwargs: {"exit_code": 1, "stdout": "", "stderr": "boom", "runtime": "codex"},
    )

    phase_config = next(phase for phase in orchestrator.TIER2_PHASES if phase["name"] == "foundation")

    success = orchestrator.run_phase(
        manifest_path=str(manifest_path),
        phase_config=phase_config,
        non_interactive=True,
        attempt=1,
    )

    assert success is False
    repaired = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert repaired["phases"]["foundation"]["status"] == "failed"


def test_restart_from_phase_resets_selected_and_later_phases(tmp_path):
    manifest_path = tmp_path / "migration-manifest.json"
    phases = {
        "foundation": {"status": "done", "completedAt": "2026-04-16T00:00:00Z"},
        "module_discovery": {"status": "awaiting_approval", "awaitingApprovalAt": "2026-04-16T00:00:01Z"},
        "domain_discovery": {"status": "failed", "failedAt": "2026-04-16T00:00:02Z", "error": "boom"},
        "conflict_resolution": {"status": "done", "completedAt": "2026-04-16T00:00:03Z"},
        "domain_planning": {"status": "pending"},
        "domain_execution": {"status": "pending"},
        "rewiring": {"status": "pending"},
        "integration_review": {"status": "pending"},
        "reiterate": {"status": "pending"},
    }
    manifest = _write_manifest(manifest_path, phases=phases)

    restarted = orchestrator.restart_from_phase(str(manifest_path), manifest, "module_discovery")

    assert restarted["meta"]["status"] == "pending"
    assert restarted["phases"]["foundation"]["status"] == "done"
    assert restarted["phases"]["module_discovery"]["status"] == "pending"
    assert "awaitingApprovalAt" not in restarted["phases"]["module_discovery"]
    assert restarted["phases"]["domain_discovery"]["status"] == "pending"
    assert "failedAt" not in restarted["phases"]["domain_discovery"]
    assert "error" not in restarted["phases"]["domain_discovery"]

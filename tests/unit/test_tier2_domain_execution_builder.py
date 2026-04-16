import json
from pathlib import Path

import tier2_common
import tier2_domain_execution_builder as domain_execution_builder


def test_infer_target_candidate_paths_skips_target_root_placeholder():
    candidates = tier2_common.infer_target_candidate_paths("mospi_server.py")

    assert candidates == ["mospi_server.py", "mospi_server.ts"]


def test_build_execution_keeps_single_file_domain_pending_until_target_file_exists(tmp_path):
    summaries_dir = tmp_path / "migration-summaries"
    planning_dir = summaries_dir / "domain-planning" / "interface" / "planning"
    planning_dir.mkdir(parents=True)
    decoupled_files_path = planning_dir / "decoupled-files.interface.json"
    decoupled_files_path.write_text(json.dumps({"ownedFiles": ["mospi_server.py"]}), encoding="utf-8")

    overview_path = summaries_dir / "domain-planning" / "domain-plan-overview.json"
    overview_path.parent.mkdir(parents=True, exist_ok=True)
    overview_path.write_text(
        json.dumps(
            {
                "domains": [
                    {
                        "name": "interface",
                        "decoupledFilesPath": str(decoupled_files_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    target_root = tmp_path / "target"
    target_root.mkdir()
    output_dir = tmp_path / "domain-execution"

    payload = domain_execution_builder.build_execution(
        {
            "summaries_dir": str(summaries_dir),
            "meta": {"targetPath": str(target_root)},
        },
        output_dir,
    )

    assert payload["summary"]["completedDomains"] == 0
    assert payload["domains"][0]["status"] == "no-op"

    execution_json = json.loads(
        (output_dir / "interface" / "execution" / "execution.interface.json").read_text(encoding="utf-8")
    )
    assert execution_json["summary"]["resolvedTargetCount"] == 0
    assert execution_json["summary"]["pendingCount"] == 1
    assert execution_json["files"] == [
        {
            "sourcePath": "mospi_server.py",
            "targetCandidates": ["mospi_server.py", "mospi_server.ts"],
            "resolvedTarget": None,
            "status": "pending",
        }
    ]


def test_build_execution_marks_existing_concrete_target_file_present(tmp_path):
    summaries_dir = tmp_path / "migration-summaries"
    planning_dir = summaries_dir / "domain-planning" / "interface" / "planning"
    planning_dir.mkdir(parents=True)
    decoupled_files_path = planning_dir / "decoupled-files.interface.json"
    decoupled_files_path.write_text(json.dumps({"ownedFiles": ["mospi_server.py"]}), encoding="utf-8")

    overview_path = summaries_dir / "domain-planning" / "domain-plan-overview.json"
    overview_path.parent.mkdir(parents=True, exist_ok=True)
    overview_path.write_text(
        json.dumps(
            {
                "domains": [
                    {
                        "name": "interface",
                        "decoupledFilesPath": str(decoupled_files_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    target_root = tmp_path / "target"
    target_root.mkdir()
    target_file = target_root / "mospi_server.py"
    target_file.write_text("# migrated\n", encoding="utf-8")
    output_dir = tmp_path / "domain-execution"

    payload = domain_execution_builder.build_execution(
        {
            "summaries_dir": str(summaries_dir),
            "meta": {"targetPath": str(target_root)},
        },
        output_dir,
    )

    assert payload["summary"]["completedDomains"] == 1
    assert payload["domains"][0]["status"] == "completed"

    execution_json = json.loads(
        (output_dir / "interface" / "execution" / "execution.interface.json").read_text(encoding="utf-8")
    )
    assert execution_json["summary"]["resolvedTargetCount"] == 1
    assert execution_json["summary"]["pendingCount"] == 0
    assert execution_json["files"][0]["resolvedTarget"] == str(target_file.resolve())
    assert execution_json["files"][0]["status"] == "present"

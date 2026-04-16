from pathlib import Path

import migrate_wizard


def test_discover_style_guides_reads_repo_sections(tmp_path):
    styleguide_root = tmp_path / "styleguide"
    rust_dir = styleguide_root / "rust"
    sections_dir = rust_dir / "sections"
    sections_dir.mkdir(parents=True)
    (rust_dir / "style.md").write_text(
        "# Rust Style Guide\n\n## Naming And API Shape\n- `snake_case` for functions.\n",
        encoding="utf-8",
    )
    (sections_dir / "code-formatting-and-naming.md").write_text(
        "# Code Formatting and Naming\n\n## Naming Conventions\n- `snake_case` for values.\n- `UpperCamelCase` for types.\n",
        encoding="utf-8",
    )

    guides = migrate_wizard.discover_style_guides(styleguide_root)

    assert len(guides) == 1
    assert guides[0].language == "rust"
    assert guides[0].title == "Rust Style Guide"
    assert guides[0].style_path.endswith("styleguide/rust/style.md")
    assert guides[0].naming_path.endswith("styleguide/rust/sections/code-formatting-and-naming.md")
    assert guides[0].naming_preview == [
        "`snake_case` for values.",
        "`UpperCamelCase` for types.",
    ]


def test_build_non_negotiables_uses_selected_style_and_naming_entries():
    rules = migrate_wizard.build_non_negotiables(
        style_guides=[
            {
                "source": "repo",
                "label": "Rust Style Guide",
                "path": "styleguide/rust/style.md",
            },
            {
                "source": "custom-text",
                "text": "Keep public APIs stable",
            },
        ],
        naming_conventions=[
            {
                "source": "repo",
                "path": "styleguide/rust/sections/code-formatting-and-naming.md",
            },
            {
                "source": "custom-text",
                "text": "prefer snake_case in generated Python modules",
            },
        ],
        custom_items=["Preserve plugin compatibility"],
    )

    assert rules == [
        "Follow the Rust Style Guide at styleguide/rust/style.md.",
        "Keep public APIs stable.",
        "Use the naming conventions in styleguide/rust/sections/code-formatting-and-naming.md.",
        "Naming conventions: prefer snake_case in generated Python modules.",
        "Preserve plugin compatibility.",
    ]


def test_build_manifest_persists_styleguide_metadata(tmp_path, monkeypatch):
    source_path = tmp_path / "source"
    source_path.mkdir()
    target_path = tmp_path / "target"

    class _FixedDatetime:
        @staticmethod
        def now(_tz):
            import datetime as _dt

            return _dt.datetime(2026, 4, 16, 12, 0, 0, tzinfo=_dt.timezone.utc)

    monkeypatch.setattr(migrate_wizard, "datetime", _FixedDatetime)
    monkeypatch.setattr(migrate_wizard, "token_hex", lambda _: "a1b2c3")

    manifest = migrate_wizard.build_manifest(
        {
            "recipe": "example-generic",
            "sourcePath": str(source_path),
            "targetPath": str(target_path),
            "referencePath": None,
            "sourceOrigin": "/tmp/original-source",
            "sourceImportMode": "copy",
            "sourceDescription": "Python service",
            "targetDescription": "Rust service",
            "testCommand": "cargo test",
            "buildCommand": "cargo build",
            "lintCommand": "cargo clippy",
            "nonNegotiables": [
                "Follow the Rust Style Guide at styleguide/rust/style.md.",
                "Use the naming conventions in styleguide/rust/sections/code-formatting-and-naming.md.",
            ],
            "tier": "high",
            "domains": ["core", "tests"],
            "domainOrdering": {"core": [], "tests": ["core"]},
            "styleGuides": [{"source": "repo", "path": "styleguide/rust/style.md"}],
            "namingConventions": [{"source": "repo", "path": "styleguide/rust/sections/code-formatting-and-naming.md"}],
        }
    )

    assert manifest["meta"]["sessionId"] == "migrate-20260416-a1b2c3"
    assert manifest["meta"]["frameworkVersion"] == "tier-2"
    assert manifest["meta"]["sourceOrigin"] == "/tmp/original-source"
    assert manifest["meta"]["sourceImportMode"] == "copy"
    assert manifest["meta"]["styleGuides"] == [{"source": "repo", "path": "styleguide/rust/style.md"}]
    assert manifest["meta"]["namingConventions"] == [
        {"source": "repo", "path": "styleguide/rust/sections/code-formatting-and-naming.md"}
    ]
    assert list(manifest["phases"]) == [
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


def test_resolve_source_setup_copies_external_path_into_workspace(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    imports_root = repo_root / "experiments" / "imported-sources"
    external_root = tmp_path / "outside"
    external_source = external_root / "example-project"
    external_source.mkdir(parents=True)
    (external_source / "README.md").write_text("hello\n", encoding="utf-8")

    monkeypatch.setattr(migrate_wizard, "REPO_ROOT", repo_root)
    monkeypatch.setattr(migrate_wizard, "IMPORTS_ROOT", imports_root)

    setup = migrate_wizard.resolve_source_setup(str(external_source))

    assert setup.import_mode == "copy"
    assert setup.origin == str(external_source.resolve())
    assert setup.source_path == (imports_root / "example-project" / "source").resolve()
    assert setup.default_target_path == (imports_root / "example-project" / "migrated").resolve()
    assert (setup.source_path / "README.md").read_text(encoding="utf-8") == "hello\n"


def test_resolve_source_setup_clones_git_url_into_workspace(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    imports_root = repo_root / "experiments" / "imported-sources"

    monkeypatch.setattr(migrate_wizard, "REPO_ROOT", repo_root)
    monkeypatch.setattr(migrate_wizard, "IMPORTS_ROOT", imports_root)

    captured = {}

    def _fake_clone(source_url, destination):
        captured["source_url"] = source_url
        captured["destination"] = destination
        destination.mkdir(parents=True)
        (destination / "Cargo.toml").write_text("[package]\nname = 'demo'\n", encoding="utf-8")

    monkeypatch.setattr(migrate_wizard, "clone_source_repo", _fake_clone)

    setup = migrate_wizard.resolve_source_setup("https://github.com/example/demo.git")

    assert setup.import_mode == "git-clone"
    assert setup.origin == "https://github.com/example/demo.git"
    assert setup.source_path == (imports_root / "demo" / "source").resolve()
    assert setup.default_target_path == (imports_root / "demo" / "migrated").resolve()
    assert captured["source_url"] == "https://github.com/example/demo.git"
    assert captured["destination"] == imports_root / "demo" / "source"


def test_launch_orchestrator_detaches_stdin(tmp_path, monkeypatch):
    manifest_path = tmp_path / "migration-manifest.json"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    monkeypatch.setattr(
        migrate_wizard.mf,
        "load",
        lambda _path: {"meta": {"artifactsDir": str(artifacts_dir)}},
    )

    captured = {}

    class _Process:
        pid = 12345

    def _fake_popen(cmd, cwd, stdin, stdout, stderr, start_new_session):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return _Process()

    monkeypatch.setattr(migrate_wizard.subprocess, "Popen", _fake_popen)

    pid, log_path = migrate_wizard.launch_orchestrator(manifest_path, runtime="codex", model="gpt-5.4")

    assert pid == 12345
    assert log_path == artifacts_dir / "wizard-launch.log"
    assert captured["stdin"] is migrate_wizard.subprocess.DEVNULL
    assert captured["start_new_session"] is True
    assert captured["cmd"][-5:] == ["--non-interactive", "--runtime", "codex", "--model", "gpt-5.4"]

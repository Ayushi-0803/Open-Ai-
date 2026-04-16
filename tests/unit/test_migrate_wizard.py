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

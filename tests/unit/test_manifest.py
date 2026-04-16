import json
from pathlib import Path

import manifest


def _write_manifest(path: Path):
    payload = {
        "meta": {"status": "in_progress"},
        "phases": {"discovery": {"status": "pending"}},
        "checkpoints": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_update_phase_sets_status_and_meta(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    monkeypatch.setattr(manifest.time, "strftime", lambda *_: "2026-01-01T00:00:00Z")

    updated = manifest.update_phase(str(manifest_path), "discovery", "done")

    assert updated["phases"]["discovery"]["status"] == "done"
    assert updated["phases"]["discovery"]["completedAt"] == "2026-01-01T00:00:00Z"
    assert updated["meta"]["status"] == "complete"


def test_update_phase_sets_failed(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    monkeypatch.setattr(manifest.time, "strftime", lambda *_: "2026-01-01T00:00:00Z")

    updated = manifest.update_phase(str(manifest_path), "discovery", "failed", extra={"error": "boom"})

    assert updated["phases"]["discovery"]["status"] == "failed"
    assert updated["phases"]["discovery"]["error"] == "boom"
    assert updated["phases"]["discovery"]["failedAt"] == "2026-01-01T00:00:00Z"
    assert updated["meta"]["status"] == "failed"


def test_add_checkpoint_appends_entry(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)
    monkeypatch.setattr(manifest.time, "strftime", lambda *_: "2026-01-01T00:00:00Z")

    manifest.add_checkpoint(str(manifest_path), "discovery", "abc123")

    data = json.loads(manifest_path.read_text())
    assert data["checkpoints"] == [
        {"phase": "discovery", "gitRef": "abc123", "timestamp": "2026-01-01T00:00:00Z"}
    ]

import subprocess

import agent_runner


def test_run_with_heartbeat_calls_callback(monkeypatch):
    callbacks: list[int] = []

    class _FakeProcess:
        def __init__(self):
            self.returncode = 0
            self.calls = 0

        def communicate(self, input=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(cmd=["codex"], timeout=timeout)
            return ("ok", "")

        def kill(self):
            raise AssertionError("kill should not be called in this test")

    monkeypatch.setattr(agent_runner.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())

    result = agent_runner._run_with_heartbeat(
        ["codex", "exec"],
        prompt="prompt",
        cwd=".",
        runtime="codex",
        timeout=60,
        on_heartbeat=callbacks.append,
        heartbeat_interval=1,
    )

    assert result["exit_code"] == 0
    assert result["stdout"] == "ok"
    assert callbacks


def test_spawn_codex_uses_ephemeral_sessions(monkeypatch, tmp_path):
    skill_path = tmp_path / "skill.md"
    skill_path.write_text("Skill body\n", encoding="utf-8")
    captured = {}

    def _fake_run(cmd, *, prompt, cwd, runtime, timeout, on_heartbeat=None, heartbeat_interval=30):
        captured["cmd"] = cmd
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        captured["runtime"] = runtime
        return {"exit_code": 0, "stdout": "", "stderr": "", "runtime": runtime}

    monkeypatch.setattr(agent_runner, "_run_with_heartbeat", _fake_run)

    result = agent_runner.spawn_codex(str(skill_path), {"working_dir": str(tmp_path)})

    assert result["runtime"] == "codex"
    assert captured["cmd"][:4] == ["codex", "exec", "--ephemeral", "--full-auto"]

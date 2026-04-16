import threading
import time
from pathlib import Path

import agent_runner


def test_poll_for_completion_success(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def writer():
        time.sleep(0.02)
        (output_dir / "DONE.md").write_text("ok", encoding="utf-8")

    t = threading.Thread(target=writer)
    t.start()

    result = agent_runner.poll_for_completion(str(output_dir), ["DONE.md"], timeout=1, interval=0.01)

    t.join()
    assert result == "success"


def test_poll_for_completion_failure(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "ERROR").write_text("boom", encoding="utf-8")

    result = agent_runner.poll_for_completion(str(output_dir), ["DONE.md"], timeout=0.1, interval=0.01)

    assert result == "failure"

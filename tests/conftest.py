import sys
from pathlib import Path


def _add_scripts_to_path():
    repo_root = Path(__file__).resolve().parents[1]
    scripts_dir = repo_root / ".codex" / "scripts"
    scripts_str = str(scripts_dir)
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)


_add_scripts_to_path()

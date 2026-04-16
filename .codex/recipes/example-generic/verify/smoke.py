#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path


def main() -> int:
    source = Path(os.environ["SOURCE_PATH"])
    target = Path(os.environ["TARGET_PATH"])
    recipe_root = Path(os.environ["RECIPE_ROOT"])

    if not source.exists():
        print(f"source path missing: {source}")
        return 1
    if not target.exists():
        print(f"target path missing: {target}")
        return 1
    if not recipe_root.exists():
        print(f"recipe root missing: {recipe_root}")
        return 1

    print("smoke: source, target, and recipe root present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

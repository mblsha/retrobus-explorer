#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from test_component import CASES


def main() -> int:
    script = Path(__file__).resolve().parent / "test_component.py"
    for component in CASES:
        print(f"== Running {component} ==")
        subprocess.run([sys.executable, str(script), component, *sys.argv[1:]], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

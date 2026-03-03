#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    tool = here.parent / "spade-projects" / "tools" / "project.py"
    subprocess.run(
        [sys.executable, str(tool), "test-with-vcd", "--project", str(here), *sys.argv[1:]],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

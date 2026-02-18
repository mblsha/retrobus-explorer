#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    tools = here.parent / "tools" / "run_tb.py"
    subprocess.run(
        [
            str(tools),
            "--project",
            str(here),
            "--top",
            "main",
            "--test-module",
            "test_minimal",
        ],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

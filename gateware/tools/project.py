#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generic project entrypoint for test/build flows")
    parser.add_argument(
        "action",
        choices=["test-with-vcd", "build-with-spadeforge", "flash-with-spadeloader"],
    )
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    args, extra = parser.parse_known_args()
    args.extra = extra
    return args


TOOL_BY_ACTION = {
    "test-with-vcd": "run_tb.py",
    "build-with-spadeforge": "build_with_spadeforge.py",
    "flash-with-spadeloader": "flash_with_spadeloader.py",
}


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    tools_dir = Path(__file__).resolve().parent
    tool_name = TOOL_BY_ACTION[args.action]
    tool = tools_dir / tool_name

    cmd = [sys.executable, str(tool), "--project", str(project), *args.extra]
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

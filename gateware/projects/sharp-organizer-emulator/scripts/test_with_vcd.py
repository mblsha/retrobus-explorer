#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

project = Path(__file__).resolve().parents[1]
subprocess.run(
    [
        sys.executable,
        str(project.parents[1] / "tools/project.py"),
        "test-with-vcd",
        "--project",
        str(project),
        *sys.argv[1:],
    ],
    check=True,
)

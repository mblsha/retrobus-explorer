from __future__ import annotations

import subprocess
from pathlib import Path


def git_revision_date(repository: str | Path) -> str:
    """Return the current Git revision date, or a stable source-archive label."""

    try:
        return subprocess.check_output(
            ["git", "log", "-1", "--format=%cs"],
            cwd=repository,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNRELEASED"

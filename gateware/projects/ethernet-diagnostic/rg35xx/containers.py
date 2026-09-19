"""Running an aarch64 build in a container, for the builders that need one.

The kernel and the root filesystem are both built for the target rather than
for this host, and both are built from a shell script handed to the same kind
of container. What differs between them is the script, the mounts and the
environment, so that is all each builder states.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_IMAGE = "alpine:3.20"
# The H700 is aarch64 and the bench is Apple silicon, so the container runs
# natively for the target; anything else silently cross-builds or fails.
TARGET_PLATFORM = "linux/arm64"


def find_runner(explicit: str | None = None) -> list[str]:
    """Return the container command, preferring a plain docker or nerdctl."""
    if explicit:
        return explicit.split()
    for candidate in ("docker", "nerdctl"):
        if shutil.which(candidate):
            return [candidate]
    if shutil.which("colima"):
        return ["colima", "nerdctl", "--"]
    raise RuntimeError("need docker, nerdctl or colima to run the build")


def container_command(
    runner: list[str],
    image: str,
    script: str,
    mounts: list[tuple[Path | str, str, bool]],
    environment: dict[str, object],
    platform: str = TARGET_PLATFORM,
) -> list[str]:
    """Return the argv that runs `script` in `image` with those mounts.

    Each mount is (host path, container path, read-only). The order of both
    the mounts and the environment is the caller's, so the command a builder
    produces is stable and can be compared.
    """
    command = [*runner, "run", "--rm", "--platform", platform]
    for source, target, read_only in mounts:
        command += ["-v", f"{source}:{target}" + (":ro" if read_only else "")]
    for name, value in environment.items():
        command += ["-e", f"{name}={value}"]
    return [*command, image, "sh", "-c", script]


def run(command: list[str]) -> int:
    """Run a container build, letting its output reach the terminal."""
    return subprocess.run(command, check=False).returncode

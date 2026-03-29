#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import glob
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from project_meta import project_name

DEFAULT_BOARD = "alchitry_au"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flash a built Spade project through spadeloader-cli"
    )
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--bitstream", type=Path, help="Optional .bit file; defaults to the latest local forge output")
    parser.add_argument("--name", help="Design name shown in spadeloader history")
    parser.add_argument(
        "--board",
        default=DEFAULT_BOARD,
        help=f"Board name passed to spadeloader-cli (default: {DEFAULT_BOARD})",
    )
    parser.add_argument("--token", help="Optional auth token (or use SPADELOADER_TOKEN env var)")
    parser.add_argument("--auth-header", help="Optional auth header (or use SPADELOADER_AUTH_HEADER env var)")
    parser.add_argument("--cli", help="spadeloader-cli path/command")
    parser.add_argument("--server", help="Optional loader URL; omit for zeroconf discovery")
    parser.add_argument("--discover-timeout", default="10s", help="mDNS discovery timeout")
    args, extra = parser.parse_known_args()
    args.extra = extra
    return args


def resolve_cli(explicit: str | None) -> str:
    if explicit:
        return explicit
    path_cli = shutil.which("spadeloader-cli")
    if path_cli:
        return path_cli
    if Path("/tmp/spadeloader-cli").is_file():
        return "/tmp/spadeloader-cli"
    print("error: spadeloader-cli not found in PATH or /tmp/spadeloader-cli", file=sys.stderr)
    raise SystemExit(2)


def git_short_rev(project: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def default_design_name(project: Path) -> str:
    base = project_name(project).replace("_", "-")
    rev = git_short_rev(project)
    if rev:
        return f"{base}-{rev}"
    return base


def find_latest_bitstream(project: Path) -> Path | None:
    patterns = [
        "build/forge-output-*/*/design.bit",
        "build/forge-output-*/*/*.bit",
        "build/forge-output-*/*.bit",
        "build/**/*.bit",
    ]
    candidates: dict[Path, float] = {}
    for pattern in patterns:
        for match in glob.glob(str(project / pattern), recursive=True):
            path = Path(match).resolve()
            if path.is_file():
                candidates[path] = path.stat().st_mtime
    if not candidates:
        return None
    return max(candidates, key=lambda path: (candidates[path], str(path)))


def resolve_bitstream(project: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise SystemExit(f"error: bitstream not found: {candidate}")
        if candidate.suffix.lower() != ".bit":
            raise SystemExit(f"error: bitstream must be a .bit file: {candidate}")
        return candidate

    candidate = find_latest_bitstream(project)
    if candidate is None:
        raise SystemExit(
            "error: no local bitstream found under build/forge-output-*; "
            "run build-with-spadeforge first or pass --bitstream"
        )
    return candidate


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    bitstream = resolve_bitstream(project, args.bitstream)
    design_name = args.name or default_design_name(project)

    cmd = [
        resolve_cli(args.cli),
        "--board",
        args.board,
        "--name",
        design_name,
        "--bitstream",
        str(bitstream),
    ]

    token = args.token or os.environ.get("SPADELOADER_TOKEN")
    if token:
        cmd.extend(["--token", token])
    auth_header = args.auth_header or os.environ.get("SPADELOADER_AUTH_HEADER")
    if auth_header:
        cmd.extend(["--auth-header", auth_header])
    if args.server:
        cmd.extend(["--server", args.server])
    else:
        cmd.extend(["--discover-timeout", args.discover_timeout])
    cmd.extend(args.extra)

    print("+", shlex.join(cmd), flush=True)
    return subprocess.run(cmd, cwd=project, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

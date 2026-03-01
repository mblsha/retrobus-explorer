#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimal wrapper for spadeforge-cli build submission."
    )
    parser.add_argument("--token", help="API token (or use SPADEFORGE_TOKEN env var)")
    parser.add_argument("--cli", help="spadeforge-cli path/command (default: PATH or /tmp/spadeforge-cli)")
    parser.add_argument("--server", help="Optional server URL; omit to use zeroconf discovery")
    parser.add_argument("--discover-timeout", default="45s", help="mDNS discovery timeout")
    parser.add_argument("--output-dir", help="Optional output dir (default: build/forge-output-<UTC timestamp>)")
    parser.add_argument("--no-regenerate-xdc", action="store_true", help="Skip regenerating constraints/pins.xdc from [constraints].acf")
    parser.add_argument("--no-stream-events", action="store_true", help="Disable --stream-events")
    parser.add_argument("extra", nargs="*", help="Additional flags appended to spadeforge-cli")
    return parser.parse_args()


def resolve_cli(explicit: str | None) -> str:
    if explicit:
        return explicit
    from_path = shutil.which("spadeforge-cli")
    if from_path:
        return from_path
    if Path("/tmp/spadeforge-cli").is_file():
        return "/tmp/spadeforge-cli"
    print("error: spadeforge-cli not found in PATH or /tmp/spadeforge-cli", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    token = args.token or os.environ.get("SPADEFORGE_TOKEN")
    if not token:
        print("error: missing token; pass --token or set SPADEFORGE_TOKEN", file=sys.stderr)
        return 2

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else root / "build" / f"forge-output-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_zip = output_dir / "artifacts.zip"

    if not args.no_regenerate_xdc:
        subprocess.run(
            [
                sys.executable,
                str(root.parent / "spade-projects" / "tools" / "gen_project_xdc.py"),
                "--project",
                str(root),
            ],
            cwd=root,
            check=True,
        )

    subprocess.run(["swim", "build"], cwd=root, check=True)

    cmd = [
        resolve_cli(args.cli),
        "--token",
        token,
        "--top",
        "main",
        "--part",
        "xc7a35tftg256-1",
        "--source",
        str((root / "build/spade.sv").resolve()),
        "--xdc",
        str((root / "constraints/pins.xdc").resolve()),
        "--output-dir",
        str(output_dir),
        "--out-zip",
        str(out_zip),
    ]
    if not args.no_stream_events:
        cmd.append("--stream-events")
    if args.server:
        cmd.extend(["--server", args.server])
    else:
        cmd.extend(["--discover-timeout", args.discover_timeout])
    cmd.extend(args.extra)

    print("+", shlex.join(cmd))
    subprocess.run(cmd, cwd=root, check=True)
    print(f"artifacts: {out_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

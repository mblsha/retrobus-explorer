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
import tomllib
from datetime import UTC, datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Spade project through spadeforge-cli"
    )
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--token", help="API token (or use SPADEFORGE_TOKEN env var)")
    parser.add_argument("--cli", help="spadeforge-cli path/command")
    parser.add_argument("--server", help="Optional server URL; omit for zeroconf discovery")
    parser.add_argument("--discover-timeout", default="45s", help="mDNS discovery timeout")
    parser.add_argument("--top", default="main")
    parser.add_argument("--part", default="xc7a35tcsg324-1")
    parser.add_argument("--source", default="build/spade.sv")
    parser.add_argument("--xdc", default="constraints/pins.xdc")
    parser.add_argument("--output-dir", help="Artifact output directory")
    parser.add_argument("--no-stream-events", action="store_true")
    parser.add_argument("extra", nargs="*", help="Extra flags passed to spadeforge-cli")
    return parser.parse_args()


def resolve_cli(explicit: str | None) -> str:
    if explicit:
        return explicit
    path_cli = shutil.which("spadeforge-cli")
    if path_cli:
        return path_cli
    if Path("/tmp/spadeforge-cli").is_file():
        return "/tmp/spadeforge-cli"
    print("error: spadeforge-cli not found in PATH or /tmp/spadeforge-cli", file=sys.stderr)
    raise SystemExit(2)


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def resolve_extra_verilog(project: Path) -> list[Path]:
    config = tomllib.loads((project / "swim.toml").read_text())
    extras: list[Path] = []
    for pattern in config.get("verilog", {}).get("sources", []):
        for match in sorted(project.glob(pattern)):
            if match.is_file():
                extras.append(match.resolve())
    return extras


def build_source_bundle(project: Path, main_source: Path, extra_sources: list[Path]) -> Path:
    if not extra_sources:
        return main_source

    bundle = project / "build" / "spade_bundle.sv"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with bundle.open("w") as out:
        out.write(main_source.read_text())
        out.write("\n")
        for src in extra_sources:
            out.write(f"\n// ----- BEGIN INCLUDED VERILOG: {src} -----\n")
            out.write(src.read_text())
            out.write(f"\n// ----- END INCLUDED VERILOG: {src} -----\n")
    return bundle


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    token = args.token or os.environ.get("SPADEFORGE_TOKEN")
    if not token:
        print("error: missing token; pass --token or set SPADEFORGE_TOKEN", file=sys.stderr)
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else project / f"forge-output-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    out_zip = output_dir / "artifacts.zip"

    run(["swim", "build"], cwd=project)
    main_source = (project / args.source).resolve()
    bundled_source = build_source_bundle(project, main_source, resolve_extra_verilog(project))

    cmd = [
        resolve_cli(args.cli),
        "--token",
        token,
        "--top",
        args.top,
        "--part",
        args.part,
        "--source",
        str(bundled_source),
        "--xdc",
        str((project / args.xdc).resolve()),
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
    run(cmd, cwd=project)
    print(f"artifacts: {out_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

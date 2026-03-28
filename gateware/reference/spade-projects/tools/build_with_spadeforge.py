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

from project_meta import project_name
from project_meta import resolve_verilog_sources
from project_meta import tooling_top

BOARD_PARTS: dict[str, str] = {
    "alchitry_au": "xc7a35tftg256-1",
    "alchitry_au_plus": "xc7a100tftg256-1",
    "alchitry_au_v2": "xc7a35tftg256-2",
    "alchitry_pt_v2": "xc7a100tfgg484-2",
}

BOARD_ALIASES: dict[str, str] = {
    "au": "alchitry_au",
    "au1": "alchitry_au",
    "alchitry_au1": "alchitry_au",
    "au_plus": "alchitry_au_plus",
    "alchitry_auplus": "alchitry_au_plus",
    "au_v2": "alchitry_au_v2",
    "auv2": "alchitry_au_v2",
    "alchitry_auv2": "alchitry_au_v2",
    "pt_v2": "alchitry_pt_v2",
    "ptv2": "alchitry_pt_v2",
    "alchitry_ptv2": "alchitry_pt_v2",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Spade project through spadeforge-cli"
    )
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--token", help="API token (or use SPADEFORGE_TOKEN env var)")
    parser.add_argument("--cli", help="spadeforge-cli path/command")
    parser.add_argument("--server", help="Optional server URL; omit for zeroconf discovery")
    parser.add_argument("--discover-timeout", default="45s", help="mDNS discovery timeout")
    parser.add_argument("--top", help="Top module name (default: tooling.top or main)")
    parser.add_argument(
        "--board",
        default="alchitry_au",
        help="Board alias (default: alchitry_au). Supported: alchitry_au, alchitry_au_plus, alchitry_au_v2, alchitry_pt_v2",
    )
    parser.add_argument("--part", help="Target FPGA part (overrides --board)")
    parser.add_argument("--source", default="build/spade.sv")
    parser.add_argument("--xdc", default="constraints/pins.xdc")
    parser.add_argument("--output-dir", help="Artifact output directory")
    parser.add_argument("--no-regenerate-xdc", action="store_true", help="Skip regenerating constraints/pins.xdc from [constraints].acf")
    parser.add_argument("--no-stream-events", action="store_true")
    parser.add_argument("extra", nargs="*", help="Extra flags passed to spadeforge-cli")
    return parser.parse_args()


def resolve_target_part(explicit_part: str | None, board: str) -> str:
    if explicit_part:
        return explicit_part

    key = board.strip().lower().replace("-", "_").replace("+", "_plus")
    canonical = BOARD_ALIASES.get(key, key)
    part = BOARD_PARTS.get(canonical)
    if part:
        return part

    supported = ", ".join(sorted(BOARD_PARTS.keys()))
    raise SystemExit(
        f"error: unsupported --board {board!r}; supported values: {supported}"
    )


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


def ordered_sources(main_source: Path, extra_sources: list[Path]) -> list[Path]:
    # Keep external Verilog first, then generated Spade source last.
    # This avoids default_nettype bleed-through into legacy Verilog modules.
    ordered = [*extra_sources, main_source]
    seen: set[Path] = set()
    deduped: list[Path] = []
    for src in ordered:
        resolved = src.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    top = tooling_top(project, args.top)
    part = resolve_target_part(args.part, args.board)
    token = args.token or os.environ.get("SPADEFORGE_TOKEN")
    if not token:
        print("error: missing token; pass --token or set SPADEFORGE_TOKEN", file=sys.stderr)
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else project / "build" / f"forge-output-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    out_zip = output_dir / "artifacts.zip"

    if not args.no_regenerate_xdc:
        run(
            [
                sys.executable,
                str(Path(__file__).resolve().parent / "gen_project_xdc.py"),
                "--project",
                str(project),
                "--allow-missing",
            ],
            cwd=project,
        )

    run(["swim", "build"], cwd=project)
    main_source = (project / args.source).resolve()
    sources = ordered_sources(main_source, resolve_verilog_sources(project))

    cmd = [
        resolve_cli(args.cli),
        "--project",
        project_name(project),
        "--token",
        token,
        "--top",
        top,
        "--part",
        part,
        "--xdc",
        str((project / args.xdc).resolve()),
        "--output-dir",
        str(output_dir),
        "--out-zip",
        str(out_zip),
    ]
    for src in sources:
        cmd.extend(["--source", str(src)])
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

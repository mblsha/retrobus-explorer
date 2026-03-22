#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_GLASGOW_DIR = Path.home() / "src" / "github" / "glasgow" / "software"
DEFAULT_BAUD = 1200
DEFAULT_VOLTAGE = 5.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send a BASIC .bas listing to the PC-E500 using the local Glasgow checkout. "
            'Run LOAD"COM:" on the calculator before starting this script.'
        )
    )
    parser.add_argument(
        "listing",
        nargs="?",
        type=Path,
        help="path to a .bas listing file; if omitted, read the listing from stdin",
    )
    parser.add_argument(
        "--glasgow-dir",
        type=Path,
        default=DEFAULT_GLASGOW_DIR,
        help=f"path to the Glasgow software checkout (default: {DEFAULT_GLASGOW_DIR})",
    )
    parser.add_argument("--serial", help="use the Glasgow device with serial number SERIAL")
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD,
        help=f"UART baud rate (default: {DEFAULT_BAUD})",
    )
    parser.add_argument(
        "--voltage",
        type=float,
        default=DEFAULT_VOLTAGE,
        help=f"bank-B voltage in volts (default: {DEFAULT_VOLTAGE:g})",
    )
    parser.add_argument(
        "--quiet-instructions",
        action="store_true",
        help="do not print the calculator-side LOAD command before starting",
    )
    return parser.parse_args()


def resolve_glasgow_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not (resolved / "pyproject.toml").exists() or not (resolved / "glasgow").is_dir():
        raise SystemExit(f"Glasgow checkout not found at {resolved}")
    return resolved


def read_listing(listing_path: Path | None) -> bytes:
    if listing_path is None:
        return sys.stdin.buffer.read()

    resolved = listing_path.expanduser()
    try:
        return resolved.read_bytes()
    except OSError as exc:
        raise SystemExit(f"failed to read {resolved}: {exc}") from exc


def normalize_listing(raw: bytes) -> bytes:
    normalized = raw.rstrip(b"\x1A")
    normalized = normalized.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized and not normalized.endswith(b"\n"):
        normalized += b"\n"
    normalized = normalized.replace(b"\n", b"\r\n")
    return normalized + b"\x1A"


def build_command(args: argparse.Namespace, glasgow_dir: Path) -> list[str]:
    command = ["uv", "run", "--directory", str(glasgow_dir), "glasgow"]
    if args.serial is not None:
        command.extend(["--serial", args.serial])
    command.extend(
        [
            "run",
            "uart",
            "-V",
            f"B={args.voltage:g}",
            "--rx",
            "B2#",
            "--tx",
            "B3#",
            "--rts",
            "B1#",
            "-b",
            str(args.baud),
            "tty",
        ]
    )
    return command


def build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    return env


def main() -> int:
    args = parse_args()
    if shutil.which("uv") is None:
        raise SystemExit("uv was not found in PATH")

    glasgow_dir = resolve_glasgow_dir(args.glasgow_dir)
    payload = normalize_listing(read_listing(args.listing))
    if not args.quiet_instructions:
        print('PC-E500 command: LOAD"COM:"', file=sys.stderr)
        print(f"Sending {len(payload)} bytes including the final 0x1A marker.", file=sys.stderr)

    command = build_command(args, glasgow_dir)
    return subprocess.run(
        command,
        input=payload,
        env=build_subprocess_env(),
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())

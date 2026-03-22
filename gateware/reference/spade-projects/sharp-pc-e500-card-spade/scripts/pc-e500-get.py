#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


DEFAULT_GLASGOW_DIR = Path.home() / "src" / "github" / "glasgow" / "software"
DEFAULT_BAUD = 1200
DEFAULT_VOLTAGE = 5.0
TERMINATOR = b"\x1A"
READ_CHUNK_SIZE = 4096


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print PC-E500 UART traffic to the terminal using the local Glasgow checkout, "
            "stopping automatically when the calculator sends 0x1A. "
            'Run SAVE"COM:1200,N,8,1,A,L,&1A,X,N" on the calculator after starting this script.'
        )
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
        help="do not print the calculator-side SAVE command before starting",
    )
    return parser.parse_args()


def resolve_glasgow_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not (resolved / "pyproject.toml").exists() or not (resolved / "glasgow").is_dir():
        raise SystemExit(f"Glasgow checkout not found at {resolved}")
    return resolved


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
            "--cts",
            "B0#",
            "-b",
            str(args.baud),
            "tty",
            "--stream",
        ]
    )
    return command


def build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    return env


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    if os.name == "posix":
        process.send_signal(signal.SIGINT)
    else:
        process.terminate()

    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)


def run_until_terminator(command: list[str]) -> int:
    process = subprocess.Popen(
        command,
        env=build_subprocess_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        bufsize=0,
    )
    saw_terminator = False

    try:
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(READ_CHUNK_SIZE)
            if not chunk:
                break

            terminator_at = chunk.find(TERMINATOR)
            if terminator_at == -1:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                continue

            if terminator_at:
                sys.stdout.buffer.write(chunk[:terminator_at])
                sys.stdout.buffer.flush()

            saw_terminator = True
            print("saw 0x1A terminator; stopping UART capture", file=sys.stderr)
            stop_process(process)
            break
    finally:
        if process.stdout is not None:
            process.stdout.close()

    return_code = process.wait()
    if saw_terminator:
        return 0

    print("UART stream ended before the 0x1A terminator was received", file=sys.stderr)
    return return_code or 1


def main() -> int:
    args = parse_args()
    if shutil.which("uv") is None:
        raise SystemExit("uv was not found in PATH")

    glasgow_dir = resolve_glasgow_dir(args.glasgow_dir)
    if not args.quiet_instructions:
        print('PC-E500 command: SAVE"COM:1200,N,8,1,A,L,&1A,X,N"', file=sys.stderr)
        print("Printing received UART data to stdout until 0x1A arrives.", file=sys.stderr)

    command = build_command(args, glasgow_dir)
    try:
        return run_until_terminator(command)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

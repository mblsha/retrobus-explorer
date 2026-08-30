#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_ASSEMBLER_DIR = Path.home() / "src" / "github" / "binja-esr-tests" / "public-src"
DEFAULT_AU1_SCRIPT = Path(__file__).with_name("au1_usb_uart_probe.py")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CARD_ROM_BASE = 0x10000
CARD_ROM_SIZE = 0x800
CARD_ROM_LAST = CARD_ROM_BASE + CARD_ROM_SIZE - 1
DEFAULT_FILL_BYTE = 0xFF
DEFAULT_TIMING = 5
DEFAULT_CONTROL_TIMING = 10

ASSEMBLER_SNIPPET = """
import json
import sys
from pathlib import Path

from sc62015.pysc62015.sc_asm import Assembler

source = Path(sys.argv[1]).read_text()
binfile = Assembler().assemble(source)
print(json.dumps([
    {"address": segment.address, "data_hex": segment.data.hex()}
    for segment in binfile.segments
]))
"""


def parse_int(text: str) -> int:
    cleaned = text.strip().replace("_", "")
    if not cleaned:
        raise argparse.ArgumentTypeError("expected a numeric value")
    try:
        return int(cleaned, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid numeric value {text!r}") from exc


def parse_byte(text: str) -> int:
    value = parse_int(text)
    if not 0 <= value <= 0xFF:
        raise argparse.ArgumentTypeError("fill byte must be in the range 0..255")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble SC62015 card-ROM code via ~/src/github/binja-esr-tests/public-src "
            "and optionally program it into the Au1-backed FPGA card ROM."
        )
    )
    parser.add_argument("source", type=Path, help="path to the SC62015 assembly source")
    parser.add_argument(
        "--out",
        type=Path,
        help="path for the assembled binary image; defaults to SOURCE with a .bin suffix",
    )
    parser.add_argument(
        "--assembler-dir",
        type=Path,
        default=DEFAULT_ASSEMBLER_DIR,
        help=f"path to the SC62015 assembler checkout (default: {DEFAULT_ASSEMBLER_DIR})",
    )
    parser.add_argument(
        "--fill-byte",
        type=parse_byte,
        default=DEFAULT_FILL_BYTE,
        help=f"byte value used to fill address gaps between segments (default: 0x{DEFAULT_FILL_BYTE:02X})",
    )
    parser.add_argument(
        "--program",
        action="store_true",
        help="program the assembled image into the FPGA card-ROM window after assembling",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify the programmed bytes by reading them back over the Au1 UART",
    )
    parser.add_argument(
        "--no-fast",
        action="store_false",
        dest="fast",
        help="disable the fast concatenated-write path when programming",
    )
    parser.set_defaults(fast=True)
    parser.add_argument(
        "--timing",
        type=int,
        default=DEFAULT_TIMING,
        help=(
            "set normal CE1/CE6 memory timing to this many 10 ns units before "
            f"programming (default: {DEFAULT_TIMING})"
        ),
    )
    parser.add_argument(
        "--no-timing",
        action="store_const",
        const=None,
        dest="timing",
        help="do not issue a timing command before programming",
    )
    parser.add_argument(
        "--control-timing",
        type=int,
        default=DEFAULT_CONTROL_TIMING,
        help=(
            "set CE6 control-page write timing to this many 10 ns units before "
            f"programming (default: {DEFAULT_CONTROL_TIMING})"
        ),
    )
    parser.add_argument(
        "--no-control-timing",
        action="store_const",
        const=None,
        dest="control_timing",
        help="do not issue a control-timing command before programming",
    )
    parser.add_argument("--port", help="serial port to forward to au1_usb_uart_probe.py")
    parser.add_argument(
        "--baud",
        type=int,
        default=1_000_000,
        help="UART baud rate to forward to au1_usb_uart_probe.py",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="reply timeout to forward to au1_usb_uart_probe.py",
    )
    return parser.parse_args()


def resolve_existing_dir(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise SystemExit(f"{label} not found at {resolved}")
    return resolved


def resolve_existing_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SystemExit(f"{label} not found at {resolved}")
    return resolved


def build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["FORCE_BINJA_MOCK"] = "1"
    env["UV_NO_CONFIG"] = "1"
    return env


def run_checked(command: list[str], *, cwd: Path | None = None, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=build_subprocess_env(),
        capture_output=capture_output,
        text=True,
    )
    if completed.returncode != 0:
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    return completed


def assemble_segments(source_path: Path, assembler_dir: Path) -> list[tuple[int, bytes]]:
    if shutil.which("uv") is None:
        raise SystemExit("uv was not found in PATH")

    completed = run_checked(
        ["uv", "run", "python", "-c", ASSEMBLER_SNIPPET, str(source_path)],
        cwd=assembler_dir,
        capture_output=True,
    )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"assembler returned invalid JSON: {exc}") from exc

    segments: list[tuple[int, bytes]] = []
    for item in payload:
        segments.append((int(item["address"]), bytes.fromhex(item["data_hex"])))
    if not segments:
        raise SystemExit("assembler produced no output segments")
    return sorted(segments, key=lambda item: item[0])


def build_card_rom_image(segments: list[tuple[int, bytes]], fill_byte: int) -> tuple[int, bytes]:
    start = min(address for address, _ in segments)
    end = max(address + len(data) for address, data in segments)
    if start < CARD_ROM_BASE or end - 1 > CARD_ROM_LAST:
        raise SystemExit(
            f"assembled image spans {start:05X}..{end - 1:05X}, "
            f"outside card ROM window {CARD_ROM_BASE:05X}..{CARD_ROM_LAST:05X}"
        )

    image = bytearray([fill_byte]) * (end - start)
    written = [False] * (end - start)

    for address, data in segments:
        offset = address - start
        for index, value in enumerate(data):
            image_index = offset + index
            if written[image_index] and image[image_index] != value:
                raise SystemExit(f"overlapping segments disagree at {start + image_index:05X}")
            image[image_index] = value
            written[image_index] = True

    return start, bytes(image)


def default_output_path(source_path: Path) -> Path:
    return PROJECT_ROOT / "build" / "asm" / f"{source_path.stem}.bin"


def write_output(path: Path, data: bytes) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(data)
    return resolved


def run_au1_subcommand(
    au1_script: Path,
    common_args: argparse.Namespace,
    subcommand: list[str],
) -> None:
    command = [
        "uv",
        "run",
        str(au1_script),
        "--baud",
        str(common_args.baud),
        "--timeout",
        str(common_args.timeout),
    ]
    if common_args.port is not None:
        command.extend(["--port", common_args.port])
    command.extend(subcommand)

    run_checked(command)


def main() -> int:
    args = parse_args()
    source_path = resolve_existing_file(args.source, "assembly source")
    assembler_dir = resolve_existing_dir(args.assembler_dir, "assembler checkout")
    au1_script = resolve_existing_file(DEFAULT_AU1_SCRIPT, "Au1 UART helper")

    segments = assemble_segments(source_path, assembler_dir)
    start_address, image = build_card_rom_image(segments, args.fill_byte)
    end_address = start_address + len(image) - 1
    output_path = write_output(args.out or default_output_path(source_path), image)

    print(
        f"assembled {len(image)} byte(s) for {start_address:05X}..{end_address:05X} "
        f"into {output_path}",
        file=sys.stderr,
    )
    print(f"calculator entry point: CALL &{start_address:05X}", file=sys.stderr)

    if not args.program:
        return 0

    if args.timing is not None:
        run_au1_subcommand(au1_script, args, ["timing", str(args.timing)])
    if args.control_timing is not None:
        run_au1_subcommand(
            au1_script,
            args,
            ["control-timing", str(args.control_timing)],
        )

    program_command = [
        "program",
        str(output_path),
        "--start",
        f"0x{start_address:05X}",
    ]
    if args.fast:
        program_command.append("--fast")
    if args.verify:
        program_command.append("--verify")
    run_au1_subcommand(au1_script, args, program_command)

    print(
        f"programmed card ROM at {start_address:05X}..{end_address:05X}; "
        f"run CALL &{start_address:05X} on the PC-E500",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

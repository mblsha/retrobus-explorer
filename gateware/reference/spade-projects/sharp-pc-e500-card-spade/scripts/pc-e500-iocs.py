#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path


DEFAULT_SOCKET = Path.home() / ".cache" / "pc-e500-expd.sock"
PROJECT_DIR = Path(__file__).resolve().parent.parent
EXPERIMENT_SCRIPT = PROJECT_DIR / "experiments" / "iocs_sequence.py"


def send_request(socket_path: Path, payload: dict[str, object]) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        response = bytearray()
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if b"\n" in chunk:
                break
    if not response:
        raise RuntimeError("daemon returned no response")
    return json.loads(response.decode("utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run structured PC-E500 IOCS experiments")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET, help=f"unix socket path (default: {DEFAULT_SOCKET})")
    parser.add_argument("--verbose", action="store_true", help="print full JSON response")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--name", default="iocs_sequence")
    common.add_argument("--timing", type=lambda value: int(value, 0), default=5)
    common.add_argument("--control-timing", type=lambda value: int(value, 0), default=10)
    common.add_argument("--timeout-s", type=float, default=2.0)
    common.add_argument("--start-tag", type=lambda value: int(value, 0), default=0xC1)
    common.add_argument("--stop-tag", type=lambda value: int(value, 0), default=0xC2)
    common.add_argument("--flags", type=lambda value: int(value, 0), default=0)
    common.add_argument("--no-ft-capture", action="store_true")
    common.add_argument("--no-mask-interrupts", action="store_true", help="leave interrupts enabled during IOCS sequence")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("clear", parents=[common], help="invoke IOCS 51h clear display")

    cursor_parser = subparsers.add_parser("cursor", parents=[common], help="invoke IOCS 44h set cursor")
    cursor_parser.add_argument("--x", required=True, type=lambda value: int(value, 0))
    cursor_parser.add_argument("--y", required=True, type=lambda value: int(value, 0))
    cursor_parser.add_argument("--cx", type=lambda value: int(value, 0), default=0)

    text_parser = subparsers.add_parser("text", parents=[common], help="set cursor and print text")
    text_parser.add_argument("--x", required=True, type=lambda value: int(value, 0))
    text_parser.add_argument("--y", required=True, type=lambda value: int(value, 0))
    text_parser.add_argument("--text", required=True)
    text_parser.add_argument("--cx", type=lambda value: int(value, 0), default=0)
    text_parser.add_argument("--clear-first", action="store_true")

    clear_text_parser = subparsers.add_parser("clear-text", parents=[common], help="clear display then print text")
    clear_text_parser.add_argument("--x", required=True, type=lambda value: int(value, 0))
    clear_text_parser.add_argument("--y", required=True, type=lambda value: int(value, 0))
    clear_text_parser.add_argument("--text", required=True)
    clear_text_parser.add_argument("--cx", type=lambda value: int(value, 0), default=0)

    spec_parser = subparsers.add_parser("spec", parents=[common], help="run a JSON spec file")
    spec_parser.add_argument("spec_path")

    run_parser = subparsers.add_parser("run", parents=[common], help="generic IOCS sequence")
    run_parser.add_argument("--call", action="append", default=[], help="call spec like 0x42,bl=0,bh=0,text=HELLO")
    run_parser.add_argument("--cx", type=lambda value: int(value, 0))

    return parser


def build_script_args(args: argparse.Namespace) -> list[str]:
    script_args = [
        "--name", args.name,
        "--timing", hex(args.timing),
        "--control-timing", hex(args.control_timing),
        "--timeout-s", str(args.timeout_s),
        "--start-tag", hex(args.start_tag),
        "--stop-tag", hex(args.stop_tag),
        "--flags", hex(args.flags),
    ]
    if args.no_ft_capture:
        script_args.append("--no-ft-capture")
    if args.no_mask_interrupts:
        script_args.append("--no-mask-interrupts")

    if args.command == "clear":
        return script_args + ["clear"]
    if args.command == "cursor":
        return script_args + ["cursor", "--x", hex(args.x), "--y", hex(args.y), "--cx", hex(args.cx)]
    if args.command == "text":
        payload = script_args + ["text", "--x", hex(args.x), "--y", hex(args.y), "--text", args.text, "--cx", hex(args.cx)]
        if args.clear_first:
            payload.append("--clear-first")
        return payload
    if args.command == "clear-text":
        return script_args + ["clear-text", "--x", hex(args.x), "--y", hex(args.y), "--text", args.text, "--cx", hex(args.cx)]
    if args.command == "spec":
        return script_args + ["spec", args.spec_path]
    if args.command == "run":
        payload = script_args + ["run"]
        if args.cx is not None:
            payload += ["--cx", hex(args.cx)]
        for item in args.call:
            payload += ["--call", item]
        return payload
    raise RuntimeError(f"unknown command {args.command!r}")


def format_summary(response: dict[str, object]) -> str:
    parsed = response.get("parsed") or {}
    measurement = parsed.get("first_measurement") or {}
    display_summary = parsed.get("display_summary") or {}
    lines = [
        f"experiment: {response.get('experiment', '<unknown>')}",
        f"status: {response.get('status', '<unknown>')}",
    ]
    begin_line = response.get("begin_line")
    end_line = response.get("end_line")
    if begin_line or end_line:
        lines.append(f"uart: {begin_line} -> {end_line}")
    if measurement:
        lines.append(
            "measurement: "
            f"ticks={measurement.get('ticks')} "
            f"ce_events={measurement.get('ce_events')} "
            f"addr_uart={measurement.get('addr_uart')} "
            f"FO={measurement.get('ft_overflow')}"
        )
    if parsed:
        lines.append(
            "ft: "
            f"words={parsed.get('ft_word_count')} "
            f"bytes={parsed.get('ft_raw_bytes')} "
            f"chunks={parsed.get('ft_chunk_count')}"
        )
    if display_summary:
        lines.append(f"lcd: writes={display_summary.get('lcd_write_count')}")
        text_lines = display_summary.get("lcd_text_lines") or []
        for index, line in enumerate(text_lines):
            if line:
                lines.append(f"lcd_row{index}: {line}")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    request = {
        "action": "run",
        "script": str(EXPERIMENT_SCRIPT),
        "script_args": build_script_args(args),
    }
    response = send_request(args.socket, request)
    if args.verbose:
        print(json.dumps(response, indent=2, sort_keys=True))
    else:
        print(format_summary(response))
    if response.get("status") in {"error", "timeout"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5"]
# ///
from __future__ import annotations

import argparse
import sys
import time

import serial


WINDOW_BASE = 0x040000
WINDOW_END = 0x080000


def parse_addr(text: str) -> int:
    if len(text) != 6:
        raise ValueError(f"expected 6 hex digits, got {text!r}")
    addr = int(text, 16)
    if not WINDOW_BASE <= addr < WINDOW_END:
        raise ValueError(f"address must be in 040000-07FFFF, got {text}")
    return addr


def parse_byte(text: str) -> int:
    if len(text) != 2:
        raise ValueError(f"expected 2 hex digits, got {text!r}")
    return int(text, 16)


def normalize_pin(text: str) -> str:
    pin = text.upper()
    valid = {"C1", "C6", "OE", "RW"}
    if pin in valid:
        return pin
    if len(pin) == 2 and pin[0] == "D" and pin[1].isdigit() and 0 <= int(pin[1]) <= 7:
        return pin
    if len(pin) == 2 and pin[0] == "A":
        if pin[1].isdigit() and 0 <= int(pin[1]) <= 9:
            return pin
        if "A" <= pin[1] <= "H":
            return pin
    raise ValueError(f"expected pin like C1/C6/OE/RW/A0..AH/D0..D7, got {text!r}")


def send_line(port: str, baud: int, line: str, timeout: float = 0.5) -> str:
    with serial.Serial(port, baudrate=baud, timeout=timeout) as ser:
        ser.write(line.encode("ascii") + b"\r")
        raw = ser.readline()
    return raw.decode("ascii", errors="replace")


def send_lines(port: str, baud: int, line: str, timeout: float = 0.2) -> str:
    with serial.Serial(port, baudrate=baud, timeout=timeout) as ser:
        ser.write(line.encode("ascii") + b"\r")
        parts: list[str] = []
        while True:
            raw = ser.readline()
            if not raw:
                break
            parts.append(raw.decode("ascii", errors="replace"))
            if parts[-1] == "END\r\n":
                break
    return "".join(parts)


def cmd_read(port: str, baud: int, addr_text: str) -> int:
    addr = parse_addr(addr_text)
    sys.stdout.write(send_line(port, baud, f"r{addr:06X}"))
    return 0


def cmd_write(port: str, baud: int, addr_text: str, value_text: str) -> int:
    addr = parse_addr(addr_text)
    value = parse_byte(value_text)
    sys.stdout.write(send_line(port, baud, f"w{addr:06X}={value:02X}"))
    return 0


def cmd_dump(port: str, baud: int, addr_text: str, count: int, delay: float) -> int:
    addr = parse_addr(addr_text)
    for idx in range(count):
        sys.stdout.write(send_line(port, baud, f"r{addr + idx:06X}"))
        if delay > 0:
            time.sleep(delay)
    return 0


def cmd_present(port: str, baud: int, enabled: bool) -> int:
    sys.stdout.write(send_line(port, baud, "p1" if enabled else "p0"))
    return 0


def cmd_mode(port: str, baud: int, mode: int) -> int:
    sys.stdout.write(send_line(port, baud, f"m{mode}"))
    return 0


def cmd_pin(port: str, baud: int, pin_text: str) -> int:
    pin = normalize_pin(pin_text)
    sys.stdout.write(send_line(port, baud, f"p{pin}"))
    return 0


def cmd_all_pins(port: str, baud: int) -> int:
    sys.stdout.write(send_lines(port, baud, "a"))
    return 0


def cmd_clear_pins(port: str, baud: int) -> int:
    sys.stdout.write(send_line(port, baud, "c"))
    return 0


def cmd_status(port: str, baud: int) -> int:
    sys.stdout.write(send_line(port, baud, "?"))
    return 0


def cmd_help(port: str, baud: int) -> int:
    sys.stdout.write(send_lines(port, baud, "h"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Host utility for sharp-pc-e500-card-spade")
    sub = parser.add_subparsers(dest="cmd", required=True)

    read_parser = sub.add_parser("read", help="read one byte from a card-space address")
    read_parser.add_argument("--port", required=True)
    read_parser.add_argument("--baud", type=int, default=1_000_000)
    read_parser.add_argument("addr")

    write_parser = sub.add_parser("write", help="write one byte to a card-space address")
    write_parser.add_argument("--port", required=True)
    write_parser.add_argument("--baud", type=int, default=1_000_000)
    write_parser.add_argument("addr")
    write_parser.add_argument("value")

    dump_parser = sub.add_parser("dump", help="read a run of bytes")
    dump_parser.add_argument("--port", required=True)
    dump_parser.add_argument("--baud", type=int, default=1_000_000)
    dump_parser.add_argument("--delay", type=float, default=0.0)
    dump_parser.add_argument("addr")
    dump_parser.add_argument("count", type=int)

    present_parser = sub.add_parser("present", help="toggle whether the card is visible on the bus")
    present_parser.add_argument("--port", required=True)
    present_parser.add_argument("--baud", type=int, default=1_000_000)
    present_parser.add_argument("state", choices=["on", "off"])

    mode_parser = sub.add_parser("mode", help="switch between sampled Saleae mode and USB counter mode")
    mode_parser.add_argument("--port", required=True)
    mode_parser.add_argument("--baud", type=int, default=1_000_000)
    mode_parser.add_argument("state", choices=["sampled", "counts"])

    pin_parser = sub.add_parser("pin", help="read and clear one pin transition counter")
    pin_parser.add_argument("--port", required=True)
    pin_parser.add_argument("--baud", type=int, default=1_000_000)
    pin_parser.add_argument("pin")

    all_pins_parser = sub.add_parser("all-pins", help="dump all pin transition counters")
    all_pins_parser.add_argument("--port", required=True)
    all_pins_parser.add_argument("--baud", type=int, default=1_000_000)

    clear_parser = sub.add_parser("clear-pins", help="clear all pin transition counters")
    clear_parser.add_argument("--port", required=True)
    clear_parser.add_argument("--baud", type=int, default=1_000_000)

    status_parser = sub.add_parser("status", help="read bridge status counters")
    status_parser.add_argument("--port", required=True)
    status_parser.add_argument("--baud", type=int, default=1_000_000)

    help_parser = sub.add_parser("help-cmd", help="print device help")
    help_parser.add_argument("--port", required=True)
    help_parser.add_argument("--baud", type=int, default=1_000_000)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "read":
        return cmd_read(args.port, args.baud, args.addr)
    if args.cmd == "write":
        return cmd_write(args.port, args.baud, args.addr, args.value)
    if args.cmd == "dump":
        return cmd_dump(args.port, args.baud, args.addr, args.count, args.delay)
    if args.cmd == "present":
        return cmd_present(args.port, args.baud, args.state == "on")
    if args.cmd == "mode":
        return cmd_mode(args.port, args.baud, 0 if args.state == "sampled" else 1)
    if args.cmd == "pin":
        return cmd_pin(args.port, args.baud, args.pin)
    if args.cmd == "all-pins":
        return cmd_all_pins(args.port, args.baud)
    if args.cmd == "clear-pins":
        return cmd_clear_pins(args.port, args.baud)
    if args.cmd == "status":
        return cmd_status(args.port, args.baud)
    if args.cmd == "help-cmd":
        return cmd_help(args.port, args.baud)
    raise AssertionError(f"unhandled command {args.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())

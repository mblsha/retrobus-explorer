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


def parse_saleae(text: str) -> int:
    value = int(text, 10)
    if not 0 <= value <= 7:
        raise ValueError(f"saleae pin must be 0-7, got {text!r}")
    return value


def parse_ffc(text: str) -> int:
    value = int(text, 10)
    if not 0 <= value <= 47:
        raise ValueError(f"ffc.data pin must be 0-47, got {text!r}")
    return value


def send_route(port: str, baud: int, saleae: int, ffc: int, timeout: float = 0.2) -> str:
    cmd = f"{saleae}{ffc:02d}\r".encode("ascii")
    with serial.Serial(port, baudrate=baud, timeout=timeout) as ser:
        ser.write(cmd)
        time.sleep(0.05)
        return ser.read_all().decode("ascii", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route one PC-E500 FFC.DATA pin to one Saleae pin")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("saleae", type=parse_saleae)
    parser.add_argument("ffc", type=parse_ffc)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    sys.stdout.write(send_route(args.port, args.baud, args.saleae, args.ffc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

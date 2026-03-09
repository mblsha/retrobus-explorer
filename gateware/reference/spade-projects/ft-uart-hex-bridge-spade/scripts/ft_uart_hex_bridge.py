#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5"]
# ///
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from pathlib import Path

import serial


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "py" / "d3xx").exists() and (parent / "gateware" / "reference").exists():
            return parent
    raise SystemExit("failed to locate retrobus-explorer repo root")


def parse_word_token(token: str) -> tuple[int, int]:
    token = token.strip()
    if not token:
        raise ValueError("empty token")
    if "/" in token:
        word_text, be_text = token.split("/", 1)
    else:
        word_text, be_text = token, "3"
    if len(word_text) != 4:
        raise ValueError(f"expected 4 hex digits, got {word_text!r}")
    word = int(word_text, 16)
    be = int(be_text, 16)
    if not 0 <= be <= 3:
        raise ValueError(f"byte enable must be 0..3, got {be}")
    return word, be


def uart_send(port: str, tokens: list[str], baud: int) -> int:
    with serial.Serial(port, baudrate=baud, timeout=0.2) as ser:
        for token in tokens:
            parse_word_token(token)
            ser.write(token.encode("ascii") + b"\r")
    return 0


def uart_read(port: str, baud: int, count: int, timeout: float) -> int:
    deadline = time.time() + timeout
    seen = 0
    with serial.Serial(port, baudrate=baud, timeout=0.1) as ser:
        while count <= 0 or seen < count:
            line = ser.readline()
            if line:
                sys.stdout.write(line.decode("ascii", errors="replace"))
                sys.stdout.flush()
                seen += 1
                deadline = time.time() + timeout
            elif time.time() > deadline:
                break
    return 0


class Ft600Device:
    def __init__(self) -> None:
        repo_root = find_repo_root()
        sys.path.append(str(repo_root / "py" / "d3xx"))
        import _ftd3xx_linux as mft  # type: ignore
        import ftd3xx  # type: ignore

        self._mft = mft
        self._ftd3xx = ftd3xx
        self.channel = 0
        self.dev = ftd3xx.create(0, mft.FT_OPEN_BY_INDEX)
        if self.dev is None:
            raise RuntimeError("failed to open FT device via D3XX")

    def close(self) -> None:
        if getattr(self, "dev", None) is not None:
            self.dev.close()
            self.dev = None

    def __enter__(self) -> "Ft600Device":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def write(self, data: bytes) -> int:
        buf = ctypes.create_string_buffer(data)
        return self.dev.writePipe(self.channel, buf, len(data))

    def read(self, datalen: int, timeout_ms: int = 100) -> bytes:
        bytes_transferred = self._mft.ULONG()
        data = ctypes.create_string_buffer(datalen)
        self._ftd3xx.call_ft(
            self._mft.FT_ReadPipeEx,
            self.dev.handle,
            self._mft.UCHAR(self.channel),
            data,
            self._mft.ULONG(datalen),
            ctypes.byref(bytes_transferred),
            timeout_ms,
        )
        return data.raw[:bytes_transferred.value]


def ft_encode_token(token: str) -> bytes:
    word, be = parse_word_token(token)
    lo = word & 0xFF
    hi = (word >> 8) & 0xFF
    if be == 3:
        return bytes([lo, hi])
    if be == 1:
        return bytes([lo])
    if be == 0:
        return b""
    raise ValueError(
        "direct FT host writes cannot express high-byte-only /2 words; "
        "use the UART bridge path for that edge case"
    )


def ft_send(tokens: list[str]) -> int:
    payload = b"".join(ft_encode_token(token) for token in tokens)
    with Ft600Device() as dev:
        written = dev.write(payload)
    print(f"wrote {written} bytes")
    return 0


def ft_read(count: int, timeout: float, chunk: int) -> int:
    deadline = time.time() + timeout
    total = 0
    with Ft600Device() as dev:
        while count <= 0 or total < count:
            data = dev.read(chunk)
            if data:
                print(" ".join(f"{byte:02X}" for byte in data))
                total += len(data)
                deadline = time.time() + timeout
            elif time.time() > deadline:
                break
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Host utility for ft-uart-hex-bridge-spade")
    sub = parser.add_subparsers(dest="cmd", required=True)

    uart_send_parser = sub.add_parser("uart-send", help="send hhhh[/b] tokens over USB UART")
    uart_send_parser.add_argument("--port", required=True)
    uart_send_parser.add_argument("--baud", type=int, default=1_000_000)
    uart_send_parser.add_argument("tokens", nargs="+")

    uart_read_parser = sub.add_parser("uart-read", help="read bridge lines from USB UART")
    uart_read_parser.add_argument("--port", required=True)
    uart_read_parser.add_argument("--baud", type=int, default=1_000_000)
    uart_read_parser.add_argument("--count", type=int, default=0)
    uart_read_parser.add_argument("--timeout", type=float, default=1.0)

    ft_send_parser = sub.add_parser("ft-send", help="send raw FT bytes derived from hhhh[/b] tokens")
    ft_send_parser.add_argument("tokens", nargs="+")

    ft_read_parser = sub.add_parser("ft-read", help="read raw FT bytes")
    ft_read_parser.add_argument("--count", type=int, default=0)
    ft_read_parser.add_argument("--timeout", type=float, default=1.0)
    ft_read_parser.add_argument("--chunk", type=int, default=512)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "uart-send":
        return uart_send(args.port, args.tokens, args.baud)
    if args.cmd == "uart-read":
        return uart_read(args.port, args.baud, args.count, args.timeout)
    if args.cmd == "ft-send":
        return ft_send(args.tokens)
    if args.cmd == "ft-read":
        return ft_read(args.count, args.timeout, args.chunk)
    raise AssertionError(f"unhandled command {args.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())

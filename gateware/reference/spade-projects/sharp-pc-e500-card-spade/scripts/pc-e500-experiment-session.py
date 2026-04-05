#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5"]
# ///
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Sequence

import serial


DEFAULT_BAUD = 1_000_000
DEFAULT_SERIAL_TIMEOUT = 0.05
DEFAULT_IDLE_GAP = 0.05
DEFAULT_QUIET_TIMEOUT = 5.0
DEFAULT_COMMAND_TIMEOUT = 1.0
DEFAULT_ASSEMBLER_DIR = Path.home() / "src" / "github" / "binja-esr-tests" / "public-src"
CARD_ROM_BASE = 0x10000
CARD_ROM_SIZE = 0x800
CARD_ROM_LAST = CARD_ROM_BASE + CARD_ROM_SIZE - 1
DEFAULT_FILL_BYTE = 0xFF

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


def detect_second_usb_serial_port() -> str:
    ports = sorted(str(path) for path in Path("/dev").glob("cu.usbserial-*"))
    if len(ports) < 2:
        raise SystemExit(
            "expected at least two /dev/cu.usbserial-* devices for the Au1; "
            f"found {len(ports)}"
        )
    return ports[1]


def parse_hex(text: str) -> int:
    cleaned = text.strip().replace("_", "")
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    if not cleaned:
        raise argparse.ArgumentTypeError("expected a hexadecimal value")
    try:
        return int(cleaned, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid hexadecimal value {text!r}") from exc


def parse_byte(text: str) -> int:
    value = int(text, 0)
    if not 0 <= value <= 0xFF:
        raise argparse.ArgumentTypeError("expected a byte value in the range 0..255")
    return value


def rom_offset_from_address(address: int) -> int:
    if 0 <= address < CARD_ROM_SIZE:
        return address
    if CARD_ROM_BASE <= address <= CARD_ROM_LAST:
        return address - CARD_ROM_BASE
    raise SystemExit(
        f"address {address:X} is outside the 2 KiB card-ROM window "
        f"({CARD_ROM_BASE:05X}..{CARD_ROM_LAST:05X} or offsets 000..7FF)"
    )


def absolute_address(offset: int) -> int:
    return CARD_ROM_BASE + offset


def render_terminal_bytes(data: bytes) -> str:
    rendered: list[str] = []
    for byte in data:
        if 0x20 <= byte <= 0x7E:
            rendered.append(chr(byte))
        elif byte == 0x0A:
            rendered.append("\n")
        elif byte == 0x0D:
            rendered.append("\r")
        elif byte == 0x09:
            rendered.append("\t")
        else:
            rendered.append(f"\\x{byte:02X}")
    return "".join(rendered)


def normalize_reply_lines(reply: bytes) -> list[str]:
    text = reply.decode("ascii", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return [line for line in text.split("\n") if line]


def build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["FORCE_BINJA_MOCK"] = "1"
    env["UV_NO_CONFIG"] = "1"
    return env


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


def assemble_segments(source_path: Path, assembler_dir: Path) -> list[tuple[int, bytes]]:
    if shutil.which("uv") is None:
        raise SystemExit("uv was not found in PATH")

    completed = subprocess.run(
        ["uv", "run", "python", "-c", ASSEMBLER_SNIPPET, str(source_path)],
        cwd=assembler_dir,
        env=build_subprocess_env(),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise SystemExit("assembly failed")

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


class UARTSession:
    def __init__(
        self,
        ser: serial.Serial,
        *,
        idle_gap: float,
        quiet_timeout: float,
        monitor: bool = True,
    ) -> None:
        self.ser = ser
        self.idle_gap = idle_gap
        self.quiet_timeout = quiet_timeout
        self.monitor = monitor
        self._buffer = bytearray()
        self._last_rx_at: float | None = None
        self._rx_total = 0
        self._tx_total = 0
        self._cv = threading.Condition()
        self._command_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._reader = threading.Thread(target=self._reader_loop, name="uart-reader", daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._stop_event.set()
        self._reader.join(timeout=1.0)

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self.ser.read(256)
            except serial.SerialException as exc:
                print(f"\n[session] serial read error: {exc}", file=sys.stderr)
                return
            if not chunk:
                continue
            now = time.monotonic()
            with self._cv:
                self._buffer.extend(chunk)
                self._rx_total += len(chunk)
                self._last_rx_at = now
                self._cv.notify_all()
            if self.monitor:
                sys.stdout.write(render_terminal_bytes(chunk))
                sys.stdout.flush()

    def stats(self) -> str:
        with self._cv:
            quiet_for = None if self._last_rx_at is None else time.monotonic() - self._last_rx_at
            rx_total = self._rx_total
            tx_total = self._tx_total
            buffered = len(self._buffer)
        quiet_text = "never" if quiet_for is None else f"{quiet_for:.3f}s"
        return f"rx={rx_total} tx={tx_total} buffered={buffered} quiet_for={quiet_text}"

    def wait_until_quiet(self, timeout: float | None = None, idle_gap: float | None = None) -> None:
        timeout = self.quiet_timeout if timeout is None else timeout
        idle_gap = self.idle_gap if idle_gap is None else idle_gap
        deadline = time.monotonic() + timeout
        with self._cv:
            while True:
                now = time.monotonic()
                if self._last_rx_at is None or now - self._last_rx_at >= idle_gap:
                    return
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError(
                        f"UART did not go quiet for {idle_gap:.3f}s within {timeout:.3f}s"
                    )
                self._cv.wait(timeout=min(remaining, idle_gap))

    def _capture_from(self, start: int) -> bytes:
        with self._cv:
            return bytes(self._buffer[start:])

    def send_command(self, command: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bytes:
        payload = command.encode("ascii") + b"\r"
        with self._command_lock:
            self.wait_until_quiet()
            with self._cv:
                start = len(self._buffer)
            self.ser.write(payload)
            self.ser.flush()
            with self._cv:
                self._tx_total += len(payload)

            deadline = time.monotonic() + timeout
            saw_reply = False
            while True:
                now = time.monotonic()
                with self._cv:
                    current_len = len(self._buffer)
                    last_rx_at = self._last_rx_at
                    if current_len > start:
                        saw_reply = True
                    if saw_reply and last_rx_at is not None and now - last_rx_at >= self.idle_gap:
                        return bytes(self._buffer[start:current_len])
                    remaining = deadline - now
                    if remaining <= 0:
                        return bytes(self._buffer[start:current_len])
                    self._cv.wait(timeout=min(remaining, self.idle_gap))

    def send_payload(self, payload: bytes, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bytes:
        with self._command_lock:
            self.wait_until_quiet()
            with self._cv:
                start = len(self._buffer)
            self.ser.write(payload)
            self.ser.flush()
            with self._cv:
                self._tx_total += len(payload)

            deadline = time.monotonic() + timeout
            while True:
                now = time.monotonic()
                with self._cv:
                    current_len = len(self._buffer)
                    last_rx_at = self._last_rx_at
                    if current_len > start and last_rx_at is not None and now - last_rx_at >= self.idle_gap:
                        return bytes(self._buffer[start:current_len])
                    remaining = deadline - now
                    if remaining <= 0:
                        return bytes(self._buffer[start:current_len])
                    self._cv.wait(timeout=min(remaining, self.idle_gap))

    def passive_listen(self, duration: float) -> None:
        time.sleep(duration)


def expect_substring(reply: bytes, expect: str) -> None:
    if expect.encode("ascii") not in reply:
        raise SystemExit(f"expected {expect!r} in reply, got {reply!r}")


def run_raw(session: UARTSession, text: str) -> None:
    reply = session.send_command(text)
    print(f"[cmd] {text}", file=sys.stderr)
    if reply:
        print(f"[reply] {reply.decode('ascii', errors='replace')!r}", file=sys.stderr)


def run_timing(session: UARTSession, cycles: int) -> None:
    if not 0 <= cycles <= 99:
        raise SystemExit("timing cycles must be in the range 0..99")
    reply = session.send_command(f"t{cycles:02d}")
    expect_substring(reply, f"T={cycles * 10:03d}ns")


def run_control_timing(session: UARTSession, cycles: int) -> None:
    if not 0 <= cycles <= 99:
        raise SystemExit("control timing cycles must be in the range 0..99")
    reply = session.send_command(f"c{cycles:02d}")
    expected = (f"C={cycles * 10:03d}ns", f"C={cycles * 10}ns")
    if not any(item.encode("ascii") in reply for item in expected):
        raise SystemExit(f"expected one of {expected!r} in reply, got {reply!r}")


def read_byte(session: UARTSession, address: int) -> int:
    offset = rom_offset_from_address(address)
    reply = session.send_command(f"R{offset:03X}")
    lines = normalize_reply_lines(reply)
    if len(lines) < 2:
        raise SystemExit(f"unexpected read reply {reply!r}")
    result = lines[-1].upper()
    if "=" not in result:
        raise SystemExit(f"unexpected read result line {result!r}")
    addr_text, value_text = result.split("=", 1)
    if int(addr_text, 16) != offset:
        raise SystemExit(f"read reply address mismatch in {result!r}")
    value = int(value_text, 16)
    print(
        f"[read] {absolute_address(offset):05X} (offset {offset:03X}) = {value:02X}",
        file=sys.stderr,
    )
    return value


def write_byte(session: UARTSession, address: int, value: int) -> None:
    offset = rom_offset_from_address(address)
    if not 0 <= value <= 0xFF:
        raise SystemExit("write value must be 0..255")
    reply = session.send_command(f"W{offset:03X}={value:02X}")
    lines = normalize_reply_lines(reply)
    if not lines or lines[-1].upper() != "OK":
        raise SystemExit(f"unexpected write reply {reply!r}")
    print(
        f"[write] {absolute_address(offset):05X} (offset {offset:03X}) = {value:02X}",
        file=sys.stderr,
    )


def build_write_payload(start_offset: int, data: bytes) -> bytes:
    return b"".join(
        f"W{start_offset + index:03X}={value:02X}\r".encode("ascii")
        for index, value in enumerate(data)
    )


def verify_range(session: UARTSession, start_offset: int, data: bytes) -> None:
    for index, expected in enumerate(data):
        value = read_byte(session, absolute_address(start_offset + index))
        if value != expected:
            raise SystemExit(
                f"verify mismatch at {absolute_address(start_offset + index):05X}: "
                f"expected {expected:02X}, got {value:02X}"
            )


def program_image(
    session: UARTSession,
    image_path: Path,
    *,
    start: int,
    fast: bool,
    verify: bool,
) -> None:
    data = image_path.read_bytes()
    start_offset = rom_offset_from_address(start)
    remaining = CARD_ROM_SIZE - start_offset
    if len(data) > remaining:
        raise SystemExit(
            f"image is {len(data)} bytes but only {remaining} bytes fit from offset {start_offset:03X}"
        )

    print(
        f"[program] writing {len(data)} byte(s) at "
        f"{absolute_address(start_offset):05X}..{absolute_address(start_offset + len(data) - 1):05X}",
        file=sys.stderr,
    )
    if fast:
        payload = build_write_payload(start_offset, data)
        session.send_payload(payload, timeout=max(DEFAULT_COMMAND_TIMEOUT, len(payload) / DEFAULT_BAUD + 0.5))
    else:
        for index, value in enumerate(data):
            write_byte(session, absolute_address(start_offset + index), value)

    if verify:
        verify_range(session, start_offset, data)
    print("[program] complete", file=sys.stderr)


def program_asm(
    session: UARTSession,
    source: Path,
    *,
    assembler_dir: Path,
    fill_byte: int,
    fast: bool,
    verify: bool,
) -> None:
    source_path = resolve_existing_file(source, "assembly source")
    assembler_dir = resolve_existing_dir(assembler_dir, "assembler checkout")
    segments = assemble_segments(source_path, assembler_dir)
    start_address, image = build_card_rom_image(segments, fill_byte)
    print(
        f"[asm] assembled {len(image)} byte(s) at {start_address:05X}..{start_address + len(image) - 1:05X}",
        file=sys.stderr,
    )
    temp_path = source_path.with_suffix(".assembled.bin")
    temp_path.write_bytes(image)
    try:
        program_image(session, temp_path, start=start_address, fast=fast, verify=verify)
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass
    print(f"[asm] calculator entry point: CALL &{start_address:05X}", file=sys.stderr)


def build_top_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Long-lived PC-E500 experiment UART session. "
            "Continuously monitors USB-UART traffic and waits for a quiet line "
            "before sending FPGA control commands."
        )
    )
    parser.add_argument("--port", help="serial port to use; defaults to the second /dev/cu.usbserial-* device")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"UART baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument(
        "--idle-gap",
        type=float,
        default=DEFAULT_IDLE_GAP,
        help=f"quiet gap in seconds required before sending commands (default: {DEFAULT_IDLE_GAP})",
    )
    parser.add_argument(
        "--quiet-timeout",
        type=float,
        default=DEFAULT_QUIET_TIMEOUT,
        help=f"maximum seconds to wait for quiet before sending (default: {DEFAULT_QUIET_TIMEOUT})",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="do not print background UART traffic to stdout",
    )
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help="session command to run non-interactively; may be provided multiple times",
    )
    return parser


def print_help() -> None:
    help_text = """
session commands:
  help
  status
  quiet [timeout_s]
  listen [duration_s]
  raw <text>
  timing <0..99>
  control-timing <0..99>
  read <addr>
  write <addr> <value>
  program <image> [--start <addr>] [--fast] [--verify]
  asm <source> [--assembler-dir <path>] [--fill-byte <byte>] [--fast] [--verify]
  exit
"""
    print(help_text.strip(), file=sys.stderr)


def execute_session_command(session: UARTSession, command_line: str) -> bool:
    tokens = shlex.split(command_line)
    if not tokens:
        return True
    cmd = tokens[0].lower()

    if cmd in {"exit", "quit"}:
        return False
    if cmd == "help":
        print_help()
        return True
    if cmd == "status":
        print(f"[status] {session.stats()}", file=sys.stderr)
        return True
    if cmd == "quiet":
        timeout = float(tokens[1]) if len(tokens) > 1 else session.quiet_timeout
        session.wait_until_quiet(timeout=timeout)
        print("[quiet] line is idle", file=sys.stderr)
        return True
    if cmd == "listen":
        duration = float(tokens[1]) if len(tokens) > 1 else 1.0
        session.passive_listen(duration)
        print(f"[listen] observed for {duration:.3f}s", file=sys.stderr)
        return True
    if cmd == "raw":
        if len(tokens) < 2:
            raise SystemExit("raw requires command text")
        run_raw(session, " ".join(tokens[1:]))
        return True
    if cmd == "timing":
        if len(tokens) != 2:
            raise SystemExit("timing requires one decimal value")
        run_timing(session, int(tokens[1], 10))
        return True
    if cmd == "control-timing":
        if len(tokens) != 2:
            raise SystemExit("control-timing requires one decimal value")
        run_control_timing(session, int(tokens[1], 10))
        return True
    if cmd == "read":
        if len(tokens) != 2:
            raise SystemExit("read requires one address")
        read_byte(session, int(tokens[1], 0))
        return True
    if cmd == "write":
        if len(tokens) != 3:
            raise SystemExit("write requires address and value")
        write_byte(session, int(tokens[1], 0), int(tokens[2], 0))
        return True
    if cmd == "program":
        program_parser = argparse.ArgumentParser(prog="program", add_help=False)
        program_parser.add_argument("image", type=Path)
        program_parser.add_argument("--start", type=lambda s: int(s, 0), default=CARD_ROM_BASE)
        program_parser.add_argument("--fast", action="store_true")
        program_parser.add_argument("--verify", action="store_true")
        args = program_parser.parse_args(tokens[1:])
        program_image(session, args.image, start=args.start, fast=args.fast, verify=args.verify)
        return True
    if cmd == "asm":
        asm_parser = argparse.ArgumentParser(prog="asm", add_help=False)
        asm_parser.add_argument("source", type=Path)
        asm_parser.add_argument("--assembler-dir", type=Path, default=DEFAULT_ASSEMBLER_DIR)
        asm_parser.add_argument("--fill-byte", type=parse_byte, default=DEFAULT_FILL_BYTE)
        asm_parser.add_argument("--fast", action="store_true")
        asm_parser.add_argument("--verify", action="store_true")
        args = asm_parser.parse_args(tokens[1:])
        program_asm(
            session,
            args.source,
            assembler_dir=args.assembler_dir,
            fill_byte=args.fill_byte,
            fast=args.fast,
            verify=args.verify,
        )
        return True

    raise SystemExit(f"unknown session command {cmd!r}")


def run_interactive(session: UARTSession) -> None:
    print_help()
    while True:
        try:
            line = input("\nexp> ")
        except EOFError:
            print(file=sys.stderr)
            return
        try:
            keep_going = execute_session_command(session, line)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {exc}", file=sys.stderr)
            continue
        if not keep_going:
            return


def run_batch(session: UARTSession, commands: Sequence[str]) -> None:
    for command in commands:
        print(f"[batch] {command}", file=sys.stderr)
        keep_going = execute_session_command(session, command)
        if not keep_going:
            return


def main() -> int:
    args = build_top_parser().parse_args()
    port = args.port or detect_second_usb_serial_port()
    print(f"[session] opening {port} at {args.baud} baud", file=sys.stderr)

    with serial.Serial(
        port,
        baudrate=args.baud,
        timeout=DEFAULT_SERIAL_TIMEOUT,
        write_timeout=1.0,
    ) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        session = UARTSession(
            ser,
            idle_gap=args.idle_gap,
            quiet_timeout=args.quiet_timeout,
            monitor=not args.no_monitor,
        )
        try:
            if args.command:
                run_batch(session, args.command)
            else:
                run_interactive(session)
        finally:
            session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

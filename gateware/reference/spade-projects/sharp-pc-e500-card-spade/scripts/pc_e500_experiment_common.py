from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
WRITE_COMMAND_BYTES = 8

MEASURE_END_LINE = "MEND"
READY_PREFIX = "XR,READY"
BEGIN_PREFIX = "XR,BEGIN"
END_PREFIX = "XR,END"

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


@dataclass(frozen=True)
class ParsedMeasurement:
    start_tag: int
    stop_tag: int
    ticks: int
    ce_events: int
    addr_uart: int
    ft_overflow: int


@dataclass(frozen=True)
class ParsedMeasureStatus:
    count: int
    overflow: int
    armed: bool


@dataclass(frozen=True)
class UARTLine:
    timestamp: float
    text: str


def detect_second_usb_serial_port() -> str:
    ports = sorted(str(path) for path in Path("/dev").glob("cu.usbserial-*"))
    if len(ports) < 2:
        raise RuntimeError(
            "expected at least two /dev/cu.usbserial-* devices for the Au1; "
            f"found {len(ports)}"
        )
    return ports[1]


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


def parse_key_value_csv(line: str) -> tuple[str, dict[str, int | bool]]:
    parts = line.strip().split(",")
    prefix = parts[0]
    values: dict[str, int | bool] = {}
    for part in parts[1:]:
        key, value = part.split("=", 1)
        if key == "ARM":
            values[key] = value == "1"
        else:
            values[key] = int(value, 16)
    return prefix, values


def parse_measure_status_lines(lines: list[str]) -> ParsedMeasureStatus:
    for line in lines:
        if line.startswith("MS,"):
            prefix, values = parse_key_value_csv(line)
            if prefix != "MS":
                continue
            count = int(values["CNT"])
            overflow = int(values["OVF"])
            armed = bool(values["ARM"])
            return ParsedMeasureStatus(count=count, overflow=overflow, armed=armed)
    raise RuntimeError(f"measure status line not found in {lines!r}")


def parse_measurement_lines(lines: list[str]) -> list[ParsedMeasurement]:
    measurements: list[ParsedMeasurement] = []
    for line in lines:
        if line == MEASURE_END_LINE or not line.startswith("MR,"):
            continue
        prefix, values = parse_key_value_csv(line)
        if prefix != "MR":
            continue
        measurements.append(
            ParsedMeasurement(
                start_tag=int(values["S"]),
                stop_tag=int(values["E"]),
                ticks=int(values["TK"]),
                ce_events=int(values["EV"]),
                addr_uart=int(values["AU"]),
                ft_overflow=int(values.get("FO", 0)),
            )
        )
    return measurements


def reply_contains_line(lines: list[str], expected: str) -> bool:
    return any(line == expected for line in lines)


def parse_hex_or_int(text: str) -> int:
    cleaned = text.strip().replace("_", "")
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
        return int(cleaned, 16)
    if cleaned.startswith(("0X",)):
        cleaned = cleaned[2:]
        return int(cleaned, 16)
    if all(ch in "0123456789abcdefABCDEF" for ch in cleaned) and any(ch.isalpha() for ch in cleaned):
        return int(cleaned, 16)
    return int(cleaned, 0)


def rom_offset_from_address(address: int) -> int:
    if 0 <= address < CARD_ROM_SIZE:
        return address
    if CARD_ROM_BASE <= address <= CARD_ROM_LAST:
        return address - CARD_ROM_BASE
    raise RuntimeError(
        f"address {address:X} is outside the 2 KiB card-ROM window "
        f"({CARD_ROM_BASE:05X}..{CARD_ROM_LAST:05X} or offsets 000..7FF)"
    )


def absolute_address(offset: int) -> int:
    return CARD_ROM_BASE + offset


def build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["FORCE_BINJA_MOCK"] = "1"
    env["UV_NO_CONFIG"] = "1"
    return env


def resolve_existing_dir(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"{label} not found at {resolved}")
    return resolved


def resolve_existing_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise RuntimeError(f"{label} not found at {resolved}")
    return resolved


def assemble_segments(source_path: Path, assembler_dir: Path) -> list[tuple[int, bytes]]:
    if shutil.which("uv") is None:
        raise RuntimeError("uv was not found in PATH")

    completed = subprocess.run(
        ["uv", "run", "python", "-c", ASSEMBLER_SNIPPET, str(source_path)],
        cwd=assembler_dir,
        env=build_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"assembly failed for {source_path}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    payload = json.loads(completed.stdout)
    segments: list[tuple[int, bytes]] = []
    for item in payload:
        segments.append((int(item["address"]), bytes.fromhex(item["data_hex"])))
    if not segments:
        raise RuntimeError("assembler produced no output segments")
    return sorted(segments, key=lambda item: item[0])


def assemble_text(source_text: str, assembler_dir: Path) -> list[tuple[int, bytes]]:
    with tempfile.NamedTemporaryFile("w", suffix=".asm", delete=False) as handle:
        handle.write(source_text)
        temp_path = Path(handle.name)
    try:
        return assemble_segments(temp_path, assembler_dir)
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def build_card_rom_image(segments: list[tuple[int, bytes]], fill_byte: int = DEFAULT_FILL_BYTE) -> tuple[int, bytes]:
    start = min(address for address, _ in segments)
    end = max(address + len(data) for address, data in segments)
    if start < CARD_ROM_BASE or end - 1 > CARD_ROM_LAST:
        raise RuntimeError(
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
                raise RuntimeError(f"overlapping segments disagree at {start + image_index:05X}")
            image[image_index] = value
            written[image_index] = True
    return start, bytes(image)


def build_write_payload(start_offset: int, data: bytes) -> bytes:
    return b"".join(
        f"W{start_offset + index:03X}={value:02X}\r".encode("ascii")
        for index, value in enumerate(data)
    )


class ExperimentUART:
    def __init__(
        self,
        ser: serial.Serial,
        *,
        idle_gap: float = DEFAULT_IDLE_GAP,
        quiet_timeout: float = DEFAULT_QUIET_TIMEOUT,
        monitor_stream=None,
        keep_lines: int = 2048,
    ) -> None:
        self.ser = ser
        self.idle_gap = idle_gap
        self.quiet_timeout = quiet_timeout
        self.monitor_stream = monitor_stream
        self.keep_lines = keep_lines

        self._raw = bytearray()
        self._partial_line = bytearray()
        self._lines: deque[UARTLine] = deque(maxlen=keep_lines)
        self._line_start = 0
        self._last_rx_at: float | None = None
        self._rx_total = 0
        self._tx_total = 0
        self._cv = threading.Condition()
        self._command_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._reader = threading.Thread(target=self._reader_loop, name="pc-e500-uart-reader", daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._stop_event.set()
        self._reader.join(timeout=1.0)

    def _append_lines(self, chunk: bytes, now: float) -> None:
        for byte in chunk:
            if byte == 0x0A:
                text = self._partial_line.decode("ascii", errors="replace").rstrip("\r")
                if len(self._lines) == self.keep_lines:
                    self._line_start += 1
                self._lines.append(UARTLine(timestamp=now, text=text))
                self._partial_line.clear()
            else:
                self._partial_line.append(byte)

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self.ser.read(256)
            except serial.SerialException:
                return
            if not chunk:
                continue
            now = time.monotonic()
            with self._cv:
                self._raw.extend(chunk)
                self._rx_total += len(chunk)
                self._last_rx_at = now
                self._append_lines(chunk, now)
                self._cv.notify_all()
            if self.monitor_stream is not None:
                self.monitor_stream.write(render_terminal_bytes(chunk))
                self.monitor_stream.flush()

    def stats(self) -> dict[str, float | int | None]:
        with self._cv:
            quiet_for = None if self._last_rx_at is None else time.monotonic() - self._last_rx_at
            return {
                "rx_total": self._rx_total,
                "tx_total": self._tx_total,
                "buffered_raw": len(self._raw),
                "line_count": len(self._lines),
                "quiet_for_s": quiet_for,
            }

    def line_count(self) -> int:
        with self._cv:
            return self._line_start + len(self._lines)

    def raw_count(self) -> int:
        with self._cv:
            return len(self._raw)

    def raw_since(self, index: int) -> bytes:
        with self._cv:
            start = max(index, 0)
            return bytes(self._raw[start:])

    def discard_buffered_input(self) -> None:
        with self._command_lock:
            self.ser.reset_input_buffer()
            with self._cv:
                self._raw.clear()
                self._partial_line.clear()
                self._lines.clear()
                self._line_start = 0
                self._last_rx_at = None
                self._cv.notify_all()

    def synchronize_rx_boundary(
        self,
        *,
        settle_s: float = 0.2,
        timeout_s: float = 2.0,
    ) -> None:
        """Drop stale RX traffic and wait until no late bytes arrive.

        The background reader can append a chunk after a plain input flush if it
        had already completed a `read()` call. This loop establishes a clean
        baseline by discarding buffered input, then requiring a short quiet
        settle window with no newly arrived bytes.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out synchronizing UART receive boundary")
            self.wait_until_quiet(timeout=remaining)
            self.discard_buffered_input()

            settle_deadline = time.monotonic() + settle_s
            late_bytes = False
            with self._cv:
                while True:
                    remaining_settle = settle_deadline - time.monotonic()
                    if len(self._raw) > 0:
                        late_bytes = True
                        break
                    if remaining_settle <= 0:
                        return
                    self._cv.wait(timeout=remaining_settle)
            if not late_bytes:
                return

    def lines_since(self, index: int) -> list[UARTLine]:
        with self._cv:
            start = max(index - self._line_start, 0)
            lines = list(self._lines)
            return lines[start:]

    def last_lines(self, limit: int = 20) -> list[str]:
        with self._cv:
            return [line.text for line in list(self._lines)[-limit:]]

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

    def wait_for_line(self, predicate: Callable[[str], bool], timeout: float, start_index: int = 0) -> UARTLine:
        deadline = time.monotonic() + timeout
        with self._cv:
            while True:
                lines = list(self._lines)
                start = max(start_index - self._line_start, 0)
                for line in lines[start:]:
                    if predicate(line.text):
                        return line
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("timed out waiting for UART line")
                self._cv.wait(timeout=min(remaining, self.idle_gap))

    def wait_for_bytes(self, needle: bytes, timeout: float, start_index: int = 0) -> bytes:
        deadline = time.monotonic() + timeout
        with self._cv:
            while True:
                haystack = bytes(self._raw[start_index:])
                if needle in haystack:
                    return haystack
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("timed out waiting for UART bytes")
                self._cv.wait(timeout=min(remaining, self.idle_gap))

    def send_command(self, command: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bytes:
        payload = command.encode("ascii") + b"\r"
        return self.send_payload(payload, timeout=timeout)

    def send_payload(self, payload: bytes, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bytes:
        with self._command_lock:
            self.wait_until_quiet()
            with self._cv:
                start = len(self._raw)
            self.ser.write(payload)
            self.ser.flush()
            with self._cv:
                self._tx_total += len(payload)

            deadline = time.monotonic() + timeout
            saw_reply = False
            while True:
                now = time.monotonic()
                with self._cv:
                    current_len = len(self._raw)
                    last_rx_at = self._last_rx_at
                    if current_len > start:
                        saw_reply = True
                    if saw_reply and last_rx_at is not None and now - last_rx_at >= self.idle_gap:
                        return bytes(self._raw[start:current_len])
                    remaining = deadline - now
                    if remaining <= 0:
                        return bytes(self._raw[start:current_len])
                    self._cv.wait(timeout=min(remaining, self.idle_gap))

    def run_raw(self, text: str) -> list[str]:
        return normalize_reply_lines(self.send_command(text))

    def set_timing(self, cycles: int) -> None:
        reply = self.run_raw(f"t{cycles:02d}")
        expected = f"T={cycles * 10:03d}ns"
        if expected not in reply:
            raise RuntimeError(f"expected {expected!r} in timing reply, got {reply!r}")

    def set_control_timing(self, cycles: int) -> None:
        reply = self.run_raw(f"c{cycles:02d}")
        expected = {f"C={cycles * 10:03d}ns", f"C={cycles * 10}ns"}
        if not expected.intersection(reply):
            raise RuntimeError(f"expected one of {sorted(expected)!r} in control timing reply, got {reply!r}")

    def read_rom_byte(self, address: int) -> int:
        offset = rom_offset_from_address(address)
        reply = self.run_raw(f"R{offset:03X}")
        if len(reply) < 2:
            raise RuntimeError(f"unexpected ROM read reply {reply!r}")
        result = reply[-1]
        addr_text, value_text = result.split("=", 1)
        if int(addr_text, 16) != offset:
            raise RuntimeError(f"read reply address mismatch: {result!r}")
        return int(value_text, 16)

    def write_rom_byte(self, address: int, value: int) -> None:
        offset = rom_offset_from_address(address)
        reply = self.run_raw(f"W{offset:03X}={value:02X}")
        if not reply_contains_line(reply, "OK"):
            raise RuntimeError(f"unexpected ROM write reply {reply!r}")

    def write_rom_bytes(self, start_address: int, data: bytes, *, fast: bool = True) -> None:
        start_offset = rom_offset_from_address(start_address)
        if start_offset + len(data) > CARD_ROM_SIZE:
            raise RuntimeError("ROM write range exceeds 2 KiB card ROM window")
        if fast:
            payload = build_write_payload(start_offset, data)
            wire_time = len(payload) * 10 / DEFAULT_BAUD
            processing_margin = max(1.0, len(data) * 0.002)
            self.send_payload(payload, timeout=max(DEFAULT_COMMAND_TIMEOUT, wire_time + processing_margin))
            return
        for index, value in enumerate(data):
            self.write_rom_byte(absolute_address(start_offset + index), value)

    def clear_measurements(self) -> None:
        reply = self.run_raw("m!")
        if not reply_contains_line(reply, "OK"):
            raise RuntimeError(f"unexpected measurement clear reply {reply!r}")

    def read_measure_status(self) -> ParsedMeasureStatus:
        return parse_measure_status_lines(self.run_raw("m?"))

    def dump_measurements(self) -> list[ParsedMeasurement]:
        with self._command_lock:
            self.wait_until_quiet()
            line_index = self.line_count()
            self.ser.write(b"m\r")
            self.ser.flush()
            with self._cv:
                self._tx_total += 2
            self.wait_for_line(lambda text: text == MEASURE_END_LINE, 2.0, start_index=line_index)
            self.wait_until_quiet(timeout=2.0)
            reply = [line.text for line in self.lines_since(line_index)]
        if MEASURE_END_LINE not in reply:
            raise RuntimeError(f"measurement dump missing MEND terminator: {reply!r}")
        return parse_measurement_lines(reply)


def open_uart(
    port: str | None,
    *,
    baud: int = DEFAULT_BAUD,
    monitor_stream=None,
    idle_gap: float = DEFAULT_IDLE_GAP,
    quiet_timeout: float = DEFAULT_QUIET_TIMEOUT,
) -> tuple[serial.Serial, ExperimentUART]:
    chosen_port = port or detect_second_usb_serial_port()
    ser = serial.Serial(
        chosen_port,
        baudrate=baud,
        timeout=DEFAULT_SERIAL_TIMEOUT,
        write_timeout=1.0,
    )
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    uart = ExperimentUART(
        ser,
        idle_gap=idle_gap,
        quiet_timeout=quiet_timeout,
        monitor_stream=monitor_stream,
    )
    return ser, uart

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5", "tqdm>=4.66"]
# ///
from __future__ import annotations

import argparse
import codecs
import os
import re
import sys
import threading
import time
from pathlib import Path

import serial
from tqdm import tqdm


DEFAULT_BAUD = 1_000_000
DEFAULT_TIMEOUT = 1.0
DEFAULT_COMMAND = "a"
DEFAULT_EXPECT = "ERR"
LISTEN_CHUNK_SIZE = 256
CARD_ROM_BASE = 0x10000
CARD_ROM_SIZE = 0x800
CARD_ROM_LAST = CARD_ROM_BASE + CARD_ROM_SIZE - 1
READ_REPLY_RE = re.compile(r"^([0-7][0-9A-F]{2})=([0-9A-F]{2})$")
BITS_PER_BYTE = 10
WRITE_COMMAND_BYTES = 8
FAST_FOLLOWUP_SETTLE_MARGIN = 0.02
FAST_DRAIN_READ_SIZE = 4096
STARTUP_IDLE_GAP = 0.05
STARTUP_MAX_WAIT = 0.5


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


def decode_expect_text(text: str) -> bytes:
    """Decode CLI expect strings like \"OK\\r\\n\" into raw bytes."""
    decoded = codecs.decode(text, "unicode_escape")
    try:
        return decoded.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise argparse.ArgumentTypeError(
            f"expected text must decode to single-byte characters: {text!r}"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Talk to the Alchitry Au1 slow USB-UART on macOS. By default this auto-selects "
            "the second /dev/cu.usbserial-* device."
        )
    )
    parser.add_argument(
        "--port",
        help="serial port to use; defaults to the second /dev/cu.usbserial-* device",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD,
        help=f"UART baud rate (default: {DEFAULT_BAUD})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"seconds to wait for a reply (default: {DEFAULT_TIMEOUT:g})",
    )

    subparsers = parser.add_subparsers(dest="command")

    probe_parser = subparsers.add_parser(
        "probe",
        help="send a probe command and verify the expected reply",
    )
    probe_parser.add_argument(
        "--probe-command",
        default=DEFAULT_COMMAND,
        help=f"text to send before carriage return (default: {DEFAULT_COMMAND!r})",
    )
    probe_parser.add_argument(
        "--expect",
        default=DEFAULT_EXPECT,
        help=f"substring expected in the reply (supports \\\\r/\\\\n escapes; default: {DEFAULT_EXPECT!r})",
    )

    raw_parser = subparsers.add_parser(
        "raw",
        help="send an arbitrary UART command terminated by carriage return",
    )
    raw_parser.add_argument("text", help="command text to send before carriage return")
    raw_parser.add_argument(
        "--expect",
        help="optional substring expected in the reply; supports \\r/\\n escapes",
    )

    timing_parser = subparsers.add_parser(
        "timing",
        help="set normal CE1/CE6 memory timing with tNN, where NN is in 10 ns units",
    )
    timing_parser.add_argument(
        "cycles",
        type=int,
        help="timing value in 10 ns units; 20 means 200 ns",
    )

    control_timing_parser = subparsers.add_parser(
        "control-timing",
        help=(
            "set CE6 control-page write timing with cNN for 0x1FFF0..0x1FFFF, "
            "where NN is in 10 ns units"
        ),
    )
    control_timing_parser.add_argument(
        "cycles",
        type=int,
        help="control-write timing value in 10 ns units; 10 means 100 ns",
    )

    listen_parser = subparsers.add_parser(
        "listen",
        help="listen for raw bytes on the USB-UART and optionally verify an expected string",
    )
    listen_parser.add_argument(
        "--expect",
        help="expected bytes from the device; supports \\r/\\n/\\xNN escapes",
    )
    listen_parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="maximum seconds to listen before timing out (default: 10)",
    )
    listen_parser.add_argument(
        "--quiet",
        action="store_true",
        help="do not print captured bytes to stdout while listening",
    )

    read_parser = subparsers.add_parser(
        "read",
        help="read one byte from the FPGA card-ROM window using Rxxx",
    )
    read_parser.add_argument(
        "address",
        type=parse_hex,
        help=(
            "ROM address as calculator address (10000..107FF hex) or FPGA offset "
            "(000..7FF hex)"
        ),
    )

    write_parser = subparsers.add_parser(
        "write",
        help="write one byte to the FPGA card-ROM window using Wxxx=xx",
    )
    write_parser.add_argument(
        "address",
        type=parse_hex,
        help=(
            "ROM address as calculator address (10000..107FF hex) or FPGA offset "
            "(000..7FF hex)"
        ),
    )
    write_parser.add_argument(
        "value",
        type=parse_hex,
        help="byte value to write (00..FF hex)",
    )

    program_parser = subparsers.add_parser(
        "program",
        help="program raw bytes from a file into the FPGA card-ROM window",
    )
    program_parser.add_argument("image", type=Path, help="binary image to write")
    program_parser.add_argument(
        "--start",
        type=parse_hex,
        default=CARD_ROM_BASE,
        help=(
            f"start address as calculator address or FPGA offset (default: {CARD_ROM_BASE:05X})"
        ),
    )
    program_parser.add_argument(
        "--echo",
        action="store_true",
        help="print the device echo and OK reply for every programmed byte",
    )
    program_parser.add_argument(
        "--verify",
        action="store_true",
        help="read each byte back after writing and fail on mismatch",
    )
    program_parser.add_argument(
        "--fast",
        action="store_true",
        help="blast all write commands as one UART payload and verify later if requested",
    )

    benchmark_parser = subparsers.add_parser(
        "benchmark-random",
        help="write random bytes to the card-ROM window and time the write pass",
    )
    benchmark_parser.add_argument(
        "--start",
        type=parse_hex,
        default=CARD_ROM_BASE,
        help=(
            f"start address as calculator address or FPGA offset (default: {CARD_ROM_BASE:05X})"
        ),
    )
    benchmark_parser.add_argument(
        "--count",
        type=int,
        default=CARD_ROM_SIZE,
        help=f"number of bytes to write (default: {CARD_ROM_SIZE})",
    )
    benchmark_parser.add_argument(
        "--keep-random",
        action="store_true",
        help="leave the random data in ROM instead of restoring the original contents",
    )
    benchmark_parser.add_argument(
        "--verify",
        action="store_true",
        help="read the random image back after the timed write and fail on mismatch",
    )
    benchmark_parser.add_argument(
        "--fast",
        action="store_true",
        help="use one large concatenated write payload instead of per-byte command/response writes",
    )

    return parser.parse_args()


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


def normalize_reply_lines(reply: bytes) -> list[str]:
    return [line for line in reply.decode("ascii", errors="replace").replace("\r\n", "\n").split("\n") if line]


def read_reply(ser: serial.Serial, timeout: float, idle_gap: float = 0.05) -> bytes:
    deadline = time.monotonic() + timeout
    last_data_at: float | None = None
    chunks: list[bytes] = []

    while time.monotonic() < deadline:
        data = ser.read(256)
        if data:
            chunks.append(data)
            last_data_at = time.monotonic()
            continue
        if last_data_at is not None and time.monotonic() - last_data_at >= idle_gap:
            break

    return b"".join(chunks)


def drain_until_quiet(
    ser: serial.Serial,
    *,
    idle_gap: float = STARTUP_IDLE_GAP,
    max_wait: float = STARTUP_MAX_WAIT,
) -> int:
    deadline = time.monotonic() + max_wait
    last_data_at: float | None = None
    discarded = 0

    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting:
            discarded += len(ser.read(min(waiting, FAST_DRAIN_READ_SIZE)))
            last_data_at = time.monotonic()
            continue
        if last_data_at is None:
            break
        if time.monotonic() - last_data_at >= idle_gap:
            break
        time.sleep(0.005)

    return discarded


def print_reply(reply: bytes) -> None:
    sys.stdout.write(reply.decode("ascii", errors="replace"))
    sys.stdout.flush()


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


def exchange(ser: serial.Serial, command: str, timeout: float) -> bytes:
    payload = command.encode("ascii") + b"\r"
    ser.reset_input_buffer()
    ser.write(payload)
    ser.flush()
    return read_reply(ser, timeout)


def run_probe(ser: serial.Serial, *, command: str, expect: str, timeout: float) -> int:
    reply = exchange(ser, command, timeout)
    print_reply(reply)
    expect_bytes = decode_expect_text(expect)
    if expect_bytes not in reply:
        print(f"did not receive expected reply {expect!r}", file=sys.stderr)
        return 1
    print(f"received expected reply {expect!r}", file=sys.stderr)
    return 0


def run_raw(
    ser: serial.Serial,
    *,
    command: str,
    timeout: float,
    expect: str | None = None,
) -> int:
    reply = exchange(ser, command, timeout)
    print_reply(reply)
    if expect is None:
        return 0
    expect_bytes = decode_expect_text(expect)
    if expect_bytes not in reply:
        print(f"did not receive expected reply {expect!r}", file=sys.stderr)
        return 1
    print(f"received expected reply {expect!r}", file=sys.stderr)
    return 0


def run_timing(ser: serial.Serial, *, cycles: int, timeout: float) -> int:
    if not 0 <= cycles <= 99:
        raise SystemExit("timing cycles must be in the range 0..99")
    command = f"t{cycles:02d}"
    expect = f"T={cycles * 10:03d}ns"
    return run_raw(ser, command=command, timeout=timeout, expect=expect)


def run_control_timing(ser: serial.Serial, *, cycles: int, timeout: float) -> int:
    if not 0 <= cycles <= 99:
        raise SystemExit("control timing cycles must be in the range 0..99")
    command = f"c{cycles:02d}"
    reply = exchange(ser, command, timeout)
    print_reply(reply)

    expected_replies = (
        f"C={cycles * 10:03d}ns",
        f"C={cycles * 10}ns",
    )
    for expect in expected_replies:
        if decode_expect_text(expect) in reply:
            print(f"received expected reply {expect!r}", file=sys.stderr)
            return 0

    print(
        "did not receive expected control timing reply "
        + " or ".join(repr(expect) for expect in expected_replies),
        file=sys.stderr,
    )
    return 1


def listen_for_bytes(
    ser: serial.Serial,
    *,
    duration: float,
    expect: bytes | None = None,
    quiet: bool = False,
) -> int:
    ser.reset_input_buffer()
    deadline = time.monotonic() + duration
    captured = bytearray()

    while time.monotonic() < deadline:
        chunk = ser.read(LISTEN_CHUNK_SIZE)
        if not chunk:
            continue
        captured.extend(chunk)
        if not quiet:
            sys.stdout.write(render_terminal_bytes(chunk))
            sys.stdout.flush()
        if expect is not None and expect in captured:
            print(f"received expected byte sequence {expect!r}", file=sys.stderr)
            return 0

    if expect is None:
        print(f"listen timed out after {duration:.1f}s", file=sys.stderr)
        return 0

    print(
        f"timed out after {duration:.1f}s waiting for {expect!r}; "
        f"captured {render_terminal_bytes(bytes(captured))!r}",
        file=sys.stderr,
    )
    return 1


def read_byte(
    ser: serial.Serial,
    offset: int,
    timeout: float,
    *,
    echo: bool = True,
    report: bool = True,
) -> int:
    command = f"R{offset:03X}"
    reply = exchange(ser, command, timeout)
    if echo:
        print_reply(reply)

    lines = normalize_reply_lines(reply)
    if len(lines) < 2 or lines[0].upper() != command:
        raise SystemExit(f"unexpected read reply for {command}: {reply!r}")

    match = READ_REPLY_RE.fullmatch(lines[-1].upper())
    if match is None:
        raise SystemExit(f"unexpected read result line {lines[-1]!r}")

    reply_offset = int(match.group(1), 16)
    if reply_offset != offset:
        raise SystemExit(
            f"read reply address mismatch: expected {offset:03X}, got {reply_offset:03X}"
        )

    value = int(match.group(2), 16)
    if report:
        print(
            f"read {absolute_address(offset):05X} (offset {offset:03X}) = {value:02X}",
            file=sys.stderr,
        )
    return value


def write_byte(ser: serial.Serial, offset: int, value: int, timeout: float, *, echo: bool = True) -> None:
    if not 0 <= value <= 0xFF:
        raise SystemExit(f"value {value:X} is outside byte range 00..FF")

    command = f"W{offset:03X}={value:02X}"
    reply = exchange(ser, command, timeout)
    if echo:
        print_reply(reply)

    lines = normalize_reply_lines(reply)
    if len(lines) < 2 or lines[0].upper() != command:
        raise SystemExit(f"unexpected write reply for {command}: {reply!r}")

    status = lines[-1].upper()
    if status != "OK":
        raise SystemExit(f"write {command} failed with status {status!r}")

    print(
        f"wrote {absolute_address(offset):05X} (offset {offset:03X}) = {value:02X}",
        file=sys.stderr,
    )


def build_write_payload(start_offset: int, data: bytes) -> bytes:
    return b"".join(f"W{start_offset + index:03X}={value:02X}\r".encode("ascii") for index, value in enumerate(data))


def _drain_serial_until_stopped(
    ser: serial.Serial,
    stop_event: threading.Event,
    stats: dict[str, bytes | int | str],
) -> None:
    chunks: list[bytes] = []
    total = 0
    while not stop_event.is_set():
        try:
            data = ser.read(FAST_DRAIN_READ_SIZE)
        except serial.SerialException as exc:
            stats["error"] = str(exc)
            break
        if not data:
            continue
        total += len(data)
        if len(chunks) >= 8:
            chunks.pop(0)
        chunks.append(data)
    stats["bytes"] = total
    stats["tail"] = b"".join(chunks)


def write_range_fast(
    ser: serial.Serial,
    start_offset: int,
    data: bytes,
    baud: int,
    *,
    keep_rx_clean: bool = False,
) -> tuple[float, float]:
    payload = build_write_payload(start_offset, data)
    drain_stats: dict[str, bytes | int | str] = {"bytes": 0, "tail": b""}
    stop_event = threading.Event()
    reader: threading.Thread | None = None

    ser.reset_input_buffer()
    if keep_rx_clean:
        reader = threading.Thread(
            target=_drain_serial_until_stopped,
            args=(ser, stop_event, drain_stats),
            daemon=True,
        )
        reader.start()

    wire_seconds = (len(payload) * BITS_PER_BYTE) / baud
    start = time.perf_counter()
    ser.write(payload)
    ser.flush()
    minimum_wait = wire_seconds
    if keep_rx_clean:
        minimum_wait += FAST_FOLLOWUP_SETTLE_MARGIN
    remaining = start + minimum_wait - time.perf_counter()
    if remaining > 0:
        time.sleep(remaining)
    elapsed = time.perf_counter() - start

    if reader is not None:
        stop_event.set()
        reader.join(timeout=1.0)
        ser.reset_input_buffer()
        drained = int(drain_stats["bytes"])
        tail = bytes(drain_stats["tail"])
        error = str(drain_stats.get("error", ""))
        print(
            f"fast write drained {drained} reply byte(s)"
            + (f"; tail={tail!r}" if tail else "")
            + (f"; reader_error={error}" if error else ""),
            file=sys.stderr,
        )

    return elapsed, wire_seconds

def read_range(
    ser: serial.Serial,
    start_offset: int,
    length: int,
    timeout: float,
    *,
    progress_label: str = "read",
) -> bytes:
    data = bytearray()
    show_progress = sys.stderr.isatty()
    with tqdm(
        total=length,
        unit="B",
        desc=progress_label,
        disable=not show_progress,
        file=sys.stderr,
        leave=False,
    ) as progress:
        for index in range(length):
            data.append(
                read_byte(
                    ser,
                    start_offset + index,
                    timeout,
                    echo=False,
                    report=False,
                )
            )
            progress.update(1)
            if not show_progress and ((index + 1) % 64 == 0 or index + 1 == length):
                print(
                    f"{progress_label} {index + 1}/{length} bytes",
                    file=sys.stderr,
                )
    return bytes(data)


def write_range(
    ser: serial.Serial,
    start_offset: int,
    data: bytes,
    timeout: float,
    *,
    echo: bool = False,
    verify: bool = False,
    progress_label: str = "programmed",
) -> None:
    for index, value in enumerate(data):
        offset = start_offset + index
        write_byte(ser, offset, value, timeout, echo=echo)
        if verify:
            verify_value = read_byte(ser, offset, timeout, echo=echo)
            if verify_value != value:
                raise SystemExit(
                    f"verify mismatch at {absolute_address(offset):05X}: "
                    f"wrote {value:02X}, read back {verify_value:02X}"
                )
        if not echo and ((index + 1) % 64 == 0 or index + 1 == len(data)):
            print(f"{progress_label} {index + 1}/{len(data)} bytes", file=sys.stderr)


def program_image(
    ser: serial.Serial,
    image_path: Path,
    start_offset: int,
    baud: int,
    timeout: float,
    *,
    echo: bool,
    verify: bool,
    fast: bool,
) -> int:
    try:
        data = image_path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"failed to read {image_path}: {exc}") from exc

    remaining = CARD_ROM_SIZE - start_offset
    if len(data) > remaining:
        raise SystemExit(
            f"image is {len(data)} bytes but only {remaining} bytes fit from offset {start_offset:03X}"
        )

    print(
        f"programming {len(data)} byte(s) starting at {absolute_address(start_offset):05X} "
        f"(offset {start_offset:03X})",
        file=sys.stderr,
    )

    if fast:
        elapsed, wire_seconds = write_range_fast(
            ser,
            start_offset,
            data,
            baud,
            keep_rx_clean=verify,
        )
        wire_bps = (len(data) * WRITE_COMMAND_BYTES * BITS_PER_BYTE) / elapsed if elapsed > 0 else float("inf")
        wire_utilization = (wire_bps / baud) * 100 if baud > 0 else float("inf")
        print(
            f"fast write complete: {len(data)} bytes in {elapsed:.3f}s "
            f"({wire_bps:.0f} bit/s on-wire, {wire_utilization:.1f}% of {baud} baud, "
            f"payload wire time {wire_seconds:.3f}s)",
            file=sys.stderr,
        )
        if verify:
            verify_start = time.perf_counter()
            verify_data = read_range(
                ser,
                start_offset,
                len(data),
                timeout,
                progress_label="verify",
            )
            verify_elapsed = time.perf_counter() - verify_start
            print(
                f"verify complete: {len(data)} bytes in {verify_elapsed:.3f}s",
                file=sys.stderr,
            )
            if verify_data != data:
                raise SystemExit("verification failed after fast write")
    else:
        write_range(ser, start_offset, data, timeout, echo=echo, verify=verify)

    print("programming complete", file=sys.stderr)
    return 0


def benchmark_random_write(
    ser: serial.Serial,
    start_offset: int,
    count: int,
    baud: int,
    timeout: float,
    *,
    keep_random: bool,
    verify: bool,
    fast: bool,
) -> int:
    if count < 1:
        raise SystemExit("--count must be at least 1")
    if start_offset + count > CARD_ROM_SIZE:
        raise SystemExit(
            f"requested range offset {start_offset:03X} count {count} exceeds ROM window 000..7FF"
        )

    original = b""
    if not keep_random:
        print(f"reading existing {count} byte(s) for backup", file=sys.stderr)
        original = read_range(
            ser,
            start_offset,
            count,
            timeout,
            progress_label="backup",
        )

    random_data = os.urandom(count)

    print(
        f"writing {count} random byte(s) to "
        f"{absolute_address(start_offset):05X}..{absolute_address(start_offset + count - 1):05X}",
        file=sys.stderr,
    )
    if fast:
        elapsed, wire_seconds = write_range_fast(
            ser,
            start_offset,
            random_data,
            baud,
            keep_rx_clean=verify or not keep_random,
        )
    else:
        start = time.perf_counter()
        write_range(
            ser,
            start_offset,
            random_data,
            timeout,
            echo=False,
            verify=False,
            progress_label="timed write",
        )
        elapsed = time.perf_counter() - start
        wire_seconds = (count * 8 * BITS_PER_BYTE) / baud

    throughput_bytes = count / elapsed if elapsed > 0 else float("inf")
    wire_bps = (count * WRITE_COMMAND_BYTES * BITS_PER_BYTE) / elapsed if elapsed > 0 else float("inf")
    wire_utilization = (wire_bps / baud) * 100 if baud > 0 else float("inf")
    print(
        f"timed write complete: {count} programmed byte(s) in {elapsed:.3f}s "
        f"({throughput_bytes:.1f} programmed B/s, {wire_bps:.0f} bit/s on-wire, "
        f"{wire_utilization:.1f}% of {baud} baud, "
        f"payload wire time {wire_seconds:.3f}s)",
        file=sys.stderr,
    )

    if verify:
        print("verifying random image", file=sys.stderr)
        verify_start = time.perf_counter()
        verify_data = read_range(
            ser,
            start_offset,
            count,
            timeout,
            progress_label="verify",
        )
        verify_elapsed = time.perf_counter() - verify_start
        print(
            f"verify complete: {count} bytes in {verify_elapsed:.3f}s",
            file=sys.stderr,
        )
        if verify_data != random_data:
            raise SystemExit("verification failed: ROM contents do not match written random data")
        print("verification passed", file=sys.stderr)

    if keep_random:
        print("leaving random data in card ROM", file=sys.stderr)
        return 0

    print("restoring original ROM contents", file=sys.stderr)
    if fast:
        write_range_fast(ser, start_offset, original, baud, keep_rx_clean=False)
    else:
        write_range(
            ser,
            start_offset,
            original,
            timeout,
            echo=False,
            verify=False,
            progress_label="restored",
        )
    print("restore complete", file=sys.stderr)
    return 0


def main() -> int:
    args = parse_args()
    port = args.port or detect_second_usb_serial_port()
    command = args.command or "probe"

    print(f"opening {port} at {args.baud} baud", file=sys.stderr)

    with serial.Serial(port, baudrate=args.baud, timeout=0.1, write_timeout=1.0) as ser:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        discarded = drain_until_quiet(ser)
        ser.reset_input_buffer()
        if discarded:
            print(
                f"discarded {discarded} stale reply byte(s) before issuing a new command",
                file=sys.stderr,
            )

        if command == "probe":
            probe_command = getattr(args, "probe_command", DEFAULT_COMMAND)
            print(f"sending {probe_command.encode('ascii') + b'\\r'!r}", file=sys.stderr)
            return run_probe(ser, command=probe_command, expect=args.expect, timeout=args.timeout)

        if command == "raw":
            raw_text = getattr(args, "text")
            print(f"sending {raw_text.encode('ascii') + b'\\r'!r}", file=sys.stderr)
            return run_raw(ser, command=raw_text, expect=args.expect, timeout=args.timeout)

        if command == "timing":
            cycles = getattr(args, "cycles")
            print(f"setting read timing to {cycles * 10} ns", file=sys.stderr)
            return run_timing(ser, cycles=cycles, timeout=args.timeout)

        if command == "control-timing":
            cycles = getattr(args, "cycles")
            print(
                f"setting control-write timing to {cycles * 10} ns",
                file=sys.stderr,
            )
            return run_control_timing(ser, cycles=cycles, timeout=args.timeout)

        if command == "listen":
            expect = getattr(args, "expect", None)
            expect_bytes = decode_expect_text(expect) if expect is not None else None
            print(f"listening for raw UART bytes for {args.duration:.1f}s", file=sys.stderr)
            return listen_for_bytes(
                ser,
                duration=args.duration,
                expect=expect_bytes,
                quiet=args.quiet,
            )

        if command == "read":
            offset = rom_offset_from_address(args.address)
            read_byte(ser, offset, args.timeout)
            return 0

        if command == "write":
            offset = rom_offset_from_address(args.address)
            write_byte(ser, offset, args.value, args.timeout)
            return 0

        if command == "program":
            start_offset = rom_offset_from_address(args.start)
            return program_image(
                ser,
                args.image,
                start_offset,
                args.baud,
                args.timeout,
                echo=args.echo,
                verify=args.verify,
                fast=args.fast,
            )

        if command == "benchmark-random":
            start_offset = rom_offset_from_address(args.start)
            return benchmark_random_write(
                ser,
                start_offset,
                args.count,
                args.baud,
                args.timeout,
                keep_random=args.keep_random,
                verify=args.verify,
                fast=args.fast,
            )

    raise AssertionError(f"unhandled command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5"]
# ///
"""Au1 USB-UART client for a removable Sharp organizer card."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


BAUD = 5_000_000
BURST_CHUNK = 65535
CONTROL_BITS = "RW OE CI E2 MSKROM SRAM1 SRAM2 EPROM".split()
PROTECTED_BITS = "STNBY VBATT VPP NC02 NC42 NC43 NC44".split()


def number(text: str) -> int:
    return int(text, 0)


def bounded(value: int, bits: int, label: str) -> int:
    if not 0 <= value < 1 << bits:
        raise ValueError(f"{label} must fit in {bits} bits: {value}")
    return value


def open_port(path: str, baud: int = BAUD):
    import serial

    port = serial.Serial(port=None, baudrate=baud, timeout=0.5, write_timeout=0.5)
    port.dtr = False
    port.rts = False
    port.port = path
    port.open()
    port.reset_input_buffer()
    return port


def read_exact(port, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = port.read(size - len(result))
        if not chunk:
            raise TimeoutError(f"UART response ended after {len(result)}/{size} bytes")
        result.extend(chunk)
    return bytes(result)


@dataclass(frozen=True)
class Snapshot:
    address: int
    data: int
    control: int
    protected: int
    address_drive: int
    address_oe: int
    control_drive: int
    control_oe: int
    armed: bool

    @classmethod
    def decode(cls, raw: bytes) -> Snapshot:
        if len(raw) != 16 or raw[0] != ord("S"):
            raise ValueError(f"invalid snapshot: {raw.hex(' ')}")
        return cls(
            address=int.from_bytes(raw[1:4], "big"),
            data=raw[4],
            control=raw[5],
            protected=raw[6],
            address_drive=int.from_bytes(raw[7:10], "big"),
            address_oe=int.from_bytes(raw[10:13], "big"),
            control_drive=raw[13],
            control_oe=raw[14],
            armed=bool(raw[15]),
        )


class Probe:
    def __init__(self, port):
        self.port = port
        self.protocol: str | None = None
        self.burst_phase_ns = 5000

    def __enter__(self) -> Probe:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.protocol is not None:
            self.park()

    def exchange(self, payload: bytes, size: int) -> bytes:
        if self.port.write(payload) != len(payload):
            raise IOError("short UART write")
        self.port.flush()
        return read_exact(self.port, size)

    def ack(self, payload: bytes, expected: bytes) -> None:
        actual = self.exchange(payload, 1)
        if actual != expected:
            raise RuntimeError(f"probe rejected {payload[:1]!r}: {actual!r}")

    def identify(self) -> None:
        actual = self.exchange(b"I", 5)
        if actual not in (b"OBP2\n", b"OBP3\n", b"OBP4\n"):
            raise RuntimeError(f"wrong gateware or UART framing: {actual!r}")
        self.protocol = actual.decode().strip()

    def snapshot(self) -> Snapshot:
        return Snapshot.decode(self.exchange(b"?", 16))

    def unlock(self) -> None:
        self.ack(b"UREAD", b"U")

    def release(self) -> None:
        self.ack(b"Z", b"Z")

    def park(self) -> Snapshot:
        """Release FPGA outputs and verify the observable drive enables are zero."""
        self.release()
        snapshot = self.snapshot()
        if snapshot.armed or snapshot.address_oe or snapshot.control_oe:
            raise RuntimeError(f"probe is still driving pins: {format_snapshot(snapshot)}")
        return snapshot

    def set_read_timing(self, phase_ns: int) -> None:
        if phase_ns % 50 or not 200 <= phase_ns <= 5000:
            raise ValueError("read phase must be 200..5000 ns in 50 ns steps")
        if self.protocol not in ("OBP3", "OBP4"):
            raise RuntimeError("adjustable read timing requires OBP3 or OBP4 gateware")
        self.ack(bytes([ord("T"), phase_ns // 50]), b"T")
        self.burst_phase_ns = phase_ns

    def address(self, value: int, mask: int) -> None:
        value = bounded(value, 20, "address")
        mask = bounded(mask, 20, "address mask")
        self.ack(b"A" + value.to_bytes(3, "big") + mask.to_bytes(3, "big"), b"A")

    def control(self, value: int, mask: int) -> None:
        value = bounded(value, 8, "control")
        mask = bounded(mask, 8, "control mask")
        self.ack(bytes([ord("C"), value, mask]), b"C")

    def burst(self, start: int, count: int, idle: int, active: int, mask: int) -> bytes:
        bounded(start, 20, "start")
        bounded(count, 16, "count")
        if count == 0 or start + count > 1 << 20:
            raise ValueError("burst range must be nonempty and within 20 address bits")
        validate_cycle(idle, active, mask, 0)
        if not (mask & idle & active & 1):
            raise ValueError("burst reads must drive RW high in both phases")
        request = (b"R" + start.to_bytes(3, "big") + count.to_bytes(2, "big")
                   + bytes([idle, active, mask]))
        if self.port.write(request) != len(request):
            raise IOError("short UART write")
        self.port.flush()
        ack = read_exact(self.port, 1)
        if ack != b"R":
            raise RuntimeError(f"probe rejected burst: {ack!r}")
        return read_exact(self.port, count)

    def write_byte(self, address: int, value: int, sram: int) -> None:
        if self.protocol not in ("OBP3", "OBP4"):
            raise RuntimeError("SRAM writes require OBP3 or OBP4 gateware")
        bounded(address, 20, "address")
        bounded(value, 8, "data")
        if sram not in (1, 2):
            raise ValueError("SRAM selector must be 1 or 2")
        self.ack(b"W" + address.to_bytes(3, "big") + bytes([value, sram]), b"W")

    def write_profiled_byte(self, address: int, value: int, selected: int) -> None:
        if self.protocol != "OBP4":
            raise RuntimeError("profiled SRAM writes require OBP4 gateware")
        bounded(address, 20, "address")
        bounded(value, 8, "data")
        bounded(selected, 8, "selected control")
        if selected & 0x93 != 0x93 or selected & 0x60 not in (0x20, 0x40):
            raise ValueError("write profile must select exactly one SRAM with RW/OE and ROM selects high")
        selector = 1 if selected & 0x20 == 0 else 2
        config = selector | (~selected & 0x0c)
        self.ack(b"W" + address.to_bytes(3, "big") + bytes([value, config]), b"W")


def format_snapshot(s: Snapshot) -> str:
    controls = ",".join(name for bit, name in enumerate(CONTROL_BITS) if s.control & (1 << bit))
    protected = ",".join(name for bit, name in enumerate(PROTECTED_BITS) if s.protected & (1 << bit))
    return (
        f"addr=0x{s.address:05x} data=0x{s.data:02x} control=0x{s.control:02x} "
        f"[{controls}] protected=0x{s.protected:02x} [{protected}]\n"
        f"drive addr=0x{s.address_drive:05x}/0x{s.address_oe:05x} "
        f"control=0x{s.control_drive:02x}/0x{s.control_oe:02x} armed={s.armed}"
    )


def validate_cycle(idle: int, active: int, mask: int, settle_us: int) -> None:
    bounded(idle, 8, "idle control")
    bounded(active, 8, "active control")
    bounded(mask, 8, "control mask")
    if mask == 0 or ((idle ^ active) & mask) == 0:
        raise ValueError("idle and active must differ on a driven control bit")
    if not 0 <= settle_us <= 100_000:
        raise ValueError("settle-us must be between 0 and 100000")


def cycle(probe: Probe, address: int, idle: int, active: int, mask: int, settle_us: int) -> Snapshot:
    probe.control(idle, mask)
    probe.address(address, 0xFFFFF)
    try:
        probe.control(active, mask)
        if settle_us:
            time.sleep(settle_us / 1_000_000)
        snapshot = probe.snapshot()
    finally:
        probe.control(idle, mask)
    if not snapshot.armed or snapshot.address_oe != 0xFFFFF or snapshot.control_oe != mask:
        raise RuntimeError(f"drive was lost during read: {format_snapshot(snapshot)}")
    if snapshot.address != address or ((snapshot.control ^ active) & mask):
        raise RuntimeError(f"observed pins differ from requested cycle: {format_snapshot(snapshot)}")
    return snapshot


def run_dump(probe: Probe, args) -> None:
    bounded(args.start, 20, "start")
    if args.length < 1 or args.start + args.length > 1 << 20:
        raise ValueError("dump range must be nonempty and within 20 address bits")
    if args.passes < 2:
        raise ValueError("dump requires at least two comparison passes")
    validate_cycle(args.idle, args.active, args.mask, args.settle_us)
    if not (args.mask & args.idle & args.active & 1):
        raise ValueError("dumps must drive RW high in both phases")
    baseline: bytearray | None = None
    try:
        for pass_index in range(args.passes):
            current = bytearray()
            for offset in range(0, args.length, 1 if args.slow else BURST_CHUNK):
                count = min(1 if args.slow else BURST_CHUNK, args.length - offset)
                probe.unlock()
                if args.slow:
                    data = bytes([cycle(
                        probe, args.start + offset, args.idle, args.active, args.mask,
                        args.settle_us,
                    ).data])
                else:
                    data = probe.burst(args.start + offset, count, args.idle, args.active, args.mask)
                if baseline is not None:
                    for index, value in enumerate(data):
                        if value != baseline[offset + index]:
                            address = args.start + offset + index
                            raise RuntimeError(
                                f"read mismatch at 0x{address:05x}: "
                                f"first=0x{baseline[offset + index]:02x} "
                                f"pass{pass_index + 1}=0x{value:02x}"
                            )
                current.extend(data)
            if baseline is None:
                baseline = current
            print(f"pass {pass_index + 1}/{args.passes}: {len(current)} bytes matched")
    finally:
        if sys.exc_info()[0] is None:
            probe.release()
        else:
            try:
                probe.release()
            except (OSError, TimeoutError, RuntimeError):
                pass
    assert baseline is not None
    args.output.write_bytes(baseline)
    metadata = {
        "start": args.start,
        "length": args.length,
        "passes": args.passes,
        "idle": args.idle,
        "active": args.active,
        "control_mask": args.mask,
        "settle_us": args.settle_us if args.slow else None,
        "mode": "slow" if args.slow else "burst",
        "uart_baud": getattr(probe.port, "baudrate", None),
        "burst_request_bytes": None if args.slow else BURST_CHUNK,
        "burst_phase_us": None if args.slow else probe.burst_phase_ns / 1000,
        "sha256": hashlib.sha256(baseline).hexdigest(),
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(json.dumps(metadata, indent=2))


def read_sram_byte(probe: Probe, address: int, sram: int) -> int:
    if sram not in (1, 2):
        raise ValueError("SRAM selector must be 1 or 2")
    active = 0xDD if sram == 1 else 0xBD
    probe.unlock()
    try:
        return probe.burst(address, 1, 0xFF, active, 0xFF)[0]
    finally:
        probe.release()


def verify_committed_backup(image: Path) -> None:
    image = image.resolve()
    try:
        repo = subprocess.run(
            ["git", "-C", str(image.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, check=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError("SRAM backup is not in a Git repository") from exc
    root = Path(repo).resolve()
    for path in (image, image.with_suffix(".bin.json")):
        relative = path.relative_to(root).as_posix()
        try:
            committed = subprocess.run(
                ["git", "-C", str(root), "show", f"HEAD:{relative}"],
                capture_output=True, check=True,
            ).stdout
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"SRAM backup is not committed at HEAD: {path}") from exc
        if committed != path.read_bytes():
            raise ValueError(f"backup file differs from HEAD: {path}")


def test_sram_write(probe: Probe, backup_image: Path, result_dir: Path,
                    sram: int, address: int | None) -> dict:
    if probe.protocol not in ("OBP3", "OBP4"):
        raise RuntimeError("SRAM write test requires OBP3 or OBP4 gateware")
    verify_committed_backup(backup_image)
    backup = backup_image.read_bytes()
    if not backup or len(backup) > 1 << 20:
        raise ValueError("backup must contain 1 through 1048576 bytes")
    backup_metadata = json.loads(backup_image.with_suffix(".bin.json").read_text())
    backup_sha256 = hashlib.sha256(backup).hexdigest()
    if backup_metadata["sha256"] != backup_sha256 or backup_metadata["length"] != len(backup):
        raise ValueError("backup bytes do not match their committed metadata")
    if backup_metadata.get("media_kind") != "battery_backed_sram":
        raise ValueError("backup image is not attributed to battery-backed SRAM")
    if address is None:
        address = len(backup) - 1
    if not 0 <= address < len(backup):
        raise ValueError("test address is outside the backup")
    if result_dir.exists():
        raise FileExistsError(result_dir)
    result_dir.mkdir(parents=True)
    active = 0xDD if sram == 1 else 0xBD

    def dump_to(name: str) -> bytes:
        image = result_dir / name
        run_dump(probe, SimpleNamespace(
            start=0, length=len(backup), passes=2, idle=0xFF, active=active,
            mask=0xFF, settle_us=20, slow=False, output=image,
        ))
        return image.read_bytes()

    before = dump_to("before.bin")
    if before != backup:
        raise RuntimeError("live SRAM differs from the committed backup; no write attempted")
    original = backup[address]
    trial = original ^ 0x5A
    observed_trial = None
    restore_error = None
    attempted = False
    try:
        probe.unlock()
        attempted = True
        probe.write_byte(address, trial, sram)
        snapshot = probe.snapshot()
        if snapshot.armed or snapshot.address_oe or snapshot.control_oe:
            raise RuntimeError("write command left address/control pins driven")
        observed_trial = read_sram_byte(probe, address, sram)
    finally:
        if attempted:
            try:
                probe.unlock()
                probe.write_byte(address, original, sram)
            except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
                restore_error = str(exc)
        probe.release()

    after = dump_to("after-restore.bin")
    result = {
        "schema": 1,
        "protocol": probe.protocol,
        "backup_image": str(backup_image),
        "backup_sha256": backup_sha256,
        "sram_selector": sram,
        "address": address,
        "original": original,
        "trial": trial,
        "observed_trial": observed_trial,
        "restore_error": restore_error,
        "after_restore_sha256": hashlib.sha256(after).hexdigest(),
        "after_restore_matches_backup": after == backup,
        "write_verified": observed_trial == trial and restore_error is None and after == backup,
    }
    (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def shell(probe: Probe) -> None:
    print("Commands: i identify; s sample; a VALUE MASK; c VALUE MASK; "
          "r ADDRESS IDLE ACTIVE MASK [SETTLE_US]; z release; q quit")
    print("Each drive command unlocks; idle for one second releases the pins.")
    while True:
        try:
            words = shlex.split(input("probe> "))
        except EOFError:
            break
        if not words:
            continue
        try:
            op, *arg = words
            values = [number(value) for value in arg]
            if op in ("q", "quit"):
                break
            if op == "i" and not arg:
                probe.identify()
                print(probe.protocol)
            elif op == "s" and not arg:
                print(format_snapshot(probe.snapshot()))
            elif op == "a" and len(values) == 2:
                probe.unlock()
                probe.address(*values)
                print(format_snapshot(probe.snapshot()))
            elif op == "c" and len(values) == 2:
                probe.unlock()
                probe.control(*values)
                print(format_snapshot(probe.snapshot()))
            elif op == "r" and len(values) in (4, 5):
                address, idle, active, mask = values[:4]
                settle_us = values[4] if len(values) == 5 else 20
                validate_cycle(idle, active, mask, settle_us)
                probe.unlock()
                try:
                    print(format_snapshot(cycle(probe, address, idle, active, mask, settle_us)))
                finally:
                    probe.release()
            elif op == "z" and not arg:
                probe.release()
                print("released")
            else:
                print("invalid command or argument count")
        except (OSError, ValueError, TimeoutError, RuntimeError) as exc:
            print(f"error: {exc}")
    probe.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Au1 USB-UART device path")
    parser.add_argument("--baud", type=int, default=BAUD, help="USB-UART baud rate (default: 5000000)")
    parser.add_argument("--read-phase-ns", type=int, default=5000,
                        help="each burst read phase in ns, 200..5000 in 50 ns steps")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("identify")
    commands.add_parser("sample")
    commands.add_parser("park", help="release outputs and verify zero drive masks")
    commands.add_parser("shell")
    single = commands.add_parser("cycle", help="run one explicit control cycle")
    dump = commands.add_parser("dump", help="read and compare at least two passes")
    for command in (single, dump):
        command.add_argument("--idle", type=number, required=True)
        command.add_argument("--active", type=number, required=True)
        command.add_argument("--mask", type=number, required=True)
        command.add_argument("--settle-us", type=number, default=20)
    single.add_argument("--address", type=number, required=True)
    dump.add_argument("--start", type=number, default=0)
    dump.add_argument("--length", type=number, required=True)
    dump.add_argument("--passes", type=int, default=2)
    dump.add_argument("--slow", action="store_true", help="use host-timed single-byte cycles")
    dump.add_argument("--output", type=Path, required=True)
    banks = commands.add_parser("dump-banks", help="read named banks from a JSON pin plan")
    banks.add_argument("--plan", type=Path, required=True)
    banks.add_argument("--output-dir", type=Path, required=True)
    banks.add_argument("--passes", type=int, default=2)
    banks.add_argument("--slow", action="store_true", help="use host-timed single-byte cycles")
    banks.add_argument("--settle-us", type=number, default=20)
    banks.add_argument("--dry-run", action="store_true", help="validate and show selections without accessing hardware")
    card = commands.add_parser("dump-card", help="discover and capture all single-select card views")
    card.add_argument("--output-dir", type=Path, required=True)
    card.add_argument("--passes", type=int, default=2)
    card.add_argument("--scan-length", type=number, default=1 << 20)
    card.add_argument("--reported-model")
    archive = commands.add_parser("capture-card", help="capture, commit backup, then probe SRAM candidates")
    archive.add_argument("--archive-dir", type=Path, required=True,
                         help="capture parent directory inside a Git repository")
    archive.add_argument("--capture-id", help="UTC capture directory name; defaults to current UTC time")
    archive.add_argument("--scan-length", type=number, default=1 << 20)
    archive.add_argument("--reported-model")
    archive.add_argument("--read-only", action="store_true", help="commit capture without write probes")
    archive.add_argument("--passes", type=int, default=2)
    import_capture = commands.add_parser("archive-discovery", help="archive a completed read-only discovery scan")
    import_capture.add_argument("--source-dir", type=Path, required=True)
    import_capture.add_argument("--archive-dir", type=Path, required=True)
    import_capture.add_argument("--capture-id")
    import_capture.add_argument("--read-only", action="store_true")
    probe_ram_cmd = commands.add_parser("probe-ram", help="probe SRAM from a committed capture")
    probe_ram_cmd.add_argument("--capture-dir", type=Path, required=True)
    probe_ram_cmd.add_argument("--result-dir", type=Path, required=True)
    write_sram_cmd = commands.add_parser("write-sram", help="write verified SRAM from a committed backup")
    write_sram_cmd.add_argument("--capture-dir", type=Path, required=True)
    write_sram_cmd.add_argument("--probe-result", type=Path, required=True)
    write_sram_cmd.add_argument("--view", required=True)
    write_sram_cmd.add_argument("--address", type=number, required=True)
    write_sram_cmd.add_argument("--input", type=Path, required=True)
    write_sram_cmd.add_argument("--expected-image", type=Path,
                                help="committed current full-bank image; defaults to original capture")
    write_sram_cmd.add_argument("--result-dir", type=Path, required=True)
    write_test = commands.add_parser("test-sram-write", help="test one byte and restore it from a committed SRAM backup")
    write_test.add_argument("--backup-image", type=Path, required=True)
    write_test.add_argument("--result-dir", type=Path, required=True)
    write_test.add_argument("--sram", type=int, choices=(1, 2), required=True)
    write_test.add_argument("--address", type=number)
    args = parser.parse_args()
    if args.command == "dump-banks":
        from bank_dump import describe_plan, load_plan, run_plan

        plan = load_plan(args.plan)
        if args.dry_run:
            print(json.dumps(describe_plan(plan), indent=2))
            return
    if not args.port:
        parser.error("--port is required for hardware commands")
    with open_port(args.port, args.baud) as port, Probe(port) as probe:
        probe.identify()
        if args.read_phase_ns != 5000:
            probe.set_read_timing(args.read_phase_ns)
        if args.command == "identify":
            print(probe.protocol)
        elif args.command == "sample":
            print(format_snapshot(probe.snapshot()))
        elif args.command == "park":
            print(format_snapshot(probe.park()))
        elif args.command == "shell":
            shell(probe)
        elif args.command == "cycle":
            validate_cycle(args.idle, args.active, args.mask, args.settle_us)
            probe.unlock()
            try:
                sample = cycle(
                    probe, args.address, args.idle, args.active, args.mask, args.settle_us
                )
                print(format_snapshot(sample))
            finally:
                probe.release()
        elif args.command == "dump-banks":
            result = run_plan(probe, plan, args.output_dir, args.passes,
                              args.slow, args.settle_us)
            print(json.dumps({"output_dir": str(args.output_dir),
                              "banks": len(result["banks"]),
                              "plan_sha256": result["plan_sha256"]}, indent=2))
        elif args.command == "dump-card":
            from card_discovery import capture

            result = capture(probe, args.output_dir, limit=args.scan_length,
                             passes=args.passes, reported_model=args.reported_model)
            print(json.dumps({"output_dir": str(args.output_dir),
                              "images": len(result["images"]),
                              "views": len(result["views"])}, indent=2))
        elif args.command in ("capture-card", "archive-discovery"):
            from datetime import datetime, timezone
            from card_discovery import capture, validate_capture_files
            from card_write import commit_capture, commit_directory, probe_ram

            capture_id = args.capture_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", capture_id):
                raise ValueError("capture ID must use letters, digits, underscore or hyphen")
            dest = args.archive_dir / capture_id
            if args.command == "capture-card":
                result = capture(probe, dest, limit=args.scan_length, passes=args.passes,
                                 reported_model=args.reported_model)
            else:
                source_manifest = validate_capture_files(args.source_dir)
                if source_manifest.get("gateware_protocol") != probe.protocol:
                    raise ValueError("source protocol differs from the connected probe")
                result = source_manifest
                shutil.copytree(args.source_dir, dest)
            backup_commit = commit_capture(dest)
            summary = {"capture_dir": str(dest), "backup_commit": backup_commit,
                       "images": len(result["images"]), "views": len(result["views"])}
            if not args.read_only:
                probe_dir = dest / "write-probes"
                try:
                    summary["ram_probe"] = probe_ram(probe, dest, probe_dir)
                finally:
                    if (probe_dir / "result.json").exists():
                        summary["probe_commit"] = commit_directory(probe_dir,
                            f"Record Sharp organizer SRAM probes {capture_id}")
            print(json.dumps(summary, indent=2))
        elif args.command == "probe-ram":
            from card_write import commit_directory, probe_ram

            try:
                result = probe_ram(probe, args.capture_dir, args.result_dir)
            finally:
                if (args.result_dir / "result.json").exists():
                    commit_directory(args.result_dir, "Record Sharp organizer SRAM presence probes")
            print(json.dumps(result, indent=2))
        elif args.command == "write-sram":
            from card_write import commit_directory, write_sram

            try:
                result = write_sram(probe, args.capture_dir, args.probe_result,
                                    args.view, args.address, args.input.read_bytes(),
                                    args.result_dir, args.expected_image)
            finally:
                if (args.result_dir / "result.json").exists():
                    commit_directory(args.result_dir,
                        f"Record Sharp organizer SRAM write {args.view}")
            print(json.dumps(result, indent=2))
        elif args.command == "test-sram-write":
            result = test_sram_write(probe, args.backup_image, args.result_dir,
                                     args.sram, args.address)
            print(json.dumps(result, indent=2))
            if not result["write_verified"]:
                raise RuntimeError("SRAM write or full restore did not verify")
        else:
            run_dump(probe, args)


if __name__ == "__main__":
    main()

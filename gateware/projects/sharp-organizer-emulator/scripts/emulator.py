#!/usr/bin/env python3
"""OEM1 UART control and FT600 trace/continuous-input tools; no catalog paths."""

from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import struct
import sys
import threading
import time
from functools import reduce
from operator import xor
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROM_SIZE = 0x4000
PAYLOAD_START, MAILBOX, SEQUENCE, CONTROL = 0x400, 0x3FC0, 0x3FDF, 0x3FF0
STATUS_NAMES = {
    1: "checksum",
    2: "range/argument",
    3: "busy/protected",
    4: "unsealed image",
    5: "unknown command",
}
CONTROL_NAMES = ("RW", "OE", "CI", "E2", "MSKROM", "SRAM1", "SRAM2", "EPROM")
AUX_NAMES = ("STNBY", "VBATT", "VPP", "NC02", "NC42", "NC43", "NC44")


class ProtocolError(OSError):
    pass


class StatusError(ProtocolError):
    def __init__(self, op, code):
        self.code = code
        super().__init__(f"{op}: {STATUS_NAMES.get(code, 'unknown status')} ({code})")


def request(op: str, address=0, arg0=0, arg1=0, arg2=0) -> bytes:
    if (
        len(op) != 1
        or not 0 <= address <= 0xFFFF
        or any(not 0 <= x <= 255 for x in (arg0, arg1, arg2))
    ):
        raise ValueError("invalid command fields")
    body = struct.pack("<BBHBBB", 0xA5, ord(op), address, arg0, arg1, arg2)
    return body + bytes([reduce(xor, body)])


def decode_reply(raw: bytes, op: str) -> bytes:
    if len(raw) != 16 or raw[:2] != bytes([0xD5, ord(op)]) or reduce(xor, raw):
        raise ProtocolError(f"invalid OEM1 reply: {raw.hex()}")
    if raw[2]:
        raise StatusError(op, raw[2])
    return raw[3:15]


class Client:
    """One command outstanding. Closing the UART does not disarm the card."""

    def __init__(self, port: str, *, serial_factory=None):
        if serial_factory is None:
            import serial

            serial_factory = serial.Serial
        self.serial = serial_factory(
            port, baudrate=4_000_000, timeout=1, write_timeout=1
        )
        self.lock = threading.Lock()
        try:
            if self.command("I")[:4] != b"OEM1":
                raise ProtocolError("this port is not an OEM1 organizer emulator")
        except Exception:
            self.close()
            raise

    def command(self, op, address=0, arg0=0, arg1=0, arg2=0):
        deadline = time.monotonic() + 1
        while True:
            try:
                return self._command_once(op, address, arg0, arg1, arg2)
            except StatusError as exc:
                # A BUSY memory operation has no side effect and can be
                # retried in a gap between the CPU's mailbox polls.
                if (
                    exc.code != 3
                    or op not in ("R", "W")
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.001)

    def _command_once(self, op, address=0, arg0=0, arg1=0, arg2=0):
        with self.lock:
            return self._exchange(op, address, arg0, arg1, arg2)

    def _exchange(self, op, address, arg0, arg1, arg2):
        raw = request(op, address, arg0, arg1, arg2)
        if self.serial.write(raw) != len(raw):
            raise ProtocolError(
                "partial UART request; wait for parser timeout before reconnecting"
            )
        deadline = time.monotonic() + 1
        reply = bytearray()
        while len(reply) < 16 and time.monotonic() < deadline:
            chunk = self.serial.read(16 - len(reply))
            if not chunk:
                break
            reply.extend(chunk)
        return decode_reply(bytes(reply), op)

    def status(self):
        data = self.command("S")
        seq, drops, underflows = struct.unpack("<III", self.command("S", 1))
        return dict(
            protocol="OEM1",
            armed=bool(data[0] & 1),
            idle=bool(data[0] & 2),
            sealed=bool(data[0] & 4),
            rx_empty=bool(data[0] & 8),
            rx_full=bool(data[0] & 16),
            trace_full=bool(data[0] & 32),
            read_delay_ns=data[1] * 10,
            write_delay_ns=data[2] * 10,
            flags=data[3],
            rom_select=CONTROL_NAMES[(data[4].bit_length() - 1)] if data[4] else None,
            timing_version=int.from_bytes(data[5:7], "little"),
            last_begin=data[7],
            last_end=data[8],
            attempted_records=seq,
            dropped_records=drops,
            rx_underflows=underflows,
        )

    def token(self, op):
        return self.command(op, 0x5241, 0x4D, 0x21)

    def read(self, address, size):
        check_memory_range(address, size)
        return bytes(self.command("R", address + i)[0] for i in range(size))

    def write(self, address, data, *, verify=True):
        check_memory_range(address, len(data))
        for i, byte in enumerate(data):
            self.command("W", address + i, byte)
        if verify and self.read(address, len(data)) != data:
            raise ProtocolError("UART memory readback differs; image remains unsealed")

    def load(self, image: bytes):
        if len(image) != ROM_SIZE:
            raise ValueError("load requires a complete 16384-byte image")
        self.command("Z")
        self.write(0, image)
        self.token("V")
        return dict(
            image_sha256=hashlib.sha256(image).hexdigest(),
            image_bytes=len(image),
            **self.status(),
        )

    def job(self, payload: bytes, *, timeout=5, wait=True):
        status = self.status()
        if not status["armed"] or not status["idle"] or not status["flags"] & 2:
            raise ProtocolError(
                "native supervisor must be armed, idle, and have eval registers enabled"
            )
        if not payload or len(payload) > MAILBOX - PAYLOAD_START:
            raise ValueError("experiment must occupy 1..15296 bytes at offset 0x0400")
        seq = status["last_end"] % 255 + 1
        # Clear commit byte first. No partial body/upload may start execution.
        self.write(SEQUENCE, b"\0")
        self.write(PAYLOAD_START, payload)
        body = b"XR\x01\0" + bytes([seq, seq]) + bytes(25)
        self.write(MAILBOX, body)
        self.write(SEQUENCE, bytes([seq]), verify=False)
        if not wait:
            return dict(
                sequence=seq,
                state="committed",
                payload_sha256=hashlib.sha256(payload).hexdigest(),
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.status()
            if result["last_end"] == seq and result["idle"]:
                return dict(
                    sequence=seq,
                    payload_sha256=hashlib.sha256(payload).hexdigest(),
                    **result,
                )
            time.sleep(0.02)
        # A hung target keeps running; never overwrite its instructions.
        raise TimeoutError(
            f"experiment {seq} did not return; reset/re-enter supervisor before another upload"
        )

    def close(self):
        self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def check_memory_range(address, size):
    if size < 0 or not (
        (0 <= address < 0x4000 and address + size <= 0x4000)
        or (0x8000 <= address < 0x8800 and address + size <= 0x8800)
    ):
        raise ValueError(
            "memory range must stay within ROM 0000..3fff or SRAM2 8000..87ff"
        )


class TraceDecoder:
    """Incremental decoder; preserves sequence gaps, 10 ns ticks and raw pins."""

    def __init__(self):
        self.pending = bytearray()
        self.previous_sequence = None
        self.previous_ticks = None
        self.tick_epoch = 0
        self.records = 0
        self.gaps = 0

    def feed(self, raw):
        self.pending.extend(raw)
        result = []
        while len(self.pending) >= 16:
            magic, ticks, bus, meta = struct.unpack_from("<IIII", self.pending)
            if magic >> 16 != 0xE701:
                raise ProtocolError(
                    "FT record framing mismatch; reset FPGA and start a fresh capture"
                )
            del self.pending[:16]
            seq = magic & 0xFFFF
            gap = (
                0
                if self.previous_sequence is None
                else (seq - self.previous_sequence - 1) & 0xFFFF
            )
            if self.previous_ticks is not None and ticks < self.previous_ticks:
                self.tick_epoch += 1 << 32
            control = (bus >> 20) & 255
            aux = (meta >> 8) & 127
            kind = bus >> 28
            if kind not in (1, 2, 3):
                raise ProtocolError(f"unknown event kind {kind}")
            result.append(
                dict(
                    sequence=seq,
                    gap_before=gap,
                    ticks=ticks,
                    elapsed_ns=(self.tick_epoch + ticks) * 10,
                    address=bus & 0xFFFFF,
                    kind={1: "read", 2: "write", 3: "register-write"}[kind],
                    data=meta & 255,
                    control=control,
                    pins={
                        name: bool(control & (1 << i))
                        for i, name in enumerate(CONTROL_NAMES)
                    },
                    auxiliary=aux,
                    aux_pins={
                        name: bool(aux & (1 << i)) for i, name in enumerate(AUX_NAMES)
                    },
                    armed=bool(meta & (1 << 16)),
                    idle=bool(meta & (1 << 17)),
                    data_driving=bool(meta & (1 << 18)),
                )
            )
            self.previous_sequence, self.previous_ticks = seq, ticks
            self.records += 1
            self.gaps += gap
        return result

    def finish(self):
        if self.pending:
            raise ProtocolError(
                f"truncated FT record ({len(self.pending)} trailing bytes)"
            )


class Ft600:
    """Reuse the qualified probe's exact-serial D3XX opening/config checks."""

    def __init__(self, serial):
        sys.path.insert(0, str(PROJECT.parent / "sharp-organizer-probe/scripts"))
        from ft600_transport import Ft600 as ProbeFt600

        self.transport = ProbeFt600(serial)
        if sys.platform == "win32":
            self.transport.close()
            raise OSError(
                "this bidirectional FT600 client currently supports the macOS/Linux D3XX ABI"
            )
        import ftd3xx

        self.bindings = ftd3xx
        self.api = ftd3xx._ft

    def read(self, size=65536):
        buffer = ctypes.create_string_buffer(size)
        count = self.api.ULONG()
        status = self.bindings.call_ft(
            self.api.FT_ReadPipeEx,
            self.transport.dev.handle,
            self.api.UCHAR(0),
            buffer,
            self.api.ULONG(size),
            ctypes.byref(count),
            20,
        )
        if status not in self.transport._valid_status or not 0 <= count.value <= size:
            raise OSError(f"FT600 output failed: status={status}, bytes={count.value}")
        return buffer.raw[: count.value]

    def write(self, data):
        if len(data) % 2:
            raise ValueError(
                "FT600 input is a 16-bit stream; provide an even number of bytes"
            )
        buffer = ctypes.create_string_buffer(data, len(data))
        # Keep call-local status: the wrapper's shared dev.status races when
        # independent input/output pipes are serviced by different threads.
        count = self.api.ULONG()
        status = self.bindings.call_ft(
            self.api.FT_WritePipeEx,
            self.transport.dev.handle,
            self.api.UCHAR(0),
            buffer,
            self.api.ULONG(len(data)),
            ctypes.byref(count),
            100,
        )
        if (
            status not in self.transport._valid_status
            or not 0 <= count.value <= len(data)
            or count.value % 2
        ):
            raise OSError(f"FT600 input failed: status={status}, bytes={count.value}")
        return count.value

    def close(self):
        self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def capture(
    client,
    ft,
    output: Path,
    seconds: float,
    input_path: Path | None,
    *,
    stop_on_exit=False,
    decode_live=False,
):
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    if input_path is not None and input_path.stat().st_size % 2:
        raise ValueError(
            "input file length must be even; the CPU receives its exact low/high bytes"
        )
    output.mkdir(parents=True, exist_ok=False)
    before = client.status()
    started = time.time()
    deadline = time.monotonic() + seconds
    stop = threading.Event()
    writer_errors = []
    sent = [0]

    # Separate OS thread keeps outbound draining while inbound backpressure
    # waits for the CPU. A single D3XX device has independent RX/TX pipes.
    def feed():
        try:
            if input_path:
                with input_path.open("rb") as source:
                    while not stop.is_set() and time.monotonic() < deadline:
                        chunk = source.read(4096)
                        if not chunk:
                            return
                        offset = 0
                        while (
                            offset < len(chunk)
                            and not stop.is_set()
                            and time.monotonic() < deadline
                        ):
                            count = ft.write(chunk[offset:])
                            offset += count
                            sent[0] += count
                            if count == 0:
                                time.sleep(0.001)
        except Exception as exc:
            writer_errors.append(exc)
            stop.set()

    writer = threading.Thread(target=feed, name="organizer-ft-input", daemon=True)
    decoder = TraceDecoder()
    raw_bytes = 0
    error = None
    cleanup_errors = []
    writer.start()
    try:
        with (
            (output / "trace.bin").open("wb") as raw_file,
            (output / "events.jsonl").open("w") as event_file,
        ):
            while not stop.is_set() and time.monotonic() < deadline:
                raw = ft.read()
                raw_file.write(raw)
                raw_bytes += len(raw)
                if decode_live:
                    for event in decoder.feed(raw):
                        event_file.write(json.dumps(event) + "\n")
    except BaseException as exc:
        error = str(exc)
        raise
    finally:
        stop.set()
        writer.join(timeout=1)
        if writer.is_alive():
            writer_errors.append(TimeoutError("FT input transfer did not stop"))
        if stop_on_exit:
            try:
                client.command("Z")
            except Exception as exc:
                cleanup_errors.append(str(exc))
        try:
            after = client.status()
        except Exception as exc:
            after = None
            cleanup_errors.append(str(exc))
        manifest = dict(
            format="OEM1-capture-v1",
            started_unix=started,
            ended_unix=time.time(),
            ft_serial=ft.transport.serial,
            ft_configuration=ft.transport.configuration,
            before=before,
            after=after,
            raw_bytes=raw_bytes,
            decode_live=decode_live,
            records=decoder.records if decode_live else raw_bytes // 16,
            observed_sequence_gaps=decoder.gaps if decode_live else None,
            trailing_record_bytes=len(decoder.pending)
            if decode_live
            else raw_bytes % 16,
            input_bytes_sent=sent[0],
            input_file=str(input_path) if input_path else None,
            error=error,
            input_errors=[str(e) for e in writer_errors],
            cleanup_errors=cleanup_errors,
            disarm_requested=stop_on_exit,
            disarmed_on_exit=bool(
                stop_on_exit and after and not after.get("armed", True)
            ),
        )
        manifest["input_complete"] = (
            input_path is None or sent[0] == input_path.stat().st_size
        )
        manifest["capture_complete"] = (
            not error
            and not writer_errors
            and not cleanup_errors
            and not manifest["trailing_record_bytes"]
            and manifest["input_complete"]
        )
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if writer_errors:
        raise writer_errors[0]
    if cleanup_errors:
        raise ProtocolError(
            "capture saved, but final UART status/release was not confirmed: "
            + "; ".join(cleanup_errors)
        )
    return manifest


def number(value):
    return int(value, 0)


def build_supervisor(
    assembler_root: Path, cpu_base: int, output: Path, template="supervisor"
):
    if cpu_base < 0 or cpu_base > 0xFC000 or cpu_base % ROM_SIZE:
        raise ValueError("CPU base must be a 16 KiB aligned 20-bit address")
    sys.path.insert(0, str(assembler_root.resolve()))
    from sc62015.pysc62015.sc_asm import Assembler

    source = (
        (PROJECT / "asm" / f"{template}.asm.in")
        .read_text()
        .replace("@BASE@", f"0x{cpu_base:05x}")
    )
    # Templates use individual absolute addresses for assembler portability.
    for offset in (
        0x100,
        0x400,
        0x3FC0,
        0x3FC1,
        0x3FC2,
        0x3FC4,
        0x3FC5,
        0x3FDF,
        0x3FF0,
        0x3FF1,
        0x3FF2,
        0x3FF5,
        0x3FF7,
        0x3FF8,
        0x3FFA,
    ):
        source = source.replace(f"@{offset:04X}@", f"0x{cpu_base + offset:05x}")
    binary = Assembler().assemble(source)
    image = bytearray(ROM_SIZE)
    ranges = []
    lower, upper = (0x100, 0x400) if template == "supervisor" else (0x400, MAILBOX)
    for segment in binary.segments:
        start = segment.address - cpu_base
        data = bytes(segment.data)
        if not lower <= start < upper or start + len(data) > upper:
            raise ValueError(
                f"{template} exceeds reserved {lower:04x}..{upper - 1:04x} area"
            )
        if any(start < end and start + len(data) > begin for begin, end in ranges):
            raise ValueError("overlapping assembled segments")
        ranges.append((start, start + len(data)))
        image[start : start + len(data)] = data
    if not ranges:
        raise ValueError("assembler returned no code")
    if template != "supervisor":
        image = image[lower : max(end for _, end in ranges)]
    output.write_bytes(image)
    output.with_suffix(output.suffix + ".asm").write_text(source)
    meta = dict(
        format="OEM1-image-v1",
        template=template,
        cpu_base=cpu_base,
        entry=cpu_base + lower,
        payload_entry=cpu_base + 0x400,
        mailbox=cpu_base + MAILBOX,
        bytes=len(image),
        sha256=hashlib.sha256(image).hexdigest(),
        header="absent",
        launch="external native PC entry required; organizer boot ABI unqualified",
    )
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(meta, indent=2) + "\n"
    )
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="exact Au1 USB-UART path (4 Mbaud)")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("status", "arm", "disarm"):
        sub.add_parser(name)
    p = sub.add_parser("load")
    p.add_argument("image", type=Path)
    p = sub.add_parser("read")
    p.add_argument("address", type=number)
    p.add_argument("size", type=number)
    p.add_argument("output", type=Path)
    p = sub.add_parser("write")
    p.add_argument("address", type=number)
    p.add_argument("input", type=Path)
    p = sub.add_parser("timing")
    p.add_argument("--read-ns", type=int, required=True)
    p.add_argument("--write-ns", type=int, required=True)
    p = sub.add_parser("config")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--eval", action="store_true")
    p.add_argument("--no-sram", action="store_true")
    p.add_argument("--rom-select", choices=("EPROM", "MSKROM"), default="EPROM")
    p = sub.add_parser("job")
    p.add_argument("payload", type=Path)
    p.add_argument("--timeout", type=float, default=5)
    p.add_argument(
        "--no-wait",
        action="store_true",
        help="commit a continuous experiment and return",
    )
    p = sub.add_parser("capture")
    p.add_argument("--ft-serial", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--input", type=Path)
    p.add_argument("--disarm-on-exit", action="store_true")
    p.add_argument(
        "--decode-live",
        action="store_true",
        help="emit JSONL while capturing; costs CPU throughput",
    )
    p = sub.add_parser("decode")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p = sub.add_parser("build-supervisor")
    p.add_argument("--assembler-root", type=Path, required=True)
    p.add_argument("--cpu-base", type=number, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--template",
        choices=("supervisor", "boot_smoke", "stream_echo"),
        default="supervisor",
    )
    args = parser.parse_args()
    if args.action == "decode":
        if args.input.resolve() == args.output.resolve():
            parser.error("input and decoded output must be different files")
        decoder = TraceDecoder()
        with args.input.open("rb") as source, args.output.open("w") as dest:
            while chunk := source.read(65536):
                for event in decoder.feed(chunk):
                    dest.write(json.dumps(event) + "\n")
            decoder.finish()
        print(
            json.dumps(
                dict(records=decoder.records, observed_sequence_gaps=decoder.gaps)
            )
        )
        return
    if args.action == "build-supervisor":
        print(
            json.dumps(
                build_supervisor(
                    args.assembler_root, args.cpu_base, args.output, args.template
                ),
                indent=2,
            )
        )
        return
    if not args.port:
        parser.error("--port is required for hardware commands")
    with Client(args.port) as client:
        result = None
        if args.action == "status":
            result = client.status()
        elif args.action == "load":
            result = client.load(args.image.read_bytes())
        elif args.action == "arm":
            client.token("A")
            result = client.status()
        elif args.action == "disarm":
            client.command("Z")
            result = client.status()
        elif args.action == "read":
            args.output.write_bytes(client.read(args.address, args.size))
        elif args.action == "write":
            client.write(args.address, args.input.read_bytes())
            result = client.status()
        elif args.action == "timing":
            for value in (args.read_ns, args.write_ns):
                if not 0 <= value <= 2550 or value % 10:
                    parser.error("delays must be multiples of 10 ns in 0..2550")
            client.command("T", arg0=args.read_ns // 10, arg1=args.write_ns // 10)
            result = client.status()
        elif args.action == "config":
            flags = (
                int(args.trace) | (int(args.eval) << 1) | (int(not args.no_sram) << 2)
            )
            client.command(
                "F", arg0=flags, arg1=0x80 if args.rom_select == "EPROM" else 0x10
            )
            result = client.status()
        elif args.action == "job":
            result = client.job(
                args.payload.read_bytes(), timeout=args.timeout, wait=not args.no_wait
            )
        elif args.action == "capture":
            with Ft600(args.ft_serial) as ft:
                result = capture(
                    client,
                    ft,
                    args.output,
                    args.seconds,
                    args.input,
                    stop_on_exit=args.disarm_on_exit,
                    decode_live=args.decode_live,
                )
        if result is not None:
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

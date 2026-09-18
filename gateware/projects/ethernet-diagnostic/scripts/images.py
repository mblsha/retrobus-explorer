#!/usr/bin/env python3
"""Reliable UDP image upload/download and exclusive SD ownership control."""

import argparse
import fcntl
import os
import tempfile
from dataclasses import dataclass
from enum import IntEnum
import hashlib
import json
from pathlib import Path
import secrets
import socket
import struct
import sys
import time
import zlib


SECTOR_BYTES = 512
CAPACITY_SECTORS = 524288
HEADER_BYTES = 24
CRC_BYTES = 4
TRACE_WORDS = 64
ENHANCED_TRACE_MAGIC = 0x32435453
DEFAULT_WINDOW = 10
MAX_WINDOW = 16
BULK_RETRY_LIMIT = 12
BULK_RETRY_SECONDS = 0.02


class Opcode(IntEnum):
    BEGIN = 1
    WRITE = 2
    READ = 3
    ARM = 4
    DISARM = 5
    STATUS = 6
    BULK_READ = 7
    TRACE = 8


ORDERED_OPCODES = frozenset(
    (Opcode.WRITE, Opcode.READ, Opcode.ARM, Opcode.DISARM, Opcode.STATUS)
)


STATUS_MESSAGES = {
    1: "format/CRC",
    2: "session",
    3: "sequence",
    4: "armed or not quiescent",
    5: "bounds/order",
    6: "DDR not initialized",
    7: "memory error",
    8: "incomplete image",
    9: "conflicting retry",
}
# These replies consume the ordered request even when the operation failed.
SEQUENCE_CONSUMING_STATUSES = frozenset((0, 4, 5, 7, 8))


class RemoteError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(
            f"FPGA status {status}: {STATUS_MESSAGES.get(status, 'unknown')}"
        )


def encode(opcode, session, sequence, lba=0, count=0, data=b"", compact=False):
    """Encode a request without changing the legacy padded wire format."""
    if len(data) > SECTOR_BYTES:
        raise ValueError("A block is at most 512 bytes")
    if compact and (opcode not in (Opcode.BULK_READ, Opcode.TRACE) or data):
        raise ValueError("Only bulk reads and SD trace requests are compact")
    body = (
        b"RBS1"
        + bytes([opcode, 0, 0, 0])
        + struct.pack("<IIII", session, sequence, lba, count)
    )
    if not compact:
        body += data.ljust(SECTOR_BYTES, b"\0")
    return body + struct.pack("<I", zlib.crc32(body))


def decode(reply, request):
    """Validate a reply against its request; malformed or stale replies return None."""
    if len(reply) < 6 or reply[:4] != b"RBA1":
        return None
    two_sector_success = (
        request[4] == Opcode.BULK_READ
        and struct.unpack_from("<I", request, 20)[0] == 2
        and reply[5] == 0
    )
    payload_bytes = SECTOR_BYTES * (2 if two_sector_success else 1)
    if len(reply) != HEADER_BYTES + payload_bytes + CRC_BYTES:
        return None
    if reply[4] != request[4] or reply[6:HEADER_BYTES] != request[6:HEADER_BYTES]:
        return None
    if zlib.crc32(reply[:-CRC_BYTES]) != int.from_bytes(reply[-CRC_BYTES:], "little"):
        return None
    return reply[5], reply[HEADER_BYTES:-CRC_BYTES]


def validate_download_range(blocks, start):
    if start < 0 or blocks < 1 or start + blocks > CAPACITY_SECTORS:
        raise ValueError("Download range exceeds physical DDR")


def _uint32(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 0xFFFFFFFF
    ):
        raise ValueError(f"Invalid journal: {name} must be a 32-bit unsigned integer")
    return value


def validate_journal(saved, host):
    """Validate all persisted state before it can cause recovery traffic."""
    if not isinstance(saved, dict):
        raise ValueError("Invalid journal: expected a JSON object")
    if saved.get("host") != host:
        raise ValueError("State belongs to another FPGA address")
    session = _uint32(saved.get("session"), "session")
    sequence = _uint32(saved.get("sequence"), "sequence")

    pending_hex = saved.get("pending")
    pending = None
    if pending_hex is not None:
        if not isinstance(pending_hex, str):
            raise ValueError("Invalid journal: pending request must be hexadecimal")
        try:
            pending = bytes.fromhex(pending_hex)
        except ValueError as error:
            raise ValueError(
                "Invalid journal: pending request is not hexadecimal"
            ) from error
        if len(pending) != HEADER_BYTES + SECTOR_BYTES + CRC_BYTES:
            raise ValueError("Invalid journal: pending request has the wrong length")
        if pending[:4] != b"RBS1" or pending[5:8] != bytes(3):
            raise ValueError("Invalid journal: pending request header is malformed")
        if zlib.crc32(pending[:-CRC_BYTES]) != int.from_bytes(
            pending[-CRC_BYTES:], "little"
        ):
            raise ValueError("Invalid journal: pending request CRC is wrong")
        if pending[4] not in ORDERED_OPCODES:
            raise ValueError("Invalid journal: pending request is not ordered")
        pending_session, pending_sequence = struct.unpack_from("<II", pending, 8)
        if (pending_session, pending_sequence) != (session, sequence):
            raise ValueError(
                "Invalid journal: pending request does not match session state"
            )

    verification = saved.get("initial_upload")
    if verification is not None:
        if not isinstance(verification, dict):
            raise ValueError(
                "Invalid journal: initial_upload must be an object or null"
            )
        marker_session = _uint32(verification.get("session"), "initial_upload.session")
        sectors = verification.get("sectors")
        digest = verification.get("sha256")
        verified = verification.get("verified")
        if marker_session != session:
            raise ValueError("Invalid journal: verification belongs to another session")
        if (
            isinstance(sectors, bool)
            or not isinstance(sectors, int)
            or not 1 <= sectors <= CAPACITY_SECTORS
        ):
            raise ValueError(
                "Invalid journal: verification sector count is out of range"
            )
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Invalid journal: verification SHA-256 is malformed")
        if not isinstance(verified, bool) or (verified and digest is None):
            raise ValueError("Invalid journal: verification state is inconsistent")
    return session, sequence, pending, verification


def load_journal(path, host):
    try:
        saved = json.loads(Path(path).read_text())
    except json.JSONDecodeError as error:
        raise ValueError("Invalid journal: malformed JSON") from error
    return validate_journal(saved, host)


def pending_summary(request):
    if request is None:
        return None
    _, _, lba, count = struct.unpack_from("<IIII", request, 8)
    return {"operation": Opcode(request[4]).name, "lba": lba, "count": count}


def arm_guard_permits(session, verification):
    return bool(
        verification
        and verification.get("verified") is True
        and verification.get("session") == session
        and verification.get("sha256")
    )


def inspect_journal(path, host):
    """Return validated local state without creating a network socket."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Journal does not exist: {path}")
    lock = path.with_suffix(path.suffix + ".lock").open("a")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Session is already in use by another client") from None
        session, sequence, pending, verification = load_journal(path, host)
        return {
            "knowledge": "local journal only; FPGA state was not queried",
            "session": session,
            "next_sequence": sequence,
            "pending": pending_summary(pending),
            "initial_upload": verification,
            "local_arm_guard_permits": arm_guard_permits(session, verification),
        }
    finally:
        lock.close()


@dataclass
class PendingRead:
    """An immutable wire request with mutable retry bookkeeping."""

    request: bytes
    output_offset: int
    sector_count: int
    sent_at: float
    retries: int = 0


class Images:
    def __init__(
        self,
        host="192.168.10.2",
        source="192.168.10.1",
        state=None,
        timeout=0.5,
        progress=None,
    ):
        self.state_path = Path(state) if state else None
        self._lock = None
        self.socket = None
        try:
            if self.state_path:
                self._lock = self.state_path.with_suffix(
                    self.state_path.suffix + ".lock"
                ).open("a")
                try:
                    fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError(
                        "Session is already in use by another client"
                    ) from None
            self.session, self.sequence = 0, 0
            self.last_request = None
            self.pending = None
            self.initial_upload = None
            self.host = host
            self.retries = 0
            self.progress = progress
            if self.state_path and self.state_path.exists():
                (
                    self.session,
                    self.sequence,
                    self.pending,
                    self.initial_upload,
                ) = load_journal(self.state_path, host)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind((source, 0))
            self.socket.connect((host, 4000))
            self.socket.settimeout(timeout)
        except BaseException:
            self.close()
            raise

    def save(self):
        if self.state_path:
            temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "host": self.host,
                        "session": self.session,
                        "sequence": self.sequence,
                        "pending": self.pending.hex() if self.pending else None,
                        "initial_upload": self.initial_upload,
                    }
                )
                + "\n"
            )
            temporary.replace(self.state_path)

    def report(self, message):
        if self.progress is not None:
            self.progress(message)

    def exchange(self, request, retries=8):
        timeout = self.socket.gettimeout()
        try:
            for _ in range(retries):
                self.socket.send(request)
                deadline = time.monotonic() + timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.socket.settimeout(remaining)
                    try:
                        reply = self.socket.recv(2048)
                    except (socket.timeout, ConnectionRefusedError):
                        break
                    decoded = decode(reply, request)
                    if decoded is not None:
                        return decoded
                self.retries += 1
            raise TimeoutError(f"No validated reply after {retries} identical attempts")
        finally:
            self.socket.settimeout(timeout)

    def begin(self, blocks, wait=90):
        if not 1 <= blocks <= CAPACITY_SECTORS:
            raise ValueError("Image must contain 1..524288 sectors")
        self.recover()
        self.report("Waiting for DDR and starting a new image session")
        new_session = secrets.randbelow(0xFFFFFFFF) + 1
        request = encode(Opcode.BEGIN, new_session, 0, count=blocks)
        deadline = time.monotonic() + wait
        while True:
            try:
                status, _ = self.exchange(request, retries=1)
                if status == 0:
                    self.session, self.sequence = new_session, 1
                    self.last_request = request
                    self.initial_upload = {
                        "session": new_session,
                        "sectors": blocks,
                        "sha256": None,
                        "verified": False,
                    }
                    self.save()
                    return
                if status != 6:
                    raise RemoteError(status)
            except (TimeoutError, OSError):
                if time.monotonic() >= deadline:
                    raise
            if time.monotonic() >= deadline:
                raise TimeoutError("DDR did not become ready")
            time.sleep(0.2)

    def recover(self, *, read_only=False):
        if self.pending is not None:
            if read_only and self.pending[4] not in (
                Opcode.READ,
                Opcode.BULK_READ,
                Opcode.STATUS,
            ):
                pending = pending_summary(self.pending)
                raise RuntimeError(
                    f"Cannot perform a read-only operation: this journal contains an "
                    f"unresolved {pending['operation']} to LBA {pending['lba']}. "
                    "No recovery request was sent."
                )
            return self.finish(self.pending)

    def finish(self, request):
        status, payload = self.exchange(request)
        self.last_request = request
        if status in SEQUENCE_CONSUMING_STATUSES:
            self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        self.pending = None
        self.save()
        if status:
            raise RemoteError(status)
        return payload

    def command(self, opcode, lba=0, count=0, data=b""):
        if opcode not in ORDERED_OPCODES:
            raise ValueError(
                "Use begin() or bulk_download() for non-ordered operations"
            )
        if not self.session:
            raise ValueError("Begin an image session first")
        request = encode(opcode, self.session, self.sequence, lba, count, data)
        if opcode == Opcode.ARM and not arm_guard_permits(
            self.session, self.initial_upload
        ):
            raise RuntimeError(
                "Initial upload is not verified; complete a verified upload before ARM"
            )
        # An identical pending request satisfies this call. A different mutating
        # operation explicitly completes the old request before issuing the new one.
        same_request = self.pending == request
        recovered = self.recover(read_only=opcode in (Opcode.READ, Opcode.STATUS))
        if same_request:
            return recovered
        request = encode(opcode, self.session, self.sequence, lba, count, data)
        self.pending = request
        self.save()
        return self.finish(request)

    def trace(self):
        """Read passive SD activity without recovery or ordered-state changes."""
        fields = []
        for index in range(TRACE_WORDS):
            request = encode(Opcode.TRACE, 0, 0, lba=index, compact=True)
            status, payload = self.exchange(request)
            if status:
                raise RemoteError(status)
            fields.append(struct.unpack_from("<I", payload)[0])
        if fields[0] != 0x31544453:
            raise ValueError("FPGA returned an invalid SD trace payload")
        flags = fields[1]
        result = {
            "armed": bool(flags & 1),
            "ddr_initialized": bool(flags & 2),
            "clock_edge_event": bool(flags & 4),
            "command_frame_event": bool(flags & 8),
            "write_busy": bool(flags & 16),
            "read_request_active": bool(flags & 32),
            "clock_edges": fields[2],
            "command_frames": fields[3],
            "valid_commands": fields[4],
            "invalid_frames": fields[5],
            "last_command": fields[6],
            "last_argument": fields[7],
            "read_requests": fields[8],
            "last_read_lba": fields[9],
            "writes": fields[10],
            "responses": fields[11],
            "recent_commands": [
                (word >> shift) & 0x3F
                for word in (fields[18], fields[12])
                for shift in (18, 12, 6, 0)
            ],
            "recent_arguments": fields[19:27],
            "recent_multiblock_reads": [
                {"lba": word >> 12, "blocks": word & 0xFFF}
                for word in fields[27:31]
            ],
            "completed_responses": fields[13],
            "protocol_status": {
                "response_bits_left": fields[14] & 0xFF,
                "card_state": (fields[14] >> 8) & 0xF,
                "mmc_mode": bool(fields[14] & (1 << 12)),
                "open_drain_reply": bool(fields[14] & (1 << 13)),
                "select_busy": bool(fields[14] & (1 << 14)),
                "idle_data_high": bool(fields[14] & (1 << 15)),
                "select_ready": bool(fields[14] & (1 << 15)),
                "last_response_command": (fields[14] >> 16) & 0x3F,
                "command_drive": bool(fields[14] & (1 << 22)),
                "command_level": bool(fields[14] & (1 << 23)),
                "data_drive": bool(fields[14] & (1 << 24)),
                "data_enable": (fields[14] >> 25) & 0xF,
                "block_length_256": bool(fields[14] & (1 << 29)),
                "wide_bus": bool(fields[14] & (1 << 30)),
                "loader_read_seen": bool(fields[14] & (1 << 31)),
            },
            "pin_response": {
                "sampled_bits": fields[15] & 0xFF,
                "calculated_crc7": (fields[15] >> 8) & 0x7F,
                "received_crc7": (fields[15] >> 15) & 0x7F,
                "command_index": (fields[15] >> 22) & 0x3F,
                "end_bit": bool(fields[15] & (1 << 28)),
                "start_bit": bool(fields[15] & (1 << 29)),
                "transmission_bit": bool(fields[15] & (1 << 30)),
                "serializer_mismatch": bool(fields[15] & (1 << 31)),
                "expected_high_observed_low": fields[31] & 0xFF,
                "expected_low_observed_high": (fields[31] >> 8) & 0xFF,
                "first_mismatch_bit": None
                if ((fields[31] >> 16) & 0xFF) == 0xFF
                else (fields[31] >> 16) & 0xFF,
            },
            "pin_data": {
                "sampled_edges": fields[16] & 0xFFFF,
                "completed_blocks": (fields[16] >> 16) & 0xFF,
                "serializer_mismatch": bool(fields[16] & (1 << 24)),
                "active": bool(fields[16] & (1 << 25)),
                "enabled_lanes": (fields[16] >> 26) & 0xF,
                "mismatch_count": fields[17] & 0xFFFF,
                "first_mismatch_edge": None
                if (fields[17] >> 16) == 0xFFFF
                else fields[17] >> 16,
            },
        }
        if fields[32] == ENHANCED_TRACE_MAGIC:
            r2 = bytes([fields[38] & 0xFF]) + b"".join(
                word.to_bytes(4, "big") for word in fields[39:43]
            )
            prefix = b"".join(word.to_bytes(4, "big") for word in fields[48:56])
            r2_state = fields[37] >> 8 & 0x3
            block_state = fields[43] & 0x7
            result["enhanced"] = {
                "negotiation": {
                    "cmd6_count": fields[33] & 0xFF,
                    "cmd13_count": fields[33] >> 8 & 0xFF,
                    "switch_error_observed": bool(fields[33] & (1 << 16)),
                    "falling_edge_data_launch": bool(fields[33] & (1 << 17)),
                    "early_command_launch": bool(fields[33] & (1 << 18)),
                    "last_cmd6_argument": fields[34],
                    "last_cmd6_response": fields[35],
                    "last_cmd13_response": fields[36],
                },
                "r2": {
                    "state": ("idle", "waiting", "capturing", "done")[r2_state],
                    "sampled_bits": fields[37] & 0xFF,
                    "bytes": r2.hex() if r2_state == 3 else None,
                },
                "first_mmc_block": {
                    "state": (
                        "idle",
                        "waiting",
                        "payload",
                        "crc",
                        "end",
                        "done",
                    )[block_state],
                    "payload_bits": fields[43] >> 8 & 0x1FFF,
                    "end_bit": bool(fields[43] & (1 << 3)),
                    "crc_match": bool(fields[43] & (1 << 4))
                    if block_state == 5
                    else None,
                    "capture_lba": fields[44],
                    "calculated_crc16": fields[45] & 0xFFFF,
                    "observed_crc16": fields[45] >> 16,
                    "first_32_bytes": prefix.hex() if block_state == 5 else None,
                    "sample_edge_span": fields[47],
                },
                "timing": {
                    "minimum_rising_period_fabric_cycles": fields[46] & 0xFFFF,
                    "maximum_rising_period_fabric_cycles": fields[46] >> 16,
                    "cmd18": fields[56],
                    "r1_end": fields[57],
                    "data_start": fields[58],
                    "first_block_end": fields[59],
                    "cmd12": fields[60],
                    "data_release": fields[61],
                    "data_start_edge": fields[62],
                    "first_block_end_edge": fields[63],
                },
            }
        else:
            result["enhanced"] = None
        return result

    def upload(self, image, window=0):
        if not image or len(image) % SECTOR_BYTES:
            raise ValueError("Image must be nonempty and a multiple of 512 bytes")
        if window and not 1 <= window <= MAX_WINDOW:
            raise ValueError("Invalid upload readback window")
        self.begin(len(image) // SECTOR_BYTES)
        self.initial_upload["sha256"] = hashlib.sha256(image).hexdigest()
        self.save()
        blocks = len(image) // SECTOR_BYTES
        self.report(f"Uploading {blocks} sectors")
        progress_interval = max(1, blocks // 100)
        for lba in range(blocks):
            self.command(
                Opcode.WRITE,
                lba,
                1,
                image[lba * SECTOR_BYTES : (lba + 1) * SECTOR_BYTES],
            )
            if (lba + 1) % progress_interval == 0 or lba + 1 == blocks:
                self.report(f"Uploaded {lba + 1}/{blocks} sectors")
        # Verify the actual DDR contents before making the image eligible for use.
        self.report(f"Verifying readback of {blocks} sectors")
        downloaded = (
            self.bulk_download(len(image) // SECTOR_BYTES, window=window)
            if window
            else self.download(len(image) // SECTOR_BYTES)
        )
        if downloaded != image:
            raise RuntimeError("DDR upload readback differs from image")
        self.initial_upload["verified"] = True
        self.save()

    def download(self, blocks, start=0):
        validate_download_range(blocks, start)
        self.report(f"Downloading {blocks} sectors from LBA {start}")
        return b"".join(
            self.command(Opcode.READ, lba, 1) for lba in range(start, start + blocks)
        )

    def bulk_download(
        self, blocks, start=0, window=DEFAULT_WINDOW, retry_seconds=BULK_RETRY_SECONDS
    ):
        """Read stable, disarmed DDR using a bounded window of independent tokens.

        Refuse unresolved mutating requests. Bulk requests leave
        the journal and ordered sequence untouched, even on failure. Retrying
        uses identical bytes; duplicate, corrupt and unrelated replies cannot
        complete another request. The caller must keep DDR unchanged throughout.
        """
        if not self.session:
            raise ValueError("Begin an image session first")
        validate_download_range(blocks, start)
        if not 1 <= window <= MAX_WINDOW or retry_seconds <= 0:
            raise ValueError("Require window 1..16 and a positive retry interval")
        self.recover(read_only=True)
        self.report(
            f"Downloading {blocks} sectors from LBA {start} with window {window}"
        )
        output = bytearray(blocks * SECTOR_BYTES)
        pending: dict[int, PendingRead] = {}
        next_block = 0
        token = secrets.randbelow(0xFFFFFFFF)
        old_timeout = self.socket.gettimeout()
        try:
            while next_block < blocks or pending:
                while next_block < blocks and len(pending) < window:
                    count = min(2, blocks - next_block)
                    token = (token + 1) & 0xFFFFFFFF
                    request = encode(
                        Opcode.BULK_READ,
                        self.session,
                        token,
                        start + next_block,
                        count,
                        compact=True,
                    )
                    self.socket.send(request)
                    pending[token] = PendingRead(
                        request, next_block * SECTOR_BYTES, count, time.monotonic()
                    )
                    next_block += count
                now = time.monotonic()
                deadline = min(
                    item.sent_at + retry_seconds for item in pending.values()
                )
                self.socket.settimeout(max(0.0001, deadline - now))
                self._receive_bulk_reply(pending, output)
                self._retry_bulk_reads(pending, retry_seconds)
            return bytes(output)
        finally:
            self.socket.settimeout(old_timeout)

    def _receive_bulk_reply(self, pending, output):
        try:
            reply = self.socket.recv(2048)
        except (socket.timeout, ConnectionRefusedError):
            return
        if len(reply) < 16:
            return
        token = struct.unpack_from("<I", reply, 12)[0]
        item = pending.get(token)
        decoded = decode(reply, item.request) if item else None
        if decoded is None:
            return
        status, payload = decoded
        if status:
            raise RemoteError(status)
        if len(payload) != item.sector_count * SECTOR_BYTES:
            raise RuntimeError("Bulk reply has an unexpected payload length")
        output[item.output_offset : item.output_offset + len(payload)] = payload
        del pending[token]

    def _retry_bulk_reads(self, pending, retry_seconds):
        now = time.monotonic()
        for item in pending.values():
            if now - item.sent_at < retry_seconds:
                continue
            if item.retries >= BULK_RETRY_LIMIT:
                raise TimeoutError("Bulk read exhausted identical-request retries")
            self.socket.send(item.request)
            item.sent_at = now
            item.retries += 1
            self.retries += 1

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        if self._lock is not None:
            self._lock.close()
            self._lock = None


def atomic_download(destination, image):
    """Preserve any existing download until the complete replacement is written."""
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=destination.name + ".", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(image)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.10.2")
    parser.add_argument("--source", default="192.168.10.1")
    parser.add_argument(
        "--state", required=True, help="Private local session/sequence file"
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--upload", type=Path)
    action.add_argument("--download", type=Path)
    action.add_argument("--arm", action="store_true")
    action.add_argument("--disarm", action="store_true")
    action.add_argument("--status", action="store_true")
    action.add_argument(
        "--trace",
        action="store_true",
        help="Read passive SD activity without changing card or journal state",
    )
    action.add_argument(
        "--inspect",
        action="store_true",
        help="Show validated local journal state without sending packets",
    )
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="Use retry-safe two-sector windowed reads (new gateware required)",
    )
    parser.add_argument("--window", type=int, choices=range(1, MAX_WINDOW + 1))
    parser.add_argument("--blocks", type=int)
    parser.add_argument("--start", type=int)
    args = parser.parse_args()
    if args.download and args.blocks is None:
        parser.error("--download requires --blocks")
    if not args.download and (args.blocks is not None or args.start is not None):
        parser.error("--blocks and --start require --download")
    if (args.bulk or args.window is not None) and not (args.upload or args.download):
        parser.error("--bulk and --window require an upload or download")
    if args.window is not None and not args.bulk:
        parser.error("--window requires --bulk")
    args.start = 0 if args.start is None else args.start
    args.window = DEFAULT_WINDOW if args.window is None else args.window
    if args.download:
        try:
            validate_download_range(args.blocks, args.start)
        except ValueError as error:
            parser.error(str(error))
    if args.inspect:
        print(json.dumps(inspect_journal(args.state, args.host), indent=2))
        return

    def progress(message):
        print(message, file=sys.stderr, flush=True)

    client = Images(args.host, args.source, args.state, progress=progress)
    started = time.monotonic()
    operation = (
        "upload"
        if args.upload
        else "download"
        if args.download
        else "arm"
        if args.arm
        else "disarm"
        if args.disarm
        else "trace"
        if args.trace
        else "status"
    )
    try:
        result = {}
        if args.upload:
            image = args.upload.read_bytes()
            client.upload(image, window=args.window if args.bulk else 0)
            result = {
                "uploaded_bytes": len(image),
                "verified_sha256": hashlib.sha256(image).hexdigest(),
                "armed": False,
            }
        elif args.download:
            image = (
                client.bulk_download(args.blocks, args.start, args.window)
                if args.bulk
                else client.download(args.blocks, args.start)
            )
            atomic_download(args.download, image)
            result = {
                "downloaded_bytes": len(image),
                "sha256": hashlib.sha256(image).hexdigest(),
            }
        elif args.trace:
            result = {"sd_trace": client.trace()}
        else:
            if args.arm:
                opcode = Opcode.ARM
            elif args.disarm:
                opcode = Opcode.DISARM
            else:
                opcode = Opcode.STATUS
            client.command(opcode)
            result = {
                "command": "arm" if args.arm else "disarm" if args.disarm else "status",
                "acknowledged": True,
            }
        result.update(
            elapsed_seconds=time.monotonic() - started, retries=client.retries
        )
        print(json.dumps(result, indent=2))
    except BaseException:
        pending = pending_summary(client.pending)
        detail = (
            f"pending {pending['operation']} at LBA {pending['lba']} remains journaled"
            if pending
            else "no pending request is journaled"
        )
        print(
            f"{operation} failed after {client.retries} network retries; {detail}",
            file=sys.stderr,
            flush=True,
        )
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()

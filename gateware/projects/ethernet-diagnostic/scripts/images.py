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
import time
import zlib


SECTOR_BYTES = 512
CAPACITY_SECTORS = 524288
HEADER_BYTES = 24
CRC_BYTES = 4
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
    if compact and (opcode != Opcode.BULK_READ or data):
        raise ValueError("Only bulk reads have compact requests")
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
        self, host="192.168.10.2", source="192.168.10.1", state=None, timeout=0.5
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
            if self.state_path and self.state_path.exists():
                saved = json.loads(self.state_path.read_text())
                if saved["host"] != host:
                    raise ValueError("State belongs to another FPGA address")
                self.session, self.sequence = saved["session"], saved["sequence"]
                self.pending = (
                    bytes.fromhex(saved["pending"]) if saved.get("pending") else None
                )
                if self.pending is not None and self.pending[4] not in ORDERED_OPCODES:
                    raise ValueError("Journal contains a non-ordered request")
                self.initial_upload = saved.get("initial_upload")
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
                raise RuntimeError(
                    "Pending mutating request: resume the original operation before reading"
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
        if opcode == Opcode.ARM and not (
            self.initial_upload
            and self.initial_upload.get("verified") is True
            and self.initial_upload.get("session") == self.session
            and self.initial_upload.get("sha256")
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

    def upload(self, image, window=0):
        if not image or len(image) % SECTOR_BYTES:
            raise ValueError("Image must be nonempty and a multiple of 512 bytes")
        if window and not 1 <= window <= MAX_WINDOW:
            raise ValueError("Invalid upload readback window")
        self.begin(len(image) // SECTOR_BYTES)
        self.initial_upload["sha256"] = hashlib.sha256(image).hexdigest()
        self.save()
        for lba in range(len(image) // SECTOR_BYTES):
            self.command(
                Opcode.WRITE,
                lba,
                1,
                image[lba * SECTOR_BYTES : (lba + 1) * SECTOR_BYTES],
            )
        # Verify the actual DDR contents before making the image eligible for use.
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
    client = Images(args.host, args.source, args.state)
    started = time.monotonic()
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
    finally:
        client.close()


if __name__ == "__main__":
    main()

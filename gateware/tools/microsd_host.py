"""Identity guards and exact, aligned I/O for the external volatile FPGA card."""

import mmap
import os
from pathlib import Path

CAPACITY = 8 * 1024 * 1024
CID = "7f52425350414445101234567801916b"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def validate_target(
    bus_width,
    capacity=CAPACITY,
    clock_hz=1_000_000,
    actual_clock_hz=None,
    *,
    writable=True,
):
    actual_clock_hz = clock_hz if actual_clock_hz is None else actual_clock_hz
    require(0 < actual_clock_hz <= clock_hz, "Invalid actual clock")
    require(capacity in (8 << 20, 256 << 20), "Unsupported card capacity")
    require(0 < clock_hz <= 25_000_000, "Invalid requested clock")
    require(bus_width in (1, 4), "Invalid bus width")
    host = Path("/sys/class/mmc_host/mmc1")
    require("2a310000.mmc" in str(host.resolve()), "Wrong external MMC controller")
    card = host / "mmc1:0001"
    disk = Path("/sys/class/block/mmcblk1")
    require((card / "name").read_text().strip() == "SPADE", "Wrong card name")
    require((card / "cid").read_text().strip() == CID, "Wrong card CID")
    require(
        (disk / "device").resolve() == card.resolve(),
        "Block device belongs to a different card",
    )
    require(
        (disk / "ro").read_text().strip() == ("0" if writable else "1"),
        "Unexpected card write protection",
    )
    require(
        int((disk / "size").read_text()) * 512 == capacity, "Unexpected card capacity"
    )
    require(not list((disk / "holders").iterdir()), "Card has active device holders")
    for filename, skip_header in (("/proc/mounts", False), ("/proc/swaps", True)):
        lines = Path(filename).read_text().splitlines()[int(skip_header) :]
        require(
            not any(line.split()[0].startswith("/dev/mmcblk1") for line in lines),
            f"Card is in use: {filename}",
        )
    ios = Path("/sys/kernel/debug/mmc1/ios").read_text()
    require(f"({bus_width} bits)" in ios, "Unexpected bus width")
    fields = dict(line.split(":", 1) for line in ios.splitlines())
    require(fields["clock"].strip() == f"{clock_hz} Hz", "Unexpected requested clock")
    if "actual clock" in fields:
        require(
            fields["actual clock"].strip() == f"{actual_clock_hz} Hz",
            "Unexpected actual clock",
        )
    return ios, card


def read_into(fd, buffer, offset):
    os.lseek(fd, offset, os.SEEK_SET)
    count = os.readv(fd, [buffer])
    if count != len(buffer):
        raise RuntimeError(
            f"Short direct read at {offset}: {count}/{len(buffer)} bytes"
        )


def write_from(fd, buffer, offset):
    os.lseek(fd, offset, os.SEEK_SET)
    count = os.writev(fd, [buffer])
    if count != len(buffer):
        raise RuntimeError(
            f"Short direct write at {offset}: {count}/{len(buffer)} bytes"
        )


def direct_read(fd, offset, size):
    with mmap.mmap(-1, size) as buffer:
        read_into(fd, buffer, offset)
        return buffer[:]


def direct_write(fd, offset, data):
    with mmap.mmap(-1, len(data)) as buffer:
        buffer[:] = data
        write_from(fd, buffer, offset)

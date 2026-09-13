"""Identity guards and exact, aligned I/O for the external volatile FPGA card."""

import argparse
from contextlib import contextmanager
import mmap
import os
import re
import stat
from pathlib import Path

CAPACITY = 8 * 1024 * 1024
CID = "7f52425350414445101234567801916b"


def target_parser(description):
    """Common target arguments for the small-image raw and filesystem checks."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    parser.add_argument("--capacity-mib", type=int, choices=(8, 256), default=8)
    parser.add_argument("--clock-hz", type=int, default=1_000_000)
    parser.add_argument(
        "--actual-clock-hz",
        type=int,
        help="Expected divider output; defaults to requested clock",
    )
    return parser


@contextmanager
def direct_device(flags):
    """Close the external card on success or failure; callers choose access flags."""
    fd = os.open("/dev/mmcblk1", flags | os.O_DIRECT)
    try:
        yield fd
    finally:
        os.close(fd)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def require_unused(disk):
    """Reject use of this disk or any of its direct sysfs partitions."""
    devices = [disk] + [
        entry for entry in disk.iterdir() if (entry / "partition").exists()
    ]
    numbers = set()
    for device in devices:
        major, minor = (device / "dev").read_text().strip().split(":")
        numbers.add((int(major), int(minor)))
        require(
            not list((device / "holders").iterdir()), f"Active holder on {device.name}"
        )
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        major, minor = line.split()[2].split(":")
        require((int(major), int(minor)) not in numbers, "Card or partition is mounted")
    for line in Path("/proc/swaps").read_text().splitlines()[1:]:
        # proc escapes whitespace in pathnames using octal sequences.
        filename = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), line.split()[0])
        try:
            info = Path(filename).stat()  # Follow aliases to their device identity.
        except OSError as error:
            raise RuntimeError(
                f"Cannot establish active swap identity: {filename}"
            ) from error
        require(
            stat.S_ISBLK(info.st_mode) or stat.S_ISREG(info.st_mode),
            f"Unexpected swap object: {filename}",
        )
        number = info.st_rdev if stat.S_ISBLK(info.st_mode) else info.st_dev
        require(
            (os.major(number), os.minor(number)) not in numbers,
            "Card or partition contains active swap",
        )


def require_emulator(card, disk):
    require((card / "name").read_text().strip() == "SPADE", "Wrong card name")
    require((card / "cid").read_text().strip() == CID, "Wrong card CID")
    require(
        (disk / "device").resolve() == card.resolve(),
        "Block device belongs to a different card",
    )


def prepare_for_programming():
    """Detach only the verified external controller, with no active media."""
    controller = "2a310000.mmc"
    device = Path("/sys/bus/platform/devices") / controller
    driver = Path("/sys/bus/platform/drivers/dwmmc_rockchip")
    host = Path("/sys/class/mmc_host/mmc1")
    require(device.is_dir(), "External MMC controller is missing")
    require(
        (device / "of_node").is_dir()
        and (device / "of_node").resolve().name == "mmc@2a310000",
        "Unexpected external controller device-tree identity",
    )
    if not (device / "driver").is_symlink() and not (device / "driver").exists():
        require(not host.exists(), "Unbound controller still has an MMC host")
        return "already-unbound"
    require((device / "driver").resolve() == driver.resolve(), "Wrong MMC driver")
    require(
        host.is_dir() and host.resolve().parent.parent == device.resolve(),
        "Wrong external MMC host",
    )
    cards = list(host.glob("mmc1:*"))
    disk = Path("/sys/class/block/mmcblk1")
    if cards:
        require(len(cards) == 1 and cards[0].name == "mmc1:0001", "Unexpected card")
        card = cards[0]
        require_emulator(card, disk)
        require_unused(disk)
        state = "unused-emulator"
    else:
        require(not disk.exists(), "Block device exists without an enumerated card")
        state = "no-card"
    (driver / "unbind").write_text(controller)
    return state


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
    require_emulator(card, disk)
    require(
        (disk / "ro").read_text().strip() == ("0" if writable else "1"),
        "Unexpected card write protection",
    )
    require(
        int((disk / "size").read_text()) * 512 == capacity, "Unexpected card capacity"
    )
    require_unused(disk)
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

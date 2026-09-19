"""The raw debug partition: its sector map and its record format.

Partition 2 deliberately carries no filesystem, so a write into it cannot
damage a boot file, and every writer addresses it by sector. Three parties
share those sectors -- the host, U-Boot's boot script and userspace's init --
and the only thing that keeps them from overwriting each other is this map.
It is therefore defined once here and imported by everything that writes or
reads the partition, rather than restated as a literal in each of them.
"""

from __future__ import annotations

SECTOR_SIZE = 512
MAGIC = "RG35DBG1"

# The partition the target sees this volume as. The boot script resolves the
# absolute LBAs it writes from this index and the real partition table, so a
# card partitioned differently still gets a correct script.
DEBUG_PARTITION = 2

# Sector 0 is the host's command to the target.
COMMAND_SECTOR = 0
# Sectors 1..7 are U-Boot's milestones. The EROFS boot script writes the first
# once the script is running, the third once the kernel is at kernel_addr_r
# and the fifth once the device tree is loaded.
UBOOT_BASE = 1
UBOOT_SECTORS = 7
SCRIPT_RUNNING = 1
KERNEL_LOADED = 3
DEVICE_TREE_LOADED = 5
# Sectors 8..15 hold an optional `env export` dump. The board has no console,
# so a variable U-Boot resolves at run time cannot be read any other way.
ENV_EXPORT_SECTOR = 8
ENV_EXPORT_SECTORS = 8
# Sectors 16..31 are userspace's, stage N at USERSPACE_BASE + N, so a U-Boot
# record and a userspace record from the same boot both survive to be read
# back together.
USERSPACE_BASE = 16
USERSPACE_SECTORS = 16
# What a host reads back to see one whole boot.
DEBUG_SECTORS = USERSPACE_BASE + USERSPACE_SECTORS


def absolute_lba(debug_start_lba: int, sector: int) -> int:
    """Return the card LBA of a debug sector in a partition starting there."""
    if not 0 <= sector < DEBUG_SECTORS:
        raise ValueError(f"sector {sector} is outside the debug partition map")
    return debug_start_lba + sector


def encode_command(command: str) -> bytes:
    record = f"{MAGIC}\ndirection=host-to-target\ncommand={command}\n".encode()
    if len(record) > SECTOR_SIZE:
        raise ValueError("debug command does not fit in one sector")
    return record.ljust(SECTOR_SIZE, b"\0")


def decode_records(data: bytes) -> list[dict[str, str]]:
    if len(data) % SECTOR_SIZE:
        raise ValueError("debug data must contain whole 512-byte sectors")
    records = []
    for offset in range(0, len(data), SECTOR_SIZE):
        text = data[offset : offset + SECTOR_SIZE].rstrip(b"\0").decode(
            errors="replace"
        )
        if not text.startswith(f"{MAGIC}\n"):
            continue
        fields = {"sector": str(offset // SECTOR_SIZE)}
        for line in text.splitlines()[1:]:
            key, separator, value = line.partition("=")
            if separator:
                fields[key] = value
        records.append(fields)
    return records

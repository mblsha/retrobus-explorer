#!/usr/bin/env python3
"""Create and decode fixed-size RG35XX Plus boot-debug sectors.

Sector 0 is a host-to-target command. Sectors 1..31 are target-to-host
milestones. The partition deliberately has no filesystem so these writes cannot
damage the boot files.
"""

from __future__ import annotations

import argparse
import zlib
import gzip
import io
import hashlib
import json
import subprocess
import struct
from pathlib import Path

SECTOR_SIZE = 512
MAGIC = "RG35DBG1"
SPL_OFFSET = 8192
SPL_CHECKSUM_STAMP = 0x5F0A6C39
SPL_LOOP_INSTRUCTION = 0xEAFFFFFE
REQUIRED_BOOT_FILES = ("BOOT.SCR", "BOOTMARK", "KERNEL", "INITRD", "DTB.IMG")


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


def make_spl_entry_loop(image: bytes) -> bytes:
    """Return a checksum-valid diagnostic image that loops at the SPL entry."""
    if len(image) < SPL_OFFSET + 32:
        raise ValueError("boot image is truncated before the SPL")
    result = bytearray(image)
    if result[SPL_OFFSET + 4 : SPL_OFFSET + 12] != b"eGON.BT0":
        raise ValueError("missing H700 eGON.BT0 SPL at byte 8192")
    length = int.from_bytes(result[SPL_OFFSET + 16 : SPL_OFFSET + 20], "little")
    if length < 0x64 or length % 4 or SPL_OFFSET + length > len(result):
        raise ValueError("invalid H700 SPL length")
    spl = memoryview(result)[SPL_OFFSET : SPL_OFFSET + length]
    stored = int.from_bytes(spl[12:16], "little")
    checksum_input = bytearray(spl)
    checksum_input[12:16] = SPL_CHECKSUM_STAMP.to_bytes(4, "little")
    calculated = (
        sum(word[0] for word in struct.iter_unpack("<I", checksum_input))
        & 0xFFFFFFFF
    )
    if stored != calculated:
        raise ValueError("H700 SPL checksum mismatch")
    first = int.from_bytes(spl[0:4], "little")
    branch_target = 8 + ((first & 0xFFFFFF) << 2)
    if first >> 24 != 0xEA or branch_target != 0x60:
        raise ValueError("H700 SPL entry does not branch to offset 0x60")
    spl[0x60:0x64] = SPL_LOOP_INSTRUCTION.to_bytes(4, "little")
    spl[12:16] = SPL_CHECKSUM_STAMP.to_bytes(4, "little")
    checksum = sum(word[0] for word in struct.iter_unpack("<I", spl)) & 0xFFFFFFFF
    spl[12:16] = checksum.to_bytes(4, "little")
    return bytes(result)


def _partition(entry: bytes) -> dict[str, int]:
    return {
        "boot": entry[0],
        "type": entry[4],
        "start_lba": int.from_bytes(entry[8:12], "little"),
        "sectors": int.from_bytes(entry[12:16], "little"),
    }


def _read_at(stream, offset: int, size: int) -> bytes:
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("boot image is truncated")
    return data


def _verify_spl(stream, first_partition_lba: int) -> dict[str, int | str]:
    header = bytearray(_read_at(stream, SPL_OFFSET, 32))
    if header[4:12] != b"eGON.BT0":
        raise ValueError("missing H700 eGON.BT0 SPL at byte 8192")
    length = int.from_bytes(header[16:20], "little")
    if length < 32 or length % 4 or SPL_OFFSET + length > first_partition_lba * SECTOR_SIZE:
        raise ValueError("invalid H700 SPL length")
    spl = bytearray(_read_at(stream, SPL_OFFSET, length))
    stored = int.from_bytes(spl[12:16], "little")
    spl[12:16] = SPL_CHECKSUM_STAMP.to_bytes(4, "little")
    calculated = sum(word[0] for word in struct.iter_unpack("<I", spl)) & 0xFFFFFFFF
    if calculated != stored:
        raise ValueError("H700 SPL checksum mismatch")
    return {"offset": SPL_OFFSET, "length": length, "checksum": f"{stored:08x}"}


class _Fat16:
    def __init__(self, stream, start_lba: int, sectors: int):
        self.stream = stream
        self.start = start_lba * SECTOR_SIZE
        self.length = sectors * SECTOR_SIZE
        boot = _read_at(stream, self.start, SECTOR_SIZE)
        self.bytes_per_sector = int.from_bytes(boot[11:13], "little")
        self.sectors_per_cluster = boot[13]
        reserved = int.from_bytes(boot[14:16], "little")
        fats = boot[16]
        root_entries = int.from_bytes(boot[17:19], "little")
        fat_sectors = int.from_bytes(boot[22:24], "little")
        if (
            self.bytes_per_sector != SECTOR_SIZE
            or not self.sectors_per_cluster
            or not reserved
            or not fats
            or not root_entries
            or not fat_sectors
            or boot[510:512] != b"\x55\xaa"
        ):
            raise ValueError("partition 1 is not a supported FAT16 boot volume")
        self.cluster_size = self.bytes_per_sector * self.sectors_per_cluster
        self.fat_offset = self.start + reserved * self.bytes_per_sector
        root_sector = reserved + fats * fat_sectors
        root_bytes = root_entries * 32
        self.root_offset = self.start + root_sector * self.bytes_per_sector
        self.data_offset = self.root_offset + (
            (root_bytes + self.bytes_per_sector - 1) // self.bytes_per_sector
        ) * self.bytes_per_sector
        self.files: dict[str, tuple[int, int]] = {}
        root = _read_at(stream, self.root_offset, root_bytes)
        for offset in range(0, len(root), 32):
            entry = root[offset : offset + 32]
            if entry[0] == 0:
                break
            if entry[0] == 0xE5 or entry[11] == 0x0F or entry[11] & 0x18:
                continue
            base = entry[:8].decode("ascii").rstrip()
            extension = entry[8:11].decode("ascii").rstrip()
            name = base + (("." + extension) if extension else "")
            self.files[name] = (
                int.from_bytes(entry[26:28], "little"),
                int.from_bytes(entry[28:32], "little"),
            )

    def clusters(self, name: str):
        """Yield (cluster, file offset) along a file's real FAT chain."""
        cluster, size = self.files[name]
        offset = 0
        visited = set()
        while cluster < 0xFFF8 and offset < size:
            if cluster < 2 or cluster in visited:
                raise ValueError(f"invalid FAT chain for {name}")
            visited.add(cluster)
            yield cluster, offset
            offset += self.cluster_size
            cluster = int.from_bytes(
                _read_at(self.stream, self.fat_offset + cluster * 2, 2), "little"
            )

    def read(self, name: str) -> bytes:
        try:
            cluster, size = self.files[name]
        except KeyError as error:
            raise ValueError(f"FAT boot volume lacks {name}") from error
        if size == 0:
            return b""
        output = bytearray()
        visited = set()
        while cluster < 0xFFF8 and len(output) < size:
            if cluster < 2 or cluster in visited:
                raise ValueError(f"invalid FAT chain for {name}")
            visited.add(cluster)
            offset = self.data_offset + (cluster - 2) * self.cluster_size
            if offset + self.cluster_size > self.start + self.length:
                raise ValueError(f"FAT chain for {name} leaves partition 1")
            output.extend(_read_at(self.stream, offset, self.cluster_size))
            cluster = int.from_bytes(
                _read_at(self.stream, self.fat_offset + cluster * 2, 2), "little"
            )
        if len(output) < size:
            raise ValueError(f"short FAT chain for {name}")
        return bytes(output[:size])


UIMAGE_MAGIC = 0x27051956
MILESTONE_SCRIPT = """mmc write ${ramdisk_addr_r} 0x1c001 1
fatload mmc 0:1 ${ramdisk_addr_r} BOOTMARK
mmc write ${ramdisk_addr_r} 0x1c002 1
setenv bootargs 'console=tty0 console=ttyS0,115200 loglevel=7 rdinit=/init baredebug=/dev/mmcblk0p2'
fatload mmc 0:1 ${kernel_addr_r} KERNEL
mmc write ${kernel_addr_r} 0x1c003 1
fatload mmc 0:1 ${ramdisk_addr_r} INITRD
setenv initrd_size ${filesize}
mmc write ${ramdisk_addr_r} 0x1c004 1
fatload mmc 0:1 ${fdt_addr_r} dtb.img
mmc write ${fdt_addr_r} 0x1c005 1
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
"""


def build_boot_script(header: bytes, script: str = MILESTONE_SCRIPT) -> bytes:
    """Wrap script text in a legacy U-Boot script image, reusing header fields.

    U-Boot's source command reads a length word from the payload and then skips
    eight bytes before executing. A script image whose payload starts directly
    with its text therefore begins execution in the middle of the first command
    and aborts, which is how the RG35XX image shipped.
    """
    if len(header) != 64 or int.from_bytes(header[0:4], "big") != UIMAGE_MAGIC:
        raise ValueError("BOOT.SCR does not start with a legacy uImage header")
    text = script.encode()
    payload = struct.pack(">II", len(text), 0) + text
    rebuilt = bytearray(header)
    rebuilt[12:16] = struct.pack(">I", len(payload))
    rebuilt[24:28] = struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    rebuilt[4:8] = b"\0\0\0\0"
    rebuilt[4:8] = struct.pack(">I", zlib.crc32(bytes(rebuilt)) & 0xFFFFFFFF)
    return bytes(rebuilt) + payload


COMPRESSED_KERNEL_SCRIPT = """mmc write ${ramdisk_addr_r} 0x1c001 1
fatload mmc 0:1 ${ramdisk_addr_r} BOOTMARK
mmc write ${ramdisk_addr_r} 0x1c002 1
setenv bootargs 'console=tty0 console=ttyS0,115200 loglevel=7 rdinit=/init baredebug=/dev/mmcblk0p2'
fatload mmc 0:1 ${kernel_comp_addr_r} KERNEL
unzip ${kernel_comp_addr_r} ${kernel_addr_r}
mmc write ${kernel_addr_r} 0x1c003 1
fatload mmc 0:1 ${ramdisk_addr_r} INITRD
setenv initrd_size ${filesize}
mmc write ${ramdisk_addr_r} 0x1c004 1
fatload mmc 0:1 ${fdt_addr_r} dtb.img
mmc write ${fdt_addr_r} 0x1c005 1
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
"""


def _script_body(boot_script: bytes) -> bytes:
    """Return the text U-Boot would actually execute from a legacy script image.

    A script image is only usable if its header describes its payload and the
    payload opens with the eight-byte length table that U-Boot's source command
    reads and skips. A script whose payload begins directly with its text still
    looks like a uImage, but execution starts eight bytes into the first
    command and the script aborts.
    """
    header, payload = boot_script[:64], boot_script[64:]
    if int.from_bytes(header[12:16], "big") != len(payload):
        raise ValueError("BOOT.SCR header size does not match its payload")
    if int.from_bytes(header[24:28], "big") != zlib.crc32(payload) & 0xFFFFFFFF:
        raise ValueError("BOOT.SCR payload does not match its uImage CRC")
    checked = bytearray(header)
    checked[4:8] = bytes(4)
    if int.from_bytes(header[4:8], "big") != zlib.crc32(bytes(checked)) & 0xFFFFFFFF:
        raise ValueError("BOOT.SCR header does not match its uImage CRC")
    if len(payload) < 8 or int.from_bytes(payload[0:4], "big") != len(payload) - 8:
        raise ValueError("BOOT.SCR lacks the legacy script length table")
    return payload[8:]


def replace_file(image: bytes, name: str, payload: bytes) -> bytes:
    """Replace a file in the FAT boot volume, reallocating its clusters.

    The initramfs grows from a stub into a real BusyBox userspace, so the
    payload no longer fits the chain the directory entry points at. Both FAT
    copies are rewritten together; a volume whose copies disagree is what
    fsck repairs by guessing.
    """
    stream = io.BytesIO(image)
    mbr = _read_at(stream, 0, SECTOR_SIZE)
    partition = _partition(mbr[446:462])
    fat = _Fat16(stream, partition["start_lba"], partition["sectors"])
    if name not in fat.files:
        raise ValueError(f"FAT boot volume lacks {name}")

    boot = _read_at(stream, fat.start, SECTOR_SIZE)
    fat_sectors = int.from_bytes(boot[22:24], "little")
    copies = boot[16]
    table_bytes = fat_sectors * SECTOR_SIZE
    table = bytearray(_read_at(stream, fat.fat_offset, table_bytes))
    total = min(
        table_bytes // 2,
        2 + (fat.start + fat.length - fat.data_offset) // fat.cluster_size,
    )

    def entry(index: int) -> int:
        return int.from_bytes(table[index * 2 : index * 2 + 2], "little")

    def set_entry(index: int, value: int) -> None:
        table[index * 2 : index * 2 + 2] = value.to_bytes(2, "little")

    for cluster, _ in fat.clusters(name):
        set_entry(cluster, 0)
    needed = (len(payload) + fat.cluster_size - 1) // fat.cluster_size
    available = [index for index in range(2, total) if entry(index) == 0]
    if len(available) < needed:
        raise ValueError(
            f"{name} needs {needed} clusters and the volume has {len(available)} free"
        )
    # Prefer one contiguous run. U-Boot walks the chain a cluster at a time and
    # re-reads the FAT as it goes, so a scattered file costs far more than its
    # own size: a fragmented 1.5 MiB initramfs added about 63,000 sector reads
    # and twelve seconds to the measured boot.
    free = available[:needed]
    run_start = None
    run = 0
    for index in available:
        run = run + 1 if run_start is not None and index == run_start + run else 1
        if run == 1:
            run_start = index
        if run == needed:
            free = list(range(run_start, run_start + needed))
            break

    patched = bytearray(image)
    for position, cluster in enumerate(free):
        set_entry(cluster, 0xFFFF if position + 1 == needed else free[position + 1])
        offset = fat.data_offset + (cluster - 2) * fat.cluster_size
        chunk = payload[position * fat.cluster_size :][: fat.cluster_size]
        patched[offset : offset + fat.cluster_size] = chunk.ljust(
            fat.cluster_size, b"\0"
        )
    for copy in range(copies):
        start = fat.fat_offset + copy * table_bytes
        patched[start : start + table_bytes] = bytes(table)

    root = bytearray(_read_at(stream, fat.root_offset, fat.data_offset - fat.root_offset))
    base, _, extension = name.partition(".")
    target = base.ljust(8).encode() + extension.ljust(3).encode()
    for offset in range(0, len(root), 32):
        if root[offset : offset + 11] == target:
            root[offset + 26 : offset + 28] = (free[0] if needed else 0).to_bytes(
                2, "little"
            )
            root[offset + 28 : offset + 32] = len(payload).to_bytes(4, "little")
            break
    else:
        raise ValueError(f"{name} has no root directory entry")
    patched[fat.root_offset : fat.root_offset + len(root)] = root
    return bytes(patched)


ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
GZIP_MAGIC = b"\x1f\x8b"


def compress_kernel(image: bytes, method: str = "gzip") -> bytes:
    """Store KERNEL gzip-compressed and boot it through U-Boot's unzip.

    The card reads about 2.6 MB/s, so the 31.9 MB Image costs twelve seconds of
    the seventeen-second boot. Compression trades that read against a decompress
    the H700 does from DRAM. The FIT's U-Boot already ships the unzip command
    and an environment with kernel_comp_addr_r and kernel_comp_size, so nothing
    on the target has to change.
    """
    stream = io.BytesIO(image)
    mbr = _read_at(stream, 0, SECTOR_SIZE)
    partition = _partition(mbr[446:462])
    fat = _Fat16(stream, partition["start_lba"], partition["sectors"])
    kernel = fat.read("KERNEL")
    if kernel[:2] == GZIP_MAGIC or kernel[:4] == ZSTD_MAGIC:
        raise ValueError("KERNEL is already compressed")
    if kernel[56:60] != b"ARM\x64":
        raise ValueError("KERNEL is not an arm64 Image")
    if method == "zstd":
        # zstd is both smaller and far cheaper to expand on an A53 than gzip,
        # and U-Boot's booti handles it through kernel_comp_addr_r. There is no
        # unzstd command, so the two-step unzip form cannot be used.
        compressed = subprocess.run(
            ["zstd", "-19", "-q", "-c"], input=kernel,
            stdout=subprocess.PIPE, check=True,
        ).stdout
    else:
        compressed = gzip.compress(kernel, 9, mtime=0)
    patched = replace_file(image, "KERNEL", compressed)
    return repair_boot_script(patched, COMPRESSED_KERNEL_SCRIPT)


def repair_boot_script(image: bytes, script: str = MILESTONE_SCRIPT) -> bytes:
    """Replace BOOT.SCR in a boot image with a correctly framed script image."""
    stream = io.BytesIO(image)
    mbr = _read_at(stream, 0, SECTOR_SIZE)
    partition = _partition(mbr[446:462])
    fat = _Fat16(stream, partition["start_lba"], partition["sectors"])
    if "BOOT.SCR" not in fat.files:
        raise ValueError("boot image has no BOOT.SCR")
    rebuilt = build_boot_script(fat.read("BOOT.SCR")[:64], script)
    return replace_file(image, "BOOT.SCR", rebuilt)


DEFAULT_BOOTARGS = (
    "console=tty0 console=ttyS0,115200 loglevel=7 rdinit=/init "
    "baredebug=/dev/mmcblk0p2"
)
# The target has no serial attached, so every message sent to ttyS0 is written
# into a console the kernel still has to drive. Dropping it and silencing the
# log attacks the kernel-init term of the boot directly.
QUIET_BOOTARGS = (
    "console=tty0 quiet loglevel=0 rdinit=/init baredebug=/dev/mmcblk0p2"
)


def raw_kernel_script(image: bytes, bootargs: str = DEFAULT_BOOTARGS) -> bytes:
    """Load the payload by absolute sector instead of through the filesystem.

    Roughly six cold starts in ten issue one CMD18 at the kernel's first sector
    and then read about four times the file, in two discrete and reproducible
    lengths, before giving up. The card serves it at the normal rate with no
    mismatch, so the host is reading a length it computed. `mmc read` states the
    block count explicitly, which removes U-Boot's filesystem length handling
    from the boot path entirely, and skips the directory and FAT reads as well.
    """
    stream = io.BytesIO(image)
    mbr = _read_at(stream, 0, SECTOR_SIZE)
    partition = _partition(mbr[446:462])
    fat = _Fat16(stream, partition["start_lba"], partition["sectors"])
    placement = {}
    for name in ("KERNEL", "INITRD", "DTB.IMG"):
        chain = [cluster for cluster, _ in fat.clusters(name)]
        if chain != list(range(chain[0], chain[0] + len(chain))):
            raise ValueError(f"{name} is fragmented and cannot be read raw")
        sectors_per_cluster = fat.cluster_size // SECTOR_SIZE
        size = fat.files[name][1]
        placement[name] = (
            fat.data_offset // SECTOR_SIZE + (chain[0] - 2) * sectors_per_cluster,
            (size + SECTOR_SIZE - 1) // SECTOR_SIZE,
            size,
        )
    kernel, initrd, dtb = (placement[n] for n in ("KERNEL", "INITRD", "DTB.IMG"))
    stored = fat.read("KERNEL")
    # gzip is expanded by the unzip command, which needs the compressed image
    # somewhere other than its destination. zstd has no such command, so booti
    # expands it itself into kernel_comp_addr_r and the compressed image is
    # loaded at kernel_addr_r, well clear of that window.
    expand = (
        "unzip ${kernel_comp_addr_r} ${kernel_addr_r}\n"
        if stored[:2] == GZIP_MAGIC else ""
    )
    target = (
        "${kernel_comp_addr_r}" if stored[:2] == GZIP_MAGIC else "${kernel_addr_r}"
    )
    script = (
        "mmc dev 0\n"
        "mmc write ${ramdisk_addr_r} 0x1c001 1\n"
        f"setenv bootargs '{bootargs}'\n"
        f"mmc read {target} {kernel[0]:#x} {kernel[1]:#x}\n"
        f"{expand}"
        "mmc write ${kernel_addr_r} 0x1c003 1\n"
        f"mmc read ${{ramdisk_addr_r}} {initrd[0]:#x} {initrd[1]:#x}\n"
        f"setenv initrd_size {initrd[2]:#x}\n"
        "mmc write ${ramdisk_addr_r} 0x1c004 1\n"
        f"mmc read ${{fdt_addr_r}} {dtb[0]:#x} {dtb[1]:#x}\n"
        "mmc write ${fdt_addr_r} 0x1c005 1\n"
        "booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}\n"
    )
    return repair_boot_script(image, script)


EROFS_MAGIC = b"\xe2\xe1\xf5\xe0"
EXT2_MAGIC = b"\x53\xef"
EROFS_SUPERBLOCK_OFFSET = 1024
EXT2_MAGIC_OFFSET = 1024 + 56
# Logical partitions are preceded by their own boot record, and the payload is
# aligned rather than laid directly behind it so every slot starts on the same
# boundary as the primaries do.
LOGICAL_ALIGNMENT = 2048
EXTENDED_TYPE = 0x0F
LINUX_TYPE = 0x83

EROFS_BOOTARGS = (
    "console=tty0 quiet loglevel=0 root=/dev/mmcblk0p{root} rootfstype=erofs "
    "ro rootwait init=/sbin/init baredebug=/dev/mmcblk0p2"
)


def _partition_entry(kind: int, start_lba: int, sectors: int) -> bytes:
    """Return a 16-byte MBR entry with the CHS fields left at their maximum.

    Nothing in this boot path reads CHS: the BootROM loads by absolute sector,
    U-Boot reads by LBA and Linux uses the LBA fields. The saturated values are
    what every LBA-only tool writes for partitions past the CHS limit.
    """
    return bytes(
        [0, 0xFE, 0xFF, 0xFF, kind, 0xFE, 0xFF, 0xFF]
    ) + start_lba.to_bytes(4, "little") + sectors.to_bytes(4, "little")


# Sectors 1..7 of the debug partition carry U-Boot's milestones and 16..31 the
# userspace ones, so an environment dump goes between them.
ENV_EXPORT_LBA = 0x1C008
ENV_EXPORT_SECTORS = 8


def erofs_slot_script(image: bytes, root_partition: int,
                      export_env: bool = False) -> str:
    """Return the boot script for a card whose root is an EROFS partition.

    The initramfs is gone from the boot path entirely. U-Boot no longer reads
    it, the kernel no longer unpacks it, and the root filesystem is mounted
    straight off the card, where EROFS pages in only the blocks that are
    touched. The file stays in the boot volume as a fallback but nothing loads
    it.

    The active slot is compiled into this script rather than read from the
    debug sector at run time. Reading it would need `setexpr`, which this
    U-Boot has not been shown to have, and a script that aborts on an unknown
    command produces no boot and no milestone to diagnose it with. Switching
    slots rewrites this one file, which is what an update would do anyway.
    """
    stream = io.BytesIO(image)
    mbr = _read_at(stream, 0, SECTOR_SIZE)
    partition = _partition(mbr[446:462])
    fat = _Fat16(stream, partition["start_lba"], partition["sectors"])
    placement = {}
    for name in ("KERNEL", "DTB.IMG"):
        chain = [cluster for cluster, _ in fat.clusters(name)]
        if chain != list(range(chain[0], chain[0] + len(chain))):
            raise ValueError(f"{name} is fragmented and cannot be read raw")
        sectors_per_cluster = fat.cluster_size // SECTOR_SIZE
        size = fat.files[name][1]
        placement[name] = (
            fat.data_offset // SECTOR_SIZE + (chain[0] - 2) * sectors_per_cluster,
            (size + SECTOR_SIZE - 1) // SECTOR_SIZE,
        )
    kernel, dtb = placement["KERNEL"], placement["DTB.IMG"]
    stored = fat.read("KERNEL")
    if stored[:2] != GZIP_MAGIC and stored[:4] != ZSTD_MAGIC:
        raise ValueError("the EROFS boot script expects a gzip or zstd kernel")
    bootargs = EROFS_BOOTARGS.format(root=root_partition)
    # The board has no serial header populated, so a variable U-Boot resolves
    # at run time cannot be read any other way. `env export` renders the whole
    # environment as text into memory, and the debug partition carries it back.
    # Guessing at kernel_comp_addr_r instead would risk writing the compressed
    # image over the device tree.
    export = (
        f"env export -t ${{ramdisk_addr_r}} {ENV_EXPORT_SECTORS * SECTOR_SIZE:#x}\n"
        f"mmc write ${{ramdisk_addr_r}} {ENV_EXPORT_LBA:#x} "
        f"{ENV_EXPORT_SECTORS:#x}\n"
        if export_env else ""
    )
    return (
        "mmc dev 0\n"
        f"{export}"
        "mmc write ${ramdisk_addr_r} 0x1c001 1\n"
        f"setenv bootargs '{bootargs}'\n"
        f"{_kernel_load(stored, kernel)}"
        "mmc write ${kernel_addr_r} 0x1c003 1\n"
        f"mmc read ${{fdt_addr_r}} {dtb[0]:#x} {dtb[1]:#x}\n"
        "mmc write ${fdt_addr_r} 0x1c005 1\n"
        "booti ${kernel_addr_r} - ${fdt_addr_r}\n"
    )


# booti decompresses into kernel_comp_addr_r and refuses to start unless
# kernel_comp_size is also set, which is what the first attempt at a zstd
# kernel was missing: it read the image, wrote every milestone and then stopped
# without a console to say why.
KERNEL_COMP_SIZE = 0x2000000


def _kernel_load(stored: bytes, kernel: tuple[int, int]) -> str:
    """Return the commands that put a runnable kernel at kernel_addr_r.

    gzip is expanded by U-Boot's own unzip, which needs the compressed image
    somewhere other than its destination, so it is read into the scratch area
    and expanded out of it. zstd has no such command and is handed to booti
    compressed, which expands it through its own path.
    """
    if stored[:2] == GZIP_MAGIC:
        return (
            f"mmc read ${{kernel_comp_addr_r}} {kernel[0]:#x} {kernel[1]:#x}\n"
            "unzip ${kernel_comp_addr_r} ${kernel_addr_r}\n"
        )
    return (
        f"mmc read ${{kernel_addr_r}} {kernel[0]:#x} {kernel[1]:#x}\n"
        f"setenv kernel_comp_size {KERNEL_COMP_SIZE:#x}\n"
    )


def erofs_layout(debug_end: int, slot_sectors: int, data_sectors: int) -> dict:
    """Return the sector map for the system, spare and data regions.

    They sit behind the debug partition rather than in front of it, so the
    boot volume, the raw sectors the kernel is read from and the debug
    partition all keep the addresses they were qualified at. That leaves one
    primary slot for three regions, so they are logical partitions inside an
    extended one; Linux numbers those from five, which is the numbering the
    root argument uses.
    """
    slices = []
    cursor = debug_end
    for sectors in (slot_sectors, slot_sectors, data_sectors):
        slices.append(
            {
                "ebr_lba": cursor,
                "start_lba": cursor + LOGICAL_ALIGNMENT,
                "sectors": sectors,
                "slice_sectors": LOGICAL_ALIGNMENT + sectors,
            }
        )
        cursor += LOGICAL_ALIGNMENT + sectors
    return {
        "extended_lba": debug_end,
        "extended_sectors": cursor - debug_end,
        "image_sectors": cursor,
        "system_a": slices[0],
        "system_b": slices[1],
        "data": slices[2],
    }


MINIMUM_SLOT_SECTORS = 32768


def make_erofs_image(image: bytes, system: bytes, data: bytes,
                     root_partition: int = 5,
                     minimum_slot_sectors: int = MINIMUM_SLOT_SECTORS,
                     export_env: bool = False) -> bytes:
    """Return a card image carrying EROFS system slots and an ext2 data volume.

    Both slots are written with the same image and are exactly the same size,
    so either is bootable and an update can be staged into the inactive one
    without moving anything.
    """
    if system[EROFS_SUPERBLOCK_OFFSET:EROFS_SUPERBLOCK_OFFSET + 4] != EROFS_MAGIC:
        raise ValueError("system image is not EROFS")
    if data[EXT2_MAGIC_OFFSET:EXT2_MAGIC_OFFSET + 2] != EXT2_MAGIC:
        raise ValueError("data image is not ext2")
    if root_partition not in (5, 6):
        raise ValueError("root must be the first or second system slot")
    stream = io.BytesIO(image)
    mbr = bytearray(_read_at(stream, 0, SECTOR_SIZE))
    debug = _partition(mbr[462:478])
    if debug["type"] != LINUX_TYPE:
        raise ValueError("partition 2 is not the raw debug volume")
    if any(mbr[478 + index * 16 + 4] for index in range(2)):
        raise ValueError("partitions 3 and 4 are already in use")

    slot_sectors = max(
        LOGICAL_ALIGNMENT,
        -(-len(system) // SECTOR_SIZE // LOGICAL_ALIGNMENT) * LOGICAL_ALIGNMENT,
    )
    # A slot with no room to grow would have to be repartitioned by the first
    # update that adds a file, so it is rounded well past what fits today.
    slot_sectors = max(slot_sectors, minimum_slot_sectors)
    data_sectors = -(-len(data) // SECTOR_SIZE)
    layout = erofs_layout(
        debug["start_lba"] + debug["sectors"], slot_sectors, data_sectors
    )

    grown = bytearray(image)
    grown.extend(bytes(layout["image_sectors"] * SECTOR_SIZE - len(grown)))
    mbr[478:494] = _partition_entry(
        EXTENDED_TYPE, layout["extended_lba"], layout["extended_sectors"]
    )
    grown[0:SECTOR_SIZE] = bytes(mbr)

    regions = (layout["system_a"], layout["system_b"], layout["data"])
    payloads = (system, system, data)
    for index, (region, payload) in enumerate(zip(regions, payloads)):
        record = bytearray(SECTOR_SIZE)
        record[446:462] = _partition_entry(
            LINUX_TYPE, LOGICAL_ALIGNMENT, region["sectors"]
        )
        if index + 1 < len(regions):
            following = regions[index + 1]
            # The link entry is relative to the extended partition, while the
            # data entry above is relative to this record. Mixing the two bases
            # is the classic way to produce a chain Linux silently truncates.
            record[462:478] = _partition_entry(
                EXTENDED_TYPE,
                following["ebr_lba"] - layout["extended_lba"],
                following["slice_sectors"],
            )
        record[510:512] = b"\x55\xaa"
        offset = region["ebr_lba"] * SECTOR_SIZE
        grown[offset:offset + SECTOR_SIZE] = bytes(record)
        start = region["start_lba"] * SECTOR_SIZE
        grown[start:start + len(payload)] = payload

    return repair_boot_script(
        bytes(grown), erofs_slot_script(bytes(grown), root_partition, export_env)
    )


def logical_partitions(stream, mbr: bytes) -> list[dict[str, int]]:
    """Return the logical partitions behind an extended entry, in chain order.

    Each boot record holds at most two entries: the payload, addressed relative
    to that record, and a link to the next record, addressed relative to the
    extended partition. The walk is bounded by the number of records that could
    fit, so a chain that points back at itself ends rather than hanging.
    """
    extended = next(
        (
            entry
            for entry in (
                _partition(mbr[446 + index * 16 : 462 + index * 16])
                for index in range(4)
            )
            if entry["type"] in (0x05, 0x0F) and entry["sectors"]
        ),
        None,
    )
    if extended is None:
        return []
    found = []
    cursor = extended["start_lba"]
    seen = set()
    while cursor not in seen and len(found) < extended["sectors"]:
        seen.add(cursor)
        record = _read_at(stream, cursor * SECTOR_SIZE, SECTOR_SIZE)
        if record[510:512] != b"\x55\xaa":
            raise ValueError(f"extended boot record at {cursor} lacks a signature")
        payload = _partition(record[446:462])
        if not payload["sectors"]:
            break
        found.append(
            {
                "index": 5 + len(found),
                "ebr_lba": cursor,
                "type": payload["type"],
                "start_lba": cursor + payload["start_lba"],
                "sectors": payload["sectors"],
            }
        )
        link = _partition(record[462:478])
        if not link["sectors"]:
            break
        cursor = extended["start_lba"] + link["start_lba"]
    return found


def describe_lba(path: Path, lba: int) -> str:
    """Name what an absolute image LBA holds.

    Card access traces report backend LBAs, and a boot is only legible once
    those map onto the SPL, the FIT, filesystem metadata or a named boot file.
    File positions follow the real FAT chain rather than assuming contiguity.
    """
    size = path.stat().st_size
    if lba < 0 or (lba + 1) * SECTOR_SIZE > size:
        return "beyond the image"
    with path.open("rb") as stream:
        if lba == 0:
            return "partition table"
        sector = _read_at(stream, lba * SECTOR_SIZE, SECTOR_SIZE)
        if sector[:4] == b"\xd0\x0d\xfe\xed":
            return "FIT image"
        spl_lba = SPL_OFFSET // SECTOR_SIZE
        header = _read_at(stream, SPL_OFFSET, SECTOR_SIZE)
        if header[4:12] == b"eGON.BT0":
            declared = int.from_bytes(header[16:20], "little")
            span = (declared + SECTOR_SIZE - 1) // SECTOR_SIZE
            if spl_lba <= lba < spl_lba + span:
                return f"SPL+{(lba - spl_lba) * SECTOR_SIZE}"
        mbr = _read_at(stream, 0, SECTOR_SIZE)
        partitions = [
            _partition(mbr[446 + index * 16 : 462 + index * 16]) for index in range(4)
        ]
        names = {5: "system A", 6: "system B", 7: "data"}
        for logical in logical_partitions(stream, mbr):
            if lba == logical["ebr_lba"]:
                return f"extended boot record for partition {logical['index']}"
            start, count = logical["start_lba"], logical["sectors"]
            if start <= lba < start + count:
                name = names.get(logical["index"], f"partition {logical['index']}")
                return f"{name}+{(lba - start) * SECTOR_SIZE}"
        for index, partition in enumerate(partitions, start=1):
            start, count = partition["start_lba"], partition["sectors"]
            if not count or not start <= lba < start + count:
                continue
            if partition["type"] in (0x05, 0x0F):
                return f"extended partition {index} gap sector {lba - start}"
            if partition["type"] != 0x0E:
                return f"partition {index} sector {lba - start}"
            fat = _Fat16(stream, start, count)
            fat_lba = fat.fat_offset // SECTOR_SIZE
            root_lba = fat.root_offset // SECTOR_SIZE
            data_lba = fat.data_offset // SECTOR_SIZE
            if lba < fat_lba:
                return "boot partition reserved sectors"
            if lba < root_lba:
                return "boot partition FAT table"
            if lba < data_lba:
                return "boot partition root directory"
            sectors_per_cluster = fat.cluster_size // SECTOR_SIZE
            for name in fat.files:
                for cluster, offset in fat.clusters(name):
                    first = data_lba + (cluster - 2) * sectors_per_cluster
                    if first <= lba < first + sectors_per_cluster:
                        return f"{name}+{offset + (lba - first) * SECTOR_SIZE}"
            return "boot partition free cluster"
    return "unallocated area"


def verify_boot_image(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        size = path.stat().st_size
        if size % SECTOR_SIZE:
            raise ValueError("boot image does not contain whole sectors")
        mbr = _read_at(stream, 0, SECTOR_SIZE)
        if mbr[510:512] != b"\x55\xaa":
            raise ValueError("boot image lacks an MBR signature")
        partitions = [
            _partition(mbr[446 + index * 16 : 462 + index * 16])
            for index in range(2)
        ]
        boot_partition, debug_partition = partitions
        if boot_partition["type"] != 0x0E or boot_partition["sectors"] == 0:
            raise ValueError("partition 1 is not the expected FAT16 LBA boot volume")
        if (
            debug_partition["type"] != 0x83
            or debug_partition["sectors"] < 32
            or debug_partition["start_lba"]
            != boot_partition["start_lba"] + boot_partition["sectors"]
        ):
            raise ValueError("partition 2 is not the contiguous raw debug volume")
        if (debug_partition["start_lba"] + debug_partition["sectors"]) * SECTOR_SIZE > size:
            raise ValueError("partition table extends beyond the boot image")

        spl = _verify_spl(stream, boot_partition["start_lba"])
        fat = _Fat16(stream, boot_partition["start_lba"], boot_partition["sectors"])
        payloads = {name: fat.read(name) for name in REQUIRED_BOOT_FILES}
        boot_script = payloads["BOOT.SCR"]
        if not boot_script.startswith(b"\x27\x05\x19\x56"):
            raise ValueError("BOOT.SCR is not a U-Boot legacy script image")
        script_text = _script_body(boot_script)
        required_script_text = [b"mmc write", b"baredebug=/dev/mmcblk0p2", b"booti "]
        if payloads["KERNEL"][:2] == GZIP_MAGIC:
            # A gzip kernel is useless unless the script expands it; a zstd one
            # is expanded by booti itself.
            required_script_text.append(b"unzip ")
        if any(text not in script_text for text in required_script_text):
            raise ValueError("BOOT.SCR lacks raw milestone write or bare Linux boot")
        bootmark = decode_records(payloads["BOOTMARK"])
        if not bootmark or bootmark[0].get("stage") != "0":
            raise ValueError("BOOTMARK is not the U-Boot stage-0 milestone")
        kernel = payloads["KERNEL"]
        if kernel[:2] == GZIP_MAGIC:
            kernel = gzip.decompress(kernel)
        elif kernel[:4] == ZSTD_MAGIC:
            kernel = subprocess.run(
                ["zstd", "-d", "-q", "-c"], input=kernel,
                stdout=subprocess.PIPE, check=True,
            ).stdout
        if kernel[56:60] != b"ARM\x64":
            raise ValueError("KERNEL is not an arm64 Image")
        if not payloads["INITRD"].startswith(b"\x1f\x8b"):
            raise ValueError("INITRD is not gzip-compressed")
        if not payloads["DTB.IMG"].startswith(b"\xd0\x0d\xfe\xed"):
            raise ValueError("dtb.img lacks an FDT header")

        logicals = logical_partitions(stream, mbr)
        system_slots = []
        if logicals:
            if len(logicals) != 3:
                raise ValueError("expected exactly system A, system B and data")
            system_a, system_b, data_partition = logicals
            if system_a["sectors"] != system_b["sectors"]:
                raise ValueError("the system slots are not the same size")
            if system_a["start_lba"] < debug_partition["start_lba"]:
                raise ValueError("the system slots overlap the qualified regions")
            for slot in (system_a, system_b):
                magic = _read_at(
                    stream,
                    slot["start_lba"] * SECTOR_SIZE + EROFS_SUPERBLOCK_OFFSET,
                    4,
                )
                if magic != EROFS_MAGIC:
                    raise ValueError(f"partition {slot['index']} is not EROFS")
                system_slots.append(slot)
            data_magic = _read_at(
                stream,
                data_partition["start_lba"] * SECTOR_SIZE + EXT2_MAGIC_OFFSET,
                2,
            )
            if data_magic != EXT2_MAGIC:
                raise ValueError("the data partition is not ext2")
            if (
                data_partition["start_lba"] + data_partition["sectors"]
            ) * SECTOR_SIZE > size:
                raise ValueError("the extended chain runs past the image")
            # A root argument naming a slot that holds no filesystem is the one
            # failure this layout can produce that still looks bootable.
            roots = [
                f"root=/dev/mmcblk0p{slot['index']}".encode()
                for slot in system_slots
                if f"root=/dev/mmcblk0p{slot['index']}".encode() in script_text
            ]
            if len(roots) != 1:
                raise ValueError("BOOT.SCR does not name exactly one system slot")

        debug_offset = debug_partition["start_lba"] * SECTOR_SIZE
        debug_data = _read_at(stream, debug_offset, 32 * SECTOR_SIZE)
        records = decode_records(debug_data)
        if (
            len(records) != 1
            or records[0].get("sector") != "0"
            or records[0].get("direction") != "host-to-target"
            or not records[0].get("command")
        ):
            raise ValueError("raw debug volume lacks one pristine host command")

    return {
        "image": str(path),
        "bytes": size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "spl": spl,
        "partitions": partitions,
        "logical_partitions": logicals,
        "boot_files": {name: len(payloads[name]) for name in REQUIRED_BOOT_FILES},
        "debug_command": records[0]["command"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--make-command", metavar="COMMAND")
    group.add_argument("--decode", type=Path, metavar="IMAGE")
    group.add_argument("--verify-image", type=Path, metavar="IMAGE")
    group.add_argument("--make-spl-loop", type=Path, metavar="IMAGE")
    group.add_argument("--repair-boot-script", type=Path, metavar="IMAGE")
    group.add_argument("--describe", type=Path, metavar="IMAGE")
    group.add_argument("--replace-file", type=Path, metavar="IMAGE")
    group.add_argument("--compress-kernel", type=Path, metavar="IMAGE")
    group.add_argument("--raw-kernel", type=Path, metavar="IMAGE")
    group.add_argument("--make-erofs-image", type=Path, metavar="IMAGE")
    parser.add_argument(
        "--kernel-compression", choices=("gzip", "zstd"), default="gzip",
    )
    parser.add_argument(
        "--quiet-boot", action="store_true",
        help="Drop the unattached serial console and silence the kernel log",
    )
    parser.add_argument("--system", type=Path, help="EROFS system image")
    parser.add_argument("--data", type=Path, help="ext2 data image")
    parser.add_argument(
        "--export-env", action="store_true",
        help="Also dump U-Boot's environment into the debug partition",
    )
    parser.add_argument(
        "--slot", choices=("a", "b"), default="a",
        help="Which system slot the boot script roots from",
    )
    parser.add_argument("--name")
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--lba", type=int, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.make_command is not None:
        if args.output is None:
            parser.error("--make-command requires --output")
        args.output.write_bytes(encode_command(args.make_command))
        return

    if args.verify_image is not None:
        print(json.dumps(verify_boot_image(args.verify_image), indent=2))
        return


    if args.make_erofs_image is not None:
        if args.output is None or args.system is None or args.data is None:
            parser.error("--make-erofs-image requires --system, --data and --output")
        built = make_erofs_image(
            args.make_erofs_image.read_bytes(),
            args.system.read_bytes(),
            args.data.read_bytes(),
            root_partition=5 if args.slot == "a" else 6,
            export_env=args.export_env,
        )
        args.output.write_bytes(built)
        with io.BytesIO(built) as stream:
            mbr = _read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "bytes": len(built),
                    "sha256": hashlib.sha256(built).hexdigest(),
                    "root": f"/dev/mmcblk0p{5 if args.slot == 'a' else 6}",
                    "logical_partitions": chain,
                },
                indent=2,
            )
        )
        return

    if args.raw_kernel is not None:
        if args.output is None:
            parser.error("--raw-kernel requires --output")
        patched = raw_kernel_script(
            args.raw_kernel.read_bytes(),
            QUIET_BOOTARGS if args.quiet_boot else DEFAULT_BOOTARGS,
        )
        args.output.write_bytes(patched)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "image_sha256": hashlib.sha256(patched).hexdigest(),
                },
                indent=2,
            )
        )
        return

    if args.compress_kernel is not None:
        if args.output is None:
            parser.error("--compress-kernel requires --output")
        source = args.compress_kernel.read_bytes()
        patched = compress_kernel(source, args.kernel_compression)
        args.output.write_bytes(patched)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "image_sha256": hashlib.sha256(patched).hexdigest(),
                },
                indent=2,
            )
        )
        return

    if args.replace_file is not None:
        if args.output is None or args.name is None or args.payload is None:
            parser.error("--replace-file requires --name, --payload and --output")
        patched = replace_file(
            args.replace_file.read_bytes(), args.name, args.payload.read_bytes()
        )
        args.output.write_bytes(patched)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "replaced": args.name,
                    "bytes": args.payload.stat().st_size,
                    "sha256": hashlib.sha256(patched).hexdigest(),
                },
                indent=2,
            )
        )
        return

    if args.describe is not None:
        if not args.lba:
            parser.error("--describe requires at least one --lba")
        for lba in args.lba:
            print(f"{lba} {describe_lba(args.describe, lba)}")
        return

    if args.repair_boot_script is not None:
        if args.output is None:
            parser.error("--repair-boot-script requires --output")
        repaired = repair_boot_script(args.repair_boot_script.read_bytes())
        args.output.write_bytes(repaired)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "sha256": hashlib.sha256(repaired).hexdigest(),
                },
                indent=2,
            )
        )
        return

    if args.make_spl_loop is not None:
        if args.output is None:
            parser.error("--make-spl-loop requires --output")
        diagnostic = make_spl_entry_loop(args.make_spl_loop.read_bytes())
        args.output.write_bytes(diagnostic)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "sha256": hashlib.sha256(diagnostic).hexdigest(),
                },
                indent=2,
            )
        )
        return

    for record in decode_records(args.decode.read_bytes()):
        print(" ".join(f"{key}={value}" for key, value in record.items()))


if __name__ == "__main__":
    main()

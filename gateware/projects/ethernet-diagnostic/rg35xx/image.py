"""The card image: its partition layout, its SPL, and what makes it bootable.

Everything the delivered boot path needs is built here. The base image is a
FAT16 boot volume and a raw debug partition that were qualified at fixed
addresses, so the EROFS system slots and the data volume are appended behind
them as logical partitions rather than inserted anywhere in front.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import re
import struct
import subprocess
from pathlib import Path

from rg35xx.boot_script import GZIP_MAGIC
from rg35xx.boot_script import ZSTD_MAGIC
from rg35xx.boot_script import _script_body
from rg35xx.boot_script import erofs_slot_script
from rg35xx.boot_script import repair_boot_script
from rg35xx.debug_partition import DEBUG_PARTITION
from rg35xx.debug_partition import DEBUG_SECTORS
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import decode_records
from rg35xx.device_tree import CARD_CLOCK_PROPERTY
from rg35xx.device_tree import CARD_CONTROLLER
from rg35xx.device_tree import get_cell
from rg35xx.device_tree import set_cell
from rg35xx.fat16 import Fat16
from rg35xx.fat16 import boot_volume
from rg35xx.fat16 import mbr_partition as _partition
from rg35xx.fat16 import read_at
from rg35xx.fat16 import replace_file

SPL_OFFSET = 8192
SPL_CHECKSUM_STAMP = 0x5F0A6C39
SPL_LOOP_INSTRUCTION = 0xEAFFFFFE
# INITRD is deliberately absent: the delivered boot loads no initramfs.
REQUIRED_BOOT_FILES = ("BOOT.SCR", "BOOTMARK", "KERNEL", "DTB.IMG")

FAT16_LBA_TYPE = 0x0E
LINUX_TYPE = 0x83
EXTENDED_TYPE = 0x0F
EXTENDED_CHS_TYPE = 0x05
EXTENDED_TYPES = (EXTENDED_CHS_TYPE, EXTENDED_TYPE)

EROFS_MAGIC = b"\xe2\xe1\xf5\xe0"
EXT2_MAGIC = b"\x53\xef"
EROFS_SUPERBLOCK_OFFSET = 1024
EXT2_MAGIC_OFFSET = 1024 + 56
FDT_MAGIC = b"\xd0\x0d\xfe\xed"

# Logical partitions are preceded by their own boot record, and the payload is
# aligned rather than laid directly behind it so every slot starts on the same
# boundary as the primaries do.
LOGICAL_ALIGNMENT = 2048
MINIMUM_SLOT_SECTORS = 32768

# Linux numbers logical partitions from five, so the three regions behind the
# extended entry are what the target sees as partitions 5, 6 and 7. Nothing
# chooses these numbers; the layout does, and the boot script's root argument
# and the rootfs's data mount both have to agree with it.
BOOT_PARTITION = 1
FIRST_LOGICAL_PARTITION = 5
SYSTEM_A_PARTITION = FIRST_LOGICAL_PARTITION
SYSTEM_B_PARTITION = FIRST_LOGICAL_PARTITION + 1
DATA_PARTITION = FIRST_LOGICAL_PARTITION + 2
LOGICAL_NAMES = {
    SYSTEM_A_PARTITION: "system A",
    SYSTEM_B_PARTITION: "system B",
    DATA_PARTITION: "data",
}


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


def _verify_spl(stream, first_partition_lba: int) -> dict[str, int | str]:
    header = bytearray(read_at(stream, SPL_OFFSET, 32))
    if header[4:12] != b"eGON.BT0":
        raise ValueError("missing H700 eGON.BT0 SPL at byte 8192")
    length = int.from_bytes(header[16:20], "little")
    if length < 32 or length % 4 or SPL_OFFSET + length > first_partition_lba * SECTOR_SIZE:
        raise ValueError("invalid H700 SPL length")
    spl = bytearray(read_at(stream, SPL_OFFSET, length))
    stored = int.from_bytes(spl[12:16], "little")
    spl[12:16] = SPL_CHECKSUM_STAMP.to_bytes(4, "little")
    calculated = sum(word[0] for word in struct.iter_unpack("<I", spl)) & 0xFFFFFFFF
    if calculated != stored:
        raise ValueError("H700 SPL checksum mismatch")
    return {"offset": SPL_OFFSET, "length": length, "checksum": f"{stored:08x}"}


def compress_kernel(image: bytes, method: str = "gzip") -> bytes:
    """Store KERNEL compressed, leaving the boot script alone.

    The card reads about 2.6 MB/s, so the 31.9 MB Image costs twelve seconds of
    the seventeen-second boot. Compression trades that read against a decompress
    the H700 does from DRAM. The FIT's U-Boot already ships the unzip command
    and an environment with kernel_comp_addr_r and kernel_comp_size, so nothing
    on the target has to change.

    The script that loads the result is written by `make_erofs_image`, which
    owns it: it has to name the kernel's sectors, and those are only known once
    the compressed file has been placed.
    """
    _, fat, _ = boot_volume(image)
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
    return replace_file(image, "KERNEL", compressed)


def _partition_entry(kind: int, start_lba: int, sectors: int) -> bytes:
    """Return a 16-byte MBR entry with the CHS fields left at their maximum.

    Nothing in this boot path reads CHS: the BootROM loads by absolute sector,
    U-Boot reads by LBA and Linux uses the LBA fields. The saturated values are
    what every LBA-only tool writes for partitions past the CHS limit.
    """
    return bytes(
        [0, 0xFE, 0xFF, 0xFF, kind, 0xFE, 0xFF, 0xFF]
    ) + start_lba.to_bytes(4, "little") + sectors.to_bytes(4, "little")


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


def make_erofs_image(image: bytes, system: bytes, data: bytes,
                     root_partition: int = SYSTEM_A_PARTITION,
                     minimum_slot_sectors: int = MINIMUM_SLOT_SECTORS,
                     export_env: bool = False,
                     card_max_hz: int | None = None) -> bytes:
    """Return a card image carrying EROFS system slots and an ext2 data volume.

    Both slots are written with the same image and are exactly the same size,
    so either is bootable and an update can be staged into the inactive one
    without moving anything.

    card_max_hz caps the clock Linux gives the emulated card, in the device
    tree, where U-Boot's own clock is out of its reach. Linux otherwise runs the
    card at 12.5 MHz, twice U-Boot's rate, and at that rate the link fails
    within a second of the display starting.
    """
    if system[EROFS_SUPERBLOCK_OFFSET:EROFS_SUPERBLOCK_OFFSET + 4] != EROFS_MAGIC:
        raise ValueError("system image is not EROFS")
    if data[EXT2_MAGIC_OFFSET:EXT2_MAGIC_OFFSET + 2] != EXT2_MAGIC:
        raise ValueError("data image is not ext2")
    if root_partition not in (SYSTEM_A_PARTITION, SYSTEM_B_PARTITION):
        raise ValueError("root must be the first or second system slot")
    stream = io.BytesIO(image)
    mbr = bytearray(read_at(stream, 0, SECTOR_SIZE))
    debug = _partition(mbr[462:478])
    if debug["type"] != LINUX_TYPE:
        raise ValueError(f"partition {DEBUG_PARTITION} is not the raw debug volume")
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

    built = bytes(grown)
    if card_max_hz is not None:
        # Before the script is written: replacing the file moves it, and the
        # script reads it by sector.
        _, fat, _ = boot_volume(built)
        built = replace_file(
            built, "DTB.IMG",
            set_cell(fat.read("DTB.IMG"), CARD_CONTROLLER, CARD_CLOCK_PROPERTY,
                     card_max_hz),
        )
    return repair_boot_script(
        built, erofs_slot_script(built, root_partition, export_env)
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
            if entry["type"] in EXTENDED_TYPES and entry["sectors"]
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
        record = read_at(stream, cursor * SECTOR_SIZE, SECTOR_SIZE)
        if record[510:512] != b"\x55\xaa":
            raise ValueError(f"extended boot record at {cursor} lacks a signature")
        payload = _partition(record[446:462])
        if not payload["sectors"]:
            break
        found.append(
            {
                "index": FIRST_LOGICAL_PARTITION + len(found),
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
        sector = read_at(stream, lba * SECTOR_SIZE, SECTOR_SIZE)
        if sector[:4] == FDT_MAGIC:
            return "FIT image"
        spl_lba = SPL_OFFSET // SECTOR_SIZE
        header = read_at(stream, SPL_OFFSET, SECTOR_SIZE)
        if header[4:12] == b"eGON.BT0":
            declared = int.from_bytes(header[16:20], "little")
            span = (declared + SECTOR_SIZE - 1) // SECTOR_SIZE
            if spl_lba <= lba < spl_lba + span:
                return f"SPL+{(lba - spl_lba) * SECTOR_SIZE}"
        mbr = read_at(stream, 0, SECTOR_SIZE)
        partitions = [
            _partition(mbr[446 + index * 16 : 462 + index * 16]) for index in range(4)
        ]
        for logical in logical_partitions(stream, mbr):
            if lba == logical["ebr_lba"]:
                return f"extended boot record for partition {logical['index']}"
            start, count = logical["start_lba"], logical["sectors"]
            if start <= lba < start + count:
                name = LOGICAL_NAMES.get(
                    logical["index"], f"partition {logical['index']}"
                )
                return f"{name}+{(lba - start) * SECTOR_SIZE}"
        for index, partition in enumerate(partitions, start=1):
            start, count = partition["start_lba"], partition["sectors"]
            if not count or not start <= lba < start + count:
                continue
            if partition["type"] in EXTENDED_TYPES:
                return f"extended partition {index} gap sector {lba - start}"
            if partition["type"] != FAT16_LBA_TYPE:
                return f"partition {index} sector {lba - start}"
            fat = Fat16(stream, start, count)
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


def _card_max_hz(device_tree: bytes) -> int | None:
    """Return the clock the device tree lets Linux give the card, if it says."""
    try:
        return get_cell(device_tree, CARD_CONTROLLER, CARD_CLOCK_PROPERTY)
    except (ValueError, struct.error):
        return None


def verify_boot_image(path: Path) -> dict[str, object]:
    """Check everything the delivered boot path depends on, before programming.

    INITRD is not among the required files and is not inspected. The delivered
    boot loads no initramfs: U-Boot does not read one and the kernel mounts the
    EROFS system partition directly. Images built before that change still
    carry the file, and nothing removes it, but its presence and its contents
    are no longer part of this contract.
    """
    with path.open("rb") as stream:
        size = path.stat().st_size
        if size % SECTOR_SIZE:
            raise ValueError("boot image does not contain whole sectors")
        mbr = read_at(stream, 0, SECTOR_SIZE)
        if mbr[510:512] != b"\x55\xaa":
            raise ValueError("boot image lacks an MBR signature")
        partitions = [
            _partition(mbr[446 + index * 16 : 462 + index * 16])
            for index in range(2)
        ]
        boot_partition, debug_partition = partitions
        if boot_partition["type"] != FAT16_LBA_TYPE or boot_partition["sectors"] == 0:
            raise ValueError(
                f"partition {BOOT_PARTITION} is not the expected FAT16 LBA boot volume"
            )
        if (
            debug_partition["type"] != LINUX_TYPE
            or debug_partition["sectors"] < DEBUG_SECTORS
            or debug_partition["start_lba"]
            != boot_partition["start_lba"] + boot_partition["sectors"]
        ):
            raise ValueError(
                f"partition {DEBUG_PARTITION} is not the contiguous raw debug volume"
            )
        if (debug_partition["start_lba"] + debug_partition["sectors"]) * SECTOR_SIZE > size:
            raise ValueError("partition table extends beyond the boot image")

        spl = _verify_spl(stream, boot_partition["start_lba"])
        fat = Fat16(stream, boot_partition["start_lba"], boot_partition["sectors"])
        payloads = {name: fat.read(name) for name in REQUIRED_BOOT_FILES}
        boot_script = payloads["BOOT.SCR"]
        if not boot_script.startswith(b"\x27\x05\x19\x56"):
            raise ValueError("BOOT.SCR is not a U-Boot legacy script image")
        script_text = _script_body(boot_script)
        required_script_text = [
            b"mmc write",
            f"baredebug=/dev/mmcblk0p{DEBUG_PARTITION}".encode(),
            b"booti ",
        ]
        if payloads["KERNEL"][:2] == GZIP_MAGIC:
            # A gzip kernel is useless unless the script expands it; a zstd one
            # is expanded by booti itself.
            required_script_text.append(b"unzip ")
        if any(text not in script_text for text in required_script_text):
            raise ValueError("BOOT.SCR lacks raw milestone write or bare Linux boot")
        # A script that reads raw sectors names where a file lay when it was
        # written. Replacing the file moves it, and U-Boot then boots the stale
        # copy without complaint, so every file has to lie where a read says.
        raw_reads = {
            (int(lba, 16), int(count, 16))
            for lba, count in re.findall(
                rb"mmc read \S+ (0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)", script_text
            )
        }
        if raw_reads:
            for name in ("KERNEL", "DTB.IMG"):
                lba, count, _ = fat.placement(name)
                if (lba, count) not in raw_reads:
                    raise ValueError(
                        f"BOOT.SCR reads raw sectors and none of its reads is "
                        f"where {name} lies now ({lba:#x}, {count:#x} sectors); "
                        "rebuild the script after replacing a file"
                    )
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
        if not payloads["DTB.IMG"].startswith(FDT_MAGIC):
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
                magic = read_at(
                    stream,
                    slot["start_lba"] * SECTOR_SIZE + EROFS_SUPERBLOCK_OFFSET,
                    4,
                )
                if magic != EROFS_MAGIC:
                    raise ValueError(f"partition {slot['index']} is not EROFS")
                system_slots.append(slot)
            data_magic = read_at(
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
        debug_data = read_at(stream, debug_offset, DEBUG_SECTORS * SECTOR_SIZE)
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
        "card_max_hz": _card_max_hz(payloads["DTB.IMG"]),
    }

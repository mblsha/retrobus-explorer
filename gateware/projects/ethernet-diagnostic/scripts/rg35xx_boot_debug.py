#!/usr/bin/env python3
"""Create and decode fixed-size RG35XX Plus boot-debug sectors.

Sector 0 is a host-to-target command. Sectors 1..31 are target-to-host
milestones. The partition deliberately has no filesystem so these writes cannot
damage the boot files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
        required_script_text = (b"mmc write", b"baredebug=/dev/mmcblk0p2", b"booti ")
        if any(text not in boot_script for text in required_script_text):
            raise ValueError("BOOT.SCR lacks raw milestone write or bare Linux boot")
        bootmark = decode_records(payloads["BOOTMARK"])
        if not bootmark or bootmark[0].get("stage") != "0":
            raise ValueError("BOOTMARK is not the U-Boot stage-0 milestone")
        if payloads["KERNEL"][56:60] != b"ARM\x64":
            raise ValueError("KERNEL is not an arm64 Image")
        if not payloads["INITRD"].startswith(b"\x1f\x8b"):
            raise ValueError("INITRD is not gzip-compressed")
        if not payloads["DTB.IMG"].startswith(b"\xd0\x0d\xfe\xed"):
            raise ValueError("dtb.img lacks an FDT header")

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

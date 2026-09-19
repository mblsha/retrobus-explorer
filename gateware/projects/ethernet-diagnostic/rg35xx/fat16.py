"""The card's partition table and the FAT16 boot volume inside partition 1.

U-Boot reads the boot files through this filesystem and walks a file's FAT
chain a cluster at a time, so where a file physically lands is a boot-time
cost rather than a detail: this module both reads the volume and rewrites a
file in it, keeping the two FAT copies in agreement.
"""

from __future__ import annotations

import io

from rg35xx.debug_partition import SECTOR_SIZE


def read_at(stream, offset: int, size: int) -> bytes:
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("boot image is truncated")
    return data


def mbr_partition(entry: bytes) -> dict[str, int]:
    """Decode one 16-byte MBR or extended-boot-record entry."""
    return {
        "boot": entry[0],
        "type": entry[4],
        "start_lba": int.from_bytes(entry[8:12], "little"),
        "sectors": int.from_bytes(entry[12:16], "little"),
    }


def mbr_partitions(stream, count: int = 4) -> list[dict[str, int]]:
    """Decode the primary partition entries of an opened image."""
    mbr = read_at(stream, 0, SECTOR_SIZE)
    return [
        mbr_partition(mbr[446 + index * 16 : 462 + index * 16])
        for index in range(count)
    ]


def boot_volume(image: bytes) -> tuple[io.BytesIO, "Fat16", list[dict[str, int]]]:
    """Open partition 1 of an in-memory image as the FAT16 boot volume."""
    stream = io.BytesIO(image)
    partitions = mbr_partitions(stream)
    fat = Fat16(stream, partitions[0]["start_lba"], partitions[0]["sectors"])
    return stream, fat, partitions


class Fat16:
    def __init__(self, stream, start_lba: int, sectors: int):
        self.stream = stream
        self.start = start_lba * SECTOR_SIZE
        self.length = sectors * SECTOR_SIZE
        boot = read_at(stream, self.start, SECTOR_SIZE)
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
        root = read_at(stream, self.root_offset, root_bytes)
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
                read_at(self.stream, self.fat_offset + cluster * 2, 2), "little"
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
            output.extend(read_at(self.stream, offset, self.cluster_size))
            cluster = int.from_bytes(
                read_at(self.stream, self.fat_offset + cluster * 2, 2), "little"
            )
        if len(output) < size:
            raise ValueError(f"short FAT chain for {name}")
        return bytes(output[:size])

    def placement(self, name: str) -> tuple[int, int, int]:
        """Return a contiguous file's (first LBA, block count, byte size).

        A raw read states its block count rather than letting the filesystem
        compute a length, so it assumes contiguity; a fragmented file would
        silently read the wrong sectors and is refused here instead.
        """
        chain = [cluster for cluster, _ in self.clusters(name)]
        if chain != list(range(chain[0], chain[0] + len(chain))):
            raise ValueError(f"{name} is fragmented and cannot be read raw")
        sectors_per_cluster = self.cluster_size // SECTOR_SIZE
        size = self.files[name][1]
        return (
            self.data_offset // SECTOR_SIZE + (chain[0] - 2) * sectors_per_cluster,
            (size + SECTOR_SIZE - 1) // SECTOR_SIZE,
            size,
        )


def replace_file(image: bytes, name: str, payload: bytes) -> bytes:
    """Replace a file in the FAT boot volume, reallocating its clusters.

    A rewritten boot script or a compressed kernel rarely fits the chain the
    directory entry points at, so the file is reallocated. Both FAT copies are
    rewritten together; a volume whose copies disagree is what fsck repairs by
    guessing.
    """
    stream, fat, _ = boot_volume(image)
    if name not in fat.files:
        raise ValueError(f"FAT boot volume lacks {name}")

    boot = read_at(stream, fat.start, SECTOR_SIZE)
    fat_sectors = int.from_bytes(boot[22:24], "little")
    copies = boot[16]
    table_bytes = fat_sectors * SECTOR_SIZE
    table = bytearray(read_at(stream, fat.fat_offset, table_bytes))
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

    root = bytearray(read_at(stream, fat.root_offset, fat.data_offset - fat.root_offset))
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

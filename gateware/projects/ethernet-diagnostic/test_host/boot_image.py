"""A miniature card image the image, FAT and boot-script tests all build on.

It is laid out like the real card -- FAT16 boot volume, raw debug partition
behind it, an eGON SPL at byte 8192 -- but at 256 sectors instead of 64 MiB,
so every test can build one in memory and assert on absolute sectors.
"""

import struct
from pathlib import Path

from rg35xx import debug_partition
from rg35xx import image as image_module
from rg35xx.boot_script import build_boot_script
from rg35xx.debug_partition import SECTOR_SIZE

BOOT_START = 128
BOOT_SECTORS = 64
DEBUG_START = 192
DEBUG_SECTORS = debug_partition.DEBUG_SECTORS


def boot_image_fixture(path: Path) -> None:
    image = bytearray(256 * SECTOR_SIZE)
    image[510:512] = b"\x55\xaa"

    def partition(index, boot, kind, start, sectors):
        offset = 446 + index * 16
        image[offset] = boot
        image[offset + 4] = kind
        image[offset + 8 : offset + 12] = start.to_bytes(4, "little")
        image[offset + 12 : offset + 16] = sectors.to_bytes(4, "little")

    partition(0, 0x80, image_module.FAT16_LBA_TYPE, BOOT_START, BOOT_SECTORS)
    partition(1, 0, image_module.LINUX_TYPE, DEBUG_START, DEBUG_SECTORS)

    spl = bytearray(SECTOR_SIZE)
    spl[4:12] = b"eGON.BT0"
    spl[16:20] = len(spl).to_bytes(4, "little")
    spl[12:16] = image_module.SPL_CHECKSUM_STAMP.to_bytes(4, "little")
    checksum = sum(word[0] for word in struct.iter_unpack("<I", spl)) & 0xFFFFFFFF
    spl[12:16] = checksum.to_bytes(4, "little")
    image[image_module.SPL_OFFSET : image_module.SPL_OFFSET + len(spl)] = spl

    boot_start = BOOT_START * SECTOR_SIZE
    boot = memoryview(image)[boot_start : boot_start + BOOT_SECTORS * SECTOR_SIZE]
    boot[11:13] = (512).to_bytes(2, "little")
    boot[13] = 1
    boot[14:16] = (1).to_bytes(2, "little")
    boot[16] = 1
    boot[17:19] = (32).to_bytes(2, "little")
    boot[19:21] = (64).to_bytes(2, "little")
    boot[21] = 0xF8
    boot[22:24] = (1).to_bytes(2, "little")
    boot[510:512] = b"\x55\xaa"
    boot[512:516] = b"\xf8\xff\xff\xff"

    milestone = debug_partition.absolute_lba(
        DEBUG_START, debug_partition.SCRIPT_RUNNING
    )
    files = {
        b"BOOT    SCR": build_boot_script(
            b"\x27\x05\x19\x56" + bytes(60),
            f"mmc write x {milestone:#x} 1\n"
            f"baredebug=/dev/mmcblk0p{debug_partition.DEBUG_PARTITION}\n"
            "booti x y z\n",
        ),
        b"BOOTMARK   ": (
            b"RG35DBG1\ndirection=target-to-host\nstage=0\ndetail=uboot-loaded-fat\n"
        ).ljust(512, b"\0"),
        b"KERNEL     ": bytes(56) + b"ARM\x64" + bytes(20),
        b"INITRD     ": b"\x1f\x8b" + bytes(30),
        b"DTB     IMG": b"\xd0\x0d\xfe\xed" + bytes(28),
    }
    root_offset = 2 * 512
    data_offset = 4 * 512
    for index, (name, payload) in enumerate(files.items()):
        cluster = index + 2
        entry = root_offset + index * 32
        boot[entry : entry + 11] = name
        boot[entry + 11] = 0x20
        boot[entry + 26 : entry + 28] = cluster.to_bytes(2, "little")
        boot[entry + 28 : entry + 32] = len(payload).to_bytes(4, "little")
        boot[512 + cluster * 2 : 514 + cluster * 2] = b"\xff\xff"
        offset = data_offset + (cluster - 2) * 512
        boot[offset : offset + len(payload)] = payload

    debug_start = DEBUG_START * SECTOR_SIZE
    image[debug_start : debug_start + SECTOR_SIZE] = debug_partition.encode_command(
        "boot-shell"
    )
    path.write_bytes(bytes(image))


def erofs_fixture(blocks: int = 8) -> bytes:
    """A blob that is EROFS only as far as this tooling inspects it."""
    blob = bytearray(blocks * SECTOR_SIZE)
    offset = image_module.EROFS_SUPERBLOCK_OFFSET
    blob[offset : offset + 4] = image_module.EROFS_MAGIC
    return bytes(blob)


def ext2_fixture(blocks: int = 16) -> bytes:
    blob = bytearray(blocks * SECTOR_SIZE)
    offset = image_module.EXT2_MAGIC_OFFSET
    blob[offset : offset + 2] = image_module.EXT2_MAGIC
    return bytes(blob)


def gzip_kernel_image(directory) -> bytes:
    """Return the fixture image with KERNEL stored gzip-compressed.

    The EROFS boot script only accepts a compressed kernel, so every test that
    builds a card image starts from this rather than from the bare fixture.
    """
    path = Path(directory) / "boot.img"
    boot_image_fixture(path)
    return image_module.compress_kernel(path.read_bytes(), "gzip")


def erofs_image(directory, slot=8, **kwargs) -> bytes:
    """Return a built card image with both system slots and the data volume."""
    return image_module.make_erofs_image(
        gzip_kernel_image(directory),
        erofs_fixture(),
        ext2_fixture(),
        minimum_slot_sectors=slot,
        **kwargs,
    )

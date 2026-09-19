"""The U-Boot script the card serves, and the legacy image that wraps it.

The script is the only program that runs between the SPL and the kernel, and
the only way it can report progress is by writing sectors of the debug
partition, so it is generated from the image it will boot: the sectors the
kernel and the device tree occupy are read out of the FAT volume, and the
milestone LBAs are resolved from the partition table rather than assumed.
"""

from __future__ import annotations

import struct
import zlib

from rg35xx.debug_partition import DEBUG_PARTITION
from rg35xx.debug_partition import DEVICE_TREE_LOADED
from rg35xx.debug_partition import ENV_EXPORT_SECTOR
from rg35xx.debug_partition import ENV_EXPORT_SECTORS
from rg35xx.debug_partition import KERNEL_LOADED
from rg35xx.debug_partition import SCRIPT_RUNNING
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import absolute_lba
from rg35xx.fat16 import boot_volume
from rg35xx.fat16 import replace_file

UIMAGE_MAGIC = 0x27051956
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
GZIP_MAGIC = b"\x1f\x8b"

EROFS_BOOTARGS = (
    "console=tty0 quiet loglevel=0 root=/dev/mmcblk0p{root} rootfstype=erofs "
    f"ro rootwait init=/sbin/init baredebug=/dev/mmcblk0p{DEBUG_PARTITION}"
)

# booti decompresses into kernel_comp_addr_r and refuses to start unless
# kernel_comp_size is also set, which is what the first attempt at a zstd
# kernel was missing: it read the image, wrote every milestone and then stopped
# without a console to say why.
KERNEL_COMP_SIZE = 0x2000000


def build_boot_script(header: bytes, script: str) -> bytes:
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


def repair_boot_script(image: bytes, script: str) -> bytes:
    """Replace BOOT.SCR in a boot image with a correctly framed script image."""
    _, fat, _ = boot_volume(image)
    if "BOOT.SCR" not in fat.files:
        raise ValueError("boot image has no BOOT.SCR")
    rebuilt = build_boot_script(fat.read("BOOT.SCR")[:64], script)
    return replace_file(image, "BOOT.SCR", rebuilt)


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


def erofs_slot_script(image: bytes, root_partition: int,
                      export_env: bool = False) -> str:
    """Return the boot script for a card whose root is an EROFS partition.

    No initramfs is in the boot path at all. U-Boot does not read one, the
    kernel does not unpack one, and the root filesystem is mounted straight off
    the card, where EROFS pages in only the blocks that are touched.

    The active slot is compiled into this script rather than read from the
    debug sector at run time. Reading it would need `setexpr`, which this
    U-Boot has not been shown to have, and a script that aborts on an unknown
    command produces no boot and no milestone to diagnose it with. Switching
    slots rewrites this one file, which is what an update would do anyway.
    """
    _, fat, partitions = boot_volume(image)
    kernel = fat.placement("KERNEL")[:2]
    dtb = fat.placement("DTB.IMG")[:2]
    stored = fat.read("KERNEL")
    if stored[:2] != GZIP_MAGIC and stored[:4] != ZSTD_MAGIC:
        raise ValueError("the EROFS boot script expects a gzip or zstd kernel")
    bootargs = EROFS_BOOTARGS.format(root=root_partition)
    # Every milestone is addressed from where the debug partition actually
    # starts, so a card laid out differently still reports into it rather than
    # into whatever happens to live at a remembered sector.
    debug_start = partitions[DEBUG_PARTITION - 1]["start_lba"]
    # The board has no serial header populated, so a variable U-Boot resolves
    # at run time cannot be read any other way. `env export` renders the whole
    # environment as text into memory, and the debug partition carries it back.
    # Guessing at kernel_comp_addr_r instead would risk writing the compressed
    # image over the device tree.
    export = (
        f"env export -t ${{ramdisk_addr_r}} {ENV_EXPORT_SECTORS * SECTOR_SIZE:#x}\n"
        f"mmc write ${{ramdisk_addr_r}} "
        f"{absolute_lba(debug_start, ENV_EXPORT_SECTOR):#x} "
        f"{ENV_EXPORT_SECTORS:#x}\n"
        if export_env else ""
    )
    return (
        "mmc dev 0\n"
        f"{export}"
        f"mmc write ${{ramdisk_addr_r}} "
        f"{absolute_lba(debug_start, SCRIPT_RUNNING):#x} 1\n"
        f"setenv bootargs '{bootargs}'\n"
        f"{_kernel_load(stored, kernel)}"
        f"mmc write ${{kernel_addr_r}} "
        f"{absolute_lba(debug_start, KERNEL_LOADED):#x} 1\n"
        f"mmc read ${{fdt_addr_r}} {dtb[0]:#x} {dtb[1]:#x}\n"
        f"mmc write ${{fdt_addr_r}} "
        f"{absolute_lba(debug_start, DEVICE_TREE_LOADED):#x} 1\n"
        "booti ${kernel_addr_r} - ${fdt_addr_r}\n"
    )

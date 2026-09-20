"""Build and inspect RG35XX Plus card images from the command line.

Sector 0 of the raw debug partition is a host-to-target command; the sectors
behind it are the target's milestones. The partition deliberately has no
filesystem so these writes cannot damage the boot files.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from rg35xx.debug_partition import JOB_LBA
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import decode_records
from rg35xx.debug_partition import kernel_log
from rg35xx.debug_partition import encode_command
from rg35xx.fat16 import read_at
from rg35xx.fat16 import replace_file
from rg35xx.image import SPL_OFFSET
from rg35xx.image import SYSTEM_A_PARTITION
from rg35xx.image import SYSTEM_B_PARTITION
from rg35xx.image import describe_lba
from rg35xx.image import install_bootloader
from rg35xx.image import logical_partitions
from rg35xx.image import make_erofs_image
from rg35xx.image import make_spl_entry_loop
from rg35xx.image import verify_boot_image


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--make-command", metavar="COMMAND")
    group.add_argument("--decode", type=Path, metavar="IMAGE")
    group.add_argument("--kernel-log", type=Path, metavar="DUMP",
                       help="Print the flight recorder page from a dump of the debug partition")
    group.add_argument("--verify-image", type=Path, metavar="IMAGE")
    group.add_argument("--make-spl-loop", type=Path, metavar="IMAGE")
    group.add_argument("--describe", type=Path, metavar="IMAGE")
    group.add_argument("--replace-file", type=Path, metavar="IMAGE")
    group.add_argument("--install-bootloader", type=Path, metavar="IMAGE",
                       help="Replace the bootloader at byte 8192 of a base image")
    group.add_argument("--make-erofs-image", type=Path, metavar="IMAGE")
    parser.add_argument("--bootloader", type=Path,
                        help="u-boot-sunxi-with-spl.bin to install")
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
    parser.add_argument(
        "--card-max-hz", type=int, metavar="HZ",
        help="Cap the clock Linux gives the emulated card, in the image's "
             "device tree; an image that starts the display needs 6000000",
    )
    parser.add_argument(
        "--debug-command",
        help="Host command to build into the image's debug sector, for an "
             "image whose whole purpose is one mode; the default is the "
             "boot-shell the base image carries",
    )
    parser.add_argument("--name")
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--lba", type=int, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

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
        root = SYSTEM_A_PARTITION if args.slot == "a" else SYSTEM_B_PARTITION
        built = make_erofs_image(
            args.make_erofs_image.read_bytes(),
            args.system.read_bytes(),
            args.data.read_bytes(),
            root_partition=root,
            export_env=args.export_env,
            card_max_hz=args.card_max_hz,
            debug_command=args.debug_command,
        )
        args.output.write_bytes(built)
        with io.BytesIO(built) as stream:
            mbr = read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "bytes": len(built),
                    "sha256": hashlib.sha256(built).hexdigest(),
                    "root": f"/dev/mmcblk0p{root}",
                    "logical_partitions": chain,
                },
                indent=2,
            )
        )
        return

    if args.install_bootloader is not None:
        if args.output is None or args.bootloader is None:
            parser.error("--install-bootloader requires --bootloader and --output")
        bootloader = args.bootloader.read_bytes()
        built = install_bootloader(
            args.install_bootloader.read_bytes(), bootloader, JOB_LBA
        )
        args.output.write_bytes(built)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "bootloader": str(args.bootloader),
                    "bootloader_bytes": len(bootloader),
                    "bootloader_sha256": hashlib.sha256(bootloader).hexdigest(),
                    "last_lba": (SPL_OFFSET + len(bootloader) - 1) // SECTOR_SIZE,
                    "reserved_lba": JOB_LBA,
                    "sha256": hashlib.sha256(built).hexdigest(),
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

    if args.kernel_log is not None:
        print(kernel_log(args.kernel_log.read_bytes()), end="")
        return

    for record in decode_records(args.decode.read_bytes()):
        print(" ".join(f"{key}={value}" for key, value in record.items()))


if __name__ == "__main__":
    main()

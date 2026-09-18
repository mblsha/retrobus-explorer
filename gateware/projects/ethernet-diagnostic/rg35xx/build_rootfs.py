#!/usr/bin/env python3
"""Build the EROFS system image and the ext2 data image for the RG35XX card.

The initramfs this replaces was read whole before the kernel could start, all
1.5 MB of it, and then held in memory for the rest of the boot. EROFS is
demand paged: the kernel mounts the partition from the card and reads only the
blocks it touches, so a system image can grow without the boot paying for it.

The compression is LZ4HC, which costs build time rather than boot time. Its
output is ordinary LZ4, so the kernel needs only CONFIG_EROFS_FS_ZIP and its
LZ4 decompressor, and decompression stays cheap on an A53.

The physical cluster size is the unit the kernel reads and decompresses, so it
decides how many card transactions a given access pattern costs. It is a build
option here because the right value is a property of this card's transfer rate
and latency and has to be measured on hardware, not assumed.

BusyBox is the same static build the initramfs used, so the userspace is a
known quantity and the only thing under test is where it is read from.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATEWARE = HERE.parents[2]
DEFAULT_BUSYBOX = "1.36.1"
DEFAULT_BUSYBOX_SHA256 = (
    "b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314"
)
DEFAULT_IMAGE = "alpine:3.20"

BUILD = r"""
set -eu
apk add --no-cache build-base perl linux-headers erofs-utils e2fsprogs \
    e2fsprogs-extra >/dev/null
mkfs.erofs --version 2>&1 | head -n 1

cd /tmp
wget -q "https://busybox.net/downloads/busybox-$BUSYBOX.tar.bz2"
actual=$(sha256sum "busybox-$BUSYBOX.tar.bz2" | cut -d' ' -f1)
echo "busybox-$BUSYBOX.tar.bz2 sha256 $actual"
if [ -n "$BUSYBOX_SHA256" ] && [ "$actual" != "$BUSYBOX_SHA256" ]; then
  echo "busybox tarball does not match the pinned hash" >&2
  exit 1
fi
tar xf "busybox-$BUSYBOX.tar.bz2"
cd "busybox-$BUSYBOX"
make defconfig >/dev/null
# Static for the same reason the initramfs was: this rootfs carries no libc.
sed -i 's/^# CONFIG_STATIC is not set$/CONFIG_STATIC=y/' .config
sed -i 's/^CONFIG_TC=y$/# CONFIG_TC is not set/' .config
make oldconfig >/dev/null
make -j"$(nproc)" >/dev/null
make CONFIG_PREFIX=/tmp/rootfs install >/dev/null

cd /tmp/rootfs
mkdir -p dev proc sys tmp data etc usr/bin
[ -e usr/bin/busybox ] || cp bin/busybox usr/bin/busybox
cp /payload/rootfs-init sbin/init
chmod 0755 sbin/init
# The kernel tries /sbin/init first, but rdinit= and init= both name paths that
# have to exist, and /init is what a converted initramfs image would use.
ln -sf sbin/init init
printf 'rg35xx-plus\n' > etc/hostname

# --all-root keeps ownership independent of the build container, and -T pins
# every timestamp so the same input produces the same image.
mkfs.erofs -zlz4hc,12 -C"$CLUSTER" -b4096 --all-root -T 0 \
    "/out/$SYSTEM_NAME" /tmp/rootfs
ls -l "/out/$SYSTEM_NAME"

# The data partition is created empty; its only job is to be writable, so the
# reserved-block percentage is zeroed and the inode count kept small.
rm -f "/out/$DATA_NAME"
mke2fs -q -t ext2 -b 1024 -m 0 -N 256 -L data -F \
    "/out/$DATA_NAME" "$DATA_KIB" >/dev/null
ls -l "/out/$DATA_NAME"
"""


def find_runner(explicit: str | None = None) -> list[str]:
    """Return the container command, preferring a plain docker or nerdctl."""
    if explicit:
        return explicit.split()
    for candidate in ("docker", "nerdctl"):
        if shutil.which(candidate):
            return [candidate]
    if shutil.which("colima"):
        return ["colima", "nerdctl", "--"]
    raise RuntimeError("need docker, nerdctl or colima to build the rootfs")


def container_command(runner: list[str], payload: Path, out: Path, image: str,
                      busybox: str, sha256: str, cluster: int, system_name: str,
                      data_name: str, data_kib: int) -> list[str]:
    return [
        *runner, "run", "--rm", "--platform", "linux/arm64",
        "-v", f"{payload}:/payload:ro",
        "-v", f"{out}:/out",
        "-e", f"BUSYBOX={busybox}",
        "-e", f"BUSYBOX_SHA256={sha256}",
        "-e", f"CLUSTER={cluster}",
        "-e", f"SYSTEM_NAME={system_name}",
        "-e", f"DATA_NAME={data_name}",
        "-e", f"DATA_KIB={data_kib}",
        image, "sh", "-c", BUILD,
    ]


def system_image_name(cluster: int) -> str:
    """Name the image after its cluster size; comparing two of them on hardware
    is the only way to choose one, so both have to coexist."""
    return f"system-c{cluster}.erofs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--busybox", default=DEFAULT_BUSYBOX)
    parser.add_argument("--busybox-sha256", default=DEFAULT_BUSYBOX_SHA256,
                        help="Pinned tarball hash; empty string skips the check")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--runner", help="Container command, e.g. 'docker'")
    parser.add_argument(
        "--cluster", type=int, default=65536,
        help="EROFS physical cluster size in bytes; the unit the kernel reads",
    )
    parser.add_argument(
        "--data-kib", type=int, default=32 * 1024,
        help="Size of the ext2 data image in KiB",
    )
    parser.add_argument(
        "--out", type=Path, default=GATEWARE / "build/rg35xx-bare",
    )
    arguments = parser.parse_args()
    arguments.out.mkdir(parents=True, exist_ok=True)
    system_name = system_image_name(arguments.cluster)
    data_name = "data.ext2"
    command = container_command(
        find_runner(arguments.runner), HERE, arguments.out.resolve(),
        arguments.image, arguments.busybox, arguments.busybox_sha256,
        arguments.cluster, system_name, data_name, arguments.data_kib,
    )
    result = subprocess.run(command, check=False)
    if result.returncode:
        sys.exit(result.returncode)
    for name in (system_name, data_name):
        path = arguments.out / name
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

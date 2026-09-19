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
import re
import sys
import tempfile
from pathlib import Path

from rg35xx.containers import DEFAULT_IMAGE
from rg35xx.containers import container_command as run_in_container
from rg35xx.containers import find_runner
from rg35xx.containers import run
from rg35xx.debug_partition import CARD_CHECK_SECTOR
from rg35xx.debug_partition import DEBUG_PARTITION
from rg35xx.debug_partition import JOB_LBA
from rg35xx.debug_partition import JOB_SECTORS
from rg35xx.debug_partition import KERNEL_LOG_SECTOR
from rg35xx.debug_partition import KERNEL_LOG_SECTORS
from rg35xx.debug_partition import MAGIC
from rg35xx.debug_partition import RESULT_OUTPUT_BYTES
from rg35xx.debug_partition import RESULT_SECTOR
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import SLEEP_MARK_SECTOR
from rg35xx.debug_partition import USERSPACE_BASE
from rg35xx.image import DATA_PARTITION
from rg35xx import display_proof

HERE = Path(__file__).resolve().parent
GATEWARE = HERE.parents[2]
DEFAULT_BUSYBOX = "1.36.1"
DEFAULT_BUSYBOX_SHA256 = (
    "b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314"
)

# PID 1 is a template rather than a script, because everything it needs to
# know -- which partition carries the debug sectors, which carries the data
# volume, the record magic and where userspace's milestones start -- is
# decided by the image layout. A second copy of those values here is a second
# place for them to drift out of agreement with the boot script.
INIT_TEMPLATE = HERE / "rootfs-init"
# The job runner init execs when the host asks for one. It is a second template
# rather than a function inside init because it runs from tmpfs, copied there
# before the loop starts, and a separate file is what can be copied.
JOB_RUNNER_TEMPLATE = HERE / "rootfs-job-runner"
PLACEHOLDER = re.compile(r"@[A-Z0-9_]+@")
def init_values() -> dict[str, str]:
    return {
        "DEBUG_DEVICE": f"/dev/mmcblk0p{DEBUG_PARTITION}",
        "DATA_DEVICE": f"/dev/mmcblk0p{DATA_PARTITION}",
        "MAGIC": MAGIC,
        "USERSPACE_BASE": str(USERSPACE_BASE),
        "KERNEL_LOG_SECTOR": str(KERNEL_LOG_SECTOR),
        "KERNEL_LOG_SECTORS": str(KERNEL_LOG_SECTORS),
        "KERNEL_LOG_BYTES": str(KERNEL_LOG_SECTORS * SECTOR_SIZE),
        "CARD_DEVICE": "/dev/mmcblk0",
        "JOB_LBA": str(JOB_LBA),
        "JOB_SECTORS": str(JOB_SECTORS),
        "RESULT_SECTOR": str(RESULT_SECTOR),
        "RESULT_OUTPUT_BYTES": str(RESULT_OUTPUT_BYTES),
        "CARD_CHECK_SECTOR": str(CARD_CHECK_SECTOR),
        "SLEEP_MARK_SECTOR": str(SLEEP_MARK_SECTOR),
    }


def render(path: Path, template: str | None = None) -> str:
    """Fill one target-side template from the layout, or refuse to build.

    An unrendered placeholder would reach the target as a shell word, and the
    failure it produces is a boot that writes nothing at all: exactly the
    silence these scripts exist to break.
    """
    text = path.read_text() if template is None else template
    for name, value in init_values().items():
        text = text.replace(f"@{name}@", value)
    left = sorted(set(PLACEHOLDER.findall(text)))
    if left:
        raise ValueError(f"{path.name} still carries {', '.join(left)}")
    return text


def render_init(template: str | None = None) -> str:
    return render(INIT_TEMPLATE, template)


def render_job_runner(template: str | None = None) -> str:
    return render(JOB_RUNNER_TEMPLATE, template)


DEFAULT_PROOF_LINES = ("RG35XX PLUS", "DISPLAY OK", "EROFS ROOT")


def write_payload(directory: Path, proof_lines=DEFAULT_PROOF_LINES) -> Path:
    """Put everything the container installs into one directory it can mount:
    the rendered init, and the picture init draws to prove the panel works."""
    directory.mkdir(parents=True, exist_ok=True)
    init = directory / INIT_TEMPLATE.name
    init.write_text(render_init())
    init.chmod(0o755)
    runner = directory / JOB_RUNNER_TEMPLATE.name
    runner.write_text(render_job_runner())
    runner.chmod(0o755)
    (directory / "display-proof.ppm").write_bytes(display_proof.render(list(proof_lines)))
    return init


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
cp /payload/rootfs-job-runner usr/bin/job-runner
chmod 0755 usr/bin/job-runner
# The kernel tries /sbin/init first, but rdinit= and init= both name paths that
# have to exist, and /init is what a converted initramfs image would use.
ln -sf sbin/init init
printf 'rg35xx-plus\n' > etc/hostname
# The picture init draws once the kernel has brought the panel up.
mkdir -p usr/share/rg35xx
cp /payload/display-proof.ppm usr/share/rg35xx/display-proof.ppm

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


def container_command(runner: list[str], payload: Path, out: Path, image: str,
                      busybox: str, sha256: str, cluster: int, system_name: str,
                      data_name: str, data_kib: int) -> list[str]:
    return run_in_container(
        runner,
        image,
        BUILD,
        mounts=[(payload, "/payload", True), (out, "/out", False)],
        environment={
            "BUSYBOX": busybox,
            "BUSYBOX_SHA256": sha256,
            "CLUSTER": cluster,
            "SYSTEM_NAME": system_name,
            "DATA_NAME": data_name,
            "DATA_KIB": data_kib,
        },
    )


def system_image_name(cluster: int) -> str:
    """Name the image after its cluster size; comparing two of them on hardware
    is the only way to choose one, so both have to coexist."""
    return f"system-c{cluster}.erofs"


def main(argv: list[str] | None = None) -> None:
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
    parser.add_argument(
        "--proof-line", action="append", default=[],
        help="Text for the display proof picture; repeat for more lines",
    )
    arguments = parser.parse_args(argv)
    arguments.out.mkdir(parents=True, exist_ok=True)
    system_name = system_image_name(arguments.cluster)
    data_name = "data.ext2"
    # The payload is staged inside the output directory, not the system temp
    # directory: a container runtime that runs in a VM shares only part of the
    # host, and a path it does not share mounts as an empty directory without
    # complaint. The output directory is known to be shared because /out is it.
    with tempfile.TemporaryDirectory(dir=arguments.out, prefix=".payload-") as directory:
        payload = Path(directory) / "payload"
        try:
            write_payload(payload, arguments.proof_line or DEFAULT_PROOF_LINES)
        except ValueError as failure:
            parser.error(str(failure))
        command = container_command(
            find_runner(arguments.runner), payload, arguments.out.resolve(),
            arguments.image, arguments.busybox, arguments.busybox_sha256,
            arguments.cluster, system_name, data_name, arguments.data_kib,
        )
        returncode = run(command)
    if returncode:
        sys.exit(returncode)
    for name in (system_name, data_name):
        path = arguments.out / name
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

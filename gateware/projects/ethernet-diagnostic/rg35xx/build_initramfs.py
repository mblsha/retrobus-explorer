#!/usr/bin/env python3
"""Build the RG35XX Plus initramfs: a static BusyBox plus this directory's init.

The shipped image carried a 3 KiB initramfs holding only /init, a shell script
calling /usr/bin/busybox. Neither that binary nor any shell was present, so
rdinit could not execute and userspace never started. This produces one that
runs.

BusyBox is built from an unpatched release tarball with defconfig plus
CONFIG_STATIC, the shape tools/zaurus-sd-boot/busybox/build_busybox.sh uses for
the Zaurus. The H700 is aarch64 and the container runs natively on Apple
silicon, so no cross prefix is needed.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATEWARE = HERE.parents[2]
DEFAULT_VERSION = "1.36.1"
DEFAULT_SHA256 = "b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314"
DEFAULT_IMAGE = "alpine:3.20"

BUILD = r"""
set -eu
apk add --no-cache build-base perl linux-headers >/dev/null
cd /tmp
wget -q "https://busybox.net/downloads/busybox-$VERSION.tar.bz2"
actual=$(sha256sum "busybox-$VERSION.tar.bz2" | cut -d' ' -f1)
echo "busybox-$VERSION.tar.bz2 sha256 $actual"
if [ -n "$EXPECTED" ] && [ "$actual" != "$EXPECTED" ]; then
  echo "busybox tarball does not match the pinned hash" >&2
  exit 1
fi
tar xf "busybox-$VERSION.tar.bz2"
cd "busybox-$VERSION"
make defconfig >/dev/null
# A static binary is the point: the initramfs carries no libc.
sed -i 's/^# CONFIG_STATIC is not set$/CONFIG_STATIC=y/' .config
# tc does not build against current kernel headers and nothing here uses it.
sed -i 's/^CONFIG_TC=y$/# CONFIG_TC is not set/' .config
make oldconfig >/dev/null
make -j"$(nproc)" >/dev/null
make CONFIG_PREFIX=/tmp/rootfs install >/dev/null
cd /tmp/rootfs
mkdir -p dev proc sys tmp usr/bin
cp /payload/init init
chmod 0755 init
# init calls busybox by absolute path and needs a shell for its shebang; both
# resolve inside the initramfs itself.
[ -e usr/bin/busybox ] || cp bin/busybox usr/bin/busybox
find . | cpio -o -H newc --quiet | gzip -9 > "/out/$OUTPUT_NAME"
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
    raise RuntimeError("need docker, nerdctl or colima to build the initramfs")


def container_command(runner: list[str], payload: Path, out: Path, image: str,
                      version: str, sha256: str, name: str) -> list[str]:
    return [
        *runner, "run", "--rm", "--platform", "linux/arm64",
        "-v", f"{payload}:/payload:ro",
        "-v", f"{out}:/out",
        "-e", f"VERSION={version}",
        "-e", f"EXPECTED={sha256}",
        "-e", f"OUTPUT_NAME={name}",
        image, "sh", "-c", BUILD,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--sha256", default=DEFAULT_SHA256,
                        help="Pinned tarball hash; empty string skips the check")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--runner", help="Container command, e.g. 'docker'")
    parser.add_argument(
        "--output", type=Path,
        default=GATEWARE / "build/rg35xx-bare/initramfs.cpio.gz",
    )
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    command = container_command(
        find_runner(arguments.runner), HERE, arguments.output.parent.resolve(),
        arguments.image, arguments.version, arguments.sha256,
        arguments.output.name,
    )
    result = subprocess.run(command, check=False)
    if result.returncode:
        sys.exit(result.returncode)
    print(f"wrote {arguments.output} ({arguments.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

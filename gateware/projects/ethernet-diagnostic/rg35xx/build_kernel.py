#!/usr/bin/env python3
"""Build a trimmed Linux kernel for the RG35XX Plus.

The shipped ROCKNIX kernel is a 30.4 MiB arm64 Image with 1,923 options built
in and 55 modules, and the card reads about 2.95 MB/s, so the kernel read is
the largest term in the boot. This builds the same source, mainline 7.2 with
ROCKNIX's H700 patches, from ROCKNIX's own configuration with everything this
device cannot use removed.

The bottleneck is I/O and the CPU is a 1.5 GHz quad A53, so the kernel is built
for size rather than speed: here that is the same thing as building it for
boot time.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATEWARE = HERE.parents[2]
# Pinned by ROCKNIX's own package.mk for the H700 device.
KERNEL_VERSION = "7.2"
KERNEL_SHA256 = "f9fef3d14c0df53819026f4be74459835c2a0b0dcbf5b5bbd9ea19f0829402b3"
DEFAULT_IMAGE = "alpine:3.20"
# The patches and the configuration come from ROCKNIX's tree, which this build
# does not fetch: they are prepared in the work directory out of band. Their
# content is what decides whether the kernel that comes out is the kernel that
# was measured, so the commit they came from and their hashes are recorded here
# and checked before the build. A re-fetch that quietly picks up a newer branch
# tip would otherwise produce a different kernel under the same name.
SOURCES = HERE / "rocknix-sources.json"

# Nothing internal is behind USB: the device tree enables one port, the
# physical socket, and disables the other three. Wi-Fi is SDIO, Bluetooth is
# UART, the controls are gpio-keys, audio is on the SoC. Charging is a
# power-supply driver and survives this.
DISABLE = [
    "USB_SUPPORT",
    "BTRFS_FS", "NTFS3_FS", "NFS_FS", "SQUASHFS", "EXT4_FS", "F2FS_FS",
    "NETFILTER",
    "SCSI", "ATA", "NVME_CORE", "MTD",
    "FTRACE", "KPROBES", "BPF_SYSCALL",
    "KEXEC", "KEXEC_FILE", "CRASH_DUMP", "HIBERNATION",
    "KALLSYMS_ALL",
    "DEBUG_FS",
    "RANDOMIZE_BASE",
    "MEDIA_SUPPORT",
]

# EROFS is absent from the ROCKNIX configuration and the rootfs depends on it.
ENABLE = [
    "EROFS_FS", "EROFS_FS_ZIP", "EXT2_FS",
    "CC_OPTIMIZE_FOR_SIZE", "TRIM_UNUSED_KSYMS",
]

# The work directory is a host mount, and unpacking a 1.4 GiB kernel tree
# across it takes longer than the build itself. Everything except the tarball,
# the patches and the result is kept on the container's own filesystem.
BUILD = r"""
set -eu
# The kernel's own scripts need bash, rsync and GNU diff; Alpine ships
# busybox equivalents that are not sufficient.
apk add --no-cache build-base perl bc bison flex openssl-dev elfutils-dev \
    xz curl patch python3 zstd linux-headers bash rsync diffutils \
    findutils >/dev/null
if [ ! -f "/work/linux-$VERSION.tar.xz" ]; then
  curl -sSL -o "/work/linux-$VERSION.tar.xz" \
    "https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-$VERSION.tar.xz"
fi
mkdir -p /build
cd /build
cp "/work/linux-$VERSION.tar.xz" .
actual=$(sha256sum "linux-$VERSION.tar.xz" | cut -d' ' -f1)
echo "linux-$VERSION.tar.xz sha256 $actual"
if [ "$actual" != "$EXPECTED" ]; then
  echo "kernel tarball does not match the hash ROCKNIX pins" >&2
  exit 1
fi
rm -rf "linux-$VERSION"
tar xf "linux-$VERSION.tar.xz"
cd "linux-$VERSION"
for p in $(ls /patches/*.patch | sort); do
  patch -p1 --batch --forward --silent < "$p" || {
    echo "patch failed: $p" >&2; exit 1; }
done
cp /config/base.config .config
# ROCKNIX leaves a build-system placeholder here, and the target boots from
# an EROFS rootfs on the card rather than an initramfs, so it is cleared.
scripts/config --set-str INITRAMFS_SOURCE ""
# ROCKNIX builds the RTL8821CS blobs into the kernel from a firmware tree its
# own build system supplies. The rootfs carries /lib/firmware instead, which is
# the normal mechanism and keeps the blobs out of the image the card must read
# before anything can run.
scripts/config --set-str EXTRA_FIRMWARE ""
for opt in $DISABLE_LIST; do scripts/config --disable "$opt"; done
for opt in $ENABLE_LIST; do scripts/config --enable "$opt"; done
make ARCH=arm64 olddefconfig >/dev/null
make ARCH=arm64 -j"$(nproc)" Image
cp arch/arm64/boot/Image /out/Image
cp .config /out/trimmed.config
ls -l /out/Image
"""


def find_runner(explicit=None):
    if explicit:
        return explicit.split()
    for candidate in ("docker", "nerdctl"):
        if shutil.which(candidate):
            return [candidate]
    if shutil.which("colima"):
        return ["colima", "nerdctl", "--"]
    raise RuntimeError("need docker, nerdctl or colima to build the kernel")


def verify_sources(work: Path, sources: Path = SOURCES) -> dict:
    """Check the work directory against the recorded ROCKNIX manifest.

    A missing, extra or altered patch all change the kernel, so all three are
    refused rather than reported. The configuration is checked the same way,
    because a trim is only meaningful relative to the configuration it trims.
    """
    manifest = json.loads(sources.read_text())
    present = {path.name: path for path in sorted(work.glob("patches/*.patch"))}
    expected = manifest["patches"]
    missing = sorted(set(expected) - set(present))
    extra = sorted(set(present) - set(expected))
    if missing or extra:
        raise ValueError(
            f"patches do not match {manifest['commit'][:12]}: "
            f"{len(missing)} missing {missing[:3]}, {len(extra)} extra {extra[:3]}"
        )
    changed = [
        name
        for name, digest in sorted(expected.items())
        if hashlib.sha256(present[name].read_bytes()).hexdigest() != digest
    ]
    config = hashlib.sha256((work / "base.config").read_bytes()).hexdigest()
    if config != manifest["config_sha256"]:
        changed.append("base.config")
    if changed:
        raise ValueError(
            f"{len(changed)} source(s) differ from the recorded manifest: "
            f"{changed[:4]}"
        )
    return manifest


def container_command(runner, work, patches, config, out, image):
    return [
        *runner, "run", "--rm", "--platform", "linux/arm64",
        "-v", f"{work}:/work",
        "-v", f"{patches}:/patches:ro",
        "-v", f"{config}:/config:ro",
        "-v", f"{out}:/out",
        "-e", f"VERSION={KERNEL_VERSION}",
        "-e", f"EXPECTED={KERNEL_SHA256}",
        "-e", f"DISABLE_LIST={' '.join(DISABLE)}",
        "-e", f"ENABLE_LIST={' '.join(ENABLE)}",
        image, "sh", "-c", BUILD,
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path,
                        default=GATEWARE / "build/rg35xx-kernel")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--runner")
    parser.add_argument(
        "--allow-unpinned", action="store_true",
        help="Build from patches that do not match the recorded manifest. Use "
        "when deliberately moving to a newer ROCKNIX tree, and re-record it.",
    )
    arguments = parser.parse_args()
    work = arguments.work.resolve()
    for required in ("patches", "base.config"):
        if not (work / required).exists():
            parser.error(f"{work / required} is missing")
    if not arguments.allow_unpinned:
        try:
            verify_sources(work)
        except ValueError as failure:
            parser.error(str(failure))
    out = work / "out"
    out.mkdir(parents=True, exist_ok=True)
    command = container_command(
        find_runner(arguments.runner), work, work / "patches", work,
        out, arguments.image,
    )
    sys.exit(subprocess.run(command, check=False).returncode)


if __name__ == "__main__":
    main()

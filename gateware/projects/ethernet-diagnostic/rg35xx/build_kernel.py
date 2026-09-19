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
import sys
from pathlib import Path

from rg35xx.containers import DEFAULT_IMAGE
from rg35xx.containers import container_command as run_in_container
from rg35xx.containers import find_runner
from rg35xx.containers import run

HERE = Path(__file__).resolve().parent
GATEWARE = HERE.parents[2]
# Pinned by ROCKNIX's own package.mk for the H700 device.
KERNEL_VERSION = "7.2"
KERNEL_SHA256 = "f9fef3d14c0df53819026f4be74459835c2a0b0dcbf5b5bbd9ea19f0829402b3"
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
# The unused network surface. This board has no wired port, and the only radio
# is the Realtek SDIO part, so every other vendor's drivers and the protocol
# menus nothing here speaks are all dead weight in a kernel read off a 2.95
# MB/s card. mac80211 and cfg80211 stay; so does the Realtek vendor menu.
DISABLE_NETWORK = [
    "ETHERNET",
    "WLAN_VENDOR_ADMTEK", "WLAN_VENDOR_ATH", "WLAN_VENDOR_ATMEL",
    "WLAN_VENDOR_BROADCOM", "WLAN_VENDOR_CISCO", "WLAN_VENDOR_INTEL",
    "WLAN_VENDOR_INTERSIL", "WLAN_VENDOR_MARVELL", "WLAN_VENDOR_MEDIATEK",
    "WLAN_VENDOR_MICROCHIP", "WLAN_VENDOR_PURELIFI", "WLAN_VENDOR_QUANTENNA",
    "WLAN_VENDOR_RALINK", "WLAN_VENDOR_RSI", "WLAN_VENDOR_SILABS",
    "WLAN_VENDOR_ST", "WLAN_VENDOR_TI", "WLAN_VENDOR_ZYDAS",
    "NET_SCHED", "BRIDGE", "VLAN_8021Q", "L2TP", "PPP", "SLIP", "ATM",
    "CAN", "NFC", "HAMRADIO", "INET_DIAG", "TCP_CONG_ADVANCED",
    "NET_IPIP", "NET_IPGRE_DEMUX", "IPV6_SIT", "IPV6_MULTIPLE_TABLES",
    "XFRM_USER", "INET_ESP", "INET_AH", "IP_MULTICAST",
]
# The crypto menu, less what WPA needs. AES, CCM, CMAC, SHA and Michael MIC
# are pulled back in by the selects mac80211 and RTW88 carry, which is why
# these can be turned off wholesale and then reconciled by olddefconfig.
DISABLE_CRYPTO = [
    "CRYPTO_USER", "CRYPTO_USER_API_HASH", "CRYPTO_USER_API_SKCIPHER",
    "CRYPTO_USER_API_RNG", "CRYPTO_USER_API_AEAD", "CRYPTO_TEST",
    "CRYPTO_CAMELLIA", "CRYPTO_CAST5", "CRYPTO_CAST6", "CRYPTO_BLOWFISH",
    "CRYPTO_TWOFISH", "CRYPTO_SERPENT", "CRYPTO_ARIA", "CRYPTO_SM3_GENERIC",
    "CRYPTO_SM4_GENERIC", "CRYPTO_DES", "CRYPTO_ANUBIS", "CRYPTO_KHAZAD",
    "CRYPTO_SEED", "CRYPTO_WP512", "CRYPTO_RMD160", "CRYPTO_MD4",
    "CRYPTO_TGR192", "CRYPTO_VMAC", "CRYPTO_LRW", "CRYPTO_OFB",
    "CRYPTO_PCBC", "CRYPTO_KEYWRAP", "CRYPTO_ADIANTUM", "CRYPTO_NHPOLY1305",
    "CRYPTO_ESSIV", "CRYPTO_CHACHA20POLY1305", "CRYPTO_XCBC",
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
# ThinLTO needs the LLVM toolchain: clang to emit the bitcode, lld to link it,
# and llvm's ar and nm to handle archives full of bitcode rather than objects.
if [ "$TOOLCHAIN" = "clang" ]; then
  apk add --no-cache clang lld llvm >/dev/null
  MAKE_TOOLCHAIN="LLVM=1"
  clang --version | head -n 1
else
  MAKE_TOOLCHAIN=""
fi
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
if [ "$TOOLCHAIN" = "clang" ]; then
  # Full LTO needs far more memory than this container has; ThinLTO gets most
  # of the cross-module trimming for a fraction of it.
  scripts/config --disable LTO_NONE
  scripts/config --enable LTO_CLANG_THIN
fi
make ARCH=arm64 $MAKE_TOOLCHAIN olddefconfig >/dev/null
if [ "$TOOLCHAIN" = "clang" ] && ! grep -q '^CONFIG_LTO_CLANG_THIN=y' .config; then
  echo "ThinLTO was requested but olddefconfig did not keep it" >&2
  exit 1
fi
make ARCH=arm64 $MAKE_TOOLCHAIN -j"$(nproc)" Image
cp arch/arm64/boot/Image /out/Image
cp .config /out/trimmed.config
ls -l /out/Image
"""


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


def container_command(runner, work, patches, config, out, image,
                      disable=None, enable=None, toolchain="gcc"):
    disable = DISABLE if disable is None else disable
    enable = ENABLE if enable is None else enable
    return run_in_container(
        runner,
        image,
        BUILD,
        mounts=[
            (work, "/work", False),
            (patches, "/patches", True),
            (config, "/config", True),
            (out, "/out", False),
        ],
        environment={
            "VERSION": KERNEL_VERSION,
            "EXPECTED": KERNEL_SHA256,
            "DISABLE_LIST": " ".join(disable),
            "ENABLE_LIST": " ".join(enable),
            "TOOLCHAIN": toolchain,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path,
                        default=GATEWARE / "build/rg35xx-kernel")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--runner")
    parser.add_argument(
        "--toolchain", choices=("gcc", "clang"), default="gcc",
        help="clang additionally builds with ThinLTO",
    )
    parser.add_argument(
        "--trim-network-and-crypto", action="store_true",
        help="Also drop the network and crypto surface this device never uses",
    )
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
    disable = list(DISABLE)
    if arguments.trim_network_and_crypto:
        disable += DISABLE_NETWORK + DISABLE_CRYPTO
    command = container_command(
        find_runner(arguments.runner), work, work / "patches", work,
        out, arguments.image, disable=disable, toolchain=arguments.toolchain,
    )
    sys.exit(run(command))


if __name__ == "__main__":
    main()

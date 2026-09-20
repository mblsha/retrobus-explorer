#!/usr/bin/env python3
"""Build the RG35XX Plus bootloader from source, with or without deep sleep.

The bootloader ROCKNIX ships for the H700 is mainline U-Boot with one DRAM
patch and one defconfig, and it carries TF-A's BL31 inside its FIT. That BL31
is where PSCI lives, so anything the firmware can be made to do about suspend
is a change to a package this device's image never rebuilt before. This builds
both from pinned sources in an arm64 container, so the bootloader on the card
is one this bench can account for byte by byte.

`--suspend none` is the parity build: the same two upstream trees ROCKNIX
builds, nothing of ours added. `--suspend wfi` adds our TF-A patch, which
implements PSCI SYSTEM_SUSPEND by stopping the CPU PLL and waiting in WFI.
The `sr` modes add a second patch that moves the wait into a stub in SRAM A1
with DRAM in self-refresh around it, one rung of the ladder each.
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
from rg35xx import rocknix

HERE = Path(__file__).resolve().parent
GATEWARE = HERE.parents[2]
SOURCES = HERE / "firmware-sources.json"
PATCHES = HERE / "firmware"

# What each mode asks the two builds for. The patch list is the subset of our
# own patches to apply; an empty list is the unmodified upstream tree.
SUSPEND_MODES = {
    "none": {},
    "wfi": {"SUNXI_SYSTEM_SUSPEND": "1"},
    "wfi32": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_CPU_32K": "1"},
    "sr": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_DRAM_LEVEL": "1"},
    "sr-gate": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_DRAM_LEVEL": "2"},
    "sr-pll": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_DRAM_LEVEL": "3"},
}

# U-Boot stamps its version string and its FIT with the moment it was built,
# and TF-A stamps its banner, so without a fixed time two builds of the same
# sources differ. Pinned here so they do not.
SOURCE_DATE_EPOCH = "1758326941"
BUILD_TIMESTAMP = "00:00:00, Jan 01 2026"

BUILD = r"""
set -eu
apk add --no-cache build-base make perl patch bash findutils diffutils coreutils \
    python3 py3-setuptools py3-elftools swig python3-dev openssl-dev bison flex \
    bc xz gzip ncurses-dev util-linux-dev dtc linux-headers gnutls-dev curl \
    >/dev/null

fetch() {
  # $1 file, $2 url, $3 sha256
  if [ ! -f "/work/dl/$1" ]; then
    curl -sSL --max-time 900 -o "/work/dl/$1.part" "$2"
    mv "/work/dl/$1.part" "/work/dl/$1"
  fi
  actual=$(sha256sum "/work/dl/$1" | cut -d' ' -f1)
  echo "$1 sha256 $actual"
  if [ "$actual" != "$3" ]; then
    echo "$1 does not match the pinned hash" >&2
    exit 1
  fi
}

mkdir -p /work/dl /build
fetch "$TFA_FILE" "$TFA_URL" "$TFA_SHA256"
fetch "$UBOOT_FILE" "$UBOOT_URL" "$UBOOT_SHA256"

cd /build
rm -rf tf-a u-boot
mkdir tf-a u-boot
tar xzf "/work/dl/$TFA_FILE" -C tf-a --strip-components=1
tar xzf "/work/dl/$UBOOT_FILE" -C u-boot --strip-components=1

cd /build/tf-a
for p in $TFA_PATCHES; do
  echo "tf-a patch $p"
  patch -p1 --batch --forward --silent < "/patches/$p"
done
# CC has to be named: an empty CROSS_COMPILE makes TF-A fall back to the
# aarch64-none-elf- prefix rather than to the native compiler, and every other
# tool in the toolchain is derived from whatever CC turns out to be.
make PLAT="$TFA_PLATFORM" CC=gcc BUILD_MESSAGE_TIMESTAMP="\"$BUILD_TIMESTAMP\"" \
    $TFA_OPTIONS -j"$(nproc)" bl31
BL31="/build/tf-a/build/$TFA_PLATFORM/release/bl31.bin"
ls -l "$BL31"

cd /build/u-boot
for p in /work/rocknix/patches/*.patch; do
  echo "u-boot patch $p"
  patch -p1 --batch --forward --silent < "$p"
done
cp /work/rocknix/configs/* configs/
export SOURCE_DATE_EPOCH
make ARCH=arm mrproper >/dev/null
make ARCH=arm "$UBOOT_DEFCONFIG" >/dev/null
make ARCH=arm BL31="$BL31" -j"$(nproc)" >/dev/null
ls -l u-boot-sunxi-with-spl.bin

cp "$BL31" /out/bl31.bin
cp u-boot-sunxi-with-spl.bin /out/u-boot-sunxi-with-spl.bin
sha256sum /out/bl31.bin /out/u-boot-sunxi-with-spl.bin
"""


def manifest(sources: Path = SOURCES) -> dict:
    return json.loads(sources.read_text())


def fetch_sources(work: Path, sources: Path = SOURCES, download=rocknix.download) -> list[str]:
    """Write the pinned ROCKNIX files into the work directory, or nothing.

    The files are ROCKNIX's patch to U-Boot's H616 DRAM driver and the
    defconfig for this board. Both decide what the bootloader is, so both are
    requested at the pinned commit and written only if their hash matches.
    """
    recorded = manifest(sources)
    repository, commit = recorded["repository"], recorded["commit"]
    written = []
    for name, entry in sorted(recorded["rocknix_files"].items()):
        content = download(repository, commit, entry["path"])
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"{name} at the pinned commit does not match its recorded hash")
        target = work / "rocknix" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written.append(name)
    return written


def verify_sources(work: Path, sources: Path = SOURCES) -> dict:
    """Refuse a work directory that is not the one the manifest describes.

    A missing, extra or altered file all change the bootloader, so all three
    are refused rather than reported: two cards that disagree about what their
    firmware is cannot be compared.
    """
    recorded = manifest(sources)
    expected = recorded["rocknix_files"]
    root = work / "rocknix"
    present = {
        str(path.relative_to(root))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    missing = sorted(set(expected) - present)
    extra = sorted(present - set(expected))
    if missing or extra:
        raise ValueError(
            f"ROCKNIX files do not match {recorded['commit'][:12]}: "
            f"{len(missing)} missing {missing[:3]}, {len(extra)} extra {extra[:3]}"
        )
    changed = [
        name
        for name, entry in sorted(expected.items())
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != entry["sha256"]
    ]
    if changed:
        raise ValueError(f"{len(changed)} ROCKNIX file(s) differ from the manifest: {changed}")
    return recorded


def patches_for(mode: str, sources: Path = SOURCES) -> list[str]:
    """Our own patches that belong in a build of this mode, in name order."""
    if mode not in SUSPEND_MODES:
        raise ValueError(f"unknown suspend mode {mode!r}")
    recorded = manifest(sources)
    return sorted(
        name
        for name, entry in recorded["our_patches"].items()
        if mode in entry["suspend"]
    )


def container_command(runner, work, patches, out, image, mode="none",
                      sources: Path = SOURCES):
    recorded = manifest(sources)
    tarballs = recorded["tarballs"]
    options = SUSPEND_MODES[mode]
    return run_in_container(
        runner,
        image,
        BUILD,
        mounts=[
            (work, "/work", False),
            (patches, "/patches", True),
            (out, "/out", False),
        ],
        environment={
            "TFA_FILE": f"tf-a-{tarballs['tf-a']['version']}.tar.gz",
            "TFA_URL": tarballs["tf-a"]["url"],
            "TFA_SHA256": tarballs["tf-a"]["sha256"],
            "UBOOT_FILE": f"u-boot-{tarballs['u-boot']['version']}.tar.gz",
            "UBOOT_URL": tarballs["u-boot"]["url"],
            "UBOOT_SHA256": tarballs["u-boot"]["sha256"],
            "TFA_PLATFORM": recorded["tf_a_platform"],
            "TFA_PATCHES": " ".join(patches_for(mode, sources)),
            "TFA_OPTIONS": " ".join(f"{k}={v}" for k, v in sorted(options.items())),
            "UBOOT_DEFCONFIG": recorded["defconfig"],
            "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
            "BUILD_TIMESTAMP": BUILD_TIMESTAMP,
        },
    )


def describe(out: Path, mode: str, sources: Path = SOURCES) -> dict:
    """What came out, so a card can be traced back to the sources it was built from."""
    recorded = manifest(sources)
    built = {}
    for name in ("bl31.bin", "u-boot-sunxi-with-spl.bin"):
        path = out / name
        built[name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {
        "suspend": mode,
        "u_boot": recorded["tarballs"]["u-boot"]["version"],
        "tf_a": recorded["tarballs"]["tf-a"]["version"],
        "rocknix_commit": recorded["commit"],
        "our_patches": {
            name: hashlib.sha256((PATCHES / name).read_bytes()).hexdigest()
            for name in patches_for(mode, sources)
        },
        "built": built,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path,
                        default=GATEWARE / "build/rg35xx-firmware-src",
                        help="Where the tarballs and the pinned ROCKNIX files live")
    parser.add_argument("--out", type=Path,
                        help="Where to put the built firmware; the default is "
                             "<work>/<suspend mode>")
    parser.add_argument("--suspend", choices=sorted(SUSPEND_MODES), default="none",
                        help="none is the upstream bootloader ROCKNIX builds; wfi "
                             "adds our PSCI SYSTEM_SUSPEND patch; wfi32 also parks "
                             "the cluster on the 32 kHz clock; sr puts DRAM into "
                             "self-refresh from a stub in SRAM; sr-gate also gates "
                             "the DRAM and MBUS clocks; sr-pll also stops PLL_DDR0")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--runner")
    parser.add_argument(
        "--fetch", action="store_true",
        help="First download the pinned ROCKNIX patch and defconfig into the "
             "work directory; each is written only if its hash matches",
    )
    parser.add_argument(
        "--allow-unpinned", action="store_true",
        help="Build from ROCKNIX files that do not match the manifest. Use when "
             "deliberately moving to a newer tree, and re-record it.",
    )
    arguments = parser.parse_args(argv)

    work = arguments.work.resolve()
    out = (arguments.out or (work / arguments.suspend)).resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / "dl").mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    if arguments.fetch:
        try:
            written = fetch_sources(work)
        except (OSError, ValueError) as failure:
            parser.error(f"fetch failed: {failure}")
        print(f"fetched {len(written)} pinned files into {work / 'rocknix'}")

    if not arguments.allow_unpinned:
        try:
            verify_sources(work)
        except (OSError, ValueError) as failure:
            parser.error(f"{failure}; --fetch downloads them")

    for name in patches_for(arguments.suspend):
        if not (PATCHES / name).is_file():
            parser.error(f"{PATCHES / name} is missing")

    command = container_command(
        find_runner(arguments.runner), work, PATCHES, out, arguments.image,
        mode=arguments.suspend,
    )
    status = run(command)
    if status:
        return status
    report = describe(out, arguments.suspend)
    (out / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

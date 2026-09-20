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

The `sr-phy` modes go further: a stub of our own, in C, compiled against
U-Boot's H616 DRAM driver from the same pinned tree the bootloader is built
from, which shuts the controller, the PHY and PLL_DDR0 down and builds them
again on the way back. That stub is GPL-2.0-or-later because the driver is, so
it lives in `firmware/stub/` and is built separately, before TF-A embeds it.

`--suspend rocknix-deep` builds none of ours. It is the implementation this work
was modelled on, kailashrs' TF-A patch and SRAM stub exactly as ROCKNIX pins
and ships them, built from source beside the same two trees: it shuts the DRAM
controller and PHY down and rebuilds them on resume, which ours does not, and
the only way to say what that is worth is to measure it on the same card.
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

# Where our own C stub lands in the container, and what each rung of it asks
# the compiler for. The stub is one program; the switches are the ladder, so
# that every step of the DRAM-side shutdown can be put on a card by itself and
# priced in milliamps. firmware/stub/src/stub.h documents each one.
OUR_STUB = "/build/ourstub/suspend_stub.bin"
OUR_STUB_MODES = {
    # Level 1 is what our assembly stub does, written in C: self-refresh and
    # nothing else. It exists to prove the SRAM C environment on its own,
    # against a register sequence that is already known to resume.
    "sr-c": "-DSTUB_LEVEL=1",
    # Level 2 is the whole DRAM side away and rebuilt on the way back.
    "sr-phy": "-DSTUB_LEVEL=2",
    # The ablations: one sub-step of level 2 left undone in each.
    "sr-phy-pllon": "-DSTUB_LEVEL=2 -DSTUB_DDR_PLL_OFF=0",
    "sr-phy-fastapb": "-DSTUB_LEVEL=2 -DSTUB_APB_32K=0 -DSTUB_CPU_32K=0",
    # And one sub-step of theirs that level 2 does not do: the DRAM pad hold,
    # whose polarity the manual and the prior art disagree about.
    "sr-phy-padhold": "-DSTUB_LEVEL=2 -DSTUB_PAD_HOLD=1",
    # Past anything the prior art does, and only because the stub's own
    # snapshot says so: PLL_VIDEO0, PLL_DE and the DE bus gate are still on at
    # the instruction before WFI, with the panel long asleep.
    "sr-phy-nodisp": "-DSTUB_LEVEL=2 -DSTUB_DISPLAY_OFF=1",
    # The same three clocks stopped, and put back after the DRAM controller
    # and its PHY have been rebuilt rather than before: one of the first three
    # sleeps of the rung above failed read calibration, and two PLLs relocking
    # while the PHY trains is the difference between it and every rung that
    # has always resumed.
    "sr-phy-nodisp-late":
        "-DSTUB_LEVEL=2 -DSTUB_DISPLAY_OFF=1 -DSTUB_DISPLAY_LATE=1",
}

# What each mode asks the two builds for. The patch list is the subset of our
# own patches to apply; an empty list is the unmodified upstream tree.
SUSPEND_MODES = {
    "none": {},
    "wfi": {"SUNXI_SYSTEM_SUSPEND": "1"},
    "wfi32": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_CPU_32K": "1"},
    "sr": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_DRAM_LEVEL": "1"},
    "sr-gate": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_DRAM_LEVEL": "2"},
    "sr-pll": {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_DRAM_LEVEL": "3"},
    **{
        mode: {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_BLOB": OUR_STUB}
        for mode in OUR_STUB_MODES
    },
    # Not ours: kailashrs' implementation exactly as ROCKNIX ships it, their
    # TF-A patch and their SRAM stub at the commit ROCKNIX pins, so that what
    # it draws can be measured beside ours on the same kernel and card.
    "rocknix-deep": {"SUNXI_SYSTEM_SUSPEND": "1",
                "SUNXI_SUSPEND_STUB": "/build/stub/suspend_stub_lpddr4.bin"},
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

cd /build/u-boot
for p in /work/rocknix/patches/*.patch; do
  echo "u-boot patch $p"
  patch -p1 --batch --forward --silent < "$p"
done
cp /work/rocknix/configs/* configs/

cd /build/tf-a
for p in $TFA_PATCHES; do
  echo "tf-a patch $p"
  patch -p1 --batch --forward --silent < "/patches/$p"
done
for p in $TFA_ROCKNIX_PATCHES; do
  echo "tf-a patch (ROCKNIX) $p"
  patch -p1 --batch --forward --silent < "/work/rocknix/tfa-patches/$p"
done

if [ -n "$OUR_STUB_DEFINES" ]; then
  # Our own stub, which compiles U-Boot's DRAM driver so that it can rebuild
  # the controller and the PHY on resume. It takes that driver from the tree
  # the bootloader is built from, patched, a few lines above; the parameter
  # block it shares with BL31 comes from the TF-A tree, patched just above
  # that. Both have to be in place before this runs, and this has to run
  # before TF-A, which embeds the result.
  rm -rf /build/ourstub
  mkdir -p /build/ourstub
  make -C /build/ourstub -f /patches/stub/Makefile SRC_DIR=/patches/stub \
      UBOOT_DIR=/build/u-boot ATF_DIR=/build/tf-a \
      DEFCONFIG="/build/u-boot/configs/$UBOOT_DEFCONFIG" \
      OUT=/build/ourstub/suspend_stub.bin CROSS_COMPILE= \
      STUB_DEFINES="$OUR_STUB_DEFINES"
  ls -l /build/ourstub/suspend_stub.bin
  cp /build/ourstub/suspend_stub.bin /out/suspend_stub.bin
fi

if [ -n "$STUB_FILE" ]; then
  # Their stub compiles U-Boot's own DRAM driver, from the tree the bootloader
  # is built from, against the header their TF-A patch adds.
  fetch "$STUB_FILE" "$STUB_URL" "$STUB_SHA256"
  rm -rf /build/stub-src /build/stub
  mkdir -p /build/stub-src /build/stub
  tar xzf "/work/dl/$STUB_FILE" -C /build/stub-src --strip-components=1
  make -C /build/stub -f /build/stub-src/Makefile SRC_DIR=/build/stub-src \
      UBOOT_DIR=/build/u-boot ATF_DIR=/build/tf-a \
      DEFCONFIG="/build/u-boot/configs/$UBOOT_DEFCONFIG" \
      OUT=suspend_stub_lpddr4.bin CROSS_COMPILE= >/dev/null
  cp /build/stub-src/suspend_stub_lpddr4.bin /build/stub/suspend_stub_lpddr4.bin
  ls -l /build/stub/suspend_stub_lpddr4.bin
  cp /build/stub/suspend_stub_lpddr4.bin /out/suspend_stub_lpddr4.bin
fi

cd /build/tf-a
# CC has to be named: an empty CROSS_COMPILE makes TF-A fall back to the
# aarch64-none-elf- prefix rather than to the native compiler, and every other
# tool in the toolchain is derived from whatever CC turns out to be.
make PLAT="$TFA_PLATFORM" CC=gcc BUILD_MESSAGE_TIMESTAMP="\"$BUILD_TIMESTAMP\"" \
    $TFA_OPTIONS -j"$(nproc)" bl31
BL31="/build/tf-a/build/$TFA_PLATFORM/release/bl31.bin"
ls -l "$BL31"

cd /build/u-boot
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


# The one mode that builds their firmware and none of ours. It is not called
# "rocknix" because the default output directory is <work>/<mode>, and
# <work>/rocknix is where the pinned ROCKNIX files live and are checked for
# strays.
THEIRS = "rocknix-deep"
ROCKNIX_TFA_PATCHES = "tfa-patches/"


def rocknix_tfa_patches_for(mode: str, sources: Path = SOURCES) -> list[str]:
    """ROCKNIX's own TF-A patches, which only the mode that builds theirs applies."""
    if mode != THEIRS:
        return []
    return sorted(
        name[len(ROCKNIX_TFA_PATCHES):]
        for name in manifest(sources)["rocknix_files"]
        if name.startswith(ROCKNIX_TFA_PATCHES)
    )


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


def _our_stub_environment(mode: str) -> dict:
    """The compiler switches that make this build's stub the rung it is."""
    return {"OUR_STUB_DEFINES": OUR_STUB_MODES.get(mode, "")}


def _stub_environment(mode: str, tarballs: dict) -> dict:
    """Where their stub comes from, or blanks for every mode that has no use for it."""
    if mode != THEIRS:
        return {"STUB_FILE": "", "STUB_URL": "", "STUB_SHA256": ""}
    stub = tarballs["suspend-stub"]
    return {
        "STUB_FILE": f"h700-suspend-stub-{stub['version'][:12]}.tar.gz",
        "STUB_URL": stub["url"],
        "STUB_SHA256": stub["sha256"],
    }


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
            "TFA_ROCKNIX_PATCHES": " ".join(rocknix_tfa_patches_for(mode, sources)),
            **_stub_environment(mode, tarballs),
            **_our_stub_environment(mode),
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
    names = ["bl31.bin", "u-boot-sunxi-with-spl.bin"]
    if mode in OUR_STUB_MODES:
        names.append("suspend_stub.bin")
    for name in names:
        path = out / name
        built[name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {
        "suspend": mode,
        "our_stub_defines": OUR_STUB_MODES.get(mode),
        "u_boot": recorded["tarballs"]["u-boot"]["version"],
        "tf_a": recorded["tarballs"]["tf-a"]["version"],
        "rocknix_commit": recorded["commit"],
        "rocknix_tfa_patches": rocknix_tfa_patches_for(mode, sources),
        "suspend_stub": recorded["tarballs"]["suspend-stub"]["version"] if mode == THEIRS else None,
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
                             "the DRAM and MBUS clocks; sr-pll also stops PLL_DDR0; "
                             "sr-c is sr again from our C stub; sr-phy is that stub "
                             "shutting the controller, PHY and PLL_DDR0 down and "
                             "rebuilding them on resume, and the sr-phy-* modes are "
                             "its ablations; rocknix-deep is not ours: ROCKNIX's own "
                             "TF-A patch and SRAM stub, for measuring theirs beside ours")
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

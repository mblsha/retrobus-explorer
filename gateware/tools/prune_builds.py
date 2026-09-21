#!/usr/bin/env python3
"""List the bitstream experiments under gateware/build/ and prune them.

A routed Arty build leaves about a gigabyte behind and a qualification campaign
leaves thirty of them, so the tree grows to tens of gigabytes of near-identical
netlists with nothing on the outside saying which one is the card that
currently works. What tells them apart is inside: result.json records the
bitstream's sha256, the placement seed it was routed with, and the options it
was configured from. This prints that as a table, largest first, and removes
the directories you do not name.

By default only a finished bitstream experiment is a candidate. The openxc7
toolchain and the pinned LiteX interpreter live in the same directory; they
take hours to reproduce and cannot be rebuilt from this repository at all. They
are refused by name and by pattern, and no option overrides that: --keep
chooses among the experiments, it never widens what may be deleted.

The `rg35xx-*` pattern is kept although the kernel trees and card images it
named now build in the `linux-consoles` repository instead. Protecting a name
that is not here costs nothing, and a directory left behind by an older
checkout would still be hours of work to reproduce.

A directory whose result.json is missing or unreadable is also refused by
default, because a directory that cannot say what it is has not earned a
deletion. Most of those are exactly the junk worth removing, though: build_ddr
deletes the previous manifest when a build starts and only publishes a new one
when the build succeeds, so every placement that missed timing leaves a
gigabyte with no manifest. --include-unfinished admits them, and only them: a
directory qualifies by holding board.v, the first file a bitstream build writes,
which nothing else in this tree contains.

Nothing is removed without --delete. The default run prints the plan, and
--delete re-checks every rule against the directory it is about to remove
rather than trusting the listing it just printed. Before a finished experiment
is removed its result.json is copied to pruned-manifests/, so the seed and the
options needed to build it again outlive the netlists.
"""

import argparse
import json
import shutil
from fnmatch import fnmatch
from pathlib import Path
from typing import NamedTuple

GATEWARE = Path(__file__).resolve().parents[1]

# Not bitstream experiments, and expensive or impossible to rebuild.
ARCHIVE = "pruned-manifests"
UNFINISHED_MARKER = "board.v"
PROTECTED_NAMES = frozenset({"openxc7-macos", "litedram-py311", ARCHIVE})
PROTECTED_GLOBS = ("rg35xx-*",)


def is_protected(directory: Path) -> bool:
    """Whether a name marks something other than a bitstream experiment."""
    return directory.name in PROTECTED_NAMES or any(
        fnmatch(directory.name, glob) for glob in PROTECTED_GLOBS
    )


def read_manifest(directory: Path):
    """Return a directory's result.json, or None if it does not have a usable one.

    build_ddr.py writes result.json last and atomically, so its presence is the
    build's own statement that it finished. A missing or damaged one means this
    tool cannot say what the directory holds, which is reason enough to keep it.
    """
    try:
        manifest = json.loads((directory / "result.json").read_text())
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def is_unfinished_build(directory: Path) -> bool:
    """Whether a directory without a manifest is nonetheless a bitstream build."""
    return (directory / UNFINISHED_MARKER).is_file()


def deletable(directory: Path, root: Path, include_unfinished: bool = False) -> bool:
    """Whether this tool may ever remove `directory`.

    Consulted when the plan is printed and again immediately before each
    deletion, so a directory that changed in between is skipped rather than
    removed on the strength of a stale listing.
    """
    if not (
        directory.is_dir()
        and not directory.is_symlink()
        and directory.parent == root
        and not is_protected(directory)
    ):
        return False
    if read_manifest(directory) is not None:
        return True
    return include_unfinished and is_unfinished_build(directory)


def directory_size(directory: Path) -> int:
    """Bytes the directory's own files occupy, not counting symlinked targets."""
    return sum(
        entry.stat().st_size
        for entry in directory.rglob("*")
        if not entry.is_symlink() and entry.is_file()
    )


class Experiment(NamedTuple):
    path: Path
    manifest: dict | None  # None for a build that never published one
    size: int

    @property
    def name(self) -> str:
        return self.path.name


def experiments(root: Path, include_unfinished: bool = False) -> list[Experiment]:
    """Every bitstream experiment directly under `root`, largest first."""
    root = root.resolve()
    found = [
        Experiment(directory, read_manifest(directory), directory_size(directory))
        for directory in sorted(root.iterdir() if root.is_dir() else [])
        if deletable(directory, root, include_unfinished)
    ]
    return sorted(found, key=lambda experiment: -experiment.size)


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def megahertz(manifest: dict, field: str) -> str:
    hertz = manifest.get(field)
    return f"{hertz / 1_000_000:g}" if isinstance(hertz, int) else "-"


HEADINGS = (
    "ACTION",
    "DIRECTORY",
    "BITSTREAM",
    "SEED",
    "PROFILE",
    "H700",
    "IO MHz",
    "CARD MHz",
    "SIZE",
)


def row(experiment: Experiment, keep: set) -> tuple:
    manifest = experiment.manifest or {}
    h700 = manifest.get("h700_mmc")
    return (
        "keep" if experiment.name in keep else "prune",
        experiment.name,
        "unfinished"
        if experiment.manifest is None
        else str(manifest.get("bitstream_sha256", "-"))[:12],
        str(manifest.get("placement_seed", "-")),
        str(manifest.get("profile") or "-"),
        "-" if h700 is None else ("yes" if h700 else "no"),
        megahertz(manifest, "sd_io_clock_hz"),
        megahertz(manifest, "sd_max_clock_hz"),
        human(experiment.size),
    )


def render_table(rows) -> str:
    lines = [HEADINGS, *rows]
    widths = [max(len(line[column]) for line in lines) for column in range(len(HEADINGS))]
    return "\n".join(
        "  ".join(value.ljust(width) for value, width in zip(line, widths)).rstrip()
        for line in lines
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--build-root",
        type=Path,
        default=GATEWARE / "build",
        help="Directory holding the build experiments (default: gateware/build)",
    )
    parser.add_argument(
        "--keep",
        metavar="NAME",
        action="extend",
        nargs="+",
        default=[],
        help="Experiment directories to retain; everything else is pruned",
    )
    parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Also prune builds that failed or were interrupted: directories "
        f"holding {UNFINISHED_MARKER} but no readable result.json",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually remove the directories instead of printing the plan",
    )
    args = parser.parse_args(argv)
    if not args.keep:
        parser.error(
            "--keep must name at least one directory to retain; this tool will "
            "not decide on its own which build is the current one"
        )
    root = args.build_root.resolve()
    missing = sorted({name for name in args.keep if not (root / name).is_dir()})
    if missing:
        parser.error(
            f"--keep names nothing in {root}: {', '.join(missing)}. A mistyped "
            "name would delete the build it was meant to save"
        )

    keep = set(args.keep)
    found = experiments(root, args.include_unfinished)
    if not found:
        print(f"No bitstream experiments under {root}.")
        return 0
    print(render_table(row(experiment, keep) for experiment in found))

    doomed = [experiment for experiment in found if experiment.name not in keep]
    total = sum(experiment.size for experiment in doomed)
    if not doomed:
        print(f"\nNothing to prune; all {len(found)} experiments were kept.")
        return 0
    print(
        f"\n{'Deleting' if args.delete else 'Would delete'} {len(doomed)} "
        f"of {len(found)} experiments, {total} bytes ({human(total)}):"
    )
    for experiment in doomed:
        print(f"  {experiment.name}")
    if not args.delete:
        print("\nNothing was removed. Re-run with --delete to remove them.")
        return 0

    freed = 0
    for experiment in doomed:
        if not deletable(experiment.path, root, args.include_unfinished):
            print(f"  skipped {experiment.name}: no longer a bitstream experiment")
            continue
        if experiment.manifest is not None:
            archive = root / ARCHIVE
            archive.mkdir(exist_ok=True)
            shutil.copy2(experiment.path / "result.json", archive / f"{experiment.name}.json")
        shutil.rmtree(experiment.path)
        freed += experiment.size
    print(f"\nFreed {freed} bytes ({human(freed)}).")
    print(f"Manifests of the finished experiments removed are in {root / ARCHIVE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

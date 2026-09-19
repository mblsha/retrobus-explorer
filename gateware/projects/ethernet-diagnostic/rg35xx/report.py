#!/usr/bin/env python3
"""Reduce a set of cold-start trials to the one number that compares them.

The target has no console, so reaching userspace is observed as a write to the
debug partition and nothing else. U-Boot writes one sector per milestone;
every write Linux makes goes through the page cache and is at least a page, so
a run has reached userspace at the first row where either the multi-block
write command is caught in the act or the sector counter has already moved by
a page. A run whose zero was never established is not comparable to one whose
zero was, so it is skipped rather than reported optimistically.

Every boot figure quoted in the notes comes from here, so that no two readings
of the same trial can disagree.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

# CMD25 is the multi-block write; U-Boot's milestones are single-block CMD24.
MULTI_BLOCK_WRITE = 25
# One page of the target's 4 KiB pages, in card sectors.
PAGE_SECTORS = 8


def userspace_time(run: dict) -> float | None:
    """Return when this run reached userspace, or None if it did not."""
    if not run.get("zero_is_sound"):
        return None
    timeline = run.get("timeline") or []
    if not timeline:
        return None
    baseline = timeline[0]["writes"]
    for row in timeline:
        # The baseline row sits at or before the zero and carries the counters
        # the run started from, so it can never be the milestone itself.
        if row["elapsed"] <= 0:
            continue
        if (
            row["last_command"] == MULTI_BLOCK_WRITE
            or row["writes"] - baseline >= PAGE_SECTORS
        ):
            return row["elapsed"]
    return None


def summarize(runs) -> dict:
    """Describe a set of runs by the spread of their userspace times.

    The spread is the finding, not the median: the same image booted twice
    differs by seconds on this bench, so a comparison between two builds is
    only meaningful against the variation within each of them.
    """
    runs = list(runs)
    values = sorted(
        value for value in (userspace_time(run) for run in runs) if value is not None
    )
    if not values:
        return {
            "runs": len(runs), "n": 0, "median": None, "min": None, "max": None,
            "stdev": None, "iqr": None, "values": [],
        }
    quartiles = (
        statistics.quantiles(values, n=4)
        if len(values) > 3
        else [values[0], statistics.median(values), values[-1]]
    )
    return {
        "runs": len(runs),
        "n": len(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else None,
        "iqr": quartiles[2] - quartiles[0],
        "values": values,
    }


def load(pattern: str) -> list[dict]:
    """Read every trial JSON a glob names, in a stable order.

    Only the shape `trial.py` writes today is read. Trials recorded before it
    carried the timeline alone, with no record of whether the run's zero was
    sound, so a number taken from one of those is not the same measurement and
    is refused rather than silently mixed in.
    """
    runs = []
    for path in sorted(glob.glob(pattern)):
        run = json.loads(Path(path).read_text())
        if not isinstance(run, dict):
            raise ValueError(f"{path} predates the trial format this reads")
        runs.append(run)
    return runs


def format_summary(label: str, summary: dict) -> list[str]:
    if not summary["n"]:
        return [f"{label:30s} no sound runs"]
    line = (
        f"{label:30s} n={summary['n']:2d}/{summary['runs']:<2d} "
        f"median {summary['median']:5.2f}  min {summary['min']:5.2f}  "
        f"max {summary['max']:5.2f}  "
    )
    if summary["stdev"] is not None:
        line += f"stdev {summary['stdev']:4.2f}  "
    return [
        line + f"IQR {summary['iqr']:4.2f}",
        f"{'':30s} {[round(value, 2) for value in summary['values']]}",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "distribution", nargs="+", metavar="LABEL=GLOB",
        help="A label and the trial JSON files it covers, e.g. erofs='ero-*.json'",
    )
    arguments = parser.parse_args()
    for entry in arguments.distribution:
        label, separator, pattern = entry.partition("=")
        if not separator:
            parser.error(f"{entry} is not LABEL=GLOB")
        for line in format_summary(label, summarize(load(pattern))):
            print(line)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run every microSD Spade/Cocotb and host check; no hardware access."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

GATEWARE = Path(__file__).resolve().parents[1]
CASES = [
    ("microsd-pin-tester", "probe_core", "test_probe"),
    ("microsd-pin-tester", "probe_uart", "test_uart"),
    ("microsd-emulator", "sd_frontend", "test_sd"),
    ("microsd-emulator", "sd_frontend", "test_sd_write"),
    ("microsd-emulator", "sd_frontend", "test_sd_write_busy"),
    ("microsd-emulator", "bram_backend", "test_storage"),
    ("microsd-emulator", "ddr_backend", "test_ddr"),
    ("microsd-emulator", "ddr_byte_writer", "test_byte_writer"),
    ("microsd-emulator", "native_bist", "test_native_bist"),
    ("microsd-emulator", "sd_clock_meter", "test_clock_meter"),
    ("microsd-emulator", "qualified_ddr", "test_qualified_ddr"),
    ("microsd-emulator", "image_loader", "test_loader"),
    ("microsd-emulator", "bram_emulator", "test_integration"),
    ("microsd-emulator", "ddr_emulator", "test_ddr_integration"),
    ("microsd-emulator", "ddr_emulator", "test_ddr_rw"),
    ("microsd-emulator", "ddr_emulator", "test_ddr_ownership"),
    ("microsd-emulator", "emulator_uart", "test_emulator_uart"),
    ("microsd-emulator", "native_cdc", "test_native_cdc"),
    ("microsd-emulator", "native_stage", "test_native_stage"),
    ("microsd-emulator", "ddr_uart", "test_ddr_uart"),
    ("microsd-emulator", "ddr_uart_80", "test_ddr_uart"),
    ("microsd-emulator", "ddr_uart_100", "test_ddr_uart"),
    ("microsd-emulator", "ddr_emulator_cdc", "test_ddr_rw"),
    ("microsd-emulator", "sd_write_receiver", "test_write_rx"),
    ("microsd-emulator", "sd_write_response", "test_write_response"),
    ("microsd-emulator", "ddr_sector_writer", "test_sector_writer"),
    ("microsd-emulator", "sd_write_transaction", "test_write_transaction"),
]
# `--fast-sd` replaces the profile rather than adding one, so CI exercised the
# native write path only at 25 MHz with the prepared output registers, and a
# default-profile regression in that path survived twenty commits unnoticed.
# These two cases run in both profiles. That costs about nine more minutes and
# covers the 1 MHz card clock, the slow command and data launch edges, and the
# H700/MMC cases the fast profile cannot build. The `test_ddr_rw` suites stay
# fast-only: ten to fifteen minutes each for the write path `test_sd_write`
# already covers here in three. Under `--extra-only` the default-profile
# `test_sd` run is the registry's own microsd-emulator run, so it is not
# repeated here; the registry runs in CI's environment, which sets no knob.
BOTH_PROFILES = {
    ("sd_frontend", "test_sd"),
    ("sd_frontend", "test_sd_write"),
}


def fast_profile(top):
    """The 100 MHz / 25 MHz SD path and 100-to-80 MHz CDC overrides."""
    env = dict(
        MICROSD_SYS_PERIOD_NS="12.5",
        MICROSD_FAST_MODE="0",
        MICROSD_HALF_NS="41",
    )
    if top in ("sd_frontend", "ddr_emulator", "ddr_emulator_cdc"):
        env.update(
            MICROSD_SYS_PERIOD_NS="10",
            MICROSD_FAST_MODE="1",
            MICROSD_HALF_NS="19.9",
            MICROSD_CLOCK_JITTER="0",
            MICROSD_SAMPLE_ADVANCE_NS="8",
        )
    if top == "native_cdc":
        env.update(MICROSD_CDC_SRC_NS="10", MICROSD_CDC_DST_NS="12.5")
    return env


def planned_runs(extra_only=False, fast_sd=False):
    """Every (name, project, top, module, overrides) the options select.

    ``overrides`` is None for the default profile, which removes every
    ``MICROSD_*`` knob the caller exported instead of layering over them.
    """
    runs = []
    for project, top, module in CASES:
        if extra_only and module == "test_probe":
            continue
        profiles = [("", fast_profile(top) if fast_sd else {})]
        if fast_sd and (top, module) in BOTH_PROFILES:
            profiles.append(("-default", None))
        for suffix, overrides in profiles:
            # The registry already runs microsd-emulator's own default top,
            # sd_frontend/test_sd, in the default profile. With --fast-sd the
            # first profile here is a different one and stays.
            if extra_only and module == "test_sd" and (overrides is None or not fast_sd):
                continue
            runs.append((f"{top}-{module}{suffix}", project, top, module, overrides))
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extra-only",
        action="store_true",
        help="CI: skip the two default project tops already tested by the registry",
    )
    parser.add_argument(
        "--fast-sd",
        action="store_true",
        help="Test the 100 MHz / 25 MHz SD path and 100-to-80 MHz CDC",
    )
    parser.add_argument(
        "--list-cases", action="store_true", help="Print the selected case names and exit"
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Run only this selected case (repeatable); skips the host checks",
    )
    args = parser.parse_args()
    runs = planned_runs(args.extra_only, args.fast_sd)
    if args.list_cases:
        for name, *_ in runs:
            print(name)
        return
    if args.case:
        unknown = sorted(set(args.case) - {name for name, *_ in runs})
        if unknown:
            parser.error(f"unknown or unselected case: {', '.join(unknown)}")
        runs = [run for run in runs if run[0] in args.case]
    out = GATEWARE / "build/microsd-tests"
    out.mkdir(parents=True, exist_ok=True)
    host_checks = () if args.case else (
        [sys.executable, "tools/project_inventory.py", "--check"],
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tools",
            "-p",
            "test_microsd*.py",
        ],
    )
    for command in host_checks:
        subprocess.run(command, cwd=GATEWARE, check=True)
    for name, project, top, module, overrides in runs:
        if overrides is None:
            env = {k: v for k, v in os.environ.items() if not k.startswith("MICROSD_")}
        else:
            env = dict(os.environ)
            env.update(overrides)
        print(f"Testing {project}: {top} ({name.removeprefix(top + '-')})", flush=True)
        (out / f"{name}-parameters.json").write_text(
            json.dumps(
                {k: v for k, v in env.items() if k.startswith("MICROSD_")}, indent=2
            )
            + "\n"
        )
        with (out / f"{name}.log").open("w") as log:
            subprocess.run(
                [
                    sys.executable,
                    "tools/run_tb.py",
                    "--project",
                    f"projects/{project}",
                    "--top",
                    top,
                    "--test-module",
                    module,
                ],
                cwd=GATEWARE,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        (out / f"{name}.xml").write_bytes(
            (GATEWARE / f"projects/{project}/test/results.xml").read_bytes()
        )
    print("All microSD tests passed.", flush=True)


if __name__ == "__main__":
    main()

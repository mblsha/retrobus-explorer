#!/usr/bin/env python3
"""Split the Spade testbenches into parallel CI jobs, and run one job's share.

`matrix` prints the GitHub Actions matrix; `run` executes the units a matrix
entry names. A unit is a registered project, one microSD suite case, the
application characterization benches, or the shared-component benches. Long
projects whose tests are independent split into shards, each run with
Cocotb's TESTCASE list; every shard checks that exactly its tests ran.

Short units are packed together so the matrix stays small. The weights below
only balance the jobs: a stale one makes CI slower, never less complete,
because every unit appears in exactly one job whatever the weights say.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

GATEWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATEWARE / "tools"))

import project_inventory  # noqa: E402
import test_microsd_suite  # noqa: E402

MICROSD_SUITE_ARGS = ("--extra-only", "--fast-sd")

# Pack units shorter than this into shared jobs of up to this many minutes,
# kept below the longest unsplittable unit (microsd-emulator, ~11 min).
BUNDLE_MINUTES = 9.0
DEFAULT_UNIT_MINUTES = 1.0
DEFAULT_TEST_SECONDS = 15.0

# Minutes per unit on ubuntu-latest, from run 36794434650 (2026-10-01),
# including the Spade and Verilator builds.
UNIT_MINUTES = {
    "project:projects/microsd-pin-tester": 0.5,
    "project:projects/ft-uart-hex-bridge": 1.7,
    "project:projects/pin-tester": 0.3,
    "project:projects/sharp-organizer-card": 6.5,
    "project:projects/sharp-pc-g850-bus": 11.3,
    "project:projects/sharp-pc-g850-streaming-rom": 0.4,
    "project:projects/test-minimal": 0.2,
    "project:projects/uart-saleae-loopback": 1.8,
    "project:projects/binary-counter": 0.4,
    "project:projects/ws2812b": 0.2,
    "project:projects/microsd-emulator": 10.8,
    "project:projects/ethernet-diagnostic": 6.0,
    "microsd:probe_uart-test_uart": 0.5,
    "microsd:sd_frontend-test_sd": 1.2,
    "microsd:sd_frontend-test_sd_write": 1.1,
    "microsd:sd_frontend-test_sd_write-default": 8.6,
    "microsd:sd_frontend-test_sd_write_busy": 0.6,
    "microsd:image_loader-test_loader": 1.4,
    "microsd:bram_emulator-test_integration": 0.9,
    "microsd:ddr_emulator-test_ddr_integration": 2.2,
    "microsd:ddr_emulator-test_ddr_rw": 4.4,
    "microsd:ddr_emulator-test_ddr_ownership": 2.2,
    "microsd:emulator_uart-test_emulator_uart": 1.2,
    "microsd:ddr_uart-test_ddr_uart": 3.6,
    "microsd:ddr_uart_80-test_ddr_uart": 3.4,
    "microsd:ddr_uart_100-test_ddr_uart": 4.1,
    "microsd:ddr_emulator_cdc-test_ddr_rw": 7.0,
    "characterization": 0.4,
    "shared-components": 3.5,
}

# Projects split across this many jobs. Their test modules must be plain
# decorated tests (see discover_tests); the build is repeated in every shard.
PROJECT_SHARDS = {
    "projects/sharp-pc-e500-card": 3,
    "projects/sharp-pc-g850-bus": 2,
}

# Seconds per test on ubuntu-latest, for the sharded projects' slow tests.
TEST_SECONDS = {
    "usb_uart_write_collisions_return_busy_and_do_not_commit_uart_write": 241,
    "usb_uart_read_collisions_return_busy": 320,
    "ft_stream_overflow_is_reported_in_measurement_results": 198,
    "ft_status_reports_source_mask_and_effective_capture_state": 72,
    "ft_status_tracks_uart_session_overflow_separately_from_total": 384,
    "measurement_reports_can_be_dumped_and_cleared": 44,
    "measurement_dump_preserves_fifo_order_for_multiple_reports": 36,
    "uart_help_and_status_commands_report_state": 164,
    "uart_unknown_command_prints_help": 148,
    "uart_map_command_reports_saleae_pin_meanings": 188,
}


def project_test_module(project: str, root: Path = GATEWARE) -> Path:
    config = tomllib.loads((root / project / "swim.toml").read_text())
    module = config.get("tooling", {}).get("test_module")
    if not module:
        raise ValueError(f"{project} has no [tooling].test_module to shard")
    return root / project / "test" / f"{module}.py"


def _is_cocotb_test(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(target) == "cocotb.test"


def discover_tests(path: Path) -> list[str]:
    """Names Cocotb would run from a module of decorated tests, in file order.

    Refuses anything a static reading could get wrong: generated tests, and a
    `skip` that is not a literal. TESTCASE runs a named test even if skipped,
    so a literally skipped test is left out rather than named.
    """
    source = path.read_text()
    if "TestFactory" in source:
        raise ValueError(f"{path.name}: generated tests cannot be sharded statically")
    names = []
    decorated = 0
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        tests = [d for d in node.decorator_list if _is_cocotb_test(d)]
        if not tests:
            continue
        decorated += 1
        skip = None
        if isinstance(tests[0], ast.Call):
            for keyword in tests[0].keywords:
                if keyword.arg == "skip":
                    skip = keyword.value
        if skip is not None:
            if not isinstance(skip, ast.Constant) or not isinstance(skip.value, bool):
                raise ValueError(f"{path.name}: {node.name} has a computed skip")
            if skip.value:
                continue
        names.append(node.name)
    if source.count("cocotb.test") != decorated:
        raise ValueError(f"{path.name}: cocotb.test is used other than as a top-level decorator")
    if not names:
        raise ValueError(f"{path.name}: no tests found")
    return names


def shard_tests(names: list[str], shards: int) -> list[list[str]]:
    """Longest-first assignment to the lightest shard; each name once."""
    bins: list[tuple[float, list[str]]] = [(0.0, []) for _ in range(shards)]
    for name in sorted(names, key=lambda n: (-TEST_SECONDS.get(n, DEFAULT_TEST_SECONDS), n)):
        index = min(range(shards), key=lambda i: bins[i][0])
        weight, members = bins[index]
        bins[index] = (weight + TEST_SECONDS.get(name, DEFAULT_TEST_SECONDS), members + [name])
    order = {name: i for i, name in enumerate(names)}
    return [sorted(members, key=order.__getitem__) for _, members in bins if members]


def units(root: Path = GATEWARE) -> list[tuple[str, float]]:
    """Every unit with its expected minutes; shards are `unit@k/n`."""
    result = [("characterization", UNIT_MINUTES["characterization"])]
    for path in project_inventory.ci_project_paths(root):
        project = Path(path).resolve().relative_to(root.resolve()).as_posix()
        unit = f"project:{project}"
        shards = PROJECT_SHARDS.get(project)
        if not shards:
            result.append((unit, UNIT_MINUTES.get(unit, DEFAULT_UNIT_MINUTES)))
            continue
        groups = shard_tests(discover_tests(project_test_module(project, root)), shards)
        for index, group in enumerate(groups, start=1):
            seconds = sum(TEST_SECONDS.get(name, DEFAULT_TEST_SECONDS) for name in group)
            result.append((f"{unit}@{index}/{len(groups)}", 1.5 + seconds / 60))
    for name, *_ in test_microsd_suite.planned_runs(extra_only=True, fast_sd=True):
        unit = f"microsd:{name}"
        result.append((unit, UNIT_MINUTES.get(unit, DEFAULT_UNIT_MINUTES)))
    result.append(("shared-components", UNIT_MINUTES["shared-components"]))
    return result


def plan(root: Path = GATEWARE) -> list[list[str]]:
    """Jobs, longest first: long units alone, short ones packed together."""
    jobs: list[tuple[float, list[str]]] = []
    bundles: list[tuple[float, list[str]]] = []
    for unit, minutes in sorted(units(root), key=lambda item: -item[1]):
        if minutes >= BUNDLE_MINUTES:
            jobs.append((minutes, [unit]))
            continue
        for index, (total, members) in enumerate(bundles):
            if total + minutes <= BUNDLE_MINUTES:
                bundles[index] = (total + minutes, members + [unit])
                break
        else:
            bundles.append((minutes, [unit]))
    jobs.extend(bundles)
    jobs.sort(key=lambda job: -job[0])
    return [members for _, members in jobs]


def label(members: list[str]) -> str:
    first = members[0].split(":", 1)[-1].removeprefix("projects/")
    return first if len(members) == 1 else f"{first} +{len(members) - 1}"


def matrix(root: Path = GATEWARE) -> dict:
    return {
        "include": [
            {"id": f"{index:02d}", "label": label(members), "units": " ".join(members)}
            for index, members in enumerate(plan(root), start=1)
        ]
    }


def _project_shard(unit: str) -> tuple[str, list[str] | None]:
    path, _, shard = unit.removeprefix("project:").partition("@")
    if not shard:
        return path, None
    index, count = (int(part) for part in shard.split("/"))
    groups = shard_tests(discover_tests(project_test_module(path)), PROJECT_SHARDS[path])
    if count != len(groups):
        raise ValueError(f"{unit}: the project now has {len(groups)} shards")
    return path, groups[index - 1]


def _ran_tests(results: Path) -> list[str]:
    return [case.get("name") for case in ET.parse(results).getroot().iter("testcase")]


def run_unit(unit: str) -> None:
    python = sys.executable
    if unit == "characterization":
        for project, top, module in (
            ("projects/sharp-organizer-card", "tb_trace_events", "test_trace_events"),
            ("projects/sharp-pc-g850-bus", "tb_bus_debug", "test_bus_debug"),
        ):
            subprocess.run(
                [python, "tools/run_tb.py", "--project", project, "--top", top,
                 "--test-module", module, "--build-dir", f"build/{top}_cocotb"],
                cwd=GATEWARE, check=True,
            )
            short = module.removeprefix("test_")
            results = GATEWARE / project / "test"
            (results / f"{short}.results.xml").write_bytes((results / "results.xml").read_bytes())
    elif unit == "shared-components":
        subprocess.run([python, "lib/shared-components/scripts/test_all_components.py"],
                       cwd=GATEWARE, check=True)
    elif unit.startswith("microsd:"):
        subprocess.run(
            [python, "tools/test_microsd_suite.py", *MICROSD_SUITE_ARGS,
             "--case", unit.removeprefix("microsd:")],
            cwd=GATEWARE, check=True,
        )
    elif unit.startswith("project:"):
        path, tests = _project_shard(unit)
        env = dict(os.environ)
        env.pop("TESTCASE", None)
        if tests:
            env["TESTCASE"] = ",".join(tests)
        subprocess.run([python, f"{path}/scripts/test_with_vcd.py"], cwd=GATEWARE, env=env, check=True)
        if tests:
            ran = _ran_tests(GATEWARE / path / "test/results.xml")
            if sorted(ran) != sorted(tests):
                raise RuntimeError(f"{unit} ran {sorted(ran)}, expected {sorted(tests)}")
    else:
        raise ValueError(f"unknown unit: {unit}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("matrix", help="Print the GitHub Actions matrix as JSON")
    run = commands.add_parser("run", help="Run units, continuing past failures")
    run.add_argument("units", nargs="+")
    args = parser.parse_args()
    if args.command == "matrix":
        print(json.dumps(matrix()))
        return 0
    failed, timings = [], []
    for unit in args.units:
        print(f"::group::{unit}", flush=True)
        started = time.monotonic()
        try:
            run_unit(unit)
        except (subprocess.CalledProcessError, RuntimeError, ValueError) as error:
            failed.append(unit)
            print(f"::error::{unit}: {error}", flush=True)
        timings.append((unit, time.monotonic() - started))
        print("::endgroup::", flush=True)
    # Paste these into UNIT_MINUTES / TEST_SECONDS when the balance drifts.
    for unit, seconds in timings:
        print(f"{seconds / 60:6.1f} min  {'FAIL' if unit in failed else 'ok  '}  {unit}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

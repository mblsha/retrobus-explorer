#!/usr/bin/env python3
"""Route placement seeds against an already synthesized netlist.

`build_ddr.py` routes exactly one seed and rejects the build if that placement
misses a constraint. Re-synthesizing to try another seed costs about ten
minutes, while routing the existing netlist costs about ninety seconds, so this
searches seeds against a finished build directory and reports which ones meet
every clock and SD output-delay bound. Feed the winner back to `build_ddr.py
--seed` to produce the verified artifact.
"""

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from pathlib import Path

GATEWARE = Path(__file__).resolve().parents[1]
EXPERIMENTS = GATEWARE / "experiments/openxc7-macos"
CLOCK_LINE = re.compile(
    r"Max frequency for clock\s+'([^']+)': ([0-9.]+) MHz \((PASS|FAIL) at ([0-9.]+) MHz\)"
)


def parse_clocks(text: str) -> dict[str, tuple[float, str, float]]:
    """Return the final reported result per clock.

    nextpnr prints an estimate before routing and the real figure after it, so
    later lines replace earlier ones, exactly as build_ddr.py reads them.
    """
    clocks: dict[str, tuple[float, str, float]] = {}
    for name, achieved, verdict, target in CLOCK_LINE.findall(text):
        clocks[name] = (float(achieved), verdict, float(target))
    return clocks


def failing_clocks(clocks: dict[str, tuple[float, str, float]]) -> list[str]:
    return sorted(name for name, result in clocks.items() if result[1] == "FAIL")


def route(output: Path, toolchain: Path, seed: int, device: str) -> Path:
    log = output / f"route-seed-{seed}.log"
    if log.exists():
        return log
    environment = dict(os.environ)
    if "DYLD_LIBRARY_PATH" not in environment:
        raise RuntimeError(
            "nextpnr needs DYLD_LIBRARY_PATH for its pinned Boost; macOS strips "
            "it through `uv run`, so invoke this with ./.venv/bin/python"
        )
    with log.open("w") as stream:
        subprocess.run(
            [
                str(toolchain / "bin/nextpnr-xilinx"),
                "--chipdb", str(toolchain / f"share/nextpnr/{device}.bin"),
                "--xdc", "board.xdc",
                "--json", "design.json",
                "--write", f"routed-seed-{seed}.json",
                "--fasm", f"design-seed-{seed}.fasm",
                "--sdf", f"routed-seed-{seed}.sdf",
                "--freq", "100",
                "--seed", str(seed),
            ],
            cwd=output,
            env=environment,
            stdout=stream,
            stderr=stream,
            check=False,
        )
    return log


def evaluate(output: Path, seed: int, **profile) -> dict[str, object]:
    """Judge one routed seed the way `build_ddr.py` would for this profile."""
    sys.path.insert(0, str(EXPERIMENTS))
    from ddr_output_timing import verify_profile_outputs

    log = output / f"route-seed-{seed}.log"
    clocks = parse_clocks(log.read_text())
    if not clocks:
        return {"seed": seed, "usable": False, "reason": "no timing results"}
    failed = failing_clocks(clocks)
    if failed:
        return {"seed": seed, "usable": False, "reason": f"clocks {failed}",
                "clocks": {k: v[0] for k, v in clocks.items()}}
    routed = output / f"routed-seed-{seed}.json"
    sdf = output / f"routed-seed-{seed}.sdf"
    try:
        paths = verify_profile_outputs(routed, sdf, **profile)
    except Exception as failure:  # the checker raises with the offending pin
        return {"seed": seed, "usable": False, "reason": f"output delay {failure}",
                "clocks": {k: v[0] for k, v in clocks.items()}}
    return {
        "seed": seed,
        "usable": True,
        "clocks": {k: v[0] for k, v in clocks.items()},
        "outputs_ps": {p["signal"]: p["route_delay_ps"] for p in paths},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Build directory holding design.json and board.xdc")
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--toolchain", type=Path,
                        default=GATEWARE / "build/openxc7-macos")
    parser.add_argument("--device", default="xc7a35tcsg324")
    # The output-edge rules depend on the profile, so these mirror the
    # build_ddr.py flags the netlist was synthesized with; pass the same ones.
    parser.add_argument("--slow-mmc", action="store_true",
                        help="The netlist was built with --slow-mmc")
    parser.add_argument("--h700-mmc", action="store_true",
                        help="The netlist was built with --h700-mmc")
    parser.add_argument("--mmc-only", action="store_true",
                        help="The netlist was built with --mmc-only")
    parser.add_argument("--jobs", type=int, default=4)
    arguments = parser.parse_args()
    if not (arguments.output / "design.json").exists():
        parser.error(f"{arguments.output} has no synthesized design.json")

    with concurrent.futures.ThreadPoolExecutor(arguments.jobs) as pool:
        list(pool.map(
            lambda seed: route(
                arguments.output, arguments.toolchain, seed, arguments.device
            ),
            arguments.seeds,
        ))
    profile = {
        # build_ddr.py refuses the legacy-MMC profiles without --slow-mmc.
        "slow_mmc": arguments.slow_mmc or arguments.h700_mmc or arguments.mmc_only,
        "h700_mmc": arguments.h700_mmc,
        "mmc_only": arguments.mmc_only,
    }
    results = [evaluate(arguments.output, seed, **profile)
               for seed in arguments.seeds]
    print(json.dumps(results, indent=2))
    usable = [result["seed"] for result in results if result["usable"]]
    print(f"usable seeds: {usable}" if usable else "no usable seed", file=sys.stderr)


if __name__ == "__main__":
    main()

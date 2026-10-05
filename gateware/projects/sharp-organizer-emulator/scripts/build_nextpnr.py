#!/usr/bin/env python3
"""Build and verify the Au1 organizer emulator with Spade, Yosys and nextpnr."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


GATEWARE = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATEWARE / "experiments/openxc7-macos"))
from build_common import (  # noqa: E402
    DEFAULT_TOOLCHAIN,
    begin_build,
    check_place_and_route_runs,
    pack_and_verify_bitstream,
    publish_result,
)


PART = "xc7a35tftg256-1"
CHIPDB = "xc7a35tftg256.bin"
INPUT_ONLY = (
    "addr",
    "conn_rw",
    "conn_oe",
    "conn_ci",
    "conn_e2",
    "conn_mskrom",
    "conn_sram1",
    "conn_sram2",
    "conn_eprom",
    "conn_stnby",
    "conn_vbatt",
    "conn_vpp",
    "conn_nc02",
    "conn_nc42",
    "conn_nc43",
    "conn_nc44",
)
NC_PORTS = ("conn_nc02", "conn_nc42", "conn_nc43", "conn_nc44")


def run_stage(stage: str, command: list[str], output: Path, *, env=None) -> None:
    print(stage, flush=True)
    with (output / f"{stage}.log").open("w") as log:
        subprocess.run(
            command,
            cwd=output,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    parser.add_argument("--seed", type=int, default=3)
    args = parser.parse_args()
    tc = args.toolchain.resolve()
    if args.seed < 1:
        parser.error("--seed must be positive")
    output_name = "nextpnr-au1" if args.seed == 3 else f"nextpnr-au1-seed{args.seed}"
    output = PROJECT / "build" / output_name
    begin_build(output)
    check_place_and_route_runs(tc)
    subprocess.run(
        [
            sys.executable,
            str(GATEWARE / "tools/gen_project_xdc.py"),
            "--project",
            str(PROJECT),
        ],
        check=True,
    )
    subprocess.run(["swim", "build"], cwd=PROJECT, check=True)
    run_stage(
        "synthesis",
        [
            str(tc / "bin/yosys"),
            "-p",
            f"read_verilog -sv {PROJECT / 'build/spade.sv'} {PROJECT / 'verilog/main_wrapper.v'} "
            f"{GATEWARE / 'lib/shared-components/verilog/fifo_v.v'} "
            f"{GATEWARE / 'lib/shared-components/verilog/ft_u16_v.v'} "
            f"{GATEWARE / 'lib/shared-components/verilog/card_memory_v.v'}; "
            # The shared FT model has Z on its internal read-side outputs.
            # Flatten before tri-state lowering; keep real connector IOBs.
            "hierarchy -top main; setattr -unset keep_hierarchy; "
            "setattr -mod -unset keep_hierarchy; flatten; tribuf -logic; "
            "synth_xilinx -flatten -nowidelut -abc9 -arch xc7 -top main; "
            "check -assert; write_json design.json",
        ],
        output,
    )
    design = json.loads((output / "design.json").read_text())["modules"]["main"]
    for port in INPUT_ONLY:
        if design["ports"][port]["direction"] != "input":
            raise RuntimeError(f"protected port {port} is not input-only")
    for port in ("data", "ft_data", "ft_be"):
        if design["ports"][port]["direction"] != "inout":
            raise RuntimeError(
                f"drive-capable port {port} unexpectedly changed direction"
            )
    run_stage(
        "route",
        [
            str(tc / "bin/nextpnr-xilinx"),
            "--chipdb",
            str(tc / "share/nextpnr" / CHIPDB),
            "--xdc",
            str(PROJECT / "constraints/pins.xdc"),
            "--json",
            "design.json",
            "--write",
            "routed.json",
            "--fasm",
            "design.fasm",
            "--freq",
            "100",
            "--seed",
            str(args.seed),
        ],
        output,
        env=os.environ.copy(),
    )
    timing = (output / "route.log").read_text()
    final_clocks = {}
    for name, frequency, outcome in re.findall(
        r"Max frequency for clock\s+'([^']+)': ([0-9.]+) MHz \((PASS|FAIL) at 100.00 MHz\)",
        timing,
    ):
        final_clocks[name] = {"mhz": float(frequency), "outcome": outcome}
    if len(final_clocks) < 2 or any(
        clock["outcome"] != "PASS" for clock in final_clocks.values()
    ):
        raise RuntimeError("post-route timing did not pass at 100 MHz")
    verified_bits = pack_and_verify_bitstream(
        tc, output, part=PART, env=os.environ.copy()
    )
    result = {
        "part": PART,
        "clock_mhz": 100,
        "post_route_clocks": final_clocks,
        "seed": args.seed,
        "input_only_ports": list(INPUT_ONLY),
        "input_only_auxiliary_ports": list(NC_PORTS),
        "verified_configuration_bits": verified_bits,
        "bitstream_bytes": (output / "design.bit").stat().st_size,
        "bitstream_sha256": hashlib.sha256(
            (output / "design.bit").read_bytes()
        ).hexdigest(),
    }
    publish_result(output, json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

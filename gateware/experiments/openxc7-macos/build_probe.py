#!/usr/bin/env python3
"""Build input-only Arty A7-35T JD microSD pin probes for both orientations."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from build_common import (
    GATEWARE,
    DEFAULT_TOOLCHAIN,
    pack_and_verify_bitstream,
    begin_build,
    publish_result,
)

sys.path.insert(0, str(GATEWARE / "tools"))
from microsd_probe import PROFILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES))
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    args = parser.parse_args()
    tc = args.toolchain.resolve()
    project = GATEWARE / "projects/microsd-pin-tester"
    requested = [
        (top, profile, GATEWARE / "build/microsd-probe" / (profile))
        for top, profile in enumerate(PROFILES)
        if args.profile is None or profile == args.profile
    ]
    for _, _, output in requested:
        begin_build(output)
    subprocess.run(["swim", "build"], cwd=project, check=True)
    for top, profile, out in requested:
        wrapper = out / "board.v"
        wrapper.write_text(
            "module board(input clk, rst_n, input [7:0] pmod, input usb_rx, output usb_tx);\n"
            f"probe_uart core(.clk(clk), .rst_n(rst_n), .pmod(pmod), .top_header(2'd{top}), .usb_rx(usb_rx), .usb_tx(usb_tx));\nendmodule\n"
        )
        steps = [
            (
                "synthesis",
                [
                    str(tc / "bin/yosys"),
                    "-p",
                    f"read_verilog -sv {project}/build/spade.sv {wrapper}; synth_xilinx -flatten -nowidelut -abc9 -arch xc7 -top board; check -assert; write_json design.json",
                ],
            ),
            (
                "route",
                [
                    str(tc / "bin/nextpnr-xilinx"),
                    "--chipdb",
                    str(tc / "share/nextpnr/xc7a35tcsg324.bin"),
                    "--xdc",
                    str(project / "constraints/pins.xdc"),
                    "--json",
                    "design.json",
                    "--write",
                    "routed.json",
                    "--fasm",
                    "design.fasm",
                    "--freq",
                    "100",
                ],
            ),
        ]
        for stage, cmd in steps:
            print(f"{profile}: {stage}", flush=True)
            with (out / f"{stage}.log").open("w") as log:
                subprocess.run(
                    cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True
                )
            if stage == "route":
                timing = (out / "route.log").read_text()
                final = timing.split("Max frequency for clock")[-1]
                if "(PASS at 100.00 MHz)" not in final:
                    raise RuntimeError("Post-route timing did not pass at 100 MHz")
            if stage == "synthesis":
                design = json.loads((out / "design.json").read_text())["modules"][
                    "board"
                ]
                if design["ports"]["pmod"]["direction"] != "input":
                    raise RuntimeError("Pin probe Pmod port must remain input-only")
                if any(
                    c["type"] in ("IOBUF", "OBUFT") for c in design["cells"].values()
                ):
                    raise RuntimeError(
                        "Pin probe unexpectedly contains a bidirectional or tri-state output buffer"
                    )
        verified_bits = pack_and_verify_bitstream(tc, out)
        result = {
            "profile": profile,
            "pmod_inputs_only": True,
            "verified_configuration_bits": verified_bits,
            "bitstream_bytes": (out / "design.bit").stat().st_size,
        }
        publish_result(out, json.dumps(result, indent=2) + "\n")
        print(result, flush=True)


if __name__ == "__main__":
    main()

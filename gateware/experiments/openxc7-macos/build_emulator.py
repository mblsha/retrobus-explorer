#!/usr/bin/env python3
"""Build read-only Arty A7-35T JD microSD emulators for both orientations."""

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
from microsd_probe import PMOD_PINS, PROFILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES))
    parser.add_argument(
        "--one-bit",
        action="store_true",
        help="Connect only DAT0 output; requires host four-bit capability disabled",
    )
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    args = parser.parse_args()
    tc = args.toolchain.resolve()
    project = GATEWARE / "projects/microsd-emulator"
    requested = [
        (
            top,
            profile,
            GATEWARE
            / "build/microsd-emulator"
            / (profile + ("-one-bit" if args.one_bit else "")),
        )
        for top, profile in enumerate(PROFILES)
        if args.profile is None or profile == args.profile
    ]
    for _, _, output in requested:
        begin_build(output)
    subprocess.run(["swim", "build"], cwd=project, check=True)
    for top, profile, out in requested:
        wrapper = out / "board.v"
        mapping = {
            signal: PMOD_PINS.index(pin) for signal, pin in PROFILES[profile].items()
        }
        text = "module board(input clk,rst_n,usb_rx, output usb_tx, inout [7:0] pmod);\nwire co,ce; wire [3:0] dout,doe; wire armed;\n"
        text += f"emulator_uart core(.clk(clk),.rst_n(rst_n),.usb_rx(usb_rx),.usb_tx(usb_tx),.sd_clk(pmod[{mapping['CLK']}]),.cmd_in(pmod[{mapping['CMD']}]),.cmd_out(co),.cmd_oe(ce),.dat_out(dout),.dat_oe(doe),.armed_status(armed));\n"
        text += f"assign pmod[{mapping['CMD']}] = ce ? co : 1'bz;\n"
        for lane in range(1 if args.one_bit else 4):
            text += f"assign pmod[{mapping['DAT' + str(lane)]}] = doe[{lane}] ? dout[{lane}] : 1'bz;\n"
        wrapper.write_text(text + "endmodule\n")
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
                if design["ports"]["pmod"]["direction"] != "inout":
                    raise RuntimeError(
                        "BRAM emulator Pmod port must support tri-state SD outputs"
                    )
                if sum(
                    (
                        c["type"] in ("IOBUF", "OBUFT")
                        and c["connections"]["T"] != ["1"]
                        for c in design["cells"].values()
                    )
                ) != (2 if args.one_bit else 5):
                    raise RuntimeError("Unexpected number of enabled SD output buffers")
        verified_bits = pack_and_verify_bitstream(tc, out)
        result = {
            "profile": profile,
            "sd_driven_lanes": 2 if args.one_bit else 5,
            "board_data_lanes": 1 if args.one_bit else 4,
            "verified_configuration_bits": verified_bits,
            "bitstream_bytes": (out / "design.bit").stat().st_size,
        }
        publish_result(out, json.dumps(result, indent=2) + "\n")
        print(result, flush=True)


if __name__ == "__main__":
    main()

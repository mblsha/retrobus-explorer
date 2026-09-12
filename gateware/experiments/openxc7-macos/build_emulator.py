#!/usr/bin/env python3
"""Build read-only Arty A7-35T JD microSD emulators for both orientations."""

import argparse
import json
import subprocess
import sys
from build_common import GATEWARE, verify_frames, begin_build, publish_result

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
    args = parser.parse_args()
    tc = GATEWARE / "build/openxc7-macos"
    project = GATEWARE / "projects/microsd-emulator"
    db = tc / "share/prjxray/artix7"
    part = "xc7a35tcsg324-1"
    subprocess.run(["swim", "build"], cwd=project, check=True)
    for top, profile in enumerate(PROFILES):
        if args.profile and profile != args.profile:
            continue
        out = (
            GATEWARE
            / "build/microsd-emulator"
            / (profile + ("-one-bit" if args.one_bit else ""))
        )
        begin_build(out)
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
            (
                "frames",
                [
                    str(tc / "venv/bin/python"),
                    str(tc / "libexec/fasm2frames.py"),
                    "--db-root",
                    str(db),
                    "--part",
                    part,
                    "design.fasm",
                ],
            ),
            (
                "bitstream",
                [
                    str(tc / "bin/xc7frames2bit"),
                    "--part_file",
                    str(db / part / "part.yaml"),
                    "--part_name",
                    part,
                    "--frm_file",
                    "design.frames",
                    "--output_file",
                    "design.bit",
                ],
            ),
            (
                "decode",
                [
                    str(tc / "bin/bitread"),
                    "--part_file",
                    str(db / part / "part.yaml"),
                    "-y",
                    "-z",
                    "-o",
                    "decoded.bits",
                    "design.bit",
                ],
            ),
        ]
        for stage, cmd in steps:
            print(f"{profile}: {stage}", flush=True)
            with (out / f"{stage}.log").open("w") as log:
                if stage == "frames":
                    with (out / "design.frames").open("w") as data:
                        subprocess.run(
                            cmd, cwd=out, stdout=data, stderr=log, check=True
                        )
                else:
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
                        "Check failed: design['ports']['pmod']['direction'] == 'inout'"
                    )
                if sum(
                    (
                        c["type"] in ("IOBUF", "OBUFT")
                        and c["connections"]["T"] != ["1"]
                        for c in design["cells"].values()
                    )
                ) != (2 if args.one_bit else 5):
                    raise RuntimeError(
                        "Check failed: sum((c['type'] in ('IOBUF', 'OBUFT') and c['connections']['T'] != ['1'] for c in design['cells'].values())) == (2 if args.one_bit else 5)"
                    )
        result = {
            "profile": profile,
            "sd_driven_lanes": 2 if args.one_bit else 5,
            "board_data_lanes": 1 if args.one_bit else 4,
            "verified_configuration_bits": verify_frames(out),
            "bitstream_bytes": (out / "design.bit").stat().st_size,
        }
        publish_result(out, json.dumps(result, indent=2) + "\n")
        print(result, flush=True)


if __name__ == "__main__":
    main()

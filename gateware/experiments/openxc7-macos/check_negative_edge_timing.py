"""Reject a nextpnr binary that times negative-edge slice FFs as rising-edge."""

import json
from pathlib import Path
import subprocess


def check(toolchain, output):
    toolchain, output = Path(toolchain).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "probe.v").write_text(
        "module probe(input clk, output reg q);\n"
        "reg source = 0;\n"
        "always @(posedge clk) source <= !source;\n"
        "always @(negedge clk) q <= source;\n"
        "endmodule\n"
    )
    (output / "probe.xdc").write_text(
        "set_property -dict {PACKAGE_PIN E3 IOSTANDARD LVCMOS33} [get_ports clk]\n"
        "set_property -dict {PACKAGE_PIN F3 IOSTANDARD LVCMOS33} [get_ports q]\n"
        "create_clock -period 10.0 [get_ports clk]\n"
    )
    commands = [
        [
            str(toolchain / "bin/yosys"),
            "-p",
            "read_verilog probe.v; synth_xilinx -top probe -arch xc7; write_json probe.json",
        ],
        [
            str(toolchain / "bin/nextpnr-xilinx"),
            "--chipdb",
            str(toolchain / "share/nextpnr/xc7a35tcsg324.bin"),
            "--json",
            "probe.json",
            "--xdc",
            "probe.xdc",
            "--freq",
            "100",
        ],
    ]
    for name, command in zip(("synthesis", "route"), commands):
        with (output / f"{name}.log").open("w") as log:
            subprocess.run(
                command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True
            )
    report = (output / "route.log").read_text()
    if "(posedge -> negedge)" not in report:
        raise RuntimeError(
            "nextpnr does not recognize the negative-edge timing path; apply nextpnr-negative-edge-timing.patch and rebuild it"
        )
    result = {"negative_edge_timing_recognized": True}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(check(args.toolchain, args.output))

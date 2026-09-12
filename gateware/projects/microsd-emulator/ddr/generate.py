#!/usr/bin/env python3
"""Generate the pinned Arty LiteDRAM core and a checked Spade native-port binding."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATEWARE = HERE.parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=GATEWARE / "build/microsd-litedram")
    args = p.parse_args()
    out = args.output.resolve()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "litedram.gen",
            str(HERE / "arty.yml"),
            "--no-compile",
            "--output-dir",
            str(out),
            "--name",
            "arty_ddr",
            "--csr-csv",
            str(out / "csr.csv"),
        ],
        check=True,
    )
    source = (out / "gateware/arty_ddr.v").read_text()
    port_block = source.split("module arty_ddr (", 1)[1].split(");", 1)[0]
    expected = {
        "user_port_native_0_cmd_addr": 24,
        "user_port_native_0_rdata_data": 128,
        "user_port_native_0_wdata_data": 128,
        "user_port_native_0_wdata_we": 16,
    }
    for name, width in expected.items():
        assert re.search(
            r"\[" + str(width - 1) + r":0\]\s+" + name + r"\b", port_block
        ), name
    ports = []
    names = []
    for line in port_block.splitlines():
        line = line.strip().rstrip(",")
        if line:
            ports.append(line)
            names.append(line.split()[-1])
    # Keep DDR pads, control Wishbone, clock/reset/status external. Native data
    # connects directly to the tested Spade DDR emulator on user_clk/user_rst.
    external = [
        decl for decl, name in zip(ports, names) if not name.startswith("user_port_")
    ]
    external += [
        "input wire rx_valid",
        "input wire [7:0] rx_byte",
        "input wire tx_ready",
        "output wire tx_valid",
        "output wire [7:0] tx_byte",
        "input wire sd_clk",
        "input wire cmd_in",
        "output wire cmd_out",
        "output wire cmd_oe",
        "output wire [3:0] dat_out",
        "output wire [3:0] dat_oe",
        "output wire armed_status",
    ]
    text = "module microsd_ddr_system(\n" + ",\n".join(external) + "\n);\n"
    for decl, name in zip(ports, names):
        if name.startswith("user_port_"):
            text += re.sub(r"^(input|output)\s+wire", "wire", decl) + ";\n"
    text += (
        "arty_ddr controller(\n"
        + ",\n".join("." + n + "(" + n + ")" for n in names)
        + "\n);\n"
    )
    connections = {
        "clk": "user_clk",
        "rst": "user_rst",
        "initialized": "init_done && !init_error && pll_locked",
    }
    for local, remote in [
        ("ddr_cmd_valid", "cmd_valid"),
        ("ddr_cmd_ready", "cmd_ready"),
        ("ddr_cmd_address", "cmd_addr"),
        ("ddr_cmd_write", "cmd_we"),
        ("ddr_rdata_valid", "rdata_valid"),
        ("ddr_rdata_ready", "rdata_ready"),
        ("ddr_rdata", "rdata_data"),
        ("ddr_wdata_valid", "wdata_valid"),
        ("ddr_wdata_ready", "wdata_ready"),
        ("ddr_wdata", "wdata_data"),
        ("ddr_wdata_mask", "wdata_we"),
    ]:
        connections[local] = "user_port_native_0_" + remote
    for n in [
        "rx_valid",
        "rx_byte",
        "tx_ready",
        "tx_valid",
        "tx_byte",
        "sd_clk",
        "cmd_in",
        "cmd_out",
        "cmd_oe",
        "dat_out",
        "dat_oe",
        "armed_status",
    ]:
        connections[n] = n
    text += (
        "ddr_emulator emulator(\n"
        + ",\n".join("." + k + "(" + v + ")" for k, v in connections.items())
        + "\n);\nendmodule\n"
    )
    (out / "gateware/microsd_ddr_system.v").write_text(text)
    print("Generated controller and checked 128-bit native binding:", out)


if __name__ == "__main__":
    main()

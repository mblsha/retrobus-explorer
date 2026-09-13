#!/usr/bin/env python3
"""Build the qualified Arty A7-35T writable 256 MiB microSD card."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from build_common import (
    GATEWARE,
    DEFAULT_TOOLCHAIN,
    pack_and_verify_bitstream,
    begin_build,
    publish_result,
)


# The supported card contract is checked against actual CMD9 responses by
# the Spade testbench, rather than inferred from the source's formatting.
SD_CSD = 0x0026001A115903FFC002800002400023
CONFIG = GATEWARE / "projects/microsd-emulator/ddr/arty-bios-80-depth2.yml"
BOARD = GATEWARE / "projects/microsd-emulator/ddr/board.v"


def sd_properties():
    speed = (SD_CSD >> 96) & 255
    values = (0, 10, 12, 13, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80)
    return dict(
        sd_csd=f"{SD_CSD:032x}",
        sd_capacity_bytes=(((SD_CSD >> 62) & 4095) + 1)
        * (1 << (((SD_CSD >> 47) & 7) + 2))
        * (1 << ((SD_CSD >> 80) & 15)),
        sd_max_clock_hz=100_000 * 10 ** (speed & 7) * values[(speed >> 3) & 15] // 10,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    parser.add_argument(
        "--output", type=Path, default=GATEWARE / "build/microsd-ddr-sd"
    )
    parser.add_argument("--seed", type=int, default=8, help="Placement seed (default: 8)")
    args = parser.parse_args()
    out = args.output.resolve()
    tc = args.toolchain.resolve()
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["SOURCE_DATE_EPOCH"] = "0"
    env["PATH"] = (
        str(GATEWARE / "build/xpack-riscv-none-elf-gcc-15.2.0-1/bin")
        + os.pathsep
        + str(GATEWARE / "build/litedram-py311/bin")
        + os.pathsep
        + env["PATH"]
    )
    begin_build(out)
    from check_negative_edge_timing import check as check_edge_timing

    check_edge_timing(tc, out / "negative-edge-timing-check")

    def run(stage, command):
        print(stage, flush=True)
        with (out / (stage + ".log")).open("w") as log:
            subprocess.run(
                command, cwd=out, env=env, check=True, stdout=log, stderr=log
            )

    run(
        "support-tests",
        [
            str(GATEWARE / "build/litedram-py311/bin/python"),
            "-m",
            "unittest",
            "discover",
            "-s",
            str(GATEWARE / "projects/microsd-emulator/ddr"),
            "-p",
            "test_*.py",
        ],
    )
    run(
        "generate",
        [
            str(GATEWARE / "build/litedram-py311/bin/python"),
            str(GATEWARE / "projects/microsd-emulator/ddr/generate_bios.py"),
            str(CONFIG.resolve()),
            "--output-dir",
            str(out),
            "--name",
            "arty_ddr_bios",
            "--csr-csv",
            str(out / "csr.csv"),
        ],
    )
    source = out / "gateware/arty_ddr_bios.v"
    clock_header = (out / "software/include/generated/soc.h").read_text()
    sys_clk_freq = int(
        re.search(r"#define CONFIG_CLOCK_FREQUENCY (0x[0-9a-fA-F]+|\d+)", clock_header)[
            1
        ],
        0,
    )
    if sys_clk_freq != 80_000_000:
        raise RuntimeError(f"Expected 80 MHz DDR controller, got {sys_clk_freq}")
    wrapper = out / "board.v"
    shutil.copyfile(BOARD, wrapper)
    reset_port = "reset_button"
    # Fixed Arty routing from litex_boards/platforms/digilent_arty.py.
    pins = {
        "a": "R2 M6 N4 T1 N6 R7 V6 U7 R8 V7 R6 U6 T6 T8",
        "ba": "R1 P4 P2",
        "ras_n": "P3",
        "cas_n": "M4",
        "we_n": "P5",
        "cs_n": "U8",
        "dm": "L1 U1",
        "dq": "K5 L3 K3 L6 M3 M1 L4 M2 V4 T5 U4 V5 V1 T3 U3 R3",
        "dqs_p": "N2 U2",
        "dqs_n": "N1 V2",
        "clk_p": "U9",
        "clk_n": "V9",
        "cke": "N5",
        "odt": "R5",
        "reset_n": "K6",
    }
    xdc = []
    for signal, pinlist in pins.items():
        values = pinlist.split()
        for i, pin in enumerate(values):
            port = "ddram_" + signal + (f"[{i}]" if len(values) > 1 else "")
            ios = (
                "DIFF_SSTL135"
                if signal in ("dqs_p", "dqs_n", "clk_p", "clk_n")
                else "SSTL135"
            )
            term = (
                " IN_TERM UNTUNED_SPLIT_40"
                if signal in ("dq", "dqs_p", "dqs_n")
                else ""
            )
            xdc.append(
                f"set_property -dict {{ PACKAGE_PIN {pin} IOSTANDARD {ios} SLEW FAST{term} }} [get_ports {{{port}}}]"
            )
    for port, pin in {
        "clk": "E3",
        reset_port: "D9",
        "usb_rx": "A9",
        "usb_tx": "D10",
        "status[0]": "H5",
        "status[1]": "J5",
        "status[2]": "T9",
    }.items():
        xdc.append(
            f"set_property -dict {{ PACKAGE_PIN {pin} IOSTANDARD LVCMOS33 }} [get_ports {{{port}}}]"
        )
    xdc += [
        "set_property INTERNAL_VREF 0.675 [get_iobanks 34]",
        "create_clock -period 10.000 -name sys_clk [get_ports {clk}]",
    ]
    for i, pin in enumerate("D4 D3 F4 F3 E2 D2 H2 G2".split()):
        slew = " SLEW FAST"
        xdc.append(
            f"set_property -dict {{ PACKAGE_PIN {pin} IOSTANDARD LVCMOS33{slew} }} [get_ports {{pmod[{i}]}}]"
        )
    (out / "board.xdc").write_text("\n".join(xdc) + "\n")
    cpu = (
        GATEWARE
        / "build/litedram-py311/lib/python3.11/site-packages/pythondata_cpu_vexriscv/verilog/VexRiscv_Min.v"
    )
    if not cpu.exists():
        raise RuntimeError(f"Missing initialization CPU HDL: {cpu}")
    project = GATEWARE / "projects/microsd-emulator"
    subprocess.run(["swim", "build"], cwd=project, env=env, check=True)
    hdl = f"{project}/build/spade.sv {GATEWARE}/lib/shared-components/verilog/fifo_v.v"
    # Register storage preserves the qualified FIFO and bank-command mappings.
    cache_mapping = 'hierarchy -top board; select -assert-count 3 */mem; setattr -set ram_style "registers" */mem; '

    memories = re.findall(
        r"reg \[23:0\] (storage(?:_\d+)?)\[0:\d+\];", source.read_text()
    )
    if len(memories) != 8:
        raise RuntimeError(f"Expected eight bank command memories, found {memories}")
    selection = " ".join("arty_ddr_bios/" + name for name in memories)
    cache_mapping += f'select -assert-count 8 {selection}; setattr -set ram_style "registers" {selection}; '
    run(
        "synthesis",
        [
            str(tc / "bin/yosys"),
            "-p",
            f"read_verilog -sv {source} {cpu} {wrapper} {hdl}; {cache_mapping}synth_xilinx -flatten -nowidelut -abc9 -arch xc7 -top board; check -assert; write_json design.json",
        ],
    )

    import collections

    mapped = json.loads((out / "design.json").read_text())["modules"]
    fifo_counts = {
        name: dict(
            collections.Counter(cell["type"] for cell in module["cells"].values())
        )
        for name, module in mapped.items()
        if name.endswith("\\async_fifo_v")
    }
    if len(fifo_counts) != 3:
        raise RuntimeError(f"Expected three native FIFOs, found {list(fifo_counts)}")
    if any(
        kind.startswith(("RAM", "SRL"))
        for counts in fifo_counts.values()
        for kind in counts
    ):
        raise RuntimeError(
            f"Native FIFO storage mapped to RAM/SRL instead of registers: {fifo_counts}"
        )
    if sum(counts.get("FDRE", 0) for counts in fifo_counts.values()) < 594:
        raise RuntimeError(
            f"Native FIFOs have fewer than the required 594 registers: {fifo_counts}"
        )
    (out / "fifo-synthesis.json").write_text(json.dumps(fifo_counts, indent=2) + "\n")

    def route(seed):
        stage = f"route-seed-{seed}"
        run(
            stage,
            [
                str(tc / "bin/nextpnr-xilinx"),
                "--chipdb",
                str(tc / "share/nextpnr/xc7a35tcsg324.bin"),
                "--xdc",
                "board.xdc",
                "--json",
                "design.json",
                "--write",
                f"routed-seed-{seed}.json",
                "--fasm",
                f"design-seed-{seed}.fasm",
                "--sdf",
                f"routed-seed-{seed}.sdf",
                "--freq",
                "100",
                "--seed",
                str(seed),
            ],
        )
        timing = (out / f"{stage}.log").read_text()
        clocks = {}
        for name, fmax, verdict, target in re.findall(
            r"Max frequency for clock\s+'([^']+)': ([0-9.]+) MHz \((PASS|FAIL) at ([0-9.]+) MHz\)",
            timing,
        ):
            clocks[name] = (float(fmax), verdict, float(target))
        if not clocks:
            raise RuntimeError(f"No timing results for seed {seed}")
        if "fclk" not in clocks or clocks["fclk"][2] != 100:
            raise RuntimeError(f"Missing 100 MHz SD fabric timing constraint: {clocks}")
        if not any(
            abs(v[2] - sys_clk_freq / 1_000_000) < 0.02 for v in clocks.values()
        ):
            raise RuntimeError(f"Missing DDR controller timing constraint: {clocks}")
        if not any(v[2] == 200 for v in clocks.values()):
            raise RuntimeError(f"Missing 200 MHz IDELAY timing constraint: {clocks}")
        return seed, clocks

    selected_seed, clocks = route(args.seed)
    for source_name, target_name in [
        (f"route-seed-{selected_seed}.log", "route.log"),
        (f"routed-seed-{selected_seed}.json", "routed.json"),
        (f"design-seed-{selected_seed}.fasm", "design.fasm"),
    ]:
        shutil.copy2(out / source_name, out / target_name)
    from ddr_cdc_timing import verify_native_cdc
    from ddr_output_timing import verify_direct_sd_outputs

    cdc_paths = verify_native_cdc(
        out / f"routed-seed-{selected_seed}.json",
        out / f"routed-seed-{selected_seed}.sdf",
        sys_clk_freq,
    )
    (out / "cdc-timing.json").write_text(json.dumps(cdc_paths, indent=2) + "\n")
    output_paths = verify_direct_sd_outputs(
        out / f"routed-seed-{selected_seed}.json",
        out / f"routed-seed-{selected_seed}.sdf",
    )
    (out / "output-timing.json").write_text(json.dumps(output_paths, indent=2) + "\n")
    if not all(v[1] == "PASS" for v in clocks.values()):
        raise RuntimeError(f"Selected placement failed clock timing: {clocks}")
    verified_bits = pack_and_verify_bitstream(tc, out, env=env)
    publish_result(
        out,
        json.dumps(
            {
                **sd_properties(),
                "verified_configuration_bits": verified_bits,
                "bitstream_sha256": hashlib.sha256(
                    (out / "design.bit").read_bytes()
                ).hexdigest(),
                "bitstream_bytes": (out / "design.bit").stat().st_size,
                "clocks_mhz": clocks,
                "placement_seed": selected_seed,
                "nextpnr_binary_sha256": hashlib.sha256(
                    (tc / "bin/nextpnr-xilinx").read_bytes()
                ).hexdigest(),
                "negative_edge_timing_checked": True,
                "with_sd": True,
                "fast_sd": True,
                "native_fifo_registers": True,
                "sd_io_slew": "FAST",
                "sd_output_fabric_edge": "falling",
                "sd_io_clock_hz": 100_000_000,
                "registered_bank": True,
                "register_command_buffers": True,
                "native_bist": True,
                "native_bist_bytes": 268435456,
                "bist_detail_format": 1,
                "sd_writable": True,
                "sys_clk_freq": sys_clk_freq,
                "reset_source": "button0",
                "configuration": CONFIG.read_text(),
            },
            indent=2,
        )
        + "\n",
    )


if __name__ == "__main__":
    main()

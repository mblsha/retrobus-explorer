#!/usr/bin/env python3
"""Build the qualified Arty A7-35T writable 256 MiB microSD card."""

import argparse
import hashlib
import json
import os
import re
import shutil
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

# The card contract and its TRAN_SPEED encoding are shared with the host-side
# tooling, so they live in tools/ and are imported the way this script already
# imports its siblings: by bare name, off sys.path.
sys.path.insert(0, str(GATEWARE / "tools"))
from sd_csd import sd_csd_with_speed, sd_properties, tran_speed_code

CONFIG = GATEWARE / "projects/microsd-emulator/ddr/arty-bios-80-depth2.yml"
BOARD = GATEWARE / "projects/microsd-emulator/ddr/board.v"

# The bitstream that qualified the RG35XX Plus was built from this exact set of
# options, which existed only in a build log until it was named here. A profile
# has to satisfy the cross-flag rules below by construction, so that asking for
# the shipped card cannot produce a combination the parser then rejects.
PROFILES = {
    "h700-rg35xx": dict(
        ethernet=True,
        slow_mmc=True,
        h700_mmc=True,
        seed=19,
        sd_io_clock_hz=64_000_000,
        sd_tran_speed=13_000_000,
        trace_capture_lba=32985,
    ),
}


def parse_arguments(argv=None):
    """Resolve the command line, expanding a profile into its settings.

    A profile supplies defaults, so a flag given alongside it still wins and
    an experiment can start from the shipped build and change one thing.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        help="Start from a named, qualified set of options; flags given "
        "alongside it override the settings it supplies",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Build directory (defaults to the selected transport)",
    )
    parser.add_argument(
        "--seed", type=int, default=8, help="Placement seed (default: 8)"
    )
    parser.add_argument(
        "--ethernet",
        action="store_true",
        help="Use the full-image service over UDP with its USB UART fallback",
    )
    parser.add_argument(
        "--slow-mmc",
        action="store_true",
        help="Use the qualified slow-command card frontend (Ethernet PHY stays at 25 MHz)",
    )
    parser.add_argument(
        "--h700-mmc",
        action="store_true",
        help="Enable the H700 legacy-MMC compatibility and diagnostics profile",
    )
    parser.add_argument(
        "--h700-early-command",
        action="store_true",
        help="Launch H700 command responses from the early diagnostic phase",
    )
    parser.add_argument(
        "--sd-tran-speed",
        type=int,
        default=13_000_000,
        help="Transfer speed the writable card advertises in its CSD; the host "
        "picks a divisor at or below it. Only the rates the SD TRAN_SPEED byte "
        "can name are accepted",
    )
    parser.add_argument(
        "--trace-capture-lba",
        type=int,
        help="Sector whose block the independent decoder captures and "
        "timestamps; defaults to the kernel's first sector",
    )
    parser.add_argument(
        "--sd-io-clock-hz",
        type=int,
        choices=(50_000_000, 64_000_000, 80_000_000, 100_000_000),
        help="Override the SD fabric clock; lower rates trade card bandwidth "
        "for routability in congested diagnostic builds",
    )
    parser.add_argument(
        "--sd-pullups",
        action="store_true",
        help="Enable the FPGA's weak pull-ups on CMD and DAT0..3, for a host "
        "that has none of its own",
    )
    parser.add_argument(
        "--mmc-only",
        action="store_true",
        help="Suppress SD negotiation so a host deterministically probes legacy MMC",
    )
    args = parser.parse_args(argv)
    if args.profile:
        # Re-reading the command line against the profile's defaults is what
        # makes an explicit flag win: argparse only falls back to a default
        # for an option the caller left out.
        parser.set_defaults(**PROFILES[args.profile])
        args = parser.parse_args(argv)
    if args.h700_mmc and not args.slow_mmc:
        parser.error("--h700-mmc requires --slow-mmc")
    if args.h700_early_command and not args.h700_mmc:
        parser.error("--h700-early-command requires --h700-mmc")
    if args.mmc_only and not (args.ethernet and args.slow_mmc):
        parser.error("--mmc-only requires --ethernet and --slow-mmc")
    if args.mmc_only and args.h700_mmc:
        parser.error("--mmc-only and --h700-mmc are distinct diagnostic profiles")
    # A slow-command frontend cannot hold the fabric at the full rate, so the
    # transport picks the clock unless the caller overrode it.
    args.sd_io_clock_hz = args.sd_io_clock_hz or (
        80_000_000 if args.slow_mmc else 100_000_000
    )
    try:
        args.sd_csd = sd_csd_with_speed(tran_speed_code(args.sd_tran_speed))
    except ValueError as unencodable:
        parser.error(str(unencodable))
    return args


def recorded_settings(args):
    """Manifest fields describing how the command line configured this build.

    They are what a later reader of build/*/result.json has to work from when
    deciding which experiment a directory holds.
    """
    return {
        "with_sd": True,
        "profile": args.profile,
        "ethernet_sd": args.ethernet,
        "serial_image_service": args.ethernet,
        "serial_baud": 1_000_000 if args.ethernet else None,
        "fast_sd": not args.slow_mmc,
        "h700_mmc": args.h700_mmc,
        "h700_early_command": args.h700_early_command,
        "trace_capture_lba": (
            32985 if args.trace_capture_lba is None else args.trace_capture_lba
        ),
        "mmc_only": args.mmc_only,
        "native_fifo_registers": True,
        "sd_io_slew": "SLOW" if args.slow_mmc else "FAST",
        "sd_pullups": args.sd_pullups,
        "sd_command_output_fabric_edge": "rising" if args.slow_mmc else "falling",
        "sd_data_output_fabric_edge": (
            "falling"
            if args.h700_mmc or args.mmc_only or not args.slow_mmc
            else "rising"
        ),
        "sd_io_clock_hz": args.sd_io_clock_hz,
    }


SD_PMOD_PINS = "D4 D3 F4 F3 E2 D2 H2 G2".split()
# board.v wires CMD to pmod[2] and DAT0..3 to pmod[3], pmod[7], pmod[0], pmod[1].
# Those are the lines the card shares with the host; pmod[6] is the clock, which
# the host always drives.
SD_SHARED_LINES = frozenset({0, 1, 2, 3, 7})


def sd_pin_constraints(slow_mmc: bool, pullups: bool) -> list[str]:
    """Return the XDC lines for the eight Pmod pins the card occupies.

    The slow MMC profile is capped at 13 MHz and benefits from gentler edges on
    the Pmod/card interconnect. The qualified SD profile keeps its existing
    fast-edge electrical contract.

    The SD bus expects pull-ups on CMD and DAT, and the card releases those
    lines between the blocks of a multi-block write and after every response.
    A host that has none leaves them held by nothing but charge, which is how
    the H700 leaves DAT0. The FPGA's own weak pull-ups are an option rather
    than the default because the qualified profiles were measured without them.
    """
    slew = " SLEW SLOW" if slow_mmc else " SLEW FAST"
    lines = []
    for i, pin in enumerate(SD_PMOD_PINS):
        pull = " PULLTYPE PULLUP" if pullups and i in SD_SHARED_LINES else ""
        lines.append(
            f"set_property -dict {{ PACKAGE_PIN {pin} IOSTANDARD LVCMOS33{slew}{pull} }} [get_ports {{pmod[{i}]}}]"
        )
    return lines


def main():
    args = parse_arguments()
    sd_csd = args.sd_csd
    project_name = "ethernet-diagnostic" if args.ethernet else "microsd-emulator"
    if args.ethernet:
        if args.mmc_only:
            default_output = "microsd-ddr-ethernet-mmc-only"
        elif args.h700_mmc:
            default_output = "microsd-ddr-ethernet-h700"
        elif args.slow_mmc:
            default_output = "microsd-ddr-ethernet-slow-mmc"
        else:
            default_output = "microsd-ddr-ethernet"
    else:
        default_output = "microsd-ddr-sd-slow-mmc" if args.slow_mmc else "microsd-ddr-sd"
    out = (args.output or GATEWARE / "build" / default_output).resolve()
    tc = args.toolchain.resolve()
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["SOURCE_DATE_EPOCH"] = "0"
    sd_io_clk_freq = args.sd_io_clock_hz
    env["MICROSD_IO_CLOCK_HZ"] = str(sd_io_clk_freq)
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
        # Arty A7 SW0 selects the H700 data launch phase while disarmed.
        "h700_phase_select": "A8",
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
    xdc += sd_pin_constraints(args.slow_mmc, args.sd_pullups)
    if args.ethernet:
        ethernet_xdc = GATEWARE / "projects/ethernet-diagnostic/constraints/pins.xdc"
        xdc.extend(ethernet_xdc.read_text().splitlines())
    (out / "board.xdc").write_text("\n".join(xdc) + "\n")
    cpu = (
        GATEWARE
        / "build/litedram-py311/lib/python3.11/site-packages/pythondata_cpu_vexriscv/verilog/VexRiscv_Min.v"
    )
    if not cpu.exists():
        raise RuntimeError(f"Missing initialization CPU HDL: {cpu}")
    project = GATEWARE / "projects" / project_name
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
    defines = " ".join(
        flag
        for enabled, flag in (
            (args.ethernet, "-D ETHERNET_SD"),
            (args.ethernet, f"-D UART_BIT_TIME=15'd{sd_io_clk_freq // 1_000_000}"),
            (args.slow_mmc, "-D SLOW_MMC"),
            (args.h700_mmc, "-D H700_MMC"),
            (args.h700_early_command, "-D H700_EARLY_COMMAND"),
            (True, f"-D SD_CSD=128'h{sd_csd:032x}"),
            (
                args.trace_capture_lba is not None,
                f"-D TRACE_CAPTURE_LBA=32'd{args.trace_capture_lba}",
            ),
            (args.mmc_only, "-D MMC_ONLY"),
        )
        if enabled
    )
    # Include register timing in ABC9 mapping for the combined SD/Ethernet
    # control paths. Routed CDC and opposite-edge output checks still apply.
    register_mapping = " -dff" if args.ethernet else ""
    run(
        "synthesis",
        [
            str(tc / "bin/yosys"),
            "-p",
            f"read_verilog -sv {defines} {source} {cpu} {wrapper} {hdl}; {cache_mapping}synth_xilinx -flatten -nowidelut -abc9{register_mapping} -arch xc7 -top board; check -assert; write_json design.json",
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
        if "fclk" not in clocks or clocks["fclk"][2] != sd_io_clk_freq / 1_000_000:
            raise RuntimeError(
                f"Missing {sd_io_clk_freq / 1_000_000:g} MHz SD fabric timing constraint: {clocks}"
            )
        if not any(
            abs(v[2] - sys_clk_freq / 1_000_000) < 0.02 for v in clocks.values()
        ):
            raise RuntimeError(f"Missing DDR controller timing constraint: {clocks}")
        if not any(v[2] == 200 for v in clocks.values()):
            raise RuntimeError(f"Missing 200 MHz IDELAY timing constraint: {clocks}")
        if args.ethernet:
            for name in ("eth_rx_global", "eth_tx_global"):
                if name not in clocks or clocks[name][2] != 25:
                    raise RuntimeError(
                        f"Missing 25 MHz MII timing constraint: {clocks}"
                    )
        return seed, clocks

    selected_seed, clocks = route(args.seed)
    for source_name, target_name in [
        (f"route-seed-{selected_seed}.log", "route.log"),
        (f"routed-seed-{selected_seed}.json", "routed.json"),
        (f"design-seed-{selected_seed}.fasm", "design.fasm"),
    ]:
        shutil.copy2(out / source_name, out / target_name)
    from ddr_cdc_timing import verify_native_cdc
    from ddr_output_timing import verify_profile_outputs

    cdc_paths = verify_native_cdc(
        out / f"routed-seed-{selected_seed}.json",
        out / f"routed-seed-{selected_seed}.sdf",
        sys_clk_freq,
        ethernet=args.ethernet,
        sd_io_clk_freq=sd_io_clk_freq,
    )
    (out / "cdc-timing.json").write_text(json.dumps(cdc_paths, indent=2) + "\n")
    routed = out / f"routed-seed-{selected_seed}.json"
    routed_sdf = out / f"routed-seed-{selected_seed}.sdf"
    output_paths = verify_profile_outputs(
        routed,
        routed_sdf,
        slow_mmc=args.slow_mmc,
        h700_mmc=args.h700_mmc,
        mmc_only=args.mmc_only,
    )
    (out / "output-timing.json").write_text(json.dumps(output_paths, indent=2) + "\n")
    if not all(v[1] == "PASS" for v in clocks.values()):
        raise RuntimeError(f"Selected placement failed clock timing: {clocks}")
    verified_bits = pack_and_verify_bitstream(tc, out, env=env)
    publish_result(
        out,
        json.dumps(
            {
                **sd_properties(sd_csd),
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
                **recorded_settings(args),
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

#!/usr/bin/env python3
"""Build an Arty A7-35T standalone LiteDRAM BIOS memory qualification image."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from build_common import GATEWARE, verify_frames


def frontend_csd(frontend, writable, fast):
    """Read the named Spade CSD choice; reject unrecognized source layouts."""
    values = re.findall(
        r"let csd:\s*uint<136>\s*=\s*if !writable\s*\{\s*(0x[0-9a-f]{28,32})\s*\}"
        r"\s*else if fast_mode\s*\{\s*(0x[0-9a-f]{28,32})\s*\}"
        r"\s*else\s*\{\s*(0x[0-9a-f]{28,32})\s*\}",
        frontend,
    )
    assert len(values) == 1, "Expected one named read-only/fast/normal CSD choice"
    return int(values[0][0 if not writable else 1 if fast else 2], 16)


def generation_record(config, env, out):
    """Fingerprint the checked DDR generator inputs and generated HDL/ROM files."""
    inputs = [config.resolve()]
    for directory, pattern in [
        (GATEWARE / "projects/microsd-emulator/ddr", "*.py"),
        (GATEWARE / "projects/microsd-emulator/src", "*.spade"),
        (GATEWARE / "lib/shared-components/src", "*.spade"),
        (GATEWARE / "experiments/openxc7-macos", "*.py"),
    ]:
        inputs.extend(sorted(directory.glob(pattern)))
    generated = sorted((out / "gateware").glob("*"))
    generated += [out / "software/include/generated/soc.h"]
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "inputs": {str(path): digest(path) for path in inputs},
        "options": {key: env[key] for key in (
            "MICROSD_MEMTEST_DEBUG", "MICROSD_CPU_MAILBOX", "MICROSD_REGISTERED_BANK",
            "MICROSD_FAST_SD", "MICROSD_NATIVE_BIST")},
        "generated": {str(path): digest(path) for path in generated if path.is_file()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=GATEWARE / "projects/microsd-emulator/ddr/arty-bios.yml",
    )
    parser.add_argument(
        "--toolchain", type=Path, default=GATEWARE / "build/openxc7-macos",
        help="Toolchain prefix; permits isolated release qualification",
    )
    parser.add_argument(
        "--output", type=Path,
        help="Separate output directory for an experimental build",
    )
    parser.add_argument("--with-sd", action="store_true")
    parser.add_argument("--reuse-ddr-generation", action="store_true", help="Reuse fingerprint-matched DDR generation and its passed support tests")
    parser.add_argument(
        "--fast-sd",
        action="store_true",
        help="Experimental 100 MHz SD domain; advertised rate comes from the Spade CSD",
    )
    parser.add_argument(
        "--sd-writable",
        action="store_true",
        help="Enable native SD CMD24/CMD25 after DDR qualification",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--route-seeds",
        type=int,
        nargs="+",
        help="Compare up to three independent placements from one synthesis",
    )
    parser.add_argument("--memtest-debug", action="store_true")
    parser.add_argument("--cpu-mailbox", action="store_true")
    parser.add_argument("--registered-bank", action="store_true")
    parser.add_argument(
        "--register-command-buffers",
        action="store_true",
        help="Implement the eight small bank command memories as registers",
    )
    parser.add_argument(
        "--reset-source",
        choices=("button0", "ck-reset"),
        default="button0",
        help="BTN0 avoids resets caused by opening USB-UART with JP2 fitted",
    )
    parser.add_argument(
        "--register-cpu-regfile",
        action="store_true",
        help="Diagnostic: map the CPU's 32x32 register file to flip-flops",
    )
    parser.add_argument(
        "--distributed-cpu-regfile",
        action="store_true",
        help="Diagnostic: map the CPU's register file to distributed RAM",
    )
    parser.add_argument(
        "--native-bist",
        action="store_true",
        help="Qualify all 256 MiB through the native port instead of the BIOS cache",
    )
    parser.add_argument(
        "--register-cache",
        action="store_true",
        help="Diagnostic: map only the 32-byte CPU data cache to registers",
    )
    parser.add_argument(
        "--no-lutram",
        action="store_true",
        help="Diagnostic: avoid distributed RAM mapping",
    )
    args = parser.parse_args()
    seeds = args.route_seeds or [args.seed]
    if not 1 <= len(seeds) <= 3 or len(set(seeds)) != len(seeds):
        parser.error("Choose one to three distinct placement seeds")
    if args.register_cpu_regfile and args.distributed_cpu_regfile:
        parser.error("Choose one CPU register-file memory implementation")
    if args.fast_sd and not (args.with_sd and args.sd_writable):
        parser.error("--fast-sd requires --with-sd --sd-writable")
    if args.sd_writable and not args.with_sd:
        parser.error("--sd-writable requires --with-sd")
    if args.native_bist and not args.with_sd:
        parser.error("--native-bist requires --with-sd")
    # Every advertised SD sector now comes from DDR. Training alone is not
    # sufficient: qualify and zero-initialize the entire region before SD.
    if args.with_sd:
        args.native_bist = True
    out = args.output.resolve() if args.output else GATEWARE / (
        "build/microsd-ddr-sd" if args.with_sd else "build/microsd-litedram-bios"
    )
    tc = args.toolchain.resolve()
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["SOURCE_DATE_EPOCH"] = "0"
    env["MICROSD_MEMTEST_DEBUG"] = "1" if args.memtest_debug else "0"
    env["MICROSD_CPU_MAILBOX"] = "1" if args.cpu_mailbox else "0"
    env["MICROSD_REGISTERED_BANK"] = "1" if args.registered_bank else "0"
    env["MICROSD_FAST_SD"] = "1" if args.fast_sd else "0"
    env["MICROSD_NATIVE_BIST"] = "1" if args.native_bist else "0"
    env["PATH"] = (
        str(GATEWARE / "build/xpack-riscv-none-elf-gcc-15.2.0-1/bin")
        + os.pathsep
        + str(GATEWARE / "build/litedram-py311/bin")
        + os.pathsep
        + env["PATH"]
    )
    out.mkdir(parents=True, exist_ok=True)
    if args.fast_sd:
        from check_negative_edge_timing import check as check_edge_timing

        check_edge_timing(tc, out / "negative-edge-timing-check")

    def run(stage, command, stdout=None):
        print(stage, flush=True)
        with (out / (stage + ".log")).open("w") as log:
            subprocess.run(
                command, cwd=out, env=env, check=True, stdout=stdout or log, stderr=log
            )

    cache = out / "generation-inputs.json"
    if args.reuse_ddr_generation:
        if not cache.exists() or json.loads(cache.read_text()) != generation_record(args.config, env, out):
            raise RuntimeError("DDR generation fingerprint changed; omit --reuse-ddr-generation")
        if "\nOK\n" not in (out / "support-tests.log").read_text():
            raise RuntimeError("Cached DDR support tests did not pass")
        print("Reusing fingerprint-matched DDR generation and passed support tests", flush=True)
    else:
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
                str(args.config.resolve()),
                "--output-dir",
                str(out),
                "--name",
                "arty_ddr_bios",
                "--csr-csv",
                str(out / "csr.csv"),
            ],
        )
        cache.write_text(json.dumps(generation_record(args.config, env, out), indent=2) + "\n")
    source = out / "gateware/arty_ddr_bios.v"
    clock_header = (out / "software/include/generated/soc.h").read_text()
    sys_clk_freq = int(
        re.search(r"#define CONFIG_CLOCK_FREQUENCY (0x[0-9a-fA-F]+|\d+)", clock_header)[
            1
        ],
        0,
    )
    ports = source.read_text().split("module arty_ddr_bios (", 1)[1].split(");", 1)[0]
    declarations = [
        line.strip().rstrip(",") for line in ports.splitlines() if line.strip()
    ]
    external = [line for line in declarations if line.split()[-1].startswith("ddram_")]
    reset_port = "reset_button" if args.reset_source == "button0" else "rst_n"
    reset_expression = reset_port if args.reset_source == "button0" else "!rst_n"
    external += [
        f"input wire clk, {reset_port}, usb_rx",
        "output wire usb_tx",
        "output wire [2:0] status",
    ]
    body, extra = "", {}
    if args.with_sd:
        from ddr_sd_wiring import wiring

        body, extra = wiring(
            native_bist=args.native_bist,
            writable=args.sd_writable,
            sys_clk_freq=sys_clk_freq,
            fast_sd=args.fast_sd,
        )
        external.append("inout wire [7:0] pmod")
    connections = []
    for decl in declarations:
        name = decl.split()[-1]
        fixed = {
            "clk": "clk",
            "rst": reset_expression,
            "uart_rx": "usb_rx",
            "uart_tx": "usb_tx",
            "init_done": "status[0]",
            "init_error": "status[1]",
            "pll_locked": "status[2]",
        }
        fixed.update(extra)
        if name in fixed:
            value = fixed[name]
        elif name.startswith("ddram_"):
            value = name
        elif name.startswith("user_port_") or name in ("user_clk", "user_rst"):
            value = "'0" if decl.startswith("input") else ""
        else:
            raise ValueError("Unmapped core port: " + decl)
        connections.append(f".{name}({value})")
    wrapper = out / "board.v"
    wrapper.write_text(
        "module board(\n"
        + ",\n".join(external)
        + "\n);\n"
        + body
        + "\narty_ddr_bios core(\n"
        + ",\n".join(connections)
        + "\n);\nendmodule\n"
    )
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
        reset_port: "D9" if args.reset_source == "button0" else "C2",
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
    if args.with_sd:
        for i, pin in enumerate("D4 D3 F4 F3 E2 D2 H2 G2".split()):
            slew = " SLEW FAST" if args.fast_sd else ""
            xdc.append(
                f"set_property -dict {{ PACKAGE_PIN {pin} IOSTANDARD LVCMOS33{slew} }} [get_ports {{pmod[{i}]}}]"
            )
    (out / "board.xdc").write_text("\n".join(xdc) + "\n")
    cpu = (
        GATEWARE
        / "build/litedram-py311/lib/python3.11/site-packages/pythondata_cpu_vexriscv/verilog/VexRiscv_Min.v"
    )
    assert cpu.exists(), cpu
    hdl = ""
    if args.with_sd:
        project = GATEWARE / "projects/microsd-emulator"
        subprocess.run(["swim", "build"], cwd=project, env=env, check=True)
        hdl = f"{project}/build/spade.sv {GATEWARE}/lib/shared-components/verilog/fifo_v.v"
    cache_mapping = ""
    if args.fast_sd:
        # These tiny dual-clock FIFOs need only shallow register storage.
        # Avoid the distributed-RAM mapping implicated by hardware data
        # corruption despite passing native DDR BIST and simulation.
        cache_mapping += 'hierarchy -top board; select -assert-count 3 */mem; setattr -set ram_style "registers" */mem; '

    if args.register_cache:
        cache_memories = " ".join(f"arty_ddr_bios/data_mem_grain{i}" for i in range(16))
        cache_mapping = f'select -assert-count 16 {cache_memories}; setattr -set ram_style "registers" {cache_memories}; '
    if args.register_command_buffers:
        memories = re.findall(
            r"reg \[23:0\] (storage(?:_\d+)?)\[0:\d+\];", source.read_text()
        )
        assert len(memories) == 8, memories
        selection = " ".join("arty_ddr_bios/" + name for name in memories)
        cache_mapping += f'select -assert-count 8 {selection}; setattr -set ram_style "registers" {selection}; '
    if args.register_cpu_regfile or args.distributed_cpu_regfile:
        memory = "VexRiscv/RegFilePlugin_regFile"
        style = "registers" if args.register_cpu_regfile else "distributed"
        cache_mapping += f'select -assert-count 1 {memory}; setattr -set ram_style "{style}" {memory}; '
    run(
        "synthesis",
        [
            str(tc / "bin/yosys"),
            "-p",
            f"read_verilog -sv {source} {cpu} {wrapper} {hdl}; {cache_mapping}synth_xilinx -flatten -nowidelut {'-nolutram' if args.no_lutram else ''} -abc9 -arch xc7 -top board; check -assert; write_json design.json",
        ],
    )

    if args.fast_sd:
        # Check the parameter-derived FIFO modules, not merely the unused
        # generic declaration: attributes must survive hierarchy elaboration.
        import collections

        mapped = json.loads((out / "design.json").read_text())["modules"]
        fifo_counts = {
            name: dict(
                collections.Counter(cell["type"] for cell in module["cells"].values())
            )
            for name, module in mapped.items()
            if name.endswith("\\async_fifo_v")
        }
        assert len(fifo_counts) == 3, fifo_counts
        assert all(
            not any(kind.startswith(("RAM", "SRL")) for kind in counts)
            for counts in fifo_counts.values()
        ), fifo_counts
        assert sum(counts.get("FDRE", 0) for counts in fifo_counts.values()) >= 594, (
            fifo_counts
        )
        (out / "fifo-synthesis.json").write_text(
            json.dumps(fifo_counts, indent=2) + "\n"
        )

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
        assert clocks, f"No timing results for seed {seed}"
        if args.fast_sd:
            assert "fclk" in clocks and clocks["fclk"][2] == 100, clocks
        assert any(v[2] == 100 for v in clocks.values()), clocks
        assert any(abs(v[2] - sys_clk_freq / 1e6) < 0.02 for v in clocks.values()), (
            clocks
        )
        assert any(v[2] == 200 for v in clocks.values()), clocks
        return seed, clocks

    with ThreadPoolExecutor(max_workers=len(seeds)) as pool:
        candidates = list(pool.map(route, seeds))
    selected_seed, clocks = max(
        candidates, key=lambda item: min(v[0] / v[2] for v in item[1].values())
    )
    for source_name, target_name in [
        (f"route-seed-{selected_seed}.log", "route.log"),
        (f"routed-seed-{selected_seed}.json", "routed.json"),
        (f"design-seed-{selected_seed}.fasm", "design.fasm"),
    ]:
        shutil.copy2(out / source_name, out / target_name)
    (out / "placement-results.json").write_text(
        json.dumps(
            dict(selected_seed=selected_seed, candidates=dict(candidates)), indent=2
        )
        + "\n"
    )
    if args.fast_sd:
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
        (out / "output-timing.json").write_text(
            json.dumps(output_paths, indent=2) + "\n"
        )
    assert clocks and all(v[1] == "PASS" for v in clocks.values()), clocks
    assert any(v[2] == 100 for v in clocks.values()), clocks
    assert any(abs(v[2] - sys_clk_freq / 1e6) < 0.02 for v in clocks.values()), clocks
    assert any(v[2] == 200 for v in clocks.values()), clocks
    part = "xc7a35tcsg324-1"
    db = tc / "share/prjxray/artix7"
    with (out / "design.frames").open("w") as frames:
        run(
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
            stdout=frames,
        )
    run(
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
    )
    run(
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
    )
    sd_properties = {}
    if args.with_sd:
        frontend = (GATEWARE / "projects/microsd-emulator/src/main.spade").read_text()
        csd = frontend_csd(frontend, args.sd_writable, args.fast_sd)
        speed = (csd >> 96) & 255
        values = (0, 10, 12, 13, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80)
        sd_properties = dict(
            sd_csd=f"{csd:032x}",
            sd_capacity_bytes=(((csd >> 62) & 4095) + 1)
            * (1 << (((csd >> 47) & 7) + 2))
            * (1 << ((csd >> 80) & 15)),
            sd_max_clock_hz=100_000
            * 10 ** (speed & 7)
            * values[(speed >> 3) & 15]
            // 10,
        )
    (out / "result.json").write_text(
        json.dumps(
            {
                **sd_properties,
                "verified_configuration_bits": verify_frames(out),
                "bitstream_sha256": hashlib.sha256(
                    (out / "design.bit").read_bytes()
                ).hexdigest(),
                "bitstream_bytes": (out / "design.bit").stat().st_size,
                "clocks_mhz": clocks,
                "placement_seed": selected_seed,
                "nextpnr_binary_sha256": hashlib.sha256(
                    (tc / "bin/nextpnr-xilinx").read_bytes()
                ).hexdigest(),
                "negative_edge_timing_checked": args.fast_sd,
                "with_sd": args.with_sd,
                "fast_sd": args.fast_sd,
                "native_fifo_registers": args.fast_sd,
                "sd_io_slew": "FAST" if args.fast_sd else "SLOW",
                "sd_output_fabric_edge": "falling" if args.fast_sd else "rising",
                "sd_io_clock_hz": 100_000_000 if args.fast_sd else sys_clk_freq,
                "cpu_mailbox": args.cpu_mailbox,
                "no_lutram": args.no_lutram,
                "register_cache": args.register_cache,
                "registered_bank": args.registered_bank,
                "register_command_buffers": args.register_command_buffers,
                "native_bist": args.native_bist,
                "native_bist_bytes": 268435456 if args.native_bist else 0,
                "bist_detail_format": 1 if args.native_bist else 0,
                "sd_writable": args.sd_writable,
                "sys_clk_freq": sys_clk_freq,
                "reset_source": args.reset_source,
                "register_cpu_regfile": args.register_cpu_regfile,
                "distributed_cpu_regfile": args.distributed_cpu_regfile,
                "configuration": args.config.read_text(),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

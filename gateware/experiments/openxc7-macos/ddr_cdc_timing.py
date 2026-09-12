"""Check routed Gray-pointer crossings against their source clock periods.

This is a bounded delay check for the three known native FIFOs, not a complete
CDC or external-I/O static timing analysis. SDF comes from the same route as
its packed JSON; reloading routed Xilinx JSON is unsupported by this toolchain.
"""

import json
import re
from pathlib import Path


def verify_native_cdc(routed: Path, sdf: Path, sys_clk_freq=80_000_000):
    modules = json.loads(routed.read_text())["modules"]
    if len(modules) != 1:
        raise RuntimeError("Check failed: len(modules) == 1")
    module = next(iter(modules.values()))
    nets = module["netnames"]
    clock_periods = {
        nets["fclk"]["bits"][0]: 10_000,
        nets["dclk"]["bits"][0]: 1e12 / sys_clk_freq,
    }
    delays = {}
    sdf_text = sdf.read_text()
    if "(TIMESCALE 1ps)" not in sdf_text:
        raise RuntimeError("Check failed: '(TIMESCALE 1ps)' in sdf_text")
    for a, b, rise, fall in re.findall(
        r"\(INTERCONNECT (\S+) (\S+) \(([\d:.]+)\) \(([\d:.]+)\)\)", sdf_text
    ):
        a, b = (re.sub(r"\\(.)", r"\1", name) for name in (a, b))
        delays[a, b] = max(float(x) for group in (rise, fall) for x in group.split(":"))
    pointers = {
        name: data["bits"][0]
        for name, data in nets.items()
        if re.fullmatch(
            r"sd_memory_crossing\.async_fifo_[012]\.async_fifo_v_0\.g[wr]sync(?:\[0\])?",
            name,
        )
    }
    if len(pointers) != 6:
        raise RuntimeError(
            f"Expected 6 registered Gray-pointer bits, found {len(pointers)}"
        )
    terminals = {bit: [] for bit in pointers.values()}
    for name, cell in module["cells"].items():
        for port, bits in cell["connections"].items():
            for bit in bits:
                if bit in terminals:
                    terminals[bit].append((name, port, cell))
    result = []
    for name, bit in sorted(pointers.items()):
        source = [(n, p, c) for n, p, c in terminals[bit] if p == "Q"]
        target = [(n, p, c) for n, p, c in terminals[bit] if p == "D"]
        if not (len(source) == len(target) == 1 and len(terminals[bit]) == 2):
            raise RuntimeError(name)
        sn, sp, sc = source[0]
        tn, tp, tc = target[0]
        if not (
            sc["type"].startswith("SLICE_FF") and tc["type"].startswith("SLICE_FF")
        ):
            raise RuntimeError(name)
        source_clock = sc["connections"]["CK"][0]
        target_clock = tc["connections"]["CK"][0]
        if not (source_clock != target_clock and target_clock in clock_periods):
            raise RuntimeError(name)
        period = clock_periods[source_clock]
        delay = delays[sn + "/" + sp, tn + "/" + tp]
        # Reserve 20% of a source period for clock-to-Q, setup and skew. Keeping
        # every path below one period also bounds Gray-bus inter-bit skew.
        if not (delay < 0.8 * period):
            raise RuntimeError((name, delay, period))
        result.append(dict(net=name, route_delay_ps=delay, source_period_ps=period))
    return result

"""Check routed Gray-pointer crossings against their source clock periods.

This checks intended clock edges, two-stage topology, and bounded delay for the native FIFOs and optional Ethernet queues. It is not a complete
CDC or external-I/O static timing analysis. SDF comes from the same route as
its packed JSON; reloading routed Xilinx JSON is unsupported by this toolchain.
"""

import json
import re
from pathlib import Path


def verify_native_cdc(
    routed: Path, sdf: Path, sys_clk_freq=80_000_000, *, ethernet=False
):
    modules = json.loads(routed.read_text())["modules"]
    if len(modules) != 1:
        raise RuntimeError("Check failed: len(modules) == 1")
    module = next(iter(modules.values()))
    nets = module["netnames"]
    clock_periods = {
        nets["fclk"]["bits"][0]: 10_000,
        nets["dclk"]["bits"][0]: 1e12 / sys_clk_freq,
    }
    if ethernet:
        clock_periods.update(
            {
                nets[name]["bits"][0]: 40_000
                for name in ("eth_rx_global", "eth_tx_global")
            }
        )
    delays = {}
    sdf_text = sdf.read_text()
    if "(TIMESCALE 1ps)" not in sdf_text:
        raise RuntimeError("Check failed: '(TIMESCALE 1ps)' in sdf_text")
    for a, b, rise, fall in re.findall(
        r"\(INTERCONNECT (\S+) (\S+) \(([\d:.]+)\) \(([\d:.]+)\)\)", sdf_text
    ):
        a, b = (re.sub(r"\\(.)", r"\1", name) for name in (a, b))
        delays[a, b] = max(float(x) for group in (rise, fall) for x in group.split(":"))
    # Each entry names the queue, pointer width, and owning clock edges.
    # TX publishes in fabric and consumes on the falling-edge launch clock.
    groups = {}
    for fifo in range(3):
        write, read = (
            (("dclk", False), ("fclk", False))
            if fifo == 2
            else (("fclk", False), ("dclk", False))
        )
        prefix = f"sd_memory_crossing.async_fifo_{fifo}.async_fifo_v_0."
        groups[prefix + "gwsync"] = (1, write, read)
        groups[prefix + "grsync"] = (1, read, write)
    if ethernet:
        groups.update(
            {
                "sd.network_frontend_0.frame_receiver_0.published_gray": (
                    4,
                    ("eth_rx_global", False),
                    ("fclk", False),
                ),
                "sd.network_frontend_0.frame_receiver_0.consumed_gray": (
                    4,
                    ("fclk", False),
                    ("eth_rx_global", False),
                ),
                "sd.network_frontend_0.frame_transmitter_0.published_gray": (
                    2,
                    ("fclk", False),
                    ("eth_tx_global", True),
                ),
                "sd.network_frontend_0.frame_transmitter_0.consumed_gray": (
                    2,
                    ("eth_tx_global", True),
                    ("fclk", False),
                ),
            }
        )
    pointers = {}
    for prefix, (width, source_domain, target_domain) in groups.items():
        lanes = []
        for name, data in nets.items():
            match = re.fullmatch(re.escape(prefix) + r"(?:\[(\d+)\])?", name)
            if match:
                if len(data["bits"]) != 1:
                    raise RuntimeError(f"Expected scalar mapped pointer: {name}")
                lanes.append(int(match[1] or 0))
                pointers[name] = (data["bits"][0], source_domain, target_domain)
        if sorted(lanes) != list(range(width)):
            raise RuntimeError(
                f"Expected {width} registered pointer bits for {prefix}, found lanes {lanes}"
            )
    terminals = {}
    for name, cell in module["cells"].items():
        for port, bits in cell["connections"].items():
            for bit in bits:
                terminals.setdefault(bit, []).append((name, port, cell))

    def domain(cell):
        return (
            cell["connections"]["CK"][0],
            bool(int(str(cell.get("parameters", {}).get("IS_CLK_INVERTED", "0")), 2)),
        )

    def expected_domain(value):
        return nets[value[0]]["bits"][0], value[1]

    result = []
    for name, (bit, source_domain, target_domain) in sorted(pointers.items()):
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
        source_clock, _ = domain(sc)
        if domain(sc) != expected_domain(source_domain) or domain(
            tc
        ) != expected_domain(target_domain):
            raise RuntimeError(
                f"Unexpected clock/edge for {name}: expected {source_domain} -> {target_domain}"
            )
        first_output = tc["connections"].get("Q", [])
        if len(first_output) != 1:
            raise RuntimeError(f"Missing first synchronizer output for {name}")
        following = [
            entry for entry in terminals[first_output[0]] if entry[:2] != (tn, "Q")
        ]
        if len(following) != 1:
            raise RuntimeError(
                f"First synchronizer stage has unexpected fanout for {name}"
            )
        second_name, second_port, second = following[0]
        if (
            second_port != "D"
            or not second["type"].startswith("SLICE_FF")
            or domain(second) != domain(tc)
        ):
            raise RuntimeError(
                f"Missing same-domain second synchronizer stage for {name}"
            )
        period = clock_periods[source_clock]
        delay = delays[sn + "/" + sp, tn + "/" + tp]
        # Reserve 20% of a source period for clock-to-Q, setup and skew. Keeping
        # every path below one period also bounds Gray-bus inter-bit skew.
        if not (delay < 0.8 * period):
            raise RuntimeError((name, delay, period))
        result.append(
            dict(
                net=name,
                route_delay_ps=delay,
                source_period_ps=period,
                second_stage=second_name,
            )
        )
    return result

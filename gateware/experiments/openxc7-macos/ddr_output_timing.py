"""Check the fast SD data path has no mux after its final pad registers.

This bounded routing check complements, but does not replace, hardware I/O
qualification; external buffers, wiring and host sampling are not modeled here.
"""

import json
import re
from pathlib import Path


def verify_direct_sd_outputs(routed: Path, sdf: Path):
    modules = json.loads(routed.read_text())["modules"]
    if len(modules) != 1:
        raise RuntimeError("Check failed: len(modules) == 1")
    module = next(iter(modules.values()))
    cells = module["cells"]
    clock = module["netnames"]["fclk"]["bits"][0]
    outputs = {}
    for name, cell in cells.items():
        match = re.search(r"\.pmod\[([01237])\].*OBUFT$", name)
        if match:
            outputs[int(match[1])] = (name, cell["connections"]["IN"][0])
    if set(outputs) != {0, 1, 2, 3, 7}:
        raise RuntimeError(outputs)
    drivers = {}
    for name, cell in cells.items():
        for port, direction in cell["port_directions"].items():
            if direction == "output":
                for bit in cell["connections"][port]:
                    drivers[bit] = (name, port, cell)
    delays = {}
    text = sdf.read_text()
    if "(TIMESCALE 1ps)" not in text:
        raise RuntimeError("Check failed: '(TIMESCALE 1ps)' in text")
    for a, b, rise, fall in re.findall(
        r"\(INTERCONNECT (\S+) (\S+) \(([\d:.]+)\) \(([\d:.]+)\)\)", text
    ):
        a, b = (re.sub(r"\\(.)", r"\1", name) for name in (a, b))
        delays[a, b] = max(float(v) for group in (rise, fall) for v in group.split(":"))
    result = []
    for pin, (target, bit) in sorted(outputs.items()):
        source, port, cell = drivers[bit]
        if not (cell["type"].startswith("SLICE_FF") and port == "Q"):
            raise RuntimeError((pin, source, cell["type"]))
        if cell["connections"]["CK"] != [clock]:
            raise RuntimeError(source)
        if int(cell["parameters"].get("IS_CLK_INVERTED", "0"), 2) != 1:
            raise RuntimeError(source)
        delay = delays[source + "/Q", target + "/IN"]
        if not (delay < 4000):
            raise RuntimeError((pin, delay))
        result.append(
            dict(
                pmod_pin_index=pin,
                pmod_pin={0: 1, 1: 2, 2: 3, 3: 4, 7: 10}[pin],
                signal={0: "DAT2", 1: "DAT3", 2: "CMD", 3: "DAT0", 7: "DAT1"}[pin],
                register=source,
                route_delay_ps=delay,
            )
        )
    return result

"""Check the fast SD data path has no mux after its final pad registers.

This bounded routing check complements, but does not replace, hardware I/O
qualification; external buffers, wiring and host sampling are not modeled here.
"""

import json
import re
from pathlib import Path


def verify_direct_sd_outputs(
    routed: Path, sdf: Path, *, pins=frozenset({0, 1, 2, 3, 7}), inverted=True
):
    modules = json.loads(routed.read_text())["modules"]
    if len(modules) != 1:
        raise RuntimeError("Check failed: len(modules) == 1")
    module = next(iter(modules.values()))
    cells = module["cells"]
    clock = module["netnames"]["fclk"]["bits"][0]
    outputs = {}
    for name, cell in cells.items():
        match = re.search(r"\.pmod\[([01237])\].*OBUFT$", name)
        if match and int(match[1]) in pins:
            outputs[int(match[1])] = (name, cell["connections"]["IN"][0])
    if set(outputs) != set(pins):
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
        if bool(int(cell["parameters"].get("IS_CLK_INVERTED", "0"), 2)) != inverted:
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


def profile_output_checks(*, slow_mmc, h700_mmc=False, mmc_only=False):
    """The pins each SD profile drives directly, grouped by launch edge.

    Returns (pins, inverted) pairs for `verify_direct_sd_outputs`. The build
    and the seed search both ask this, so a seed the search calls usable is one
    the build will accept.
    """
    if h700_mmc or mmc_only:
        # Legacy-MMC profiles keep the same-edge command path for
        # identification while data uses opposite-edge launch.
        return [(frozenset({2}), False), (frozenset({0, 1, 3, 7}), True)]
    if slow_mmc:
        return [(frozenset({2}), False)]
    return [(frozenset({0, 1, 2, 3, 7}), True)]


def verify_profile_outputs(routed: Path, sdf: Path, **profile):
    """Check every directly driven SD output for the profile's launch edges."""
    paths = []
    for pins, inverted in profile_output_checks(**profile):
        paths += verify_direct_sd_outputs(routed, sdf, pins=pins, inverted=inverted)
    return paths

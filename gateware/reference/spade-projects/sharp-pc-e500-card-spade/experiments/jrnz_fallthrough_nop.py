#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


DEFAULT_COUNT = 64


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def parse_count(argv: list[str], *, index: int = 2) -> int:
    if len(argv) <= index:
        return DEFAULT_COUNT
    value = int(argv[index], 0)
    if not 1 <= value <= 256:
        raise SystemExit("count must be between 1 and 256")
    return value


def build_asm(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0",
        "    CMP A, 0",
    ]
    for _ in range(count):
        lines.append("    JRNZ +1")
        lines.append("    NOP")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)


def build_plan(count: int) -> dict[str, object]:
    return {
        "name": "jrnz_fallthrough_nop",
        "asm_text": build_asm(count),
        "fill_experiment_region": False,
        "timing": 5,
        "control_timing": 10,
        "timeout_s": 2.0,
        "start_tag": 0x3D,
        "stop_tag": 0x3E,
        "flags": 0,
        "args": [],
    }


def parse_result(raw_result_path: Path, count: int) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    measurements = raw.get("measurement", [])
    first = measurements[0] if measurements else None
    ticks_per_step = None
    if first is not None and count:
        ticks_per_step = first["ticks"] / count
    return {
        "count": count,
        "measurement_count": len(measurements),
        "first_measurement": first,
        "ticks_per_step": ticks_per_step,
        "uart_lines": raw.get("uart_lines", []),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: jrnz_fallthrough_nop.py plan|parse [args...]")
    command = argv[1]
    if command == "plan":
        return emit_json(build_plan(parse_count(argv)))
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: jrnz_fallthrough_nop.py parse RESULT.json [count]")
        count = parse_count(argv, index=3)
        return emit_json(parse_result(Path(argv[2]), count))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

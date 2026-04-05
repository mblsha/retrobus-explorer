#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASM_SOURCE = PROJECT_ROOT / "asm" / "card_rom_wait_probe.asm"
DEFAULT_LOOPS = 0x0100


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def parse_loops(argv: list[str], *, index: int = 2) -> int:
    if len(argv) <= index:
        return DEFAULT_LOOPS
    value = int(argv[index], 0)
    if not 0 <= value <= 0xFFFF:
        raise SystemExit("WAIT loop count must fit in 16 bits")
    return value


def has_flag(argv: list[str], flag: str) -> bool:
    return flag in argv[2:]


def ft_capture_enabled(argv: list[str]) -> bool:
    if has_flag(argv, "--no-ft-capture"):
        return False
    return True


def build_plan(loops: int, *, ft_capture: bool = False) -> dict[str, object]:
    return {
        "name": "wait_probe",
        "asm_source": str(ASM_SOURCE),
        "timing": 5,
        "control_timing": 10,
        "timeout_s": max(2.0, loops / 20000.0),
        "start_tag": 0x21,
        "stop_tag": 0x22,
        "flags": 0,
        "ft_capture": ft_capture,
        "args": [
            loops & 0xFF,
            (loops >> 8) & 0xFF,
        ],
    }


def parse_result(raw_result_path: Path, loops: int) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    measurements = raw.get("measurement", [])
    first = measurements[0] if measurements else None
    ticks_per_loop = None
    if first is not None and loops:
        ticks_per_loop = first["ticks"] / loops
    return {
        "loops": loops,
        "measurement_count": len(measurements),
        "first_measurement": first,
        "ticks_per_loop": ticks_per_loop,
        "uart_lines": raw.get("uart_lines", []),
        "ft_capture": raw.get("ft_capture"),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: wait_probe.py plan|parse [args...]")
    command = argv[1]
    if command == "plan":
        return emit_json(build_plan(parse_loops(argv), ft_capture=ft_capture_enabled(argv)))
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: wait_probe.py parse RESULT.json [loops]")
        loops = parse_loops(argv, index=3)
        return emit_json(parse_result(Path(argv[2]), loops))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

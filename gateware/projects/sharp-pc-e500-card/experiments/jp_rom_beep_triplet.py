#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASM_SOURCE = PROJECT_ROOT / "asm" / "card_rom_jp_rom_beep_triplet.asm"


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def build_plan() -> dict[str, object]:
    return {
        "name": "jp_rom_beep_triplet",
        "asm_source": str(ASM_SOURCE),
        "timing": 5,
        "control_timing": 10,
        "timeout_s": 5.0,
        "start_tag": 0xD5,
        "stop_tag": 0xD6,
        "flags": 0,
        "ft_capture": True,
        "args": [],
    }


def parse_result(raw_result_path: Path) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    measurements = raw.get("measurement", [])
    first = measurements[0] if measurements else None
    ft_capture = raw.get("ft_capture") or {}
    return {
        "measurement_count": len(measurements),
        "first_measurement": first,
        "uart_lines": raw.get("uart_lines", []),
        "ft_word_count": ft_capture.get("word_count"),
        "ft_raw_bytes": ft_capture.get("raw_bytes"),
        "execution_preview": ft_capture.get("execution_preview"),
        "measurement_preview": ft_capture.get("measurement_preview"),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: jp_rom_beep_triplet.py plan|parse [args...]")
    command = argv[1]
    if command == "plan":
        return emit_json(build_plan())
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: jp_rom_beep_triplet.py parse RESULT.json")
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

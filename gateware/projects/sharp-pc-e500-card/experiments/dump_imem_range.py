#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def parse_hex(text: str) -> int:
    return int(text, 0) & 0xFF


def operand_for_imem(addr: int) -> str:
    aliases = {
        0xD4: "BL",
        0xD5: "BH",
        0xD6: "CL",
        0xD7: "CH",
        0xD8: "DL",
        0xD9: "DH",
        0xDA: "SI",
        0xDB: "SI1",
        0xDC: "SI2",
        0xDD: "DI",
        0xDE: "DI1",
        0xDF: "DI2",
        0xE6: "IOCS_WS",
        0xE7: "IOCS_WS1",
        0xE8: "IOCS_WS2",
    }
    return aliases.get(addr, f"0x{addr:02X}")


def build_asm(start: int, count: int) -> str:
    lines: list[str] = [
        ".ORG 0x10100",
        "",
        "start:",
        "    PUSHU F",
        "    PUSHU A",
        "    PUSHU BA",
        "    PUSHU X",
        "    PUSHU Y",
        "",
        "    MV Y, 0x1FFF1",
    ]

    for index in range(count):
        addr = (start + index) & 0xFF
        operand = operand_for_imem(addr)
        lines.extend(
            [
                "",
                f"    MV X, prefix_{addr:02X}",
                "    CALL emit_string",
                f"    MV A, ({operand})",
                "    CALL emit_hex_byte",
                "    CALL emit_crlf",
            ]
        )

    lines.extend(
        [
            "",
            "    POPU Y",
            "    POPU X",
            "    POPU BA",
            "    POPU A",
            "    POPU F",
            "    RETF",
            "",
            "emit_crlf:",
            "    MV A, 0x0D",
            "    CALL emit_char",
            "    MV A, 0x0A",
            "    CALL emit_char",
            "    RET",
            "",
            "emit_string:",
            "    MV A, [X++]",
            "    CMP A, 0x00",
            "    JPZ emit_string_done",
            "    CALL emit_char",
            "    JP emit_string",
            "",
            "emit_string_done:",
            "    RET",
            "",
            "emit_hex_byte:",
            "    MV B, A",
            "    SWAP A",
            "    AND A, 0x0F",
            "    CALL emit_hex_nibble",
            "    MV A, B",
            "    AND A, 0x0F",
            "    CALL emit_hex_nibble",
            "    RET",
            "",
            "emit_hex_nibble:",
            "    ADD A, 0x30",
            "    CMP A, 0x3A",
            "    JPC emit_hex_nibble_done",
            "    ADD A, 0x07",
            "emit_hex_nibble_done:",
            "    CALL emit_char",
            "    RET",
            "",
            "emit_char:",
            "    MV [Y], A",
            "    NOP",
            "    NOP",
            "    NOP",
            "    RET",
        ]
    )

    for index in range(count):
        addr = (start + index) & 0xFF
        lines.extend(
            [
                "",
                f"prefix_{addr:02X}:",
                f'    defm "XR,IM,{addr:02X},"',
                "    defb 0x00",
            ]
        )

    return "\n".join(lines) + "\n"


def build_plan(start: int, count: int) -> dict[str, object]:
    return {
        "name": f"dump_imem_range_{start:02X}_{count:02X}",
        "asm_text": build_asm(start, count),
        "timing": 5,
        "control_timing": 10,
        "timeout_s": 10.0,
        "start_tag": 0xD1,
        "stop_tag": 0xD2,
        "flags": 0,
        "ft_capture": False,
        "args": [],
    }


def parse_result(raw_result_path: Path) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    uart_lines = raw.get("uart_lines", [])
    pairs: list[dict[str, int]] = []
    for line in uart_lines:
        if not line.startswith("XR,IM,"):
            continue
        parts = line.split(",")
        if len(parts) != 4:
            continue
        pairs.append({"index": int(parts[2], 16), "value": int(parts[3], 16)})
    return {
        "uart_lines": uart_lines,
        "pairs": pairs,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: dump_imem_range.py plan|parse [args...]")
    command = argv[1]
    if command == "plan":
        start = parse_hex(argv[2]) if len(argv) >= 3 else 0x00
        count = parse_hex(argv[3]) if len(argv) >= 4 else 0x10
        if count == 0:
            raise SystemExit("count must be non-zero")
        if start + count > 0xEC:
            raise SystemExit("range must stay below 0xEC to avoid SFRs")
        return emit_json(build_plan(start, count))
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: dump_imem_range.py parse RESULT.json")
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

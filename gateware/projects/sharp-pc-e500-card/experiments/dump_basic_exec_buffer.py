#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def build_asm(byte_count: int) -> str:
    lines: list[str] = [
        ".ORG 0x10100",
        "",
        "start:",
        "    PUSHU F",
        "    PUSHU BA",
        "    PUSHU X",
        "    PUSHU Y",
        "",
        "    MV Y, 0x1FFF1",
        "",
        '    MV X, d1_prefix',
        "    CALL emit_string",
        "    MV X, (0xD1)",
        "    MV (0x10), X",
        "    MV A, (0xD3)",
        "    AND A, 0x0F",
        "    CALL emit_hex_nibble",
        "    MV A, (0x11)",
        "    CALL emit_hex_byte",
        "    MV A, (0x10)",
        "    CALL emit_hex_byte",
        "    CALL emit_crlf",
        "",
        '    MV X, ptr_prefix',
        "    CALL emit_string",
        "    MV X, [(0xD1)+0x05]",
        "    MV (0x10), X",
        "    MV A, (0x12)",
        "    AND A, 0x0F",
        "    CALL emit_hex_nibble",
        "    MV A, (0x11)",
        "    CALL emit_hex_byte",
        "    MV A, (0x10)",
        "    CALL emit_hex_byte",
        "    CALL emit_crlf",
        "",
        "    MV X, [(0xD1)+0x05]",
    ]

    for index in range(byte_count):
        lines.extend(
            [
                "",
                f"    MV X, byte_prefix_{index:02X}",
                "    CALL emit_string",
                "    MV A, [X++]",
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
            "emit_char:",
            "    MV [Y], A",
            "    NOP",
            "    NOP",
            "    NOP",
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
            "d1_prefix:",
            '    defm "XR,BUF,D1,"',
            "    defb 0x00",
            "",
            "ptr_prefix:",
            '    defm "XR,BUF,PTR,"',
            "    defb 0x00",
        ]
    )

    for index in range(byte_count):
        lines.extend(
            [
                "",
                f"byte_prefix_{index:02X}:",
                f'    defm "XR,BUF,{index:02X},"',
                "    defb 0x00",
            ]
        )

    return "\n".join(lines) + "\n"


def build_plan(byte_count: int) -> dict[str, object]:
    return {
        "name": f"dump_basic_exec_buffer_{byte_count:02X}",
        "asm_text": build_asm(byte_count),
        "timing": 5,
        "control_timing": 10,
        "timeout_s": 10.0,
        "start_tag": 0xE1,
        "stop_tag": 0xE2,
        "flags": 0,
        "ft_capture": False,
        "args": [],
    }


def parse_result(raw_result_path: Path) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    uart_lines = raw.get("uart_lines", [])
    d1_ptr = None
    ptr = None
    data: list[dict[str, int]] = []
    for line in uart_lines:
        if line.startswith("XR,BUF,D1,"):
            d1_ptr = int(line.rsplit(",", 1)[-1], 16)
            continue
        if line.startswith("XR,BUF,PTR,"):
            ptr = int(line.rsplit(",", 1)[-1], 16)
            continue
        if not line.startswith("XR,BUF,"):
            continue
        parts = line.split(",")
        if len(parts) != 4:
            continue
        data.append({"index": int(parts[2], 16), "value": int(parts[3], 16)})
    return {
        "uart_lines": uart_lines,
        "d1_ptr": d1_ptr,
        "ptr": ptr,
        "data": data,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: dump_basic_exec_buffer.py plan|parse [byte_count]")
    command = argv[1]
    if command == "plan":
        byte_count = int(argv[2], 0) if len(argv) >= 3 else 16
        if byte_count <= 0 or byte_count > 32:
            raise SystemExit("byte_count must be in 1..32")
        return emit_json(build_plan(byte_count))
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: dump_basic_exec_buffer.py parse RESULT.json")
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

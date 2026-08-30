#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


OFFSETS = [0x47, 0x48, 0x49, 0x4A]


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def build_asm() -> str:
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
        "",
        "    MV X, ws_prefix",
        "    CALL emit_string",
        "    MV X, (IOCS_WS)",
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
        "    MV X, ptr28_prefix",
        "    CALL emit_string",
        "    MV X, (0x28)",
        "    MV (0x10), X",
        "    MV A, (0x2A)",
        "    AND A, 0x0F",
        "    CALL emit_hex_nibble",
        "    MV A, (0x11)",
        "    CALL emit_hex_byte",
        "    MV A, (0x10)",
        "    CALL emit_hex_byte",
        "    CALL emit_crlf",
    ]

    for offset in OFFSETS:
        lines.extend(
            [
                "",
                f"    MV X, prefix_{offset:02X}",
                "    CALL emit_string",
                f"    MV A, [(IOCS_WS)+0x{offset:02X}]",
                "    CALL emit_hex_byte",
                "    CALL emit_crlf",
                "",
                f"    MV X, prefix28_{offset:02X}",
                "    CALL emit_string",
                f"    MV A, [(0x28)+0x{offset:02X}]",
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
            "ws_prefix:",
            '    defm "XR,IOCS,WS,"',
            "    defb 0x00",
            "",
            "ptr28_prefix:",
            '    defm "XR,IOCS,28,"',
            "    defb 0x00",
        ]
    )

    for offset in OFFSETS:
        lines.extend(
            [
                "",
                f"prefix_{offset:02X}:",
                f'    defm "XR,IOCS,{offset:02X},"',
                "    defb 0x00",
                "",
                f"prefix28_{offset:02X}:",
                f'    defm "XR,28,{offset:02X},"',
                "    defb 0x00",
            ]
        )

    return "\n".join(lines) + "\n"


def build_plan() -> dict[str, object]:
    return {
        "name": "dump_iocs_exec_state",
        "asm_text": build_asm(),
        "timing": 5,
        "control_timing": 10,
        "timeout_s": 10.0,
        "start_tag": 0xE3,
        "stop_tag": 0xE4,
        "flags": 0,
        "ft_capture": False,
        "args": [],
    }


def parse_result(raw_result_path: Path) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    uart_lines = raw.get("uart_lines", [])
    ws = None
    ptr28 = None
    values: dict[str, int] = {}
    values28: dict[str, int] = {}
    for line in uart_lines:
        if line.startswith("XR,IOCS,WS,"):
            ws = int(line.rsplit(",", 1)[-1], 16)
            continue
        if line.startswith("XR,IOCS,28,"):
            ptr28 = int(line.rsplit(",", 1)[-1], 16)
            continue
        if line.startswith("XR,28,"):
            parts = line.split(",")
            if len(parts) == 4:
                values28[parts[2]] = int(parts[3], 16)
            continue
        if not line.startswith("XR,IOCS,"):
            continue
        parts = line.split(",")
        if len(parts) != 4:
            continue
        values[parts[2]] = int(parts[3], 16)
    return {
        "uart_lines": uart_lines,
        "ws": ws,
        "ptr28": ptr28,
        "values": values,
        "values28": values28,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: dump_iocs_exec_state.py plan|parse RESULT.json")
    command = argv[1]
    if command == "plan":
        return emit_json(build_plan())
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: dump_iocs_exec_state.py parse RESULT.json")
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

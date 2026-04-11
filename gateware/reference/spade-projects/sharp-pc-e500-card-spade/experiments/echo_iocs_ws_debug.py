#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


ASM_TEXT = r"""
.ORG 0x10100

start:
    PUSHU F
    PUSHU BA
    PUSHU X
    PUSHU Y

    MV Y, 0x1FFF1

    MV X, prefix_iocs
    CALL emit_string
    MV A, (IOCS_WS2)
    AND A, 0x0F
    CALL emit_hex_nibble
    MV A, (IOCS_WS1)
    CALL emit_hex_byte
    MV A, (IOCS_WS)
    CALL emit_hex_byte

    MV X, sep_bfd
    CALL emit_string
    MV A, [0x0BFD19]
    AND A, 0x0F
    CALL emit_hex_nibble
    MV A, [0x0BFD18]
    CALL emit_hex_byte
    MV A, [0x0BFD17]
    CALL emit_hex_byte

    CALL emit_crlf

    POPU Y
    POPU X
    POPU BA
    POPU F
    RETF

emit_crlf:
    MV A, 0x0D
    MV [Y], A
    NOP
    NOP
    MV A, 0x0A
    MV [Y], A
    RET

emit_char:
    MV [Y], A
    NOP
    NOP
    NOP
    RET

emit_string:
    MV A, [X++]
    CMP A, 0x00
    JPZ emit_string_done
    CALL emit_char
    JP emit_string

emit_string_done:
    RET

emit_hex_byte:
    MV B, A
    SWAP A
    AND A, 0x0F
    CALL emit_hex_nibble
    MV A, B
    AND A, 0x0F
    CALL emit_hex_nibble
    RET

emit_hex_nibble:
    ADD A, 0x30
    CMP A, 0x3A
    JPC emit_hex_nibble_done
    ADD A, 0x07
emit_hex_nibble_done:
    CALL emit_char
    RET

prefix_iocs:
    defm "XR,VALUE,E6,"
    defb 0x00

sep_bfd:
    defm ",BFD17,"
    defb 0x00
"""


def build_plan() -> dict[str, object]:
    return {
        "name": "echo_iocs_ws_debug",
        "asm_text": ASM_TEXT,
        "timing": 5,
        "control_timing": 10,
        "timeout_s": 2.0,
        "start_tag": 0xC1,
        "stop_tag": 0xC2,
        "flags": 0,
        "ft_capture": False,
        "args": [],
    }


def parse_result(raw_result_path: Path) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    xr_lines = raw.get("uart_lines", [])
    debug_line = None
    for line in xr_lines:
        if line.startswith("XR,VALUE,E6,"):
            debug_line = line
            break
    return {
        "uart_lines": xr_lines,
        "debug_line": debug_line,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: echo_iocs_ws_debug.py plan|parse [args...]")
    command = argv[1]
    if command == "plan":
        return emit_json(build_plan())
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: echo_iocs_ws_debug.py parse RESULT.json")
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

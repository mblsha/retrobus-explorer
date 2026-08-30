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
    MV X, prefix
    CALL emit_string

    MV X, (IOCS_WS)
    MV (0x10), X

    MV A, (0x12)
    AND A, 0x0F
    CALL emit_hex_nibble

    MV A, (0x11)
    CALL emit_hex_byte

    MV A, (0x10)
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

prefix:
    defm "XR,VALUE,IOCS_WS,"
    defb 0x00
"""


def build_plan() -> dict[str, object]:
    return {
        "name": "echo_iocs_ws",
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
    iocs_ws = None
    for line in xr_lines:
        if line.startswith("XR,VALUE,IOCS_WS,"):
            iocs_ws = line.rsplit(",", 1)[-1]
            break
    measurements = raw.get("measurement", [])
    first = measurements[0] if measurements else None
    return {
        "uart_lines": xr_lines,
        "iocs_ws": iocs_ws,
        "first_measurement": first,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: echo_iocs_ws.py plan|parse [args...]")
    command = argv[1]
    if command == "plan":
        return emit_json(build_plan())
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit("usage: echo_iocs_ws.py parse RESULT.json")
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

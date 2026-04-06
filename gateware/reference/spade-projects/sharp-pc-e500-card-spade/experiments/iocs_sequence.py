#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


EXPERIMENT_BASE = 0x10100
IOCS_ENTRY = 0xFFFE8
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

BYTE_REGS = {
    "a": "A",
    "bl": "(BL)",
    "bh": "(BH)",
    "cl": "CL",
    "ch": "CH",
    "il": "IL",
}

WORD_MVW_REGS = {
    "cx": "(CL)",
}

PTR_REGS = {
    "x": "X",
}


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def usage() -> str:
    return (
        "usage:\n"
        "  iocs_sequence.py plan SPEC.json\n"
        "  iocs_sequence.py parse RESULT.json\n"
    )


def parse_int(value: Any) -> int:
    if isinstance(value, bool):
        raise SystemExit(f"boolean is not a valid integer value: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise SystemExit(f"unsupported integer value: {value!r}")


def normalize_text_bytes(text: str) -> list[int]:
    try:
        encoded = text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SystemExit(f"text must be ASCII for now: {text!r}") from exc
    return list(encoded)


def load_spec(spec_path: Path) -> dict[str, Any]:
    resolved_path = resolve_spec_path(spec_path)
    raw = json.loads(resolved_path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit("top-level spec must be a JSON object")
    raw["_resolved_spec_path"] = str(resolved_path)
    return raw


def resolve_spec_path(spec_path: Path) -> Path:
    candidates = []
    if spec_path.is_absolute():
        candidates.append(spec_path)
    else:
        candidates.append(Path.cwd() / spec_path)
        candidates.append(SCRIPT_DIR / spec_path)
        candidates.append(PROJECT_DIR / spec_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit(f"spec file not found: {spec_path}")


def build_data_block(label: str, data_spec: Any) -> tuple[str, list[int]]:
    if isinstance(data_spec, str):
        return label, normalize_text_bytes(data_spec)
    if isinstance(data_spec, list):
        return label, [parse_int(item) & 0xFF for item in data_spec]
    if isinstance(data_spec, dict):
        if "ascii" in data_spec:
            return label, normalize_text_bytes(str(data_spec["ascii"]))
        if "bytes" in data_spec:
            values = data_spec["bytes"]
            if not isinstance(values, list):
                raise SystemExit(f"data.{label}.bytes must be a list")
            return label, [parse_int(item) & 0xFF for item in values]
    raise SystemExit(f"unsupported data block for {label!r}: {data_spec!r}")


def emit_loads(lines: list[str], call_spec: dict[str, Any], data_labels: set[str]) -> None:
    for key, operand in BYTE_REGS.items():
        if key in call_spec:
            value = parse_int(call_spec[key]) & 0xFF
            lines.append(f"    MV {operand}, 0x{value:02X}")

    for key, operand in WORD_MVW_REGS.items():
        if key in call_spec:
            value = parse_int(call_spec[key]) & 0xFFFF
            lines.append(f"    MVW {operand}, 0x{value:04X}")

    for key, operand in PTR_REGS.items():
        if key not in call_spec:
            continue
        target = call_spec[key]
        if isinstance(target, str) and target in data_labels:
            lines.append(f"    MV {operand}, {target}")
            continue
        value = parse_int(target) & 0xFFFFFF
        lines.append(f"    MV {operand}, 0x{value:06X}")

    if "y" in call_spec:
        value = parse_int(call_spec["y"]) & 0xFFFF
        lines.append(f"    MV Y, 0x{value:04X}")


def build_asm_text(spec: dict[str, Any]) -> str:
    calls = spec.get("calls")
    if not isinstance(calls, list) or not calls:
        raise SystemExit("spec.calls must be a non-empty list")

    data_spec = spec.get("data", {})
    if not isinstance(data_spec, dict):
        raise SystemExit("spec.data must be an object when present")

    data_blocks: list[tuple[str, list[int]]] = []
    data_labels: set[str] = set()
    for label, block in data_spec.items():
        if not isinstance(label, str) or not label:
            raise SystemExit(f"invalid data label: {label!r}")
        normalized_label, payload = build_data_block(label, block)
        data_blocks.append((normalized_label, payload))
        data_labels.add(normalized_label)

    lines = [f".ORG 0x{EXPERIMENT_BASE:05X}", "", "start:"]

    defaults = spec.get("defaults", {})
    if defaults:
        if not isinstance(defaults, dict):
            raise SystemExit("spec.defaults must be an object")
        emit_loads(lines, defaults, data_labels)

    for index, item in enumerate(calls):
        if not isinstance(item, dict):
            raise SystemExit(f"spec.calls[{index}] must be an object")
        call_spec = dict(item)

        text_value = call_spec.pop("text", None)
        if text_value is not None:
            label = f"call_{index}_text"
            if label in data_labels:
                raise SystemExit(f"duplicate generated data label {label!r}")
            data_label, payload = build_data_block(label, text_value)
            data_blocks.append((data_label, payload))
            data_labels.add(data_label)
            call_spec.setdefault("x", data_label)
            call_spec.setdefault("y", len(payload))

        if "il" not in call_spec:
            raise SystemExit(f"spec.calls[{index}] is missing required field 'il'")

        emit_loads(lines, call_spec, data_labels)
        lines.append(f"    CALLF 0x{IOCS_ENTRY:05X}")

    lines.append("    RETF")

    if data_blocks:
        lines.append("")
    for label, payload in data_blocks:
        lines.append(f"{label}:")
        if payload:
            byte_text = ", ".join(f"0x{value:02X}" for value in payload)
            lines.append(f"    .DB {byte_text}")
        else:
            lines.append("    .DB")

    return "\n".join(lines) + "\n"


def build_plan(spec_path: Path) -> dict[str, object]:
    spec = load_spec(spec_path)
    asm_text = build_asm_text(spec)
    return {
        "name": spec.get("name", spec_path.stem),
        "asm_text": asm_text,
        "timing": parse_int(spec.get("timing", 5)),
        "control_timing": parse_int(spec.get("control_timing", 10)),
        "timeout_s": float(spec.get("timeout_s", 2.0)),
        "start_tag": parse_int(spec.get("start_tag", 0xC1)),
        "stop_tag": parse_int(spec.get("stop_tag", 0xC2)),
        "flags": parse_int(spec.get("flags", 0)),
        "ft_capture": bool(spec.get("ft_capture", True)),
        "fill_experiment_region": bool(spec.get("fill_experiment_region", True)),
        "args": [],
        "source_spec": str(spec.get("_resolved_spec_path", spec_path)),
    }


def parse_result(raw_result_path: Path) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    measurements = raw.get("measurement", [])
    first = measurements[0] if measurements else None
    ft_capture = raw.get("ft_capture") or {}
    compact_preview = ft_capture.get("compact_preview") or []
    execution_preview: list[dict[str, Any]] = []
    for event in compact_preview:
        if event.get("index", 0) < 7:
            continue
        execution_preview.append(
            {
                "index": event.get("index"),
                "addr": event.get("addr"),
                "data": event.get("data"),
                "kind": event.get("kind"),
                "region": event.get("region"),
            }
        )
        if len(execution_preview) >= 24:
            break
    return {
        "measurement_count": len(measurements),
        "first_measurement": first,
        "uart_lines": raw.get("uart_lines", []),
        "ft_word_count": ft_capture.get("word_count"),
        "ft_raw_bytes": ft_capture.get("raw_bytes"),
        "ft_chunk_count": ft_capture.get("chunk_count"),
        "execution_preview": execution_preview,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        raise SystemExit(usage())
    command = argv[1]
    if command == "plan":
        return emit_json(build_plan(Path(argv[2])))
    if command == "parse":
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(usage())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

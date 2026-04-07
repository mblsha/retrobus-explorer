#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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

WORD_MV_REGS = {
    "i": "I",
}

PTR_REGS = {
    "x": "X",
}

LCD_WRITE_ADDR_MIN = 0x0A000
LCD_WRITE_ADDR_MAX = 0x0A010
STDO_WORKING_CURSOR_ABS = 0x0BFC27


def append_asm_line(lines: list[str], code: str, comment: str | None = None) -> None:
    if comment:
        lines.append(f"{code} ; {comment}")
    else:
        lines.append(code)


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


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


def load_spec(spec_path: Path) -> dict[str, Any]:
    resolved_path = resolve_spec_path(spec_path)
    raw = json.loads(resolved_path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit("top-level spec must be a JSON object")
    raw["_resolved_spec_path"] = str(resolved_path)
    return raw


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


def build_text_output_calls(x: int, y: int, text: str, cx: int) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = [{
        "i": 0x0044,
        "cx": cx,
        "bl": x,
        "bh": y,
    }, {
        "op": "seed_stdio_cursor",
        "bl": x,
        "bh": y,
    }]
    for byte in normalize_text_bytes(text):
        calls.append({
            "i": 0x000D,
            "cx": cx,
            "a": byte,
        })
    return calls


def build_clear_calls(cx: int) -> list[dict[str, Any]]:
    return [{"i": 0x0040, "cx": cx, "a": 0}]


def build_hide_cursor_calls(cx: int) -> list[dict[str, Any]]:
    return [{"i": 0x0045, "cx": cx, "a": 0}]


def emit_loads(lines: list[str], call_spec: dict[str, Any], data_labels: set[str]) -> None:
    for key, operand in BYTE_REGS.items():
        if key in call_spec:
            value = parse_int(call_spec[key]) & 0xFF
            append_asm_line(
                lines,
                f"    MV {operand}, 0x{value:02X}",
                f"load {key} with 0x{value:02X}",
            )

    for key, operand in WORD_MVW_REGS.items():
        if key in call_spec:
            value = parse_int(call_spec[key]) & 0xFFFF
            append_asm_line(
                lines,
                f"    MVW {operand}, 0x{value:04X}",
                f"load {key} with 0x{value:04X}",
            )

    for key, operand in WORD_MV_REGS.items():
        if key in call_spec:
            value = parse_int(call_spec[key]) & 0xFFFF
            append_asm_line(
                lines,
                f"    MV {operand}, 0x{value:04X}",
                f"load {key} with IOCS function 0x{value:04X}",
            )

    for key, operand in PTR_REGS.items():
        if key not in call_spec:
            continue
        target = call_spec[key]
        if isinstance(target, str) and target in data_labels:
            append_asm_line(
                lines,
                f"    MV {operand}, {target}",
                f"point {key} at data block {target}",
            )
            continue
        value = parse_int(target) & 0xFFFFFF
        append_asm_line(
            lines,
            f"    MV {operand}, 0x{value:06X}",
            f"load {key} with 0x{value:06X}",
        )

    if "y" in call_spec:
        value = parse_int(call_spec["y"]) & 0xFFFF
        append_asm_line(
            lines,
            f"    MV Y, 0x{value:04X}",
            f"load Y with 0x{value:04X}",
        )


def emit_synthetic_op(lines: list[str], call_spec: dict[str, Any]) -> bool:
    op = call_spec.get("op")
    if op == "seed_stdio_cursor":
        x = parse_int(call_spec.get("bl", 0)) & 0xFF
        y = parse_int(call_spec.get("bh", 0)) & 0xFF
        append_asm_line(lines, f"    MV (BL), 0x{x:02X}", f"stage cursor X byte 0x{x:02X}")
        append_asm_line(lines, f"    MV (BH), 0x{y:02X}", f"stage cursor Y byte 0x{y:02X}")
        append_asm_line(lines, "    MV A, (BL)", "copy the staged cursor X byte into A")
        append_asm_line(lines, f"    MV [0x{STDO_WORKING_CURSOR_ABS:05X}], A", "write cursor X to the STDO working cursor")
        append_asm_line(lines, "    MV A, (BH)", "copy the staged cursor Y byte into A")
        append_asm_line(lines, f"    MV [0x{STDO_WORKING_CURSOR_ABS + 1:05X}], A", "write cursor Y to the STDO working cursor")
        return True
    return False


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

    lines = [f".ORG 0x{EXPERIMENT_BASE:05X}", ""]
    append_asm_line(lines, "start:", "generated experiment entry point")
    if bool(spec.get("mask_interrupts", False)):
        append_asm_line(lines, "    PUSHU IMR", "save IMR on the user stack")
        append_asm_line(lines, "    MV (IMR), 0x00", "mask interrupts during IOCS setup and draw")

    defaults = spec.get("defaults", {})
    if defaults:
        if not isinstance(defaults, dict):
            raise SystemExit("spec.defaults must be an object")
        emit_loads(lines, defaults, data_labels)

    for index, item in enumerate(calls):
        if not isinstance(item, dict):
            raise SystemExit(f"spec.calls[{index}] must be an object")
        call_spec = dict(item)

        if emit_synthetic_op(lines, call_spec):
            continue

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

        if "i" not in call_spec and "il" not in call_spec:
            raise SystemExit(f"spec.calls[{index}] is missing required field 'i' or 'il'")

        emit_loads(lines, call_spec, data_labels)
        append_asm_line(lines, f"    CALLF 0x{IOCS_ENTRY:05X}", "call the IOCS dispatcher")

    if bool(spec.get("mask_interrupts", False)):
        append_asm_line(lines, "    POPU IMR", "restore the saved IMR value")
    append_asm_line(lines, "    RETF", "return to the experiment supervisor")

    if data_blocks:
        lines.append("")
    for label, payload in data_blocks:
        append_asm_line(lines, f"{label}:", f"inline data for generated call {label}")
        byte_text = ", ".join(f"0x{value:02X}" for value in payload) if payload else "0x00"
        append_asm_line(lines, f"    DEFB {byte_text}", "ASCII/text payload bytes")

    return "\n".join(lines) + "\n"


def build_plan_from_spec(spec: dict[str, Any], spec_label: str) -> dict[str, object]:
    asm_text = build_asm_text(spec)
    return {
        "name": spec.get("name", Path(spec_label).stem),
        "asm_text": asm_text,
        "timing": parse_int(spec.get("timing", 5)),
        "control_timing": parse_int(spec.get("control_timing", 10)),
        "timeout_s": float(spec.get("timeout_s", 2.0)),
        "start_tag": parse_int(spec.get("start_tag", 0xC1)),
        "stop_tag": parse_int(spec.get("stop_tag", 0xC2)),
        "flags": parse_int(spec.get("flags", 0)),
        "ft_capture": bool(spec.get("ft_capture", True)),
        "fill_experiment_region": bool(spec.get("fill_experiment_region", True)),
        "mask_interrupts": bool(spec.get("mask_interrupts", False)),
        "args": [],
        "source_spec": spec_label,
    }


def parse_call_argument(text: str) -> dict[str, Any]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise SystemExit("empty --call argument")
    call_spec: dict[str, Any] = {"i": parse_int(parts[0])}
    for item in parts[1:]:
        if "=" not in item:
            raise SystemExit(f"invalid call field {item!r}; expected key=value")
        key, raw_value = item.split("=", 1)
        key = key.strip().lower()
        raw_value = raw_value.strip()
        if key == "text":
            call_spec[key] = raw_value
        else:
            call_spec[key] = parse_int(raw_value)
    return call_spec


def build_spec_from_mode(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    default_name_map = {
        "clear": "iocs_clear",
        "cursor": "iocs_cursor",
        "text": "iocs_text",
        "clear-text": "iocs_clear_text",
        "run": "iocs_run",
        "spec": "iocs_spec",
    }
    experiment_name = args.name
    if experiment_name == "iocs_sequence":
        experiment_name = default_name_map.get(args.mode, experiment_name)

    common: dict[str, Any] = {
        "name": experiment_name,
        "timing": args.timing,
        "control_timing": args.control_timing,
        "timeout_s": args.timeout_s,
        "start_tag": args.start_tag,
        "stop_tag": args.stop_tag,
        "flags": args.flags,
        "ft_capture": not args.no_ft_capture,
        "mask_interrupts": not args.no_mask_interrupts,
    }

    if args.mode == "spec":
        spec = load_spec(Path(args.spec_path))
        spec.setdefault("name", args.name)
        return spec, str(spec.get("_resolved_spec_path", args.spec_path))

    if args.mode == "clear":
        spec = dict(common)
        spec["timeout_s"] = max(spec["timeout_s"], 5.0)
        spec["calls"] = build_hide_cursor_calls(0) + build_clear_calls(0) + build_hide_cursor_calls(0)
        return spec, "<generated:clear>"

    if args.mode == "cursor":
        spec = dict(common)
        spec["calls"] = [{"i": 0x0044, "cx": args.cx, "bl": args.x, "bh": args.y}]
        return spec, "<generated:cursor>"

    if args.mode == "text":
        spec = dict(common)
        spec["timeout_s"] = max(spec["timeout_s"], 5.0)
        calls: list[dict[str, Any]] = []
        calls.extend(build_hide_cursor_calls(args.cx))
        calls.extend(build_clear_calls(args.cx))
        calls.extend(build_text_output_calls(args.x, args.y, args.text, args.cx))
        calls.extend(build_hide_cursor_calls(args.cx))
        spec["calls"] = calls
        return spec, "<generated:text>"

    if args.mode == "clear-text":
        spec = dict(common)
        spec["timeout_s"] = max(spec["timeout_s"], 5.0)
        calls = build_hide_cursor_calls(args.cx)
        calls.extend(build_clear_calls(args.cx))
        calls.extend(build_text_output_calls(args.x, args.y, args.text, args.cx))
        calls.extend(build_hide_cursor_calls(args.cx))
        spec["calls"] = calls
        return spec, "<generated:clear-text>"

    if args.mode == "run":
        if not args.call:
            raise SystemExit("run mode requires at least one --call")
        spec = dict(common)
        calls = [parse_call_argument(item) for item in args.call]
        if args.cx is not None:
            for call in calls:
                call.setdefault("cx", args.cx)
        spec["calls"] = calls
        return spec, "<generated:run>"

    raise SystemExit(f"unknown IOCS mode {args.mode!r}")


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
    display_summary = summarize_display_writes(raw)
    return {
        "measurement_count": len(measurements),
        "first_measurement": first,
        "uart_lines": raw.get("uart_lines", []),
        "ft_word_count": ft_capture.get("word_count"),
        "ft_raw_bytes": ft_capture.get("raw_bytes"),
        "ft_chunk_count": ft_capture.get("chunk_count"),
        "execution_preview": execution_preview,
        "display_summary": display_summary,
    }


def _find_public_src() -> Path | None:
    env_candidates = [
        Path(value)
        for key in ("PCE500_PUBLIC_SRC", "PUBLIC_SRC")
        if (value := os.environ.get(key))
    ]
    path_candidates = list(env_candidates)
    for parent in SCRIPT_DIR.parents:
        path_candidates.append(parent / "public-src")
        path_candidates.append(parent.parent / "binja-esr-tests" / "public-src")
    for candidate in path_candidates:
        if (candidate / "pce500" / "display" / "text_decoder.py").is_file():
            return candidate.resolve()
    return None


def _find_rom_path(public_src: Path) -> Path | None:
    candidates = [
        public_src.parent / "roms" / "pc-e500-en.bin",
        public_src / "data" / "pc-e500-en.bin",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _load_display_modules(public_src: Path):
    import importlib.util
    import types

    display_root = public_src / "pce500" / "display"
    if "PIL" not in sys.modules:
        pil_module = types.ModuleType("PIL")
        pil_module.Image = types.SimpleNamespace(Image=object, NEAREST=0, new=lambda *args, **kwargs: None)
        sys.modules["PIL"] = pil_module
    package = types.ModuleType("iocs_display")
    package.__path__ = [str(display_root)]
    sys.modules["iocs_display"] = package
    modules = {}
    for name in ("hd61202", "pipeline", "font", "text_decoder"):
        spec = importlib.util.spec_from_file_location(
            f"iocs_display.{name}",
            display_root / f"{name}.py",
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"failed to load display module {name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"iocs_display.{name}"] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


class _RomBytesMemory:
    def __init__(self, rom: bytes) -> None:
        self._rom = rom

    def read_byte(self, address: int) -> int:
        if 0 <= address < len(self._rom):
            return self._rom[address]
        return 0


class _TraceDisplayController:
    def __init__(self, modules) -> None:
        self._hd = modules["hd61202"]
        self._pipeline_mod = modules["pipeline"]
        self.pipeline = self._pipeline_mod.LCDPipeline()
        self.chips = self.pipeline.chips

    def write(self, address: int, value: int, source_index: int | None = None) -> None:
        self.pipeline.apply_raw(address, value, source_index)

    def get_display_buffer(self):
        def pixel_on(byte: int, bit: int) -> int:
            return 1 if not ((byte >> bit) & 1) else 0

        class _SimpleBuffer:
            def __init__(self, height: int, width: int) -> None:
                self.shape = (height, width)
                self._rows = [[0 for _ in range(width)] for _ in range(height)]

            def __getitem__(self, key):
                row, col = key
                return self._rows[row][col]

            def __setitem__(self, key, value) -> None:
                row, col = key
                self._rows[row][col] = value

        buffer = _SimpleBuffer(32, 240)
        left_chip, right_chip = self.chips[0], self.chips[1]

        def copy_region(chip, start_page: int, column_range: range, dest_start_col: int, *, mirror: bool) -> None:
            for row in range(32):
                page = start_page + row // 8
                bit = row % 8
                if mirror:
                    for dest_offset, src_col in enumerate(reversed(column_range)):
                        byte = chip.vram[page][src_col]
                        buffer[row, dest_start_col + dest_offset] = pixel_on(byte, bit)
                else:
                    for dest_offset, src_col in enumerate(column_range):
                        byte = chip.vram[page][src_col]
                        buffer[row, dest_start_col + dest_offset] = pixel_on(byte, bit)

        copy_region(right_chip, 0, range(64), 0, mirror=False)
        copy_region(left_chip, 0, range(56), 64, mirror=False)
        copy_region(left_chip, 4, range(56), 120, mirror=True)
        copy_region(right_chip, 4, range(64), 176, mirror=True)
        return buffer

    def get_display_source_buffer(self):
        class _SimpleSourceBuffer:
            def __init__(self, height: int, width: int) -> None:
                self.shape = (height, width)
                self._rows = [[None for _ in range(width)] for _ in range(height)]

            def __getitem__(self, key):
                row, col = key
                return self._rows[row][col]

            def __setitem__(self, key, value) -> None:
                row, col = key
                self._rows[row][col] = value

        buffer = _SimpleSourceBuffer(32, 240)
        left_chip, right_chip = self.chips[0], self.chips[1]

        def copy_region(chip, start_page: int, column_range: range, dest_start_col: int, *, mirror: bool) -> None:
            for row in range(32):
                page = start_page + row // 8
                if mirror:
                    for dest_offset, src_col in enumerate(reversed(column_range)):
                        buffer[row, dest_start_col + dest_offset] = chip.vram_pc_source[page][src_col]
                else:
                    for dest_offset, src_col in enumerate(column_range):
                        buffer[row, dest_start_col + dest_offset] = chip.vram_pc_source[page][src_col]

        copy_region(right_chip, 0, range(64), 0, mirror=False)
        copy_region(left_chip, 0, range(56), 64, mirror=False)
        copy_region(left_chip, 4, range(56), 120, mirror=True)
        copy_region(right_chip, 4, range(64), 176, mirror=True)
        return buffer


def _extract_helper_text_request(raw: dict[str, Any]) -> tuple[int, int, str] | None:
    experiment = raw.get("experiment")
    if experiment not in {"iocs_text", "iocs_clear_text"}:
        return None
    args = raw.get("script_args")
    if not isinstance(args, list):
        return None
    try:
        mode_index = next(index for index, value in enumerate(args) if value in {"text", "clear-text"})
    except StopIteration:
        return None
    x = y = None
    text = None
    cursor = mode_index + 1
    while cursor < len(args):
        key = args[cursor]
        if key == "--x" and cursor + 1 < len(args):
            x = parse_int(args[cursor + 1])
            cursor += 2
            continue
        if key == "--y" and cursor + 1 < len(args):
            y = parse_int(args[cursor + 1])
            cursor += 2
            continue
        if key == "--text" and cursor + 1 < len(args):
            text = str(args[cursor + 1])
            cursor += 2
            continue
        cursor += 1
    if x is None or y is None or text is None:
        return None
    return x, y, text


def _helper_row_last_write_maxima(controller: _TraceDisplayController) -> list[int | None]:
    source_buffer = controller.get_display_source_buffer()
    height, width = source_buffer.shape
    row_maxima: list[int | None] = []
    for row_index in range(4):
        row_base = row_index * 8
        if row_base + 7 > height:
            row_maxima.append(None)
            continue
        max_source: int | None = None
        for row in range(row_base, row_base + 7):
            for col in range(width):
                source = source_buffer[row, col]
                if source is None:
                    continue
                if max_source is None or source > max_source:
                    max_source = source
        row_maxima.append(max_source)
    return row_maxima


def _filter_helper_lines_by_last_write(
    raw: dict[str, Any],
    controller: _TraceDisplayController,
    lines: list[str],
) -> list[str]:
    request = _extract_helper_text_request(raw)
    if request is None or not lines:
        return lines
    _, target_row, _ = request
    if target_row >= len(lines) or not lines[target_row]:
        return lines

    row_maxima = _helper_row_last_write_maxima(controller)
    target_max = row_maxima[target_row] if target_row < len(row_maxima) else None
    if target_max is None:
        return lines

    filtered = list(lines)
    for row_index, line in enumerate(filtered):
        if row_index == target_row or not line:
            continue
        row_max = row_maxima[row_index] if row_index < len(row_maxima) else None
        if row_max is None or (target_max - row_max) >= 0x1000:
            filtered[row_index] = ""
    return filtered


def summarize_display_writes(raw: dict[str, Any]) -> dict[str, Any] | None:
    ft_capture = raw.get("ft_capture") or {}
    words = ft_capture.get("words") or []
    if not isinstance(words, list) or not words:
        return None

    scripts_dir = PROJECT_DIR / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from pc_e500_ft600 import decode_word_stream

    lcd_writes = [
        event
        for event in decode_word_stream(words)
        if (not event.rw) and LCD_WRITE_ADDR_MIN <= event.addr < LCD_WRITE_ADDR_MAX
    ]
    if not lcd_writes:
        return None

    summary: dict[str, Any] = {
        "lcd_write_count": len(lcd_writes),
        "lcd_write_preview": [
            {"addr": f"0x{event.addr:05X}", "data": f"0x{event.data:02X}", "kind": event.kind}
            for event in lcd_writes[:16]
        ],
    }

    public_src = _find_public_src()
    if public_src is None:
        return summary
    rom_path = _find_rom_path(public_src)
    if rom_path is None:
        return summary

    try:
        modules = _load_display_modules(public_src)
        controller = _TraceDisplayController(modules)
        for event in lcd_writes:
            controller.write(event.addr, event.data, event.index)
        memory = _RomBytesMemory(rom_path.read_bytes())
        lines = modules["text_decoder"].decode_display_text(controller, memory)
        lines = _filter_helper_lines_by_last_write(raw, controller, lines)
    except Exception as exc:
        summary["decode_error"] = str(exc)
        return summary

    summary["lcd_text_lines"] = lines
    return summary


def build_plan_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--name", default="iocs_sequence", help="experiment name")
    parser.add_argument("--timing", type=lambda value: int(value, 0), default=5)
    parser.add_argument("--control-timing", type=lambda value: int(value, 0), default=10)
    parser.add_argument("--timeout-s", type=float, default=2.0)
    parser.add_argument("--start-tag", type=lambda value: int(value, 0), default=0xC1)
    parser.add_argument("--stop-tag", type=lambda value: int(value, 0), default=0xC2)
    parser.add_argument("--flags", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--no-ft-capture", action="store_true")
    parser.add_argument("--no-mask-interrupts", action="store_true")

    subparsers = parser.add_subparsers(dest="mode", required=True)

    spec_parser = subparsers.add_parser("spec", help="load IOCS sequence from JSON spec")
    spec_parser.add_argument("spec_path")

    subparsers.add_parser("clear", help="invoke IOCS 51h clear display")

    cursor_parser = subparsers.add_parser("cursor", help="invoke IOCS 44h set cursor")
    cursor_parser.add_argument("--x", required=True, type=lambda value: int(value, 0))
    cursor_parser.add_argument("--y", required=True, type=lambda value: int(value, 0))
    cursor_parser.add_argument("--cx", type=lambda value: int(value, 0), default=0)

    text_parser = subparsers.add_parser("text", help="set cursor, then print text via IOCS 0Dh")
    text_parser.add_argument("--x", required=True, type=lambda value: int(value, 0))
    text_parser.add_argument("--y", required=True, type=lambda value: int(value, 0))
    text_parser.add_argument("--text", required=True)
    text_parser.add_argument("--cx", type=lambda value: int(value, 0), default=0)
    text_parser.add_argument("--clear-first", action="store_true")

    clear_text_parser = subparsers.add_parser("clear-text", help="clear display then print text")
    clear_text_parser.add_argument("--x", required=True, type=lambda value: int(value, 0))
    clear_text_parser.add_argument("--y", required=True, type=lambda value: int(value, 0))
    clear_text_parser.add_argument("--text", required=True)
    clear_text_parser.add_argument("--cx", type=lambda value: int(value, 0), default=0)

    run_parser = subparsers.add_parser("run", help="generic IOCS sequence")
    run_parser.add_argument("--call", action="append", default=[], help="call spec like 0x42,bl=0,bh=0,text=HELLO")
    run_parser.add_argument("--cx", type=lambda value: int(value, 0))

    return parser


def usage() -> str:
    return (
        "usage:\n"
        "  iocs_sequence.py plan MODE ...\n"
        "  iocs_sequence.py parse RESULT.json\n"
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit(usage())
    command = argv[1]
    if command == "plan":
        args = build_plan_parser().parse_args(argv[2:])
        spec, spec_label = build_spec_from_mode(args)
        return emit_json(build_plan_from_spec(spec, spec_label))
    if command == "parse":
        if len(argv) < 3:
            raise SystemExit(usage())
        return emit_json(parse_result(Path(argv[2])))
    raise SystemExit(usage())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

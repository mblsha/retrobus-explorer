#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import re
from pathlib import Path

PIN_DEF_RE = re.compile(r"^\s*([A-Z0-9_]+)\(\"([A-Z0-9]+)\",\s*\d+\),?\s*$")
PIN_LINE_RE = re.compile(
    r"\bpin\s+([A-Za-z_][A-Za-z0-9_\[\]]*)\s+([A-Za-z0-9_]+)(?:\s+FREQUENCY\(([^)]+)\))?",
    re.IGNORECASE,
)
STD_RE = re.compile(r"STANDARD\(([^)]+)\)", re.IGNORECASE)
META_RE = re.compile(r"^\s*//\s*@meta\.([A-Za-z0-9_.-]+)\s*:\s*(.+?)\s*$")
REQUIRED_SHARED_META_KEYS = ("schema", "name", "board", "description")
ROOT_PROP_META_PREFIX = "root_property."


def parse_au_pin_map(au_pin_kt: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in au_pin_kt.read_text().splitlines():
        m = PIN_DEF_RE.match(line)
        if m:
            mapping[m.group(1)] = m.group(2)
    if not mapping:
        raise SystemExit(f"error: no pin mappings found in {au_pin_kt}")
    return mapping


def mhz_to_period_ns(freq_expr: str) -> float:
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*MHz\s*", freq_expr, re.IGNORECASE)
    if not m:
        raise ValueError(f"unsupported FREQUENCY expression: {freq_expr!r}")
    mhz = float(m.group(1))
    return 1000.0 / mhz


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    out: list[str] = []
    for line in text.splitlines():
        out.append(line.split("//", 1)[0])
    return "\n".join(out)


def parse_acf_metadata(acf: Path) -> list[tuple[str, str]]:
    metadata: list[tuple[str, str]] = []
    for raw_line in acf.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            m = META_RE.match(raw_line)
            if m:
                metadata.append((m.group(1), m.group(2).strip()))
            continue
        break
    return metadata


def collect_acf_metadata(acf_files: list[Path]) -> dict[Path, list[tuple[str, str]]]:
    return {acf: parse_acf_metadata(acf) for acf in acf_files}


def is_shared_constraints_acf(acf: Path) -> bool:
    return "shared-constraints" in acf.parts


def validate_metadata_usage(acf_files: list[Path], acf_metadata: dict[Path, list[tuple[str, str]]]) -> None:
    errors: list[str] = []
    for acf in acf_files:
        if not is_shared_constraints_acf(acf):
            continue
        metadata = acf_metadata.get(acf, [])
        if not metadata:
            errors.append(f"{acf}: missing @meta.* header for shared constraints file")
            continue
        keys = {key for key, _ in metadata}
        missing = [key for key in REQUIRED_SHARED_META_KEYS if key not in keys]
        if missing:
            errors.append(f"{acf}: missing required @meta keys: {', '.join(missing)}")
        if acf.name == "saleae.acf":
            drive_meta_key = "root_property.saleae.DRIVE"
            if drive_meta_key not in keys:
                errors.append(f"{acf}: missing required @meta key: {drive_meta_key}")
            else:
                drive_values = [value for key, value in metadata if key == drive_meta_key]
                if any(value.strip() != "4" for value in drive_values):
                    errors.append(f"{acf}: {drive_meta_key} must be 4")
            slew_meta_key = "root_property.saleae.SLEW"
            if slew_meta_key not in keys:
                errors.append(f"{acf}: missing required @meta key: {slew_meta_key}")
            else:
                slew_values = [value for key, value in metadata if key == slew_meta_key]
                if any(value.strip().upper() != "SLOW" for value in slew_values):
                    errors.append(f"{acf}: {slew_meta_key} must be SLOW")

    if errors:
        details = "\n".join(f"  - {err}" for err in errors)
        raise SystemExit(f"error: shared-constraints metadata validation failed:\n{details}")


def parse_root_properties_from_metadata(
    acf_metadata: dict[Path, list[tuple[str, str]]]
) -> dict[str, list[tuple[str, str]]]:
    parsed: dict[str, list[tuple[str, str]]] = {}

    for acf, items in acf_metadata.items():
        for key, value in items:
            if not key.startswith(ROOT_PROP_META_PREFIX):
                continue
            suffix = key[len(ROOT_PROP_META_PREFIX):]
            if "." not in suffix:
                raise SystemExit(
                    f"error: invalid root_property metadata in {acf}: {key!r}; expected root_property.<signal>.<PROP>"
                )
            root, prop = suffix.rsplit(".", 1)
            root = root.strip()
            prop = prop.strip().upper()
            v = value.strip()
            if not root or not prop or not v:
                raise SystemExit(
                    f"error: invalid root_property metadata in {acf}: {key!r}: {value!r}"
                )
            parsed.setdefault(root, []).append((prop, v))

    return parsed


def parse_acf_files(acf_files: list[Path], symbolic_to_package: dict[str, str]) -> tuple[list[tuple[str, str, str]], list[tuple[str, float]]]:
    pins: list[tuple[str, str, str]] = []
    clocks: list[tuple[str, float]] = []
    current_std = "LVCMOS33"

    for acf in acf_files:
        content = strip_comments(acf.read_text())
        for raw_line in content.splitlines():
            std_match = STD_RE.search(raw_line)
            if std_match:
                current_std = std_match.group(1).strip()

            pin_match = PIN_LINE_RE.search(raw_line)
            if not pin_match:
                continue

            signal = pin_match.group(1)
            symbolic_pin = pin_match.group(2)
            freq = pin_match.group(3)

            if symbolic_pin in symbolic_to_package:
                package_pin = symbolic_to_package[symbolic_pin]
            elif re.fullmatch(r"[A-Z][0-9]+", symbolic_pin):
                package_pin = symbolic_to_package.get(symbolic_pin, symbolic_pin)
            else:
                raise SystemExit(
                    f"error: unresolved pin token {symbolic_pin!r} for signal {signal!r} in {acf}"
                )

            pins.append((signal, package_pin, current_std))
            if freq:
                clocks.append((signal, mhz_to_period_ns(freq)))

    return pins, clocks


def dedupe_pins(pins: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for signal, package_pin, iostandard in pins:
        if signal in seen:
            continue
        seen.add(signal)
        out.append((signal, package_pin, iostandard))
    return out


def dedupe_clocks(clocks: list[tuple[str, float]]) -> list[tuple[str, float]]:
    seen: set[str] = set()
    out: list[tuple[str, float]] = []
    for signal, period in clocks:
        if signal in seen:
            continue
        seen.add(signal)
        out.append((signal, period))
    return out


def root_signal(signal: str) -> str:
    return signal.split("[", 1)[0]


def filter_to_signals(
    pins: list[tuple[str, str, str]],
    clocks: list[tuple[str, float]],
    allowed: set[str],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, float]]]:
    filtered_pins = [entry for entry in pins if root_signal(entry[0]) in allowed]
    filtered_clocks = [entry for entry in clocks if root_signal(entry[0]) in allowed]
    return filtered_pins, filtered_clocks


def parse_root_properties(specs: list[str]) -> dict[str, list[tuple[str, str]]]:
    parsed: dict[str, list[tuple[str, str]]] = {}
    for spec in specs:
        if ":" not in spec or "=" not in spec:
            raise SystemExit(
                f"error: --root-property expects root:PROP=VALUE, got {spec!r}"
            )
        root, rest = spec.split(":", 1)
        prop, value = rest.split("=", 1)
        root = root.strip()
        prop = prop.strip().upper()
        value = value.strip()
        if not root or not prop or not value:
            raise SystemExit(
                f"error: --root-property expects root:PROP=VALUE, got {spec!r}"
            )
        parsed.setdefault(root, []).append((prop, value))
    return parsed


def merge_root_properties(
    low_priority: dict[str, list[tuple[str, str]]],
    high_priority: dict[str, list[tuple[str, str]]],
) -> dict[str, list[tuple[str, str]]]:
    merged: dict[str, list[tuple[str, str]]] = {}
    seen: dict[str, set[tuple[str, str]]] = {}

    def add_items(src: dict[str, list[tuple[str, str]]]) -> None:
        for root, items in src.items():
            slot = merged.setdefault(root, [])
            seen_slot = seen.setdefault(root, set())
            for item in items:
                if item in seen_slot:
                    continue
                slot.append(item)
                seen_slot.add(item)

    add_items(low_priority)
    add_items(high_priority)
    return merged


def render_xdc(
    pins: list[tuple[str, str, str]],
    clocks: list[tuple[str, float]],
    acf_files: list[Path],
    acf_metadata: dict[Path, list[tuple[str, str]]],
    root_props: dict[str, list[tuple[str, str]]],
) -> str:
    lines: list[str] = []
    lines.append("# Auto-generated from ACF constraints:")
    for acf in acf_files:
        lines.append(f"# - {acf}")
        for key, value in acf_metadata.get(acf, []):
            lines.append(f"#   meta.{key}: {value}")
    lines.append("")

    for signal, package_pin, iostandard in pins:
        lines.append(f"set_property PACKAGE_PIN {package_pin} [get_ports {{{signal}}}]")
        lines.append(f"set_property IOSTANDARD {iostandard} [get_ports {{{signal}}}]")

    if root_props:
        lines.append("")
        for signal, _, _ in pins:
            props = root_props.get(root_signal(signal), [])
            for prop, value in props:
                lines.append(f"set_property {prop} {value} [get_ports {{{signal}}}]")
    lines.append("")

    for signal, period in clocks:
        lines.append(
            f"create_clock -name {signal} -period {period:.3f} [get_ports {{{signal}}}]"
        )

    if any(signal == "clk" for signal, _, _ in pins):
        lines.append("")
        lines.append("# Vivado placement override for Au clock pin mapping")
        lines.append("set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets {clk_IBUF}]")

    lines.append("")
    lines.append("# Allow bitstream generation even when some ports are intentionally left unconstrained")
    lines.append("set_property SEVERITY {Warning} [get_drc_checks UCIO-1]")
    lines.append("set_property SEVERITY {Warning} [get_drc_checks NSTD-1]")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an XDC from one or more ACF files")
    parser.add_argument("--au-pin-map", required=True, type=Path, help="Path to AuPin.kt")
    parser.add_argument("--out", required=True, type=Path, help="Output XDC path")
    parser.add_argument("--signal", action="append", default=[], help="Optional top-level signal name filter (repeatable)")
    parser.add_argument("--root-property", action="append", default=[], help="Apply property by root signal: root:PROP=VALUE (repeatable)")
    parser.add_argument("acf", nargs="+", type=Path, help="ACF files to merge")
    args = parser.parse_args()

    pin_map = parse_au_pin_map(args.au_pin_map)
    acf_metadata = collect_acf_metadata(args.acf)
    validate_metadata_usage(args.acf, acf_metadata)
    pins, clocks = parse_acf_files(args.acf, pin_map)
    pins = dedupe_pins(pins)
    clocks = dedupe_clocks(clocks)
    metadata_root_props = parse_root_properties_from_metadata(acf_metadata)
    cli_root_props = parse_root_properties(args.root_property)
    root_props = merge_root_properties(metadata_root_props, cli_root_props)
    if args.signal:
        pins, clocks = filter_to_signals(pins, clocks, set(args.signal))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_xdc(pins, clocks, args.acf, acf_metadata, root_props))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

DEFAULT_OUT = "constraints/pins.xdc"
DEFAULT_TOP_FILE = "src/main.spade"
DEFAULT_TOP_ENTITY = "main"

PROFILE_PATHS: dict[str, str] = {
    "alchitry_base": "Alchitry-Labs-V2/src/main/resources/library/components/Constraints/alchitry.acf",
    "saleae": "../shared-constraints/saleae.acf",
    "ft_v1": "Alchitry-Labs-V2/src/main/resources/library/components/Constraints/ft_v1.acf",
    "pin_tester_ffc": "../pin-tester/constraint/level-shifter.acf",
    "sharp_organizer_bus": "../sharp-organizer-card/constraint/sharp-organizer-card.acf",
    "sharp_pc_g850_bus": "../sharp-pc-g850-bus/constraint/pc-g850-bus.acf",
}
TOP_ENTITY_RE = re.compile(r"entity\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*\{", re.DOTALL)
PORT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a project's XDC from ACF sources defined in swim.toml"
    )
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--allow-missing", action="store_true", help="Exit 0 when [constraints].acf is not configured")
    return parser.parse_args()


def default_au_pin_map() -> str:
    reference_root = Path(__file__).resolve().parents[2]
    return str(
        reference_root
        / "Alchitry-Labs-V2"
        / "src"
        / "main"
        / "kotlin"
        / "com"
        / "alchitry"
        / "labs2"
        / "hardware"
        / "pinout"
        / "AuPin.kt"
    )


def ensure_str(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"error: {name} must be a non-empty string")
    return value


def ensure_str_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(f"error: {name} must be a non-empty list of strings")
    return list(value)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines: list[str] = []
    for line in text.splitlines():
        lines.append(line.split("//", 1)[0])
    return "\n".join(lines)


def parse_top_ports(top_file: Path, top_entity: str) -> set[str]:
    content = strip_comments(top_file.read_text())
    for entity_name, body in TOP_ENTITY_RE.findall(content):
        if entity_name != top_entity:
            continue
        return {name for name in PORT_RE.findall(body)}
    raise SystemExit(f"error: entity {top_entity!r} not found in {top_file}")


def infer_profiles(port_names: set[str]) -> list[str]:
    profiles: list[str] = ["alchitry_base"]
    if "saleae" in port_names:
        profiles.append("saleae")
    if "ffc_data" in port_names:
        profiles.append("pin_tester_ffc")
    if any(name.startswith("ft_") for name in port_names):
        profiles.append("ft_v1")
    if any(name.startswith("conn_") for name in port_names):
        profiles.append("sharp_organizer_bus")
    if (
        any(name.startswith("z80_") for name in port_names)
        or "addr_bnk" in port_names
        or "addr_ceram2" in port_names
        or "addr_cerom2" in port_names
    ):
        profiles.append("sharp_pc_g850_bus")
    return profiles


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def reference_root() -> Path:
    return Path(__file__).resolve().parents[2]


def profile_path(profile: str) -> Path:
    rel = PROFILE_PATHS.get(profile)
    if rel is None:
        supported = ", ".join(sorted(PROFILE_PATHS.keys()))
        raise SystemExit(f"error: unknown constraints profile {profile!r}; supported: {supported}")
    return (reference_root() / rel).resolve()


def relativize(project: Path, path: Path) -> str:
    return os.path.relpath(path, start=project)


def load_constraint_config(project: Path) -> tuple[str, str, list[str], set[str]] | None:
    swim_toml = project / "swim.toml"
    config = tomllib.loads(swim_toml.read_text())
    constraints = config.get("constraints", {})
    if not constraints:
        return None
    if not isinstance(constraints, dict):
        raise SystemExit("error: [constraints] must be a table in swim.toml")

    acf = constraints.get("acf")
    auto = bool(constraints.get("auto", acf is None))

    out = ensure_str(constraints.get("out", DEFAULT_OUT), "[constraints].out")
    au_pin_map = ensure_str(constraints.get("au_pin_map", default_au_pin_map()), "[constraints].au_pin_map")
    top_file = ensure_str(constraints.get("top_file", DEFAULT_TOP_FILE), "[constraints].top_file")
    top_entity_default = config.get("tooling", {}).get("top", DEFAULT_TOP_ENTITY)
    top_entity = ensure_str(constraints.get("top_entity", top_entity_default), "[constraints].top_entity")
    top_ports = parse_top_ports(project / top_file, top_entity)

    if acf is not None and not auto:
        acf_files = ensure_str_list(acf, "[constraints].acf")
        return out, au_pin_map, acf_files, top_ports

    inferred = infer_profiles(top_ports)
    include_profiles = ensure_str_list(constraints.get("profiles", []), "[constraints].profiles") if "profiles" in constraints else []
    exclude_profiles = set(
        ensure_str_list(constraints.get("exclude_profiles", []), "[constraints].exclude_profiles")
        if "exclude_profiles" in constraints
        else []
    )
    acf_extra = ensure_str_list(constraints.get("acf_extra", []), "[constraints].acf_extra") if "acf_extra" in constraints else []

    profiles = [profile for profile in dedupe(inferred + include_profiles) if profile not in exclude_profiles]
    acf_files = [relativize(project, profile_path(profile)) for profile in profiles] + acf_extra
    return out, au_pin_map, acf_files, top_ports


def main() -> int:
    args = parse_args()
    project = args.project.resolve()

    loaded = load_constraint_config(project)
    if loaded is None:
        msg = f"skip: {project} has no [constraints] section configured"
        if args.allow_missing:
            print(msg)
            return 0
        raise SystemExit(f"error: {msg}")

    out, au_pin_map, acf_files, top_ports = loaded
    tools_dir = Path(__file__).resolve().parent
    generator = tools_dir / "gen_xdc_from_acf.py"

    cmd = [
        sys.executable,
        str(generator),
        "--au-pin-map",
        au_pin_map,
        "--out",
        out,
        *acf_files,
    ]
    for signal in sorted(top_ports):
        cmd.extend(["--signal", signal])
    subprocess.run(cmd, cwd=project, check=True)
    print(f"generated: {(project / out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

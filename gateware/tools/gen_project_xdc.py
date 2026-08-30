#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import os
import re
import tomllib
from pathlib import Path

import gen_xdc_from_acf as xdc
from text_filters import strip_comments

DEFAULT_OUT = "constraints/pins.xdc"
DEFAULT_TOP_FILE = "src/main.spade"
DEFAULT_TOP_ENTITY = "main"

PROFILE_PATHS: dict[str, str] = {
    "alchitry_base": "constraints/boards/alchitry-au1/alchitry.acf",
    "saleae": "constraints/interfaces/saleae.acf",
    "ft_v1": "constraints/boards/alchitry-au1/ft_v1.acf",
    "pin_tester_ffc": "constraints/targets/pin-tester.acf",
    "sharp_organizer_bus": "constraints/targets/sharp-organizer-card.acf",
    "sharp_pc_g850_bus": "constraints/targets/sharp-pc-g850-bus.acf",
}
PORT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a project's XDC from ACF sources defined in swim.toml"
    )
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--allow-missing", action="store_true", help="Exit 0 when [constraints].acf is not configured")
    return parser.parse_args()


def default_au_pin_map() -> str:
    return str(gateware_root() / "constraints" / "boards" / "alchitry-au1" / "pins.toml")


def ensure_str(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"error: {name} must be a non-empty string")
    return value


def ensure_str_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(f"error: {name} must be a non-empty list of strings")
    return list(value)


def ensure_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise SystemExit(f"error: {name} must be a positive integer")
    return value


def parse_top_ports(top_file: Path, top_entity: str) -> set[str]:
    content = strip_comments(top_file.read_text())
    entity_re = re.compile(rf"\bentity\s+{re.escape(top_entity)}\s*\((.*?)\)\s*\{{", re.DOTALL)
    match = entity_re.search(content)
    if match is not None:
        return {name for name in PORT_RE.findall(match.group(1))}
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


def gateware_root() -> Path:
    return Path(__file__).resolve().parents[1]


def profile_path(profile: str) -> Path:
    rel = PROFILE_PATHS.get(profile)
    if rel is None:
        supported = ", ".join(sorted(PROFILE_PATHS.keys()))
        raise SystemExit(f"error: unknown constraints profile {profile!r}; supported: {supported}")
    return (gateware_root() / rel).resolve()


def relativize(project: Path, path: Path) -> str:
    return os.path.relpath(path, start=project)


def parse_root_properties(constraints: dict[object, object], top_ports: set[str]) -> list[tuple[str, str, str]]:
    root_props: list[tuple[str, str, str]] = []

    if "saleae_drive" in constraints:
        drive = ensure_positive_int(constraints["saleae_drive"], "[constraints].saleae_drive")
        if drive != 4:
            raise SystemExit("error: Saleae drive strength is fixed to 4 mA across projects")
        if "saleae" in top_ports:
            root_props.append(("saleae", "DRIVE", "4"))

    if "saleae_slew" in constraints:
        slew = ensure_str(constraints["saleae_slew"], "[constraints].saleae_slew").upper()
        if slew not in {"FAST", "SLOW"}:
            raise SystemExit("error: [constraints].saleae_slew must be FAST or SLOW")
        root_props.append(("saleae", "SLEW", slew))

    return root_props


def load_constraint_config(project: Path) -> tuple[str, str, list[str], set[str], list[tuple[str, str, str]]] | None:
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
    if "extra_signals" in constraints:
        top_ports |= set(ensure_str_list(constraints.get("extra_signals"), "[constraints].extra_signals"))
    root_props = parse_root_properties(constraints, top_ports)

    if acf is not None and not auto:
        acf_files = ensure_str_list(acf, "[constraints].acf")
        return out, au_pin_map, acf_files, top_ports, root_props

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
    return out, au_pin_map, acf_files, top_ports, root_props


def _resolved_constraint_config(
    project: Path,
) -> tuple[str, Path, list[Path], set[str], list[tuple[str, str, str]]]:
    loaded = load_constraint_config(project)
    if loaded is None:
        raise ValueError(f"{project} has no [constraints] section configured")
    out, au_pin_map, acf_files, top_ports, root_props = loaded
    return (
        out,
        Path(au_pin_map).resolve(),
        [(project / acf).resolve() for acf in acf_files],
        top_ports,
        root_props,
    )


def project_constraint_sources(project: Path) -> tuple[Path, ...]:
    _, au_pin_map, acf_files, _, _ = _resolved_constraint_config(project.resolve())
    return (au_pin_map, *acf_files)


def render_project_xdc(project: Path) -> str:
    project = project.resolve()
    _, au_pin_map, acf_files, top_ports, root_props = _resolved_constraint_config(project)

    pin_map = xdc.parse_au_pin_map(au_pin_map)
    acf_metadata = xdc.collect_acf_metadata(acf_files)
    xdc.validate_metadata_usage(acf_files, acf_metadata)
    pins, clocks = xdc.parse_acf_files(acf_files, pin_map)
    pins = xdc.dedupe_pins(pins)
    clocks = xdc.dedupe_clocks(clocks)
    metadata_root_props = xdc.parse_root_properties_from_metadata(acf_metadata)
    configured_root_props = xdc.parse_root_properties(
        [f"{root}:{prop}={value}" for root, prop, value in root_props]
    )
    merged_root_props = xdc.merge_root_properties(
        metadata_root_props,
        configured_root_props,
    )
    pins, clocks = xdc.filter_to_signals(pins, clocks, top_ports)
    config = tomllib.loads((project / "swim.toml").read_text())
    constraints = config.get("constraints", {})
    emit_clock_route_overrides = bool(constraints.get("emit_clock_route_overrides", True))
    allow_unconstrained_ports = bool(constraints.get("allow_unconstrained_ports", True))
    acf_labels = [Path(relativize(project, acf)) for acf in acf_files]
    labeled_metadata = {
        label: acf_metadata[acf]
        for label, acf in zip(acf_labels, acf_files, strict=True)
    }
    return xdc.render_xdc(
        pins,
        clocks,
        acf_labels,
        labeled_metadata,
        merged_root_props,
        emit_clock_route_overrides=emit_clock_route_overrides,
        allow_unconstrained_ports=allow_unconstrained_ports,
    )


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

    out, _, _, _, _ = loaded
    output_path = project / out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_project_xdc(project))
    print(f"generated: {(project / out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

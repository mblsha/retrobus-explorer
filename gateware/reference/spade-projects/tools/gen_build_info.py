#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate project-local Spade build metadata source"
    )
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    return parser.parse_args()


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def project_display_name(project: Path) -> str:
    pyproject = project / "pyproject.toml"
    if pyproject.is_file():
        name = load_toml(pyproject).get("project", {}).get("name")
        if isinstance(name, str) and name:
            return name

    swim = project / "swim.toml"
    if swim.is_file():
        name = load_toml(swim).get("name")
        if isinstance(name, str) and name:
            return name.replace("_", "-")

    return project.name


def build_timestamp_text() -> str:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        dt = datetime.fromtimestamp(int(source_date_epoch), UTC)
    else:
        dt = datetime.now(UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def spade_bytes_literal(text: str) -> str:
    text.encode("ascii")
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'b"{escaped}"'


def render_build_info_module(project_name: str, build_timestamp: str) -> str:
    banner = f"{project_name} built {build_timestamp}\r\n"
    banner_len = len(project_name) + len(build_timestamp) + len(" built \r\n")
    return (
        f"pub fn project_name_text() -> [uint<8>; {len(project_name)}] {{\n"
        f"    {spade_bytes_literal(project_name)}\n"
        "}\n\n"
        f"pub fn build_timestamp_text() -> [uint<8>; {len(build_timestamp)}] {{\n"
        f"    {spade_bytes_literal(build_timestamp)}\n"
        "}\n\n"
        f"pub fn boot_banner_text() -> [uint<8>; {banner_len}] {{\n"
        f"    {spade_bytes_literal(banner)}\n"
        "}\n"
    )


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    project_name = project_display_name(project)
    build_timestamp = build_timestamp_text()
    banner = f"{project_name} built {build_timestamp}\r\n"

    src_path = project / "src" / "build_info.spade"
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(render_build_info_module(project_name, build_timestamp))

    build_path = project / "build" / "build_info.json"
    build_path.parent.mkdir(parents=True, exist_ok=True)
    build_path.write_text(
        json.dumps(
            {
                "project_name": project_name,
                "build_timestamp": build_timestamp,
                "banner": banner,
            },
            indent=2,
        )
        + "\n"
    )

    print(f"generated {src_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

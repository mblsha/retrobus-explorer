#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
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
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_git(project: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(project), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_status_dirty(project: Path) -> bool:
    root_text = run_git(project, "rev-parse", "--show-toplevel")
    status_text = run_git(project, "status", "--porcelain")
    if not root_text or not status_text:
        return False

    root = Path(root_text).resolve()
    generated = {
        str((project / "src" / "build_info.spade").resolve().relative_to(root)),
        str((project / "build" / "build_info.json").resolve().relative_to(root)),
    }
    for raw in status_text.splitlines():
        path = raw[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path not in generated:
            return True
    return False


def git_hash_text(project: Path) -> str:
    return run_git(project, "rev-parse", "--short=12", "HEAD") or "000000000000"


def spade_bytes_literal(text: str) -> str:
    text.encode("ascii")
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'b"{escaped}"'


def render_build_info_module(project_name: str, build_timestamp: str, git_hash: str, dirty_text: str) -> str:
    banner = f"RBXBOOT project={project_name} git={git_hash} dirty={dirty_text} built={build_timestamp}\r\n"
    banner_len = len(banner)
    return (
        f"pub fn project_name_text() -> [uint<8>; {len(project_name)}] {{\n"
        f"    {spade_bytes_literal(project_name)}\n"
        "}\n\n"
        f"pub fn build_timestamp_text() -> [uint<8>; {len(build_timestamp)}] {{\n"
        f"    {spade_bytes_literal(build_timestamp)}\n"
        "}\n\n"
        f"pub fn git_hash_text() -> [uint<8>; {len(git_hash)}] {{\n"
        f"    {spade_bytes_literal(git_hash)}\n"
        "}\n\n"
        f"pub fn dirty_text() -> [uint<8>; {len(dirty_text)}] {{\n"
        f"    {spade_bytes_literal(dirty_text)}\n"
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
    git_hash = git_hash_text(project)
    dirty_text = "1" if git_status_dirty(project) else "0"
    banner = f"RBXBOOT project={project_name} git={git_hash} dirty={dirty_text} built={build_timestamp}\r\n"

    src_path = project / "src" / "build_info.spade"
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(render_build_info_module(project_name, build_timestamp, git_hash, dirty_text))

    build_path = project / "build" / "build_info.json"
    build_path.parent.mkdir(parents=True, exist_ok=True)
    build_path.write_text(
        json.dumps(
            {
                "project_name": project_name,
                "build_timestamp": build_timestamp,
                "git_hash": git_hash,
                "dirty": dirty_text == "1",
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

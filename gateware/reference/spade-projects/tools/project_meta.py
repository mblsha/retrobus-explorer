from __future__ import annotations

import glob
import tomllib
from pathlib import Path


def load_swim(project: Path) -> dict:
    return tomllib.loads((project / "swim.toml").read_text())


def tooling_top(project: Path, override: str | None = None) -> str:
    if override:
        return override
    config = load_swim(project)
    return config.get("tooling", {}).get("top", "main")


def tooling_test_module(project: Path, override: str | None = None) -> str | None:
    if override:
        return override
    config = load_swim(project)
    return config.get("tooling", {}).get("test_module")


def resolve_verilog_sources(project: Path) -> list[Path]:
    config = load_swim(project)
    patterns = config.get("verilog", {}).get("sources", [])
    resolved: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for match in sorted(glob.glob(str(project / pattern), recursive=True)):
            path = Path(match).resolve()
            if path.is_file() and path not in seen:
                seen.add(path)
                resolved.append(path)
    return resolved

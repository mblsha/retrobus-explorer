from __future__ import annotations

import glob
import tomllib
from pathlib import Path


def load_swim(project: Path) -> dict:
    return tomllib.loads((project / "swim.toml").read_text())


def project_name(project: Path) -> str:
    config = load_swim(project)
    name = config.get("name")
    if isinstance(name, str) and name:
        return name
    return project.name


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


def path_libraries(project: Path) -> list[Path]:
    """Directories of every path library the project compiles, transitively."""
    found: list[Path] = []
    pending = [project.resolve()]
    while pending:
        declaring = pending.pop()
        for library in load_swim(declaring).get("libraries", {}).values():
            if not isinstance(library, dict) or "path" not in library:
                continue
            # swim resolves a library path against the swim.toml declaring it.
            directory = (declaring / library["path"]).resolve()
            if directory not in found and (directory / "swim.toml").is_file():
                found.append(directory)
                pending.append(directory)
    return found

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


def _find_gateware_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "projects.toml").is_file():
            return candidate
    raise RuntimeError(f"could not locate gateware/projects.toml from {start}")


GATEWARE_ROOT = _find_gateware_root(Path(__file__).resolve().parent)
REGISTRY_PATH = GATEWARE_ROOT / "projects.toml"
ALLOWED_KINDS = frozenset({"application", "diagnostic", "example"})


@dataclass(frozen=True)
class ProjectSpec:
    path: Path
    kind: str
    ci: bool


class InventoryError(RuntimeError):
    pass


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def load_registry(root: Path = GATEWARE_ROOT) -> tuple[ProjectSpec, ...]:
    config = _load_toml(root / "projects.toml")
    if config.get("version") != 1:
        raise InventoryError("projects.toml must declare version = 1")

    rows = config.get("projects")
    if not isinstance(rows, list):
        raise InventoryError("projects.toml must contain [[projects]] entries")

    projects: list[ProjectSpec] = []
    seen: set[Path] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise InventoryError(f"projects.toml entry {index} must be a table")
        raw_path = row.get("path")
        kind = row.get("kind")
        ci = row.get("ci")
        if not isinstance(raw_path, str) or not raw_path:
            raise InventoryError(f"projects.toml entry {index} needs a non-empty path")
        path = Path(raw_path)
        if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("projects",):
            raise InventoryError(f"invalid project path: {raw_path}")
        if path in seen:
            raise InventoryError(f"duplicate project path: {raw_path}")
        if kind not in ALLOWED_KINDS:
            raise InventoryError(f"{raw_path}: unsupported kind {kind!r}")
        if not isinstance(ci, bool):
            raise InventoryError(f"{raw_path}: ci must be true or false")
        seen.add(path)
        projects.append(ProjectSpec(path=path, kind=kind, ci=ci))
    return tuple(projects)


def ci_project_paths(root: Path = GATEWARE_ROOT) -> tuple[Path, ...]:
    return tuple(root / project.path for project in load_registry(root) if project.ci)


def workspace_members(root: Path = GATEWARE_ROOT) -> tuple[str, ...]:
    config = _load_toml(root / "pyproject.toml")
    members = config.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    if not isinstance(members, list) or not all(isinstance(member, str) for member in members):
        raise InventoryError("[tool.uv.workspace].members must be a list of project paths")
    if len(members) != len(set(members)):
        raise InventoryError("uv workspace members must each appear exactly once")
    return tuple(sorted(members))


def _discovered_project_paths(root: Path) -> tuple[str, ...]:
    projects_root = root / "projects"
    if not projects_root.is_dir():
        return ()
    return tuple(
        sorted(
            path.parent.relative_to(root).as_posix()
            for path in projects_root.glob("*/swim.toml")
        )
    )


def validate_project_inventory(root: Path = GATEWARE_ROOT) -> tuple[Path, ...]:
    errors: list[str] = []
    try:
        specs = load_registry(root)
    except (FileNotFoundError, tomllib.TOMLDecodeError, InventoryError) as exc:
        raise InventoryError(f"invalid project registry: {exc}") from exc

    expected = tuple(project.path.as_posix() for project in specs)
    discovered = _discovered_project_paths(root)
    missing = sorted(set(expected) - set(discovered))
    unexpected = sorted(set(discovered) - set(expected))
    if missing:
        errors.append(f"missing registered projects: {', '.join(missing)}")
    if unexpected:
        errors.append(f"unregistered Spade projects: {', '.join(unexpected)}")

    try:
        members = workspace_members(root)
    except (FileNotFoundError, tomllib.TOMLDecodeError, InventoryError) as exc:
        errors.append(f"invalid uv workspace: {exc}")
    else:
        expected_members = tuple(sorted(expected))
        if members != expected_members:
            missing_members = sorted(set(expected_members) - set(members))
            unexpected_members = sorted(set(members) - set(expected_members))
            if missing_members:
                errors.append(f"projects missing from uv workspace: {', '.join(missing_members)}")
            if unexpected_members:
                errors.append(f"unexpected uv workspace members: {', '.join(unexpected_members)}")

    for spec in specs:
        project = root / spec.path
        for relative in (
            Path("pyproject.toml"),
            Path("swim.lock"),
            Path("scripts/test_with_vcd.py"),
        ):
            if not (project / relative).is_file():
                errors.append(f"{spec.path.as_posix()}: missing {relative.as_posix()}")

        swim_toml = project / "swim.toml"
        if not swim_toml.is_file():
            errors.append(f"{spec.path.as_posix()}: missing swim.toml")
            continue
        try:
            config = _load_toml(swim_toml)
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{spec.path.as_posix()}: invalid swim.toml: {exc}")
            continue

        tooling = config.get("tooling", {})
        test_module = tooling.get("test_module") if isinstance(tooling, dict) else None
        if not isinstance(test_module, str) or not test_module:
            errors.append(f"{spec.path.as_posix()}: [tooling].test_module must name a Cocotb module")
            continue
        test_file = project / "test" / f"{test_module}.py"
        if not test_file.is_file():
            errors.append(
                f"{spec.path.as_posix()}: configured Cocotb module is missing: "
                f"{test_file.relative_to(project)}"
            )

    if errors:
        raise InventoryError("Spade project inventory is incomplete:\n- " + "\n- ".join(errors))

    return tuple(root / spec.path for spec in specs if spec.ci)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and list the registered Spade FPGA projects"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate without printing project paths",
    )
    args = parser.parse_args()

    try:
        projects = validate_project_inventory()
    except InventoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.check:
        for project in projects:
            print(project.relative_to(GATEWARE_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

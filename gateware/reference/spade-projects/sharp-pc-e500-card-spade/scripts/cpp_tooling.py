from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def cpp_source_dir() -> Path:
    return project_root() / "cpp"


def cpp_build_dir() -> Path:
    return project_root() / ".cpp-build"


def cpp_binary_path(name: str) -> Path:
    return cpp_build_dir() / name


def _source_mtime() -> float:
    latest = 0.0
    for path in cpp_source_dir().rglob("*"):
        if path.is_file():
            latest = max(latest, path.stat().st_mtime)
    return latest


def ensure_cpp_tools_built() -> None:
    build_dir = cpp_build_dir()
    source_dir = cpp_source_dir()
    capture_bin = cpp_binary_path("capture_ft_cpp")
    vcd_bin = cpp_binary_path("ft_to_vcd_cpp")
    newest_source = _source_mtime()

    need_configure = not (build_dir / "CMakeCache.txt").exists()
    need_build = (
        not capture_bin.exists()
        or not vcd_bin.exists()
        or capture_bin.stat().st_mtime < newest_source
        or vcd_bin.stat().st_mtime < newest_source
    )

    if need_configure:
        subprocess.run(
            ["cmake", "-S", str(source_dir), "-B", str(build_dir)],
            check=True,
        )
        need_build = True

    if need_build:
        subprocess.run(
            ["cmake", "--build", str(build_dir), "--target", "capture_ft_cpp", "ft_to_vcd_cpp", "-j"],
            check=True,
        )


def exec_cpp_tool(name: str, argv: list[str]) -> "NoReturn":
    ensure_cpp_tools_built()
    binary = cpp_binary_path(name)
    os.execv(str(binary), [str(binary), *argv])


def run_cpp_tool(name: str, argv: list[str], **kwargs):
    ensure_cpp_tools_built()
    binary = cpp_binary_path(name)
    return subprocess.run([str(binary), *argv], **kwargs)

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from project_meta import resolve_verilog_sources
from project_meta import tooling_test_module
from project_meta import tooling_top


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def require_command(name: str, help_text: str) -> None:
    if shutil.which(name) is None:
        print(f"error: missing `{name}` ({help_text})", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cocotb test and emit VCD for Surfer")
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--top", help="HDL top module name (default: tooling.top or main)")
    parser.add_argument("--test-module", help="Python test module name (default: tooling.test_module)")
    parser.add_argument("--build-dir", default="build/main_cocotb", help="Cocotb build directory")
    args = parser.parse_args()

    require_command("uv", "https://docs.astral.sh/uv/")
    require_command("swim", "install swim from spade-lang")

    project = args.project.resolve()
    top = tooling_top(project, args.top)
    test_module = tooling_test_module(project, args.test_module)
    if not test_module:
        print(
            "error: missing test module; pass --test-module or set [tooling].test_module in swim.toml",
            file=sys.stderr,
        )
        return 2

    test_dir = project / "test"
    tools_dir = Path(__file__).resolve().parent
    umbrella_project = tools_dir.parent

    env = os.environ.copy()
    env["PATH"] = f"{Path.home()}/.local/share/swim/bin/oss-cad-suite/bin:{env['PATH']}"
    env["PYTHONPATH"] = str(tools_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("VIRTUAL_ENV", None)
    if shutil.which("verilator", path=env["PATH"]) is None:
        print("error: verilator not found in PATH", file=sys.stderr)
        return 1

    run(["swim", "build"], cwd=project, env=env)

    # Avoid stale cocotb/verilator makefiles when the Python env path changes.
    cocotb_build_dir = project / args.build_dir
    if cocotb_build_dir.exists():
        shutil.rmtree(cocotb_build_dir)

    verilog_sources = [project / "build" / "spade.sv"] + resolve_verilog_sources(project)
    verilog_list_repr = ", ".join(f"Path(r'{p}')" for p in verilog_sources)
    driver = (
        "from pathlib import Path\n"
        "from cocotb.runner import get_runner\n"
        "runner = get_runner('verilator')\n"
        f"runner.build(verilog_sources=[{verilog_list_repr}], hdl_toplevel='{top}', always=True, waves=True, build_dir='{args.build_dir}')\n"
        f"runner.test(hdl_toplevel='{top}', test_module='{test_module}', test_dir=Path('test'), waves=True)\n"
    )
    run(
        [
            "uv",
            "run",
            "--project",
            str(umbrella_project),
            "python",
            "-c",
            driver,
        ],
        cwd=project,
        env=env,
    )

    vcd = test_dir / "dump.vcd"
    surfer_vcd = test_dir / "dump.surfer.vcd"
    if not vcd.exists():
        print(f"error: expected {vcd}", file=sys.stderr)
        return 1

    shutil.copyfile(vcd, surfer_vcd)
    print(f"waveform: {vcd}")
    print(f"surfer waveform: {surfer_vcd}")
    print(f"results: {test_dir / 'results.xml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

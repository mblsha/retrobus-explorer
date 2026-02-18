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


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def require_command(name: str, help_text: str) -> None:
    if shutil.which(name) is None:
        print(f"error: missing `{name}` ({help_text})", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cocotb test and emit VCD for Surfer")
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--top", default="main", help="HDL top module name")
    parser.add_argument("--test-module", required=True, help="Python test module name")
    parser.add_argument("--build-dir", default="build/main_cocotb", help="Cocotb build directory")
    args = parser.parse_args()

    require_command("uv", "https://docs.astral.sh/uv/")
    require_command("swim", "install swim from spade-lang")

    project = args.project.resolve()
    test_dir = project / "test"
    venv_python = project / ".venv-host" / "bin" / "python"

    env = os.environ.copy()
    env["PATH"] = f"{Path.home()}/.local/share/swim/bin/oss-cad-suite/bin:{env['PATH']}"
    if shutil.which("verilator", path=env["PATH"]) is None:
        print("error: verilator not found in PATH", file=sys.stderr)
        return 1

    run(["swim", "build"], cwd=project, env=env)

    if not venv_python.exists():
        run(["uv", "venv", str(project / ".venv-host")], cwd=project, env=env)

    run(
        ["uv", "pip", "install", "--python", str(venv_python), "cocotb<2"],
        cwd=project,
        env=env,
    )

    driver = (
        "from pathlib import Path\n"
        "from cocotb.runner import get_runner\n"
        "runner = get_runner('verilator')\n"
        f"runner.build(verilog_sources=[Path('build/spade.sv')], hdl_toplevel='{args.top}', always=True, waves=True, build_dir='{args.build_dir}')\n"
        f"runner.test(hdl_toplevel='{args.top}', test_module='{args.test_module}', test_dir=Path('test'), waves=True)\n"
    )
    run([str(venv_python), "-c", driver], cwd=project, env=env)

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

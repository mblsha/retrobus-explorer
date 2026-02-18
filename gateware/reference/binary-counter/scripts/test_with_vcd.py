#!/usr/bin/env python3
from __future__ import annotations

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
    root_dir = Path(__file__).resolve().parent.parent
    build_dir = root_dir / "build"
    test_dir = root_dir / "test"
    compiler_repo = build_dir / "spade"
    compiler_bin = compiler_repo / "target" / "release" / "spade"
    host_venv_python = root_dir / ".venv-host" / "bin" / "python"

    require_command("uv", "https://docs.astral.sh/uv/")
    require_command("cargo", "install Rust toolchain")
    require_command("git", "needed to clone spade compiler")
    require_command("perl", "needed by verilator frontend")

    env = os.environ.copy()
    env["PATH"] = f"{Path.home()}/.local/share/swim/bin/oss-cad-suite/bin:{env['PATH']}"
    if shutil.which("verilator", path=env["PATH"]) is None:
        print("error: verilator not found in PATH", file=sys.stderr)
        return 1

    build_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    if not (compiler_repo / ".git").exists():
        run(
            ["git", "clone", "--depth", "1", "https://gitlab.com/spade-lang/spade.git", str(compiler_repo)],
            cwd=root_dir,
            env=env,
        )

    run(
        ["cargo", "build", "--release", "--manifest-path", str(compiler_repo / "spade-compiler" / "Cargo.toml")],
        cwd=root_dir,
        env=env,
    )

    run(
        [
            str(compiler_bin),
            "-o",
            str(build_dir / "spade.sv"),
            str(root_dir / "src" / "main.spade"),
        ],
        cwd=root_dir,
        env=env,
    )

    if not host_venv_python.exists():
        run(["uv", "venv", str(root_dir / ".venv-host")], cwd=root_dir, env=env)

    run(
        ["uv", "pip", "install", "--python", str(host_venv_python), "cocotb<2"],
        cwd=root_dir,
        env=env,
    )

    cocotb_runner = (
        "from pathlib import Path\n"
        "from cocotb.runner import get_runner\n"
        "runner = get_runner('verilator')\n"
        "runner.build(verilog_sources=[Path('build/spade.sv')], hdl_toplevel='main', "
        "always=True, waves=True, build_dir='build/main_cocotb')\n"
        "runner.test(hdl_toplevel='main', test_module='counter_pins', test_dir=Path('test'), waves=True)\n"
    )
    run([str(host_venv_python), "-c", cocotb_runner], cwd=root_dir, env=env)

    vcd_path = test_dir / "dump.vcd"
    if not vcd_path.exists():
        print("error: expected VCD output at test/dump.vcd", file=sys.stderr)
        return 1

    print("ok: test passed")
    print("waveform: test/dump.vcd")
    print("results: test/results.xml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

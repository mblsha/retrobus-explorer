#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, quiet: bool = False) -> None:
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    subprocess.run(cmd, cwd=cwd, env=env, check=True, stdout=stdout, stderr=stderr)


def require_command(name: str, message: str) -> None:
    if shutil.which(name) is None:
        print(f"error: {message}", file=sys.stderr)
        sys.exit(1)


def newest_wheel(dist_dir: Path) -> Path | None:
    wheels = sorted(dist_dir.glob("spade-*.whl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return wheels[0] if wheels else None


def main() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    build_dir = root_dir / "build"
    dist_dir = build_dir / "dist"
    test_dir = root_dir / "test"
    host_venv_python = root_dir / ".venv-host" / "bin" / "python"
    compiler_repo = build_dir / "spade"
    spade_bin = compiler_repo / "target" / "release" / "spade"
    translator_bin = compiler_repo / "target" / "release" / "vcd-translate"

    require_command("uv", "uv is required (https://docs.astral.sh/uv/)")
    require_command("cargo", "cargo is required")
    require_command("perl", "perl is required (verilator wrapper uses perl)")
    require_command("git", "git is required")

    env = os.environ.copy()
    env["PATH"] = f"{Path.home()}/.local/share/swim/bin/oss-cad-suite/bin:{env['PATH']}"
    if shutil.which("verilator", path=env["PATH"]) is None:
        print("error: verilator not found. Install OSS CAD Suite or set PATH accordingly.", file=sys.stderr)
        return 1

    dist_dir.mkdir(parents=True, exist_ok=True)
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
            str(spade_bin),
            "-o",
            str(build_dir / "spade.sv"),
            "--mir-output",
            str(build_dir / "spade.spmir"),
            "--state-dump",
            str(build_dir / "state.bincode"),
            "--item-list",
            str(build_dir / "items.ron"),
            "--verilator-wrapper-output",
            str(build_dir / "verilator_wrapper.hpp"),
            str(root_dir / "src" / "main.spade"),
        ],
        cwd=root_dir,
        env=env,
    )

    if not host_venv_python.exists():
        run(["uv", "venv", str(root_dir / ".venv-host")], cwd=root_dir, env=env)

    wheel = newest_wheel(dist_dir)
    if wheel is None:
        run(
            [
                "uvx",
                "maturin",
                "build",
                "--release",
                "-b",
                "pyo3",
                "-o",
                str(dist_dir),
            ],
            cwd=compiler_repo / "spade-python",
            env=env,
        )
        wheel = newest_wheel(dist_dir)

    if wheel is None:
        print("error: failed to find/build spade wheel in build/dist", file=sys.stderr)
        return 1

    run(
        ["uv", "pip", "install", "--python", str(host_venv_python), "cocotb", str(wheel)],
        cwd=root_dir,
        env=env,
        quiet=True,
    )

    cocotb_driver = (
        "from pathlib import Path\n"
        "from cocotb.runner import get_runner\n"
        "runner = get_runner('verilator')\n"
        "runner.build(verilog_sources=[Path('build/spade.sv')], hdl_toplevel='led_counter', "
        "always=True, waves=True, build_dir='build/led_counter_cocotb')\n"
        "runner.test(hdl_toplevel='led_counter', test_module='led_counter', test_dir=Path('test'), waves=True)\n"
    )
    sim_env = env.copy()
    sim_env["SWIM_SPADE_STATE"] = str(build_dir / "state.bincode")
    sim_env["SWIM_UUT"] = "led_counter"
    run([str(host_venv_python), "-c", cocotb_driver], cwd=root_dir, env=sim_env)

    raw_vcd = test_dir / "dump.vcd"
    surfer_vcd = test_dir / "dump.surfer.vcd"
    if not raw_vcd.exists():
        print("error: test run did not produce test/dump.vcd", file=sys.stderr)
        return 1

    shutil.copyfile(raw_vcd, surfer_vcd)

    translate_failed = False
    try:
        run(
            [
                "cargo",
                "build",
                "--release",
                "--manifest-path",
                str(compiler_repo / "vcd-translate" / "Cargo.toml"),
            ],
            cwd=root_dir,
            env=env,
            quiet=True,
        )
        run(
            [
                str(translator_bin),
                str(raw_vcd),
                "-s",
                str(build_dir / "state.bincode"),
                "-o",
                str(surfer_vcd),
                "-t",
                "led_counter",
            ],
            cwd=root_dir,
            env=env,
            quiet=True,
        )
    except subprocess.CalledProcessError:
        translate_failed = True

    if translate_failed:
        print("warning: vcd translation failed; test/dump.surfer.vcd is a raw VCD copy", file=sys.stderr)

    print("raw waveform: test/dump.vcd")
    print("surfer waveform: test/dump.surfer.vcd")
    print("results: test/results.xml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

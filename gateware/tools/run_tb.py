#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from project_meta import path_libraries
from project_meta import resolve_verilog_sources
from project_meta import tooling_test_module
from project_meta import tooling_top

FAILURE_RECORDS_KEPT = 20

# A Cocotb log record starts with its simulation time; the traceback of a
# failed test follows its record as indented continuation lines.
_LOG_RECORD = re.compile(r"^\s*(?:-\.--|\d+\.\d+)ns\s")
_ENVIRONMENT_READ = re.compile(rb"environ(?:\.get)?[\[(]\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def run(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    log: BinaryIO | None = None,
) -> None:
    if log is None:
        subprocess.run(cmd, cwd=cwd, env=env, check=True)
        return
    # Copy the combined output to the console and the log as it arrives. The
    # JUnit file records only that a test failed; the traceback exists nowhere
    # but in this stream.
    sys.stdout.flush()
    process = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    assert process.stdout is not None
    for chunk in iter(process.stdout.read1, b""):
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        log.write(chunk)
    if process.wait():
        raise subprocess.CalledProcessError(process.returncode, cmd)


def require_command(name: str, help_text: str) -> None:
    if shutil.which(name) is None:
        print(f"error: missing `{name}` ({help_text})", file=sys.stderr)
        raise SystemExit(1)


def cocotb_result_failures(results_path: Path) -> list[str]:
    root = ET.parse(results_path).getroot()
    testcases = root.findall(".//testcase")
    if not testcases:
        return ["Cocotb reported no test cases"]

    failures: list[str] = []
    for testcase in testcases:
        classname = testcase.get("classname", "<unknown module>")
        name = testcase.get("name", "<unknown test>")
        for outcome in ("failure", "error"):
            detail = testcase.find(outcome)
            if detail is not None:
                message = detail.get("message") or (detail.text or "").strip() or outcome
                failures.append(f"{classname}.{name}: {message}")
    return failures


@contextlib.contextmanager
def project_lock(project: Path) -> Iterator[None]:
    """Serialize runs on one project.

    Every run on a project shares its swim build directory and writes the same
    test/results.xml, whatever --build-dir, --top, or --test-module it was
    given, so two of them at once can each report the other's result.
    """
    lock_path = project / "build" / ".run_tb.lock"
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            holder = handle.read().strip() or "another process"
            print(f"waiting for {holder} to finish with {project.name}", flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        handle.write(f"run_tb.py pid {os.getpid()}\n")
        handle.flush()
        yield


def testbench_inputs(project: Path, tools_dir: Path) -> list[Path]:
    """Every file whose content decides what a run builds and asserts."""
    inputs = set(resolve_verilog_sources(project))
    inputs.update(tools_dir.glob("*.py"))
    for directory in [project, *path_libraries(project)]:
        inputs.add(directory / "swim.toml")
        inputs.update((directory / "src").rglob("*.spade"))
        inputs.update((directory / "test").rglob("*.py"))
    return sorted(path for path in inputs if path.is_file())


def fingerprint(paths: list[Path]) -> dict[Path, str]:
    digests: dict[Path, str] = {}
    for path in paths:
        # A checkout someone else is editing can lose a file between the
        # listing and the read; an absent file then compares as a change.
        with contextlib.suppress(OSError):
            digests[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def changed_inputs(before: dict[Path, str], after: dict[Path, str]) -> list[Path]:
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )


def testbench_environment(inputs: list[Path], env: dict[str, str]) -> dict[str, str]:
    """The variables that select tests or that the testbench sources read."""
    names = {"TESTCASE", "RANDOM_SEED"}
    names.update(name for name in env if name.startswith("COCOTB_"))
    for path in inputs:
        if path.suffix == ".py":
            with contextlib.suppress(OSError):
                names.update(
                    match.decode() for match in _ENVIRONMENT_READ.findall(path.read_bytes())
                )
    return {name: env[name] for name in sorted(names) if name in env}


def failure_excerpts(log_text: str) -> list[str]:
    """Each failed test's log record together with its traceback."""
    lines = log_text.splitlines()
    excerpts: list[str] = []
    for index, line in enumerate(lines):
        if not (_LOG_RECORD.match(line) and line.rstrip().endswith(" failed")):
            continue
        record = [line]
        for continuation in lines[index + 1 :]:
            if _LOG_RECORD.match(continuation) or not continuation.startswith(" "):
                break
            record.append(continuation)
        excerpts.append("\n".join(record))
    return excerpts


def git_state(directory: Path) -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=directory, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "."],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.rstrip()
    except (OSError, subprocess.CalledProcessError):
        return "git state: unavailable\n"
    return f"git HEAD: {head}\nuncommitted changes:\n{dirty or '(none)'}\n"


def failure_provenance(
    started: str,
    umbrella_project: Path,
    changed: list[Path],
    environment: dict[str, str],
    errors: list[str],
) -> str:
    """What a failed run was run against, for whoever reads its log later.

    The sources identify the design. build/spade.sv does not: the Spade
    compiler renumbers it on every rebuild of unchanged sources.
    """
    return (
        f"command: {' '.join(sys.argv)}\n"
        f"started: {started}\n"
        f"finished: {time.strftime('%Y-%m-%d %H:%M:%S %z')}\n"
        + git_state(umbrella_project)
        + "inputs changed during the run:\n"
        + "".join(f"  {path}\n" for path in changed or ["(none)"])
        + "testbench environment:\n"
        + "".join(f"  {name}={value}\n" for name, value in environment.items() or [("(none)", "")])
        + "failures:\n"
        + "".join(f"  {error}\n" for error in errors)
    )


def preserve_failure(project: Path, label: str, files: list[Path], provenance: str) -> Path:
    """Keep a failed run's evidence where the next run will not overwrite it."""
    records = project / "build" / "run_tb_failures"
    record = records / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}"
    record.mkdir(parents=True, exist_ok=True)
    for path in files:
        if path.is_file():
            shutil.copy2(path, record / path.name)
    (record / "provenance.txt").write_text(provenance)
    for stale in sorted(p for p in records.iterdir() if p.is_dir())[:-FAILURE_RECORDS_KEPT]:
        shutil.rmtree(stale)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cocotb tests; optionally emit VCD for Surfer")
    parser.add_argument("--project", required=True, type=Path, help="Spade project directory")
    parser.add_argument("--top", help="HDL top module name (default: tooling.top or main)")
    parser.add_argument("--test-module", help="Python test module name (default: tooling.test_module)")
    parser.add_argument("--build-dir", default="build/main_cocotb", help="Cocotb build directory")
    parser.add_argument("--waves", action="store_true", help="Emit dump.vcd and dump.surfer.vcd")
    args = parser.parse_args()

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

    tools_dir = Path(__file__).resolve().parent

    env = os.environ.copy()
    env["PATH"] = f"{Path.home()}/.local/share/swim/bin/oss-cad-suite/bin:{env['PATH']}"
    env["PYTHONPATH"] = str(tools_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("VIRTUAL_ENV", None)
    if shutil.which("verilator", path=env["PATH"]) is None:
        print("error: verilator not found in PATH", file=sys.stderr)
        return 1

    with project_lock(project):
        return run_locked(args, project, top, test_module, tools_dir, env)


def run_locked(
    args: argparse.Namespace,
    project: Path,
    top: str,
    test_module: str,
    tools_dir: Path,
    env: dict[str, str],
) -> int:
    test_dir = project / "test"
    vcd = test_dir / "dump.vcd"
    surfer_vcd = test_dir / "dump.surfer.vcd"
    results_xml = test_dir / "results.xml"
    log_path = project / "build" / "run_tb.log"
    umbrella_project = tools_dir.parent

    started = time.strftime("%Y-%m-%d %H:%M:%S %z")
    inputs = testbench_inputs(project, tools_dir)
    inputs_before = fingerprint(inputs)
    with log_path.open("wb") as log:
        errors = build_and_simulate(args, project, top, test_module, umbrella_project, env, log)

    # Another session editing the checkout makes a run fail, or pass, for a
    # tree that no longer exists by the time anyone looks. Say so, rather than
    # leave a result that cannot be reproduced looking like a flaky test.
    changed = changed_inputs(inputs_before, fingerprint(testbench_inputs(project, tools_dir)))
    if changed:
        print("warning: testbench inputs changed while this run was in progress:", file=sys.stderr)
        for path in changed:
            print(f"- {path}", file=sys.stderr)

    if args.waves and not errors and not vcd.exists():
        errors.append(f"expected {vcd}")

    if errors:
        print("error: testbench run failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        for excerpt in failure_excerpts(log_path.read_text(errors="replace")):
            print(excerpt, file=sys.stderr)
        provenance = failure_provenance(
            started,
            umbrella_project,
            changed,
            testbench_environment(inputs, env),
            errors,
        )
        record = preserve_failure(project, test_module, [log_path, results_xml], provenance)
        print(f"failure record: {record}", file=sys.stderr)
        return 1

    if args.waves:
        shutil.copyfile(vcd, surfer_vcd)
        print(f"waveform: {vcd}")
        print(f"surfer waveform: {surfer_vcd}")
    print(f"results: {results_xml}")
    return 0


def build_and_simulate(
    args: argparse.Namespace,
    project: Path,
    top: str,
    test_module: str,
    umbrella_project: Path,
    env: dict[str, str],
    log: BinaryIO,
) -> list[str]:
    """Build and run the testbench; return what went wrong, if anything."""
    test_dir = project / "test"
    results_xml = test_dir / "results.xml"

    # Remove the previous result first, so that a build which stops early can
    # never be followed by a reading of the last run's verdict.
    if results_xml.exists():
        results_xml.unlink()

    try:
        run(["swim", "build"], cwd=project, env=env, log=log)
    except subprocess.CalledProcessError as exc:
        return [f"`swim build` exited with status {exc.returncode}"]

    # Avoid stale cocotb/verilator makefiles when the Python env path changes.
    cocotb_build_dir = project / args.build_dir
    if cocotb_build_dir.exists():
        shutil.rmtree(cocotb_build_dir)

    if not args.waves:
        for stale_wave in (test_dir / "dump.vcd", test_dir / "dump.surfer.vcd"):
            if stale_wave.exists():
                stale_wave.unlink()

    verilog_sources = [project / "build" / "spade.sv"] + resolve_verilog_sources(project)
    verilog_list_repr = ", ".join(f"Path(r'{p}')" for p in verilog_sources)
    waves_literal = "True" if args.waves else "False"
    driver = (
        "from pathlib import Path\n"
        "from cocotb.runner import get_runner\n"
        "runner = get_runner('verilator')\n"
        f"runner.build(verilog_sources=[{verilog_list_repr}], hdl_toplevel='{top}', always=True, waves={waves_literal}, build_dir='{args.build_dir}')\n"
        f"runner.test(hdl_toplevel='{top}', test_module='{test_module}', test_dir=Path('test'), waves={waves_literal})\n"
    )
    venv_python = umbrella_project / ".venv" / "bin" / "python"
    if venv_python.is_file():
        command = [str(venv_python), "-c", driver]
    else:
        require_command("uv", "https://docs.astral.sh/uv/")
        command = ["uv", "run", "python", "-c", driver]
    errors: list[str] = []
    try:
        run(command, cwd=project, env=env, log=log)
    except subprocess.CalledProcessError as exc:
        errors.append(f"the Verilator build or simulation exited with status {exc.returncode}")

    if not results_xml.is_file():
        return errors + [f"Cocotb did not create {results_xml}"]
    try:
        return errors + cocotb_result_failures(results_xml)
    except ET.ParseError as exc:
        return errors + [f"invalid Cocotb results XML at {results_xml}: {exc}"]


if __name__ == "__main__":
    raise SystemExit(main())

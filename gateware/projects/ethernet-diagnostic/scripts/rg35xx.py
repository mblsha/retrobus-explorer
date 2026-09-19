#!/usr/bin/env python3
"""One entry point for the RG35XX Plus boot tooling.

The work is split across a package because each piece has its own contracts to
check, but a bench operator should not have to know which module a command
lives in, nor set PYTHONPATH to reach it. This puts the project directory on
the path and dispatches to the module that owns the subcommand, so every
documented command line starts the same way.
"""

import importlib
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
# Ahead of everything, including this script's own directory: that directory
# holds a module named rg35xx.py, which would otherwise shadow the rg35xx
# package the subcommands live in.
if sys.path[:1] != [str(PROJECT)]:
    sys.path.insert(0, str(PROJECT))

SUBCOMMANDS = {
    "image": "rg35xx.cli",
    "trial": "rg35xx.trial",
    "report": "rg35xx.report",
    "deploy": "rg35xx.deploy",
    "build-kernel": "rg35xx.build_kernel",
    "build-rootfs": "rg35xx.build_rootfs",
}


def describe(name: str) -> str:
    """One line for a subcommand, taken from the module that implements it.

    The description is not restated here so that it cannot drift from what the
    module's own `--help` prints.
    """
    doc = importlib.import_module(SUBCOMMANDS[name]).__doc__ or ""
    lines = [line for line in doc.strip().splitlines() if line.strip()]
    return lines[0] if lines else ""


def usage() -> str:
    width = max(len(name) for name in SUBCOMMANDS)
    lines = [
        "usage: rg35xx.py <command> [options]",
        "",
        __doc__.strip().splitlines()[0],
        "",
        "commands:",
    ]
    lines += [f"  {name:<{width}}  {describe(name)}" for name in SUBCOMMANDS]
    lines += ["", "Run 'rg35xx.py <command> --help' for that command's options."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return 0
    command, rest = argv[0], argv[1:]
    if command not in SUBCOMMANDS:
        print(f"rg35xx.py: unknown command {command!r}", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 2
    module = importlib.import_module(SUBCOMMANDS[command])
    # argparse names the program after argv[0]; naming it after the whole
    # command keeps a subcommand's own usage line copy-pasteable. It is put
    # back afterwards so that calling this from a test leaves no trace.
    program = sys.argv[0]
    sys.argv[0] = f"{Path(program).name} {command}"
    try:
        return module.main(rest) or 0
    finally:
        sys.argv[0] = program


if __name__ == "__main__":
    sys.exit(main())

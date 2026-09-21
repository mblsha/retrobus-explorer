#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Extract and compare the hardware-visible surface of a generated spade.sv.

Spade mangles the name of every internal unit as `\\path::to::unit[1234]`; a
unit marked `#[no_mangle]` or `#[no_mangle(all)]` keeps the plain name it was
written with. Those plain names, their port lists, and the parameterisations of
the external SystemVerilog the design instantiates are what the Cocotb
testbenches reach for by `dut.<port>` and what the ACF/XDC constraints bind to.
Everything else in the file is an implementation detail the compiler is free to
rename between releases, and does.

So this is the invariant to check when the compiler or the wiring style
changes: build before, build after, and compare the surfaces. Two builds whose
surfaces match still present the same design to the testbenches and to the
constraints, whatever happened to the netlist in between.

Usage:
  sv_module_surface.py <file.sv> ...           print each file's surface
  sv_module_surface.py --diff <a> <b>          compare two files, or two
                                               directories of `<project>.sv`
Exits non-zero when a surface differs.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MODULE_RE = re.compile(r"(?m)^module\s+(\\\S+\s|\w+)\s*\(")
INSTANCE_RE = re.compile(r"(?m)^\s+(\w+)\s*(#\(.*?\))?\s+\\?[\w$]+\s*\(\.")

# Words that can start a line inside a module body and look like an instance.
NOT_A_MODULE = frozenset(
    {
        "input", "output", "inout", "wire", "reg", "logic", "assign", "always",
        "always_comb", "always_ff", "always_latch", "initial", "if", "else",
        "case", "casez", "casex", "endcase", "begin", "end", "localparam",
        "parameter", "module", "endmodule", "return", "for", "while", "generate",
        "endgenerate", "function", "endfunction", "task", "endtask",
    }
)


def _is_mangled(name: str) -> bool:
    return name.startswith("\\")


def module_headers(text: str) -> list[str]:
    """`module NAME (port port ...)` for every unmangled module, sorted."""
    headers: list[str] = []
    for match in MODULE_RE.finditer(text):
        name = match.group(1).strip()
        if _is_mangled(name):
            continue
        end = text.find(");", match.end())
        if end < 0:
            raise ValueError(f"unterminated port list for module {name}")
        ports = text[match.end() : end].replace("\n", " ")
        joined = " ".join(port.strip() for port in ports.split(",") if port.strip())
        headers.append(f"module {name} ({joined})")
    return sorted(headers)


def external_instances(text: str) -> list[str]:
    """`NAME#(params)` for each plain-named module instantiated but not defined.

    These are the `#[no_mangle(all)]` extern entities -- the vendor and
    compatibility SystemVerilog under `rtl/vendor/` and each project's own
    `verilog/` -- together with the parameters they are given.
    """
    defined = {
        match.group(1).strip()
        for match in MODULE_RE.finditer(text)
        if not _is_mangled(match.group(1).strip())
    }
    found: set[str] = set()
    for match in INSTANCE_RE.finditer(text):
        name = match.group(1)
        if name in NOT_A_MODULE or name in defined:
            continue
        found.add(f"{name}{match.group(2) or ''}")
    return sorted(found)


def surface(text: str) -> list[str]:
    return module_headers(text) + [f"instantiates {n}" for n in external_instances(text)]


def render(path: Path) -> str:
    return "".join(f"{line}\n" for line in surface(path.read_text()))


def _pairs(a: Path, b: Path) -> list[tuple[str, Path, Path]]:
    if a.is_dir() or b.is_dir():
        names = sorted({p.name for p in a.glob("*.sv")} | {p.name for p in b.glob("*.sv")})
        return [(name, a / name, b / name) for name in names]
    return [(b.name, a, b)]


def diff(a: Path, b: Path, out=sys.stdout) -> int:
    differing = 0
    pairs = _pairs(a, b)
    for name, left, right in pairs:
        if not left.is_file() or not right.is_file():
            print(f"MISSING {name}: {left}={left.is_file()} {right}={right.is_file()}", file=out)
            differing += 1
            continue
        before, after = surface(left.read_text()), surface(right.read_text())
        if before == after:
            print(f"same    {name} ({len(before)} entries)", file=out)
            continue
        differing += 1
        print(f"DIFFER  {name}", file=out)
        for line in sorted(set(before) - set(after)):
            print(f"   -{line}", file=out)
        for line in sorted(set(after) - set(before)):
            print(f"   +{line}", file=out)
    print(f"{len(pairs)} file(s), {differing} differing", file=out)
    return differing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"),
                        help="compare two .sv files, or two directories of them")
    parser.add_argument("files", nargs="*", type=Path, help="generated .sv files to print")
    args = parser.parse_args()

    if args.diff:
        return 1 if diff(Path(args.diff[0]), Path(args.diff[1])) else 0

    if not args.files:
        parser.error("pass at least one .sv file, or --diff BEFORE AFTER")
    for path in args.files:
        print(f"### {path.name}")
        sys.stdout.write(render(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

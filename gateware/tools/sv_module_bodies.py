#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compare the *logic* of two generated spade.sv files, ignoring naming.

`sv_module_surface.py` answers "does this design still present the same thing
to the testbenches and the constraints". This answers the harder question a
behaviour-preserving refactor needs: "is the hardware inside still the same".

A rebuild is free to rename almost everything it emits, and does so whenever an
expression is added or removed anywhere in a unit:

- monomorphisation ids (`\\path::to::unit[1234]`) and `impl#7` indices shift,
- `(* src = "file.spade:12,5" *)` attributes move with the source lines,
- the compiler's own temporaries (`_e_41`, `__n2`, `x_n7`, `c3`) renumber,
- declaration order inside a module body is not stable,
- and Spade's alias-flattening pass emits pairs like

      reg[50:0] \\state ;  logic[50:0] __n2 ;  assign __n2 = \\state ;

  where which member of the pair carries the logic depends on that same
  ordering. Both spellings are the same net.

So each module body is canonicalised: aliases are collapsed onto one
deterministic representative per equivalence class, the now-trivial `assign`
lines are dropped, temporaries are renumbered in order of first use, and pure
declarations are sorted. Two builds that describe the same hardware then
compare equal whatever the compiler decided to call things, and what is left
over is a real difference worth reading.

Module *names* are part of the comparison, because losing a module or gaining
one is exactly the kind of change this is meant to catch. When a refactor
renames a unit on purpose -- turning `init_foo()` into `Foo::default()`, say --
pass `--rename` so the two can still be compared body to body.

Usage:
  sv_module_bodies.py <file.sv>                     canonical form to stdout
  sv_module_bodies.py --diff <a.sv> <b.sv>          compare two files
  sv_module_bodies.py --diff <dir-a> <dir-b>        compare directories of them
  sv_module_bodies.py --diff <a> <b> --verbose      also print a body diff
  sv_module_bodies.py --diff <a> <b> --rename 'old=new' ...
                                                    treat `old` in BEFORE as
                                                    `new` when matching bodies
  sv_module_bodies.py --diff <a> <b> --loose        also ignore what the nets
                                                    are called, to tell a
                                                    naming-only difference from
                                                    a real one
Exits non-zero when any body differs.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import Counter
from pathlib import Path

MONO_ID = re.compile(r"\[[0-9]+\]")
IMPL_ID = re.compile(r"impl#[0-9]+")
SRC_ATTR = re.compile(r'\(\* src = "[^"]*" \*\)')
# The compiler's own temporaries: `_e_41`, `_e_41_mut`, `name_n7`, `__n2`, `c3`.
GENERATED = re.compile(r"^(_e_\d+(_mut)?|[A-Za-z_][A-Za-z_0-9]*_n\d+|__n\d+|c\d+)$")
NUMBERED = re.compile(r"(_e_|[A-Za-z_][A-Za-z_0-9]*?_n|\\c)\d+")
IDENT = r"(?:\\[^\s]+\s|[A-Za-z_][A-Za-z_0-9]*)"
ALIAS_ASSIGN = re.compile(rf"^\s*assign\s+({IDENT})\s*=\s*({IDENT})\s*;\s*$")
TOKEN = re.compile(rf"(\\[^\s]+\s|\b[A-Za-z_][A-Za-z_0-9]*\b)")
PORT_DECL = re.compile(r"^\s*(?:input|output|inout)\b.*?([A-Za-z_][A-Za-z_0-9]*)\s*,?\s*$")
DECL = re.compile(r"\s*(logic|reg|localparam)\b")
DECLARED = re.compile(rf"^\s*(?:logic|reg|localparam)\b[^;=]*?({IDENT})\s*(?:[;=]|$)")
MODULE_NAME = re.compile(r"^module\s+(\\\S+|\w+)")


def _find(parent: dict[str, str], item: str) -> str:
    while parent.get(item, item) != item:
        parent[item] = parent.get(parent[item], parent[item])
        item = parent[item]
    return item


def _union(parent: dict[str, str], a: str, b: str) -> None:
    root_a, root_b = _find(parent, a), _find(parent, b)
    if root_a != root_b:
        parent[root_b] = root_a


def _module_ports(lines: list[str]) -> set[str]:
    """The names in the module header's port list; never renamed away."""
    ports: set[str] = set()
    for line in lines:
        if line.startswith("module "):
            continue
        match = PORT_DECL.match(line)
        if match:
            ports.add(match.group(1))
        if line.rstrip().endswith(");") and ports:
            break
    return ports


def _alpha_rename(body: list[str]) -> list[str]:
    """Rename every net the module declares to `net0`, `net1`, ... by first use.

    Spade suffixes a local when a name would collide (`\\r ` in one build,
    `r_n0` in the next) and whether it collides depends on how many units are in
    scope, so that spelling moves for reasons that have nothing to do with the
    hardware. Renaming declared nets positionally makes two bodies compare equal
    exactly when they are the same up to a consistent renaming of nets -- which
    is what "naming only" means. Port names and everything that is not a
    declared net, including keywords and instantiated module names, are left
    alone.
    """
    declared: set[str] = set()
    for line in body:
        match = DECLARED.match(line)
        if match:
            declared.add(match.group(1).strip())
    if not declared:
        return body

    mapping: dict[str, str] = {}
    statements = [line for line in body if not DECL.match(line)]

    def assign(match: re.Match) -> str:
        raw = match.group(1).strip()
        if raw in declared and raw not in mapping:
            mapping[raw] = f"net{len(mapping)}"
        return match.group(0)

    for line in statements:
        TOKEN.sub(assign, line)
    for name in sorted(declared):  # declared but never used in a statement
        mapping.setdefault(name, f"net{len(mapping)}")

    def substitute(match: re.Match) -> str:
        raw = match.group(1).strip()
        return mapping.get(raw, match.group(0))

    return [TOKEN.sub(substitute, line) for line in body]


def canonical_body(block: str, loose: bool = False) -> str:
    """One module's text, with everything the compiler may rename normalised.

    `loose` additionally alpha-renames the nets the module declares, so that two
    bodies which differ only in what the compiler called things compare equal.
    Run the strict comparison first and reach for this one to answer "was that
    difference only naming?".
    """
    lines = SRC_ATTR.sub("", block).splitlines()
    ports = _module_ports(lines)

    parent: dict[str, str] = {}
    alias_lines: set[int] = set()
    for index, line in enumerate(lines):
        match = ALIAS_ASSIGN.match(line)
        if not match:
            continue
        _union(parent, match.group(1).strip(), match.group(2).strip())
        alias_lines.add(index)

    def rank(name: str) -> tuple[int, int, str]:
        bare = name.lstrip("\\")
        return (0 if bare in ports else 1, 0 if not GENERATED.match(bare) else 1, name)

    members: dict[str, list[str]] = {}
    for name in list(parent):
        members.setdefault(_find(parent, name), []).append(name)
    representative: dict[str, str] = {}
    for group in members.values():
        chosen = min(group, key=rank)
        for name in group:
            representative[name] = chosen

    def substitute(match: re.Match) -> str:
        # A Verilog escaped identifier is terminated by whitespace, so the
        # trailing space belongs to the name written out, not the one read in.
        raw = match.group(1).strip()
        name = representative.get(raw, raw)
        return name + (" " if name.startswith("\\") else "")

    out: list[str] = []
    for index, line in enumerate(lines):
        if index in alias_lines:
            match = ALIAS_ASSIGN.match(line)
            left, right = match.group(1).strip(), match.group(2).strip()
            if representative.get(left, left) == representative.get(right, right):
                continue  # the line became `assign X = X;`
        out.append(TOKEN.sub(substitute, line))

    mapping: dict[str, str] = {}
    counts: Counter[str] = Counter()

    def renumber(match: re.Match) -> str:
        prefix, token = match.group(1), match.group(0)
        if token not in mapping:
            mapping[token] = f"{prefix}{counts[prefix]}"
            counts[prefix] += 1
        return mapping[token]

    body = NUMBERED.sub(renumber, "\n".join(out)).splitlines()
    if loose:
        body = _alpha_rename(body)
    # Collapsing an alias chain leaves one declaration per hop, all now spelling
    # the same net, and a chain's length depends on the same unstable ordering.
    # Two identical declarations can only come from that, since real Verilog
    # cannot declare one name twice, so exact duplicates are dropped.
    declarations = sorted(set(line for line in body if DECL.match(line)))
    rest = [line for line in body if not DECL.match(line)]
    return "\n".join(rest + declarations) + "\n"


def split_modules(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines(keepends=True):
        if line.startswith("module "):
            current = [line]
        elif current is not None:
            current.append(line)
            if line.startswith("endmodule"):
                blocks.append("".join(current))
                current = None
    if current:
        blocks.append("".join(current))
    return blocks


def module_name(block: str) -> str:
    match = MODULE_NAME.match(block)
    return match.group(1) if match else "<unnamed>"


def canonical_modules(
    text: str,
    renames: dict[str, str] | None = None,
    drop_build_info: bool = True,
    loose: bool = False,
) -> list[str]:
    """Every module's canonical body, sorted, ready to compare as a multiset.

    `build_info` carries the build timestamp and is dropped by default: it
    differs between any two builds and says nothing about the hardware.

    Renames are applied to the raw text, before ids are normalised, so a
    replacement may be spelled the way the compiler wrote it (`impl#3::default`)
    rather than the way this module normalises it.
    """
    for old, new in (renames or {}).items():
        text = re.sub(
            rf"(?<![A-Za-z_0-9]){re.escape(old)}(?![A-Za-z_0-9])", lambda _m, n=new: n, text
        )
    text = IMPL_ID.sub("impl#", MONO_ID.sub("[#]", text))
    blocks = split_modules(text)
    if drop_build_info:
        blocks = [b for b in blocks if "::build_info::" not in module_name(b)]
    return sorted(canonical_body(b, loose) for b in blocks)


def _pairs(a: Path, b: Path) -> list[tuple[str, Path, Path]]:
    if a.is_dir() or b.is_dir():
        names = sorted({p.name for p in a.glob("*.sv")} | {p.name for p in b.glob("*.sv")})
        return [(name, a / name, b / name) for name in names]
    return [(b.name, a, b)]


def diff(
    a: Path,
    b: Path,
    renames: dict[str, str] | None = None,
    verbose: bool = False,
    loose: bool = False,
    out=sys.stdout,
) -> int:
    differing = 0
    pairs = _pairs(a, b)
    for name, left, right in pairs:
        if not left.is_file() or not right.is_file():
            print(f"MISSING {name}", file=out)
            differing += 1
            continue
        before = canonical_modules(left.read_text(), renames, loose=loose)
        after = canonical_modules(right.read_text(), loose=loose)
        if before == after:
            print(f"same    {name} ({len(before)} modules)", file=out)
            continue
        differing += 1
        only_before = list((Counter(before) - Counter(after)).elements())
        only_after = list((Counter(after) - Counter(before)).elements())
        print(
            f"DIFFER  {name}: {len(before)} -> {len(after)} modules, "
            f"{len(only_before)} only in BEFORE, {len(only_after)} only in AFTER",
            file=out,
        )
        for module, count in sorted(Counter(module_name(x) for x in only_before).items()):
            print(f"   -{module}" + (f" x{count}" if count > 1 else ""), file=out)
        for module, count in sorted(Counter(module_name(x) for x in only_after).items()):
            print(f"   +{module}" + (f" x{count}" if count > 1 else ""), file=out)
        if verbose and only_before and only_after:
            lines = difflib.unified_diff(
                sorted(only_before)[0].splitlines(keepends=True),
                sorted(only_after)[0].splitlines(keepends=True),
                "BEFORE", "AFTER", n=1,
            )
            out.write("".join(list(lines)[:80]))
    print(f"{len(pairs)} file(s), {differing} differing", file=out)
    return differing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"),
                        help="compare two .sv files, or two directories of them")
    parser.add_argument("--rename", action="append", default=[], metavar="OLD=NEW",
                        help="rename OLD to NEW in BEFORE before comparing")
    parser.add_argument("--verbose", action="store_true",
                        help="print a body diff for the first differing module")
    parser.add_argument("--loose", action="store_true",
                        help="also alpha-rename declared nets, to answer "
                             "'was that difference only naming?'")
    parser.add_argument("files", nargs="*", type=Path, help="generated .sv files to print")
    args = parser.parse_args()

    renames: dict[str, str] = {}
    for item in args.rename:
        if "=" not in item:
            parser.error(f"--rename wants OLD=NEW, got {item!r}")
        old, new = item.split("=", 1)
        renames[old] = new

    if args.diff:
        moved = diff(Path(args.diff[0]), Path(args.diff[1]), renames,
                     args.verbose, args.loose)
        return 1 if moved else 0

    if not args.files:
        parser.error("pass at least one .sv file, or --diff BEFORE AFTER")
    for path in args.files:
        for block in canonical_modules(path.read_text(), renames, loose=args.loose):
            sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

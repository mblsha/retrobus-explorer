# Gateware repository guidelines

The active RetroBus Explorer FPGA workspace is this directory. Gateware is
written in Spade, compiled with Swim, and tested with Cocotb and Verilator.
Read [README.md](./README.md) for the workspace overview. This file is the one
set of contribution, testing and environment rules for every contributor and
coding agent; there is deliberately no `CLAUDE.md` beside it.

## Scope and organization

- Active FPGA implementations are Spade projects under `projects/`.
- Put reusable Spade modules and their focused tests in
  `lib/shared-components/`.
- Put shared ACF inputs in `constraints/boards/`, `constraints/interfaces/`,
  or `constraints/targets/`; keep truly project-specific constraints with the
  project.
- Put common test, inventory, constraint, build, and flash helpers in `tools/`.
- Put shared compatibility or vendor SystemVerilog in `rtl/vendor/`. Declare
  any HDL a project consumes under `[verilog].sources` in its `swim.toml`.
- Treat `projects.toml` as the source of truth for project discovery. Keep it
  synchronized with `[tool.uv.workspace].members` in `pyproject.toml`.

Do not duplicate a shared block in several projects. Extract stable behavior
to `lib/shared-components/`, give it a focused unit test, and keep board wiring
and application policy in the consuming project.

## Development commands

Run Python as `uv run --frozen`, and never run `uv sync`. The user's global
`~/.config/uv/uv.toml` sets `exclude-newer`, so `uv sync --locked` fails and a
plain `uv run` resolves and rewrites `uv.lock`; if `uv.lock` shows as modified,
`git checkout gateware/uv.lock` before committing. Do not delete or recreate
`gateware/.venv`: the one that exists has a working `cocotb` 1.9.2, and
building that version from source on this Mac fails at link time. A fresh
clone needs `--no-config` to sync at all, and should expect the cocotb install
to need attention.

Bitstream builds are the one exception to `uv run`: `nextpnr-xilinx` is linked
against Homebrew's Boost by absolute path, so they need
`DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib` and must be launched
with `./.venv/bin/python`, because macOS strips that variable through `uv run`.

Run these from `gateware/`:

```sh
uv run --frozen python tools/project_inventory.py --check
uv run --frozen python tools/run_tb.py --project projects/<name>
uv run --frozen python tools/run_tb.py --project projects/<name> --waves
uv run --frozen python lib/shared-components/scripts/test_component.py <component>
uv run --frozen python lib/shared-components/scripts/test_all_components.py
uv run --frozen python -m unittest discover -s tools -p 'test_*.py'
uv run --frozen python -m unittest discover \
  -s projects/ft-uart-hex-bridge/test \
  -p 'test_ft_uart_hex_bridge_host.py'
uv run --frozen python -m unittest discover -t projects/ethernet-diagnostic -s projects/ethernet-diagnostic/test_host -p 'test_*.py'
uv run --frozen python -m pytest projects/sharp-pc-e500-card/tests
```

The supported behavioral verification path is Spade, generated SystemVerilog,
Cocotb, and Verilator. `tools/run_tb.py` must finish successfully and its
strict JUnit XML check must report at least one testcase with no failures or
errors.

## Refactoring and testing

- Before refactoring behavior, add characterization tests that pass against
  the pre-refactor implementation.
- Keep pure reusable behavior covered in `lib/shared-components/test/` and
  integration, pin, protocol, reset, and tri-state behavior covered by the
  affected project's Cocotb tests.
- After a shared-library change, run its focused tests and every registered
  project that imports the changed module.
- Do not use a remote synthesis result as a replacement for unit tests.
- Preserve protocol bytes, reset behavior, timing semantics, high-impedance
  behavior, and observable UART output unless a change explicitly requests a
  behavior update.

## The Spade compiler and where it lives

Every project and `lib/shared-components` pins the compiler as
`[spade].commit` in its own `swim.lock`. All fourteen must name the same
commit; the current pin is **v0.20.0**
(`7e0bf7883d8a23dff89b5e38ce5c5f24761fafe5`). There is no library dependency
left: the one combinator this repository used from `nstd` now lives in
`lib/shared-components/src/arrays.spade`.

Spade and Swim moved from GitLab to **Codeberg** on 2026-09-18
(`https://codeberg.org/spade-lang/spade`, `.../swim`). The GitLab repository
is frozen at a "Spade has moved" commit. It still serves every tag up to
v0.20.0, which is why a swim binary built before the move -- it has the
GitLab URL compiled in -- can still fetch this pin; it will never see a
later release. Codeberg is run by volunteers on donated hardware and is less
available than GitLab was, so expect the occasional failed clone and retry.

To bump the compiler:

1. Install swim from Codeberg:
   `cargo install --git https://codeberg.org/spade-lang/swim swim`.
2. In each project whose `build/` predates the move, run
   `swim clean --and-spade`, so the old GitLab checkout under `build/spade`
   is discarded rather than fetched from a frozen repository.
3. Edit `[spade].commit` in all fourteen `swim.lock` files to the release
   commit you want. Do **not** run `swim update-spade`: it moves the pin to
   whatever the branch head is, and these locks name exact release tags.
4. Build every project, work the compiler's warnings back to zero, and only
   then run the testbenches. Go through the intermediate releases rather than
   jumping: a release that deprecates something prints a fix-it for every
   occurrence, and a later one may reuse the same syntax for a new meaning.

## Spade and HDL style

- Use four-space indentation and descriptive `snake_case` names.
- Prefer small typed functions for combinational transformations and small
  entities for stateful or clocked behavior.
- Spade has no port/value distinction any more, and the wire-layer spelling
  that used to mark it is gone. Make a pair with
  `let (x, x_w): (T, inv T) = port();`, read the forward half as `x`, and
  drive the inverted half with `set x_w = value`. No `&` on the types, no `&`
  before the value in a `set`, no `*` before a read, and `struct`, never
  `struct port`. This matters beyond tidiness: since 0.19 `&T` means a
  read-only copy view of a linear type, so a leftover `&` would still compile
  and say something quite different from what it used to.
- Ask for widths with `uint::bits_for` and `int::bits_for`, not the deprecated
  `uint_bits_to_fit` / `int_bits_to_fit`.
- Reinterpret bits with the standard library's methods rather than the
  deprecated free units in `std::conv`: `bool::as_clock`, `clock::as_bool`,
  `[bool; N]::as_uint`. A conversion named `as_*` reinterprets bits and one
  named `to_*` preserves a numeric value.
- Every project must build with zero compiler warnings. A warning here is
  usually a deprecation with a fix-it attached, and letting them accumulate is
  what makes the next compiler bump expensive.
- Centralize repeated widths, protocol constants, UART helpers, synchronizers,
  FIFOs, counters, and edge detectors in the shared library when their behavior
  is genuinely common.
- Keep top-level entities focused on board I/O, clock/reset integration, and
  composition.
- Keep mixed-SystemVerilog interfaces narrow and explicit. Add Cocotb coverage
  at the boundary.

Directory names are user-facing organization; they do not authorize renaming
the logical package name in `swim.toml`, generated boot-banner identity,
wire-protocol identifiers, or hardware-visible strings.

## Constraints and hardware safety

- Keep top-level ports aligned with their ACF/XDC mappings.
- Re-run constraint generation and affected tests after any I/O, clock, reset,
  connector, voltage-domain, or width change.
- Use `projects/pin-tester` first when validating a new board, level-shifter
  mapping, bank selection, or FFC connection.
- Bulk streaming uses the Alchitry Ft Element FT600 path. The Au USB-UART is the
  console and control path, not the high-rate capture path.

## Targets driven from the emulated card

The emulated card boots real machines, and that happens on a shared bench with
a supply on it. The device-side work -- the Anbernic RG35XX Plus (Allwinner
H700): boot time, the display, sleep current, the suspend firmware -- moved to
the **`linux-consoles`** repository, under `docs/rg35xx-plus/` and
`devices/rg35xx-plus/`. What a real H700 host taught the emulator stayed here,
in [H700-HOST-NOTES.md](projects/ethernet-diagnostic/H700-HOST-NOTES.md).

These rules are this repository's and hold for every session that touches the
bench or the client:

- `psu2` powers the target. **`psu1` powers another machine and must never be
  switched, set or commanded.** Do not change `psu2`'s voltage or current
  limit. The supply's link drops for a minute or two at a time; never act on a
  reading taken while it is offline, and confirm every power-off by reading it
  back.
- An armed FPGA must not be left driving an unpowered target. Finish every run
  with the supply's output read back OFF and the card disarmed.
- Never change the qualified bitstream (`build/microsd-ddr-ethernet-h700`) or
  the gateware to make a target experiment work. A result measured against a
  rebuilt card is a result about a different card. That bitstream was compiled
  by Spade v0.17.0 and the sources are now on v0.20.0, so a rebuild is a new
  netlist: it needs its own placement-seed search and its own hardware
  qualification before it could replace the qualified one. See
  [QUALIFICATION.md](projects/ethernet-diagnostic/QUALIFICATION.md).
- `projects/ethernet-diagnostic/scripts/images.py`, its importability as
  `scripts.images`, `PROTOCOL.md` and the `build/<experiment>/` layout
  (`design.bit` beside `result.json`) are an **interface**: `linux-consoles`
  imports that client by path through `SD_EMULATOR_CLIENT_DIR` and finds the
  bitstream through `SD_EMULATOR_BUILD_DIR`, rather than vendoring a copy that
  would drift from the gateware it speaks to. Do not move or rename them, and
  treat a wire-protocol change as a change to both repositories.

## Generated files and reviews

Do not commit generated build directories, bitstreams, VCDs, JUnit XML, or
tool logs. Do commit regenerated project `constraints/pins.xdc` snapshots when
their ACF inputs change; golden tests lock their functional command stream.
Preserve unrelated working-tree changes. Pull requests should
identify the affected projects and boards, list the exact Spade/Verilator tests
run, and call out any connector or voltage-domain impact.

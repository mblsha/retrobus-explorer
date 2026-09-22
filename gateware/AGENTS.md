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

The development machine has been on the Codeberg swim since 2026-09-22
(`swim --version` says `v0.20.0-r351-c88f2f4` or later; the previous binary is
kept as `~/.cargo/bin/swim-0.18.0-r317`), and every cached `build/spade`
checkout has had its `origin` re-pointed at Codeberg. Swim fetches from a
checkout's own `origin`, so a checkout made before the move keeps talking to
GitLab until it is re-pointed or discarded.

To bump the compiler:

1. On a machine that still has a pre-move swim, install it from Codeberg:
   `cargo install --git https://codeberg.org/spade-lang/swim swim`.
2. For each `build/spade` whose `origin` is still GitLab, either
   `git -C build/spade remote set-url origin https://codeberg.org/spade-lang/spade.git`
   or `swim clean --and-spade` (which also throws away the compiler build).
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
- State a requirement on a generic as a `where` clause beside it, not as a
  helper that fails to compile:
  `where ENTRIES >= 2 else "a fifo needs at least two entries"`, comma-separated
  after the return type. The compiler checks it at monomorphisation and quotes
  the message with a traceback through every instantiation, and unlike a guard
  unit it costs no module. Clauses take a bare generic name on the left, and
  type expressions have `+ - * / %`, comparisons, `&& || ^^ !`, `uint::bits_for`
  and `int::bits_for` -- no shift and no exponentiation, which is why
  `guards::require_power_of_two` still exists and why it is `#[inline]`.
  Prove a new constraint fires: instantiate it wrong once and read the error.
- Type expressions do **not** work in a struct member that refers to the
  struct's own generic ("Struct members cannot have const generics in their
  type"), and routing one through a type alias panics the compiler. They do work
  in a `let` annotation, which is where `memory.spade`'s `FifoAddr<ENTRIES>` and
  `FifoCount<ENTRIES>` are used, and in a `reg` annotation through an alias
  whose arguments are type expressions (`memory.spade`'s `FifoState`). Name a
  type spelling that repeats more than a few times. An alias can name a port
  pair -- `serial::UartLineBusy` is `(UartLineBusyPort, inv UartLineBusyPort)`
  and `let (a, b): UartLineBusy = port();` works -- which an earlier note here
  said was impossible; it was, before 0.19.
- Build a byte string by chaining `[T; N]::concat`, and when the same shape
  recurs (a key and its help text, a name and its length) put the shape in an
  `#[inline]` helper. A left-to-right chain shares nothing, because every step
  has a length no other step has, so a long builder written flat costs a module
  per step where the old nested `concat_arrays` tree reused its pairs;
  `console.spade`'s `key_line`/`key_pair_line` are the pattern.
- Ask a value for its own bit with `msb()`/`lsb()`, read an `Option` with
  `is_some()`/`unwrap_or()`, and know that none of them is `#[inline]` upstream:
  each monomorphisation is a one-line module in every project that reaches it.
  That is a few percent on a module count and worth it for the names; it is not
  worth it inside something instantiated many times.
- A `match` pattern is a literal or a constructor. There is no value constant
  usable as a pattern, so a state machine over `let IDLE: uint<4> = 0;` names
  stays an `if` chain unless its encoding is free to become an enum -- and the
  encodings in `ethernet-diagnostic`'s block and native decoders and in
  `trace.spade`'s readout words are not.
- Give a generic a default when one value dominates its call sites, so the call
  sites that want something else stand out: `reset_conditioner<#uint STAGES = 4>`,
  `sync_delay<#int STAGES = 2>`, `uart_rx<#uint DATA_WIDTH = 8>`,
  `async_fifo<..., #uint SYNC_STAGES = 3>`. Defaults must be trailing, and the
  value must be a literal.
- Prefer `if let` to a two-arm `match` that binds one value and falls back; keep
  `match` where it is exhaustive over a small enum, because `if let` would
  quietly stop being.
- Walk two arrays together with `zip`, not `enumerate` plus indexing into the
  second one. `arrays::enumerate` is for a closure that needs the index as a
  number.
- A reset value belongs to its type: `impl Default for X { fn default() }` and
  `reset(rst: X::default())`. A generic type gets the same treatment even though
  naming its associated function is still rejected ("Use of undeclared name
  ...BootBannerState::default"): implement the trait for it
  (`impl<#uint IDX_W> Default for BootBannerState<IDX_W>`) and call the standard
  library's free `default()`, which takes its type from the annotation on the
  `reg` beside it. A constructor that takes an *argument* -- like
  `init_byte_msg_stream(none_msg)` -- still stays a free function.
  `X::default()` is for the power-on state; a protocol sentinel like
  `tx_req_none()` keeps the name that says what it means.
- `#[inline]` anything whose whole body is a constant or a single forwarding
  call. Without it each one is a module in every project that instantiates it.
- Every project must build with zero compiler warnings. A warning here is
  usually a deprecation with a fix-it attached, and letting them accumulate is
  what makes the next compiler bump expensive. Deprecated *methods* print
  nothing, though -- only deprecated free units do -- which is how 49
  `to_bits()` calls survived a zero-warning bump; after the next one, grep for
  the methods the changelog retires as well as reading the warnings.
- A `pub fn` nothing calls is still a module in every consumer's SystemVerilog.
  Delete dead code; do not keep it "for later".
- Centralize repeated widths, protocol constants, UART helpers, synchronizers,
  FIFOs, counters, and edge detectors in the shared library when their behavior
  is genuinely common.
- Keep top-level entities focused on board I/O, clock/reset integration, and
  composition.
- Keep mixed-SystemVerilog interfaces narrow and explicit. Add Cocotb coverage
  at the boundary.

Synthesis attributes live in two places and both are deliberate.
`#[verilog_attrs(ASYNC_REG = "TRUE")]` is on `sync_delay_pipe` and
`sync_bundle_pipe` in `primitives.spade` -- on the pipelines that hold the
flops, because the attribute is rejected on a `reg` and accepted on a unit.
`#[verilog_attrs(keep_hierarchy = "yes")]` is on all nine extern
SystemVerilog instantiations, so a vendor block's boundary survives synthesis
and is still there to be named by a constraint or a report.

**Open check, for whoever next has Vivado:** whether a module-level `ASYNC_REG`
reaches the registers inside when the hierarchy is kept. It was added from a
machine with no Vivado on it, openXC7 ignores the attribute, and Verilator only
tells us it parses. Read a synthesis report before relying on it, and do not
treat it as an MTBF improvement until you have.

Known compiler issues on v0.20.0, the workaround each one forces on us, and
the simplification that becomes possible once it is fixed, live in
[docs/spade-compiler-issues.md](docs/spade-compiler-issues.md) with a
reproducer apiece. Re-run the reproducers after every compiler bump and retire
what no longer fails. The short list: a struct member cannot compute a width
from its own generic (`FifoImplState`, `BootBannerState`); destructuring a
power-of-two-length array emits an index one bit too wide; `bits[N - 1]`
inside a `gen if` recursion is typed for half the array (use `last()`); an
array repeat count cannot be a type expression; a `where` clause cannot say
"power of two" (`guards.spade` stays); deprecated methods do not warn; and
`swim build` rewrites `src/build_info.spade`, so never build in a checkout
while its suites run.

To check a refactor that is meant to preserve behaviour: build before and after,
and compare with both `tools/sv_module_surface.py --diff` (what the testbenches
and constraints bind to) and `tools/sv_module_bodies.py --diff` (the logic
itself, with `--loose` to tell a renamed net from a changed one and `--rename`
when a unit was renamed on purpose). Build the fourteen projects **one at a
time** when saving a reference: `ethernet-diagnostic` consumes
`microsd-emulator` as a library, and a concurrent build reads that library's
`build/` while swim is rewriting it.

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

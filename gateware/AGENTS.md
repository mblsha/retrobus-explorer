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

## Spade and HDL style

- Use four-space indentation and descriptive `snake_case` names.
- Prefer small typed functions for combinational transformations and small
  entities for stateful or clocked behavior.
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

## The RG35XX Plus bench

The RG35XX Plus work (boot time, the display, sleep current, the suspend
firmware) lives in `projects/ethernet-diagnostic/`. Start at the
"Documentation map" in its `README.md`: it says what each note is and when to
read it. One home per fact: commands in the runbook, results in
`RG35XX-PLUS-SLEEP.md` and `RG35XX-PLUS-FINDINGS.md`, the suspend firmware's
design in `RG35XX-PLUS-DEEP-SLEEP.md`, research and the outside review in
`RG35XX-PLUS-POWER-RESEARCH.md`, what needs a person at the bench in
`RG35XX-PLUS-BENCH-EXPERIMENTS.md`, chronology in the history. Add to the home
a fact belongs in, and leave a pointer elsewhere.

The bench is real hardware and is driven unattended. These hold for every
session:

- `psu2` is the RG35XX. **`psu1` powers another machine and must never be
  switched, set or commanded.** Do not change `psu2`'s voltage or current
  limit. The supply's link drops for a minute or two at a time; never act on a
  reading taken while it is offline, and confirm every power-off by reading it
  back.
- An armed FPGA must not be left driving an unpowered target. Finish every run
  with the supply's output read back OFF and the card disarmed.
- Never change the qualified bitstream (`build/microsd-ddr-ethernet-h700`) or
  the gateware to make a target experiment work. Card images keep
  `--card-max-hz 6000000`.
- Firmware experiments do not write the PMIC, a rail or a voltage. A register
  is written only if the H616 manual, mainline U-Boot, Linux or TF-A, or the
  credited prior art grounds it, and the comment says which. Lifting one of
  these rules is the owner's decision, not a session's.
- Nothing may depend on a person looking at the device: the target reports
  through the debug partition, the FPGA trace and the supply.
- Measure before believing: alternate configurations inside one boot, report
  the median and the mean, and do not call a difference under about 8 mA a
  difference. A configuration is not "kept" on a handful of sleeps; job 34
  exists to give a failure rate.

## Generated files and reviews

Do not commit generated build directories, bitstreams, VCDs, JUnit XML, or
tool logs. Do commit regenerated project `constraints/pins.xdc` snapshots when
their ACF inputs change; golden tests lock their functional command stream.
Preserve unrelated working-tree changes. Pull requests should
identify the affected projects and boards, list the exact Spade/Verilator tests
run, and call out any connector or voltage-domain impact.

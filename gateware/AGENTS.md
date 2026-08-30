# Gateware repository guidelines

## Scope and organization

- Active FPGA implementations are Spade projects under `projects/`.
- Put reusable Spade modules and their focused tests in
  `lib/shared-components/`.
- Put shared ACF inputs in `constraints/boards/`, `constraints/interfaces/`,
  or `constraints/targets/`; keep truly project-specific constraints with the
  project.
- Put shared compatibility or vendor SystemVerilog in `rtl/vendor/`. Declare
  any HDL a project consumes under `[verilog].sources` in its `swim.toml`.
- Treat `projects.toml` as the source of truth for project discovery. Keep it
  synchronized with `[tool.uv.workspace].members` in `pyproject.toml`.

Do not duplicate a shared block in several projects. Extract stable behavior
to `lib/shared-components/`, give it a focused unit test, and keep board wiring
and application policy in the consuming project.

## Development commands

Run commands from `gateware/`:

```sh
uv sync --locked --all-packages
uv run python tools/project_inventory.py --check
uv run python tools/run_tb.py --project projects/<name>
uv run python tools/run_tb.py --project projects/<name> --waves
uv run python lib/shared-components/scripts/test_component.py <component>
uv run python lib/shared-components/scripts/test_all_components.py
uv run python -m unittest discover -s tools -p 'test_*.py'
uv run python -m unittest discover \
  -s projects/ft-uart-hex-bridge/test \
  -p 'test_ft_uart_hex_bridge_host.py'
uv run python -m pytest projects/sharp-pc-e500-card/tests
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

## Generated files and reviews

Do not commit generated build directories, bitstreams, VCDs, JUnit XML, or
tool logs. Do commit regenerated project `constraints/pins.xdc` snapshots when
their ACF inputs change; golden tests lock their functional command stream.
Preserve unrelated working-tree changes. Pull requests should
identify the affected projects and boards, list the exact Spade/Verilator tests
run, and call out any connector or voltage-domain impact.

# FPGA gateware

This directory is the canonical workspace for RetroBus Explorer FPGA gateware.
Active designs are written in [Spade](https://spade-lang.org/), compile to
SystemVerilog with Swim, and are characterized with Cocotb and Verilator.

## Layout

- `projects/` contains buildable applications, diagnostics, and examples. Each
  project owns its `src/`, `test/`, `swim.toml`, `swim.lock`, and
  `pyproject.toml`.
- `lib/shared-components/` contains reusable Spade modules and their focused
  unit tests.
- `constraints/` contains repository-owned board, interface, and target ACF
  inputs. Project-only constraints stay with the project.
- `rtl/vendor/` contains the small amount of shared SystemVerilog that cannot
  be expressed as portable Spade.
- `tools/` contains the common test, constraint-generation, build, flash, and
  project-inventory helpers.
- `projects.toml` is the authoritative project registry. Its entries must match
  the uv workspace members in `pyproject.toml`.

The registry classifies projects as applications, diagnostics, or examples;
run `tools/project_inventory.py` rather than maintaining another project list
in documentation.

## Set up the workspace

Install Python 3.11 or newer, [uv](https://docs.astral.sh/uv/), Swim, and
Verilator. Then, from this directory:

```sh
uv sync --locked --all-packages
uv run python tools/project_inventory.py --check
```

The single `gateware/.venv` supplies Cocotb to every project. Each project's
`swim.lock` pins its Spade compiler and library revisions.

## Run tests

Run one project testbench:

```sh
uv run python tools/run_tb.py --project projects/pin-tester
```

Add waveforms when debugging:

```sh
uv run python tools/run_tb.py --project projects/pin-tester --waves
```

The runner builds the Spade source, compiles the generated and declared
SystemVerilog with Verilator, runs the configured Cocotb module, and checks
`test/results.xml`. A missing testcase, failure, or error makes the command
fail. With `--waves`, it also writes `test/dump.vcd` and
`test/dump.surfer.vcd`.

Every registered project also has a thin wrapper at
`projects/<name>/scripts/test_with_vcd.py`. Run all reusable-component tests,
or one focused component test, with:

```sh
uv run python lib/shared-components/scripts/test_all_components.py
uv run python lib/shared-components/scripts/test_component.py sync2
```

Validate workspace metadata and gateware tooling with:

```sh
uv run python -m unittest discover -s tools -p 'test_*.py'
uv run python tools/project_inventory.py --check
uv run python -m unittest discover \
  -s projects/ft-uart-hex-bridge/test \
  -p 'test_ft_uart_hex_bridge_host.py'
uv run python -m pytest projects/sharp-pc-e500-card/tests
```

For refactors, add characterization tests before changing behavior, then run
the affected shared-component tests and every project that consumes the
changed logic. Spade plus Verilator is the required behavioral test path;
remote synthesis is not a substitute for unit tests.

## Shared logic and constraints

Projects import reusable HDL through the `shared_components` library declared
in `swim.toml`. Put generally useful protocol, clocking, FIFO, memory, monitor,
and bus helpers in `lib/shared-components/` instead of copying them between
projects.

Constraint-aware hardware builds regenerate `constraints/pins.xdc` from the
project's `[constraints]` configuration. These XDC files are checked-in,
reviewable snapshots whose semantics are locked by the constraint golden
tests. Reuse ACF inputs from
`constraints/boards/`, `constraints/interfaces/`, and
`constraints/targets/`; keep unique connector mappings in the owning project.

Projects that include generated build information keep their existing
`swim.toml` package name and UART boot-banner identity. Directory cleanup does
not imply a wire-protocol or package rename.

## Build and flash hardware

The shared project entrypoint also exposes synthesis and flashing workflows:

```sh
uv run python tools/project.py build-with-spadeforge \
  --project projects/sharp-pc-g850-bus

uv run python tools/project.py flash-with-spadeloader \
  --project projects/sharp-pc-g850-bus
```

Build products remain under the selected project's `build/` directory. Keep
generated SystemVerilog, bitstreams, test results, and waveforms out of source
control. Project `constraints/pins.xdc` snapshots are the deliberate exception.

To browse projects and waveforms from another machine on the LAN:

```sh
uv run python tools/web_wave_server.py --host 0.0.0.0 --port 8090
```

Then open `http://<host>:8090`.

# FPGA gateware

This directory is the canonical workspace for RetroBus Explorer FPGA gateware.
Active designs are written in [Spade](https://spade-lang.org/), compile to
SystemVerilog with Swim, and are characterized with Cocotb and Verilator.

## Choose an organizer tool

| Task | Project and guide | Physical target / bus role | End of operation |
| --- | --- | --- | --- |
| Dump ROM/SRAM, discover banks, or program SRAM | [sharp-organizer-probe](projects/sharp-organizer-probe/README.md#quick-start) | Removable card in the Host Adapter; FPGA drives the host bus | Automatically parks and releases |
| Observe organizer bus traffic | [sharp-organizer-card](projects/sharp-organizer-card/README.md) | Organizer drives the bus; FPGA samples inputs | Organizer bus pins remain inputs |
| Emulate ROM/SRAM2, run a native eval loop, or exchange FT600 data | [sharp-organizer-emulator](projects/sharp-organizer-emulator/README.md#quick-start) | Card Adapter in the organizer; FPGA supplies selected read data | Remains armed until explicit disarm/reset |

The native emulator targets the IQ-7000-style card bus and OZ-family
experiments. Check its [qualification record](projects/sharp-organizer-emulator/QUALIFICATION.md)
before a live run. The Host Adapter and Card Adapter serve different bus roles.

## Sharp organizer card dumping and SRAM programming

The [card dumper and SRAM programmer](projects/sharp-organizer-probe/README.md#quick-start)
uses the Au1 as an active card host. Its CLI provides `dump-card` for attributed
ROM/SRAM reads, `capture-card` for Git backups and reversible SRAM presence
probes, and `write-sram` for verified writes to confirmed SRAM. The project
guide includes the Spade/nextpnr build, USB-UART and FT600 transport options,
and automatic bus release behavior. Supply your own Git archive directory.

Use the [passive organizer monitor](projects/sharp-organizer-card/README.md) for
organizer bus capture; use the probe to drive and read a removable card.

## Sharp organizer native execution card

Use the [sharp-organizer-emulator quick start](projects/sharp-organizer-emulator/README.md#quick-start) for
native experiments on an organizer: local code memory, a resident eval loop,
small SRAM2 scratch, live timing controls, and bidirectional FT600 traces and
host-fed streams. Pin-level simulation and nextpnr builds are verified; the
organizer's native launch path remains to be qualified. Its
[CLI reference](projects/sharp-organizer-emulator/README.md#cli-command-reference)
lists UART image loading, SRAM2 read/write, live timing controls, native jobs,
FT600 capture/input, and explicit disarm. The
[execution and streaming guide](projects/sharp-organizer-emulator/README.md#how-execution-and-streaming-work)
explains the FPGA buffers and mailbox protocol.

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
Verilator. Swim now lives on Codeberg:

```sh
cargo install --git https://codeberg.org/spade-lang/swim swim
```

Then, from this directory:

```sh
uv sync --locked --all-packages
uv run python tools/project_inventory.py --check
```

The single `gateware/.venv` supplies Cocotb to every project. Each project's
`swim.lock` pins the Spade compiler as `[spade].commit`; all projects name the
same release, currently **v0.20.0**. There are no library dependencies.
[AGENTS.md](./AGENTS.md) has the compiler-bump procedure.

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
uv run --frozen --no-sync python -m unittest discover \
  -s projects/sharp-organizer-emulator/test_host -v
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

## Maintain the Spade source

The [2026-10-01 modernization review](docs/spade-modernization-2026-10-01.md)
maps the previous year's Spade posts to the code, records the syntax changes
and their verification, and identifies features that were already applied.
Use [the compiler issue record](docs/spade-compiler-issues.md) when deciding
whether a language feature can replace an existing workaround.

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

## Arty A7-35T microSD card emulator

The [microSD project](projects/microsd-emulator/README.md) provides a tested
DDR-backed native SD card, with a separate [input-only pin probe](projects/microsd-pin-tester/README.md),
[native macOS build tools](experiments/openxc7-macos/README.md), and
[two microSD-Pmod PCB variants](../jitx-py/microsd-pmod-breakout/README.md).

The [Ethernet image service](projects/ethernet-diagnostic/README.md) adds UDP
upload, verified readback, and windowed downloads to the same DDR-backed card.
It uses the onboard RJ45 and requires exclusive SD/network image ownership.

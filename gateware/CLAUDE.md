# Gateware development guide

The active RetroBus Explorer FPGA workspace is this directory. Gateware is
written in Spade, compiled with Swim, and tested with Cocotb and Verilator.
Read [README.md](./README.md) for the workspace overview and
[AGENTS.md](./AGENTS.md) for contribution and testing rules.

## Working layout

- `projects/`: buildable FPGA applications, diagnostics, and examples
- `lib/shared-components/`: reusable Spade logic and unit tests
- `constraints/`: shared board, interface, and target ACF inputs
- `rtl/vendor/`: shared compatibility SystemVerilog
- `tools/`: common test, inventory, constraint, build, and flash helpers
- `projects.toml`: authoritative project registry

## Essential commands

Run these from `gateware/`:

```sh
uv sync --locked --all-packages
uv run python tools/project_inventory.py --check
uv run python tools/run_tb.py --project projects/<name>
uv run python tools/run_tb.py --project projects/<name> --waves
uv run python lib/shared-components/scripts/test_all_components.py
uv run python -m unittest discover -s tools -p 'test_*.py'
```

Add behavior-locking tests before a refactor. Shared logic needs focused unit
tests plus the affected project testbenches. Keep board wiring in projects,
move genuinely reusable behavior into `lib/shared-components/`, and preserve
existing package names, boot-banner identities, protocols, reset semantics,
and tri-state behavior unless the task explicitly changes them.

Generated SystemVerilog, bitstreams, test XML, waveforms, and build directories
are artifacts and should not be committed. Project `constraints/pins.xdc`
snapshots are checked in and verified by the constraint golden tests.

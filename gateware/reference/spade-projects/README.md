# Spade Ports of Alchitry Reference Projects

This directory contains Spade rewrites of the Lucid projects in `../../`:

- `test-minimal-spade`
- `pin-tester-spade`
- `sharp-organizer-card-spade`
- `sharp-pc-g850-bus-spade`
- `sharp-pc-g850-streaming-rom-spade`

Shared logic lives in `shared-components`, shared vendor HDL lives in `shared-verilog`, and reusable scripts are in `tools`.

## UV Workspace

`spade-projects` is a single uv umbrella workspace with `*-spade` members. Testbench Python dependencies live in one shared env at `spade-projects/.venv`.

One-time setup:

```sh
cd spade-projects
uv sync
```

## Common Commands

Run testbench + generate VCD/Surfer:

```sh
./tools/project.py test-with-vcd --project ./sharp-pc-g850-bus-spade
```

Run shared-component unit testbenches (in-place under `shared-components`):

```sh
cd shared-components
./scripts/test_component.py sync2
./scripts/test_all_components.py
```

Build through spadeforge-cli:

```sh
SPADEFORGE_TOKEN=test123 ./tools/project.py build-with-spadeforge --project ./sharp-pc-g850-bus-spade
```

By default, build artifacts are written under `build/forge-output-<timestamp>/` inside each project.

Run a local web UI to pick projects, run testbenches, and inspect `dump.surfer.vcd` in Surfer Web:

```sh
./tools/web_wave_server.py --host 0.0.0.0 --port 8090
```

Then open `http://<your-machine-ip>:8090` from other LAN devices.

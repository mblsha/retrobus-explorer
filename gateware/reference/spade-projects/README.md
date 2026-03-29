# Spade Ports of Alchitry Reference Projects

This directory contains Spade rewrites of the Lucid projects in `../../`:

- `test-minimal-spade`
- `pin-tester-spade`
- `sharp-organizer-card-spade`
- `sharp-pc-g850-bus-spade`
- `sharp-pc-g850-streaming-rom-spade`

Shared logic lives in `shared-components`, shared vendor HDL lives in `shared-verilog`, and reusable scripts are in `tools`.

All `*-spade` projects also generate `src/build_info.spade` during `swim` preprocessing via `tools/gen_build_info.py`. Projects that want a stamped UART boot banner can import `mod build_info;` locally and feed `build_info::boot_banner_text()` into the shared `shared_components::boot_banner` helper.

## FT Streaming Hardware

Streaming projects in this workspace target the same hardware path used by the
original PC-G850 tooling: Alchitry Au + Alchitry Ft Element, with bulk capture
moving over the FT600-class USB3 FIFO interface. Host capture scripts are
expected to use the repository's `py/d3xx` driver wrapper for that FT board.
The Au board's USB-UART is still useful for boot banners, command/control, and
arming stream capture, but it is not the intended high-rate capture interface.

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

Flash the latest local forge build through spadeloader-cli:

```sh
./tools/project.py flash-with-spadeloader --project ./sharp-pc-g850-bus-spade
```

This flashes the newest `.bit` under `build/forge-output-*` for that project and relies on zeroconf discovery by default. Use `--bitstream <path>` to flash an explicit file or `--server <url>` as an override.

Run a local web UI to pick projects, run testbenches, and inspect `dump.surfer.vcd` in Surfer Web:

```sh
./tools/web_wave_server.py --host 0.0.0.0 --port 8090
```

Then open `http://<your-machine-ip>:8090` from other LAN devices.

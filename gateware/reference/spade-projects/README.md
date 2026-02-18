# Spade Ports of Alchitry Reference Projects

This directory contains Spade rewrites of the Lucid projects in `../../`:

- `test-minimal-spade`
- `pin-tester-spade`
- `sharp-organizer-card-spade`
- `sharp-pc-g850-bus-spade`
- `sharp-pc-g850-streaming-rom-spade`

Shared logic lives in `shared-components`, shared vendor HDL lives in `shared-verilog`, and reusable scripts are in `tools`.

## Common Commands

Run testbench + generate VCD/Surfer:

```sh
./tools/project.py test-with-vcd --project ./sharp-pc-g850-bus-spade
```

Build through spadeforge-cli:

```sh
SPADEFORGE_TOKEN=test123 ./tools/project.py build-with-spadeforge --project ./sharp-pc-g850-bus-spade
```

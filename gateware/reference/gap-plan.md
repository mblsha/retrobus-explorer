# Lucid-to-Spade Parity Gap Plan

Date: 2026-02-21

This document tracks:
- Alchitry library component porting from `Alchitry-Labs-V2/src/main/resources/library/components`
- Feature parity gaps for `pin-tester` once those reusable components exist

## Alchitry Library Porting Scope

The Lucid projects in this repo include a subset of Alchitry components. We should port these first as reusable Spade components in `spade-projects/shared-components`.

### Required Alchitry Components (from `.alp` usage)

1. `DONE` `P0` `Conditioning/reset_conditioner.luc` -> `shared_components::primitives::reset_conditioner`
2. `DONE` `P0` `Interfaces/uart_rx.luc` -> `shared_components::serial::uart_rx`
3. `DONE` `P0` `Interfaces/uart_tx.luc` -> `shared_components::serial::uart_tx`
4. `DONE` `P0` `Miscellaneous/pipeline.luc` -> `shared_components::primitives::sync_delay`
5. `DONE` `P0` `Pulses/edge_detector.luc` -> `shared_components::primitives::{rising_edge, falling_edge}`
6. `DONE` `P1` `Memory/fifo.luc` -> `shared_components::memory::fifo_u8x8`
7. `DONE` `P1` `Memory/async_fifo.luc` -> `shared_components::memory::async_fifo_u8x8`
8. `DONE` `P1` `Interfaces/ft.luc` -> `shared_components::serial::ft_u16`
9. `P1` `Memory/simple_dual_port_ram.v` (as external Verilog module + Spade wrapper)

### Required Non-Alchitry Shared Component

1. `DONE` `P0` `shared-lib/uart/my_uart_tx.luc` -> `shared_components::serial::my_uart_tx` (used by all `sharp-*` projects)

### Implementation Notes

1. Put reusable entities under `spade-projects/shared-components/src/` grouped by function:
   - `primitives.spade` (`reset_conditioner`, `sync_delay`, edge helpers)
   - `serial.spade` (`uart_rx`, `uart_tx`, `my_uart_tx`, `ft` wrappers/adapters)
   - `memory.spade` (`fifo`, `async_fifo`, wrappers)
   - `clocking.spade`/`sharp.spade` for project-oriented shared blocks
2. Add corresponding public module exports in `spade-projects/shared-components/src/main.spade`.
3. For Verilog-backed components (`simple_dual_port_ram`, `ft`, `async_fifo`), keep canonical HDL under `spade-projects/shared-components/verilog/` and wrap with typed Spade entities.

### Unit Test Requirement (Component-First)

Every ported component needs a focused cocotb testbench that validates only that component behavior before integrating into project tops.

1. `DONE` `test_reset_conditioner.py`
2. `DONE` `test_uart_rx.py`
3. `DONE` `uart_tx` compatibility coverage (via `scripts/test_component.py uart_tx` -> `test_my_uart_tx.py`)
4. `DONE` `test_my_uart_tx.py`
5. `DONE` `test_pipeline.py` (covered by `test_sync_delay.py`)
6. `DONE` `test_rising_edge.py`, `test_falling_edge.py`
7. `DONE` `test_fifo.py` (implemented as `test_fifo_u8.py`)
8. `DONE` `test_async_fifo.py` (implemented as `test_async_fifo_u8.py`)
9. `test_simple_dual_port_ram.py`
10. `DONE` `test_ft.py` (implemented as `test_ft_u16.py`)

Each test run must generate:
- `test/dump.vcd`
- `test/dump.surfer.vcd`

## Status Refresh Evidence (2026-02-22)

1. `async_fifo` component and test are present:
   - `spade-projects/shared-components/src/memory.spade` (`async_fifo_u8x8`)
   - `spade-projects/shared-components/test/test_async_fifo_u8.py`
2. `ft` component and test are present:
   - `spade-projects/shared-components/src/serial.spade` (`ft_u16`)
   - `spade-projects/shared-components/test/test_ft_u16.py`
3. Verified passing test runs:
   - `uv run python scripts/test_component.py async_fifo_u8` -> PASS (2 tests)
   - `uv run python scripts/test_component.py ft_u16` -> PASS (4 tests)
4. `simple_dual_port_ram` currently exists only as embedded Verilog helper modules under:
   - `spade-projects/shared-components/verilog/async_fifo_u8x8.v`
   - `spade-projects/shared-components/verilog/ft_u16_v.v`
   - No standalone Spade wrapper entity + focused component test exists yet.
5. `my_uart_tx` is implemented and tested:
   - `spade-projects/shared-components/src/serial.spade` (`my_uart_tx`)
   - `spade-projects/shared-components/test/test_my_uart_tx.py`
   - Verified via `uv run python scripts/test_component.py my_uart_tx` -> PASS (3 tests)

## Pin-Tester Parity Gaps (Depends on Library Port)

This section tracks the remaining `pin-tester` behavior parity work between:
- Lucid: `pin-tester/source/alchitry_top.luc`
- Spade: `spade-projects/pin-tester-spade/src/main.spade`

1. `P0` Missing UART control and state machine parity.
   - Lucid implements `RECEIVE`/`SEND` states, bank selection (`'0'..'5'`), and mode switching (`'s'`/`'r'`).
   - Spade currently has only a free-running counter and no UART command handling.
   - Depends on: `uart_rx`, `uart_tx`, `reset_conditioner`.
   - References: `pin-tester/source/alchitry_top.luc:13`, `pin-tester/source/alchitry_top.luc:53`, `pin-tester/source/alchitry_top.luc:77`, `spade-projects/pin-tester-spade/src/main.spade:14`

2. `P0` FFC bus direction/tri-state behavior mismatch.
   - Lucid uses `inout ffc_data[48]`, defaults to high-Z, and conditionally drives only `ffc_data[0+:8]` in send mode.
   - Spade currently drives all 48 FFC bits continuously as outputs.
   - Depends on: I/O wrapper strategy (`shared-verilog` + Spade adapter).
   - References: `pin-tester/source/alchitry_top.luc:8`, `pin-tester/source/alchitry_top.luc:51`, `pin-tester/source/alchitry_top.luc:82`, `spade-projects/pin-tester-spade/build/spade.sv:283`, `spade-projects/pin-tester-spade/build/spade.sv:327`

3. `P1` LED/Saleae functional mapping mismatch.
   - Lucid displays selected external FFC bank in receive mode and selectable counter slices in send mode.
   - Spade always maps LED/Saleae to `counter[7:0]`.
   - Depends on: control FSM/componentized mux logic.
   - References: `pin-tester/source/alchitry_top.luc:55`, `pin-tester/source/alchitry_top.luc:80`, `spade-projects/pin-tester-spade/src/main.spade:15`, `spade-projects/pin-tester-spade/src/main.spade:20`, `spade-projects/pin-tester-spade/src/main.spade:21`

4. `P1` USB TX behavior mismatch.
   - Lucid uses UART TX and echoes accepted commands when not busy.
   - Spade currently hard-wires `usb_tx = usb_rx`.
   - Depends on: `uart_tx`.
   - References: `pin-tester/source/alchitry_top.luc:42`, `pin-tester/source/alchitry_top.luc:62`, `spade-projects/pin-tester-spade/src/main.spade:23`

5. `P2` Reset conditioning parity gap.
   - Lucid uses `reset_conditioner`.
   - Spade uses direct inversion of `rst_n`.
   - Depends on: `reset_conditioner`.
   - References: `pin-tester/source/alchitry_top.luc:23`, `pin-tester/source/alchitry_top.luc:39`, `spade-projects/pin-tester-spade/src/main.spade:13`

## Execution Order

1. Port and unit-test `reset_conditioner`, `pipeline`, `edge_detector`.
2. Integrate `my_uart_tx` into project tops that currently use USB loopback stubs.
3. Port and unit-test remaining `simple_dual_port_ram` wrapper + focused testbench.
4. Refactor `async_fifo`/`ft` to depend on shared `simple_dual_port_ram` wrapper where practical.
5. Rebuild `pin-tester-spade` using only reusable components.
6. Close all five pin-tester parity gaps with integration tests.

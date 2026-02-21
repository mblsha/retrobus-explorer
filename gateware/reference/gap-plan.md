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
4. `P0` `Miscellaneous/pipeline.luc`
5. `DONE` `P0` `Pulses/edge_detector.luc` -> `shared_components::primitives::{rising_edge, falling_edge}`
6. `P1` `Memory/fifo.luc`
7. `P1` `Memory/async_fifo.luc`
8. `P1` `Interfaces/ft.luc`
9. `P1` `Memory/simple_dual_port_ram.v` (as external Verilog module + Spade wrapper)

### Required Non-Alchitry Shared Component

1. `P0` `shared-lib/uart/my_uart_tx.luc` (used by all `sharp-*` projects)

### Implementation Notes

1. Put reusable entities under `spade-projects/shared-components/src/` grouped by function:
   - `reset.spade` (`reset_conditioner`)
   - `serial.spade` (`uart_rx`, `uart_tx`, `my_uart_tx`)
   - `signal.spade` (`pipeline`, `edge_detector`)
   - `memory.spade` (`fifo`, `async_fifo`, wrappers)
   - `ftdi.spade` (`ft` wrapper/adapter)
2. Add corresponding public module exports in `spade-projects/shared-components/src/main.spade`.
3. For Verilog-backed components (`simple_dual_port_ram`, potentially `ft`), keep canonical HDL under `spade-projects/shared-verilog/` and wrap with typed Spade entities.

### Unit Test Requirement (Component-First)

Every ported component needs a focused cocotb testbench that validates only that component behavior before integrating into project tops.

1. `DONE` `test_reset_conditioner.py`
2. `DONE` `test_uart_rx.py`
3. `DONE` `test_uart_tx.py`
4. `test_my_uart_tx.py`
5. `test_pipeline.py`
6. `DONE` `test_rising_edge.py`, `test_falling_edge.py`
7. `test_fifo.py`
8. `test_async_fifo.py`
9. `test_simple_dual_port_ram.py`
10. `test_ft.py`

Each test run must generate:
- `test/dump.vcd`
- `test/dump.surfer.vcd`

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
2. Port and unit-test remaining `my_uart_tx` (`uart_rx`/`uart_tx` done).
3. Port and unit-test `fifo`, `async_fifo`, `simple_dual_port_ram`.
4. Port and unit-test `ft`.
5. Rebuild `pin-tester-spade` using only reusable components.
6. Close all five pin-tester parity gaps with integration tests.

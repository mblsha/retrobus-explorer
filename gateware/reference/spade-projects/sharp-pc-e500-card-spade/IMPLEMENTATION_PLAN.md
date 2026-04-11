# PC-E500 FT Capture Plan

This note records the approved implementation shape for adding FT600-backed
capture to `sharp-pc-e500-card-spade`.

## Goals

- Preserve the existing USB-UART control path and Saleae debug outputs.
- Add an optional FT600 bulk-capture path for the existing `saleae[4]`
  sampled-bus words.
- Keep FT capture write-only on the CE6 side, with optional USB-UART source
  control.
- Report dropped FT samples alongside the existing timing report fields.

## Approved Control Surface

- Add CE6 control-page register `0x01FFF4` / low16 `0xFFF4`.
- Register name: `FT_STREAM_CFG`.
- Access: write-only.
- Payload:
  - `bit0 = 1`: enable the measurement-window FT source
  - `bit1 = 1`: enable the USB-UART-latch FT source
  - `bits7:2`: reserved, ignored
- Add CE6 control-page register `0x01FFF5` / low16 `0xFFF5`.
- Register name: `FT_STREAM_MODE`.
- Access: write-only.
- Payload:
  - `bit0 = 1`: hold the measurement-source policy sampled at `MARK_START`
    until `MARK_STOP` / `MARK_ABORT`
  - `bits7:1`: reserved, ignored
- Add USB-UART commands:
  - `F1`: set the USB-UART FT source latch
  - `F0`: clear the USB-UART FT source latch
  - `F?`: print FT status

FT capture runs when any enabled FT source is active:

- measurement source:
  - if `FT_STREAM_MODE.bit0 == 0`, capture follows the live `FT_STREAM_CFG.bit0`
    value while measurement `ARM` is active
  - if `FT_STREAM_MODE.bit0 == 1`, `MARK_START` snapshots whether
    `FT_STREAM_CFG.bit0` was enabled and holds that policy for the whole
    window
- UART source: `FT_STREAM_CFG.bit1 == 1` and the `F1` latch is currently set

## Stream Format

- FT payload is the exact existing `saleae[4]` sampled-bus word.
- Word width is `32` bits:
  - `bits 17:0` address
  - `bits 25:18` data
  - `bits 31:26` status
- Transport uses the existing Au + Ft Element FT600 path:
  - low `16` bits first
  - high `16` bits second

## Timing Semantics

- `MARK_START` does not stream its own control-page write.
- FT capture opens after the start marker's same-cycle bookkeeping.
- `MARK_STOP` and `MARK_ABORT` close the measurement FT source before their own
  control-page write is considered for FT capture.

This keeps the measurement FT source aligned with the existing measurement
interval semantics while allowing an independent UART-controlled source.

## Overflow Behavior

- FT backpressure does not stall bus sampling.
- If the dedicated FT sample FIFO is full, new sampled-bus words are dropped.
- Drops are counted in a monotonic internal counter.
- Each measurement report snapshots the drop counter at `MARK_START` and reports
  a per-window delta as `FO`.
- `F?` reports both the cumulative drop counter and the last UART-session drop
  count since `F1`.

Expected report shape:

```text
MR,S=..,E=..,TK=........,EV=........,AU=........,FO=........
```

## Implementation Outline

1. Patch docs/spec to define `FT_STREAM_CFG`, `FT_STREAM_MODE`, and the FT
   status / measurement overflow fields.
2. Add the standard FT Element Au1 ports and constraints to this project.
3. Feed `sampled_bus_word` into a dedicated FT FIFO when any enabled FT source
   is active.
4. Use the existing FT600 write transport pattern from the other Spade boards.
5. Extend cocotb coverage for:
   - config register decode
   - mode register decode
   - measurement-window gating
   - UART-source gating
   - combined-source status reporting
   - UART-session overflow reporting
   - exact `32`-bit FT payload words
   - FT overflow accounting in the measurement report

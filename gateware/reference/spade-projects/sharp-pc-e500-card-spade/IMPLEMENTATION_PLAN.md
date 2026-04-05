# PC-E500 FT Capture Plan

This note records the approved implementation shape for adding FT600-backed
capture to `sharp-pc-e500-card-spade`.

## Goals

- Preserve the existing USB-UART control path and Saleae debug outputs.
- Add an optional FT600 bulk-capture path for the existing `saleae[4]`
  sampled-bus words.
- Keep FT capture write-only and measurement-window gated.
- Report dropped FT samples alongside the existing timing report fields.

## Approved Control Surface

- Add CE6 control-page register `0x01FFF4` / low16 `0xFFF4`.
- Register name: `FT_STREAM_CFG`.
- Access: write-only.
- Payload:
  - `bit0 = 1`: enable FT capture feature
  - `bit0 = 0`: disable FT capture feature
  - `bits7:1`: reserved, ignored

FT capture only runs when both of these are true:

- `FT_STREAM_CFG.bit0 == 1`
- measurement `ARM` is active (`MARK_START` to `MARK_STOP` or `MARK_ABORT`)

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
- `MARK_STOP` and `MARK_ABORT` close the FT window before their own control-page
  write is considered for FT capture.

This keeps FT capture aligned with the existing measurement interval semantics.

## Overflow Behavior

- FT backpressure does not stall bus sampling.
- If the dedicated FT sample FIFO is full, new sampled-bus words are dropped.
- Drops are counted in a monotonic internal counter.
- Each measurement report snapshots the drop counter at `MARK_START` and reports
  a per-window delta as `FO`.

Expected report shape:

```text
MR,S=..,E=..,TK=........,EV=........,AU=........,FO=........
```

## Implementation Outline

1. Patch docs/spec to define `FT_STREAM_CFG` and the new `FO` report field.
2. Add the standard FT Element Au1 ports and constraints to this project.
3. Feed `sampled_bus_word` into a dedicated FT FIFO when the FT window is open.
4. Use the existing FT600 write transport pattern from the other Spade boards.
5. Extend cocotb coverage for:
   - config register decode
   - measurement-window gating
   - exact `32`-bit FT payload words
   - FT overflow accounting in the measurement report

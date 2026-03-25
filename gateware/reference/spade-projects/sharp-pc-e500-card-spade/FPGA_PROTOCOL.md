# PC-E500 FPGA Protocol Reference

This document describes the PC-E500 card FPGA control surface:

- USB-UART commands exposed by the FPGA
- Special CE6 control-page registers handled by the FPGA
- Response formats and practical examples

All timings below assume the current `100 MHz` FPGA clock.

## Overview

The design exposes two separate control paths:

- USB-UART command parser
  - direct host control for RAM, ROM, timing, and measurement dump
- CE6 special control page
  - calculator-visible write-only registers in the CE6 card-ROM region

Normal CE1 RAM and CE6 ROM timing uses the shared `tNN` delay.
CE6 control-page writes use the separate `cNN` delay.

## USB-UART Commands

The USB-UART runs at `1,000,000 baud`, `8N1`.

Each command must be terminated by `CR` or `CRLF`.
The FPGA echoes accepted input, then emits a response line.

### RAM Commands

These access the `2 KiB` CE1 RAM backing store.

| Command | Meaning |
| --- | --- |
| `rAAA` | Read RAM offset `0x000..0x7FF` |
| `wAAA=BB` | Write RAM offset `0x000..0x7FF` |

Rules:

- `AAA` is 3 hex digits
- `BB` is 2 hex digits
- RAM is only `2 KiB`, mirrored across the larger CE1 window

Examples:

```text
r123
123=5A
```

```text
w123=5A
OK
```

### ROM Commands

These access the `2 KiB` CE6 ROM backing store.

| Command | Meaning |
| --- | --- |
| `RAAA` | Read ROM offset `0x000..0x7FF` |
| `WAAA=BB` | Write ROM offset `0x000..0x7FF` |

Rules:

- `AAA` is 3 hex digits
- `BB` is 2 hex digits
- This writes the FPGA ROM backing store directly
- Calculator bus writes to CE6 do not program ROM; only `WAAA=BB` does

Examples:

```text
W021=A7
OK
R021
021=A7
```

### Timing Commands

| Command | Meaning | Default |
| --- | --- | --- |
| `tNN` | Set normal CE1/CE6 memory classify delay | `t45` |
| `cNN` | Set CE6 control-page write delay | `c03` |

Rules:

- `NN` is decimal `00..99`
- unit is `10 ns`

Examples:

```text
t45
T=450ns
```

```text
c03
C=030ns
```

What they control:

- `tNN`
  - CE1 RAM read/write classify timing
  - CE6 ROM read classify timing
- `cNN`
  - CE6 control-page writes in low16 `0xFFF0..0xFFFF`

### Measurement Commands

These dump measurement reports created by CE6 control-page writes.

| Command | Meaning |
| --- | --- |
| `m` | Dump all queued measurement reports |
| `m?` | Print measurement FIFO status |
| `m!` | Clear queued reports and reset overflow count |

`m?` response:

```text
MS,CNT=..,OVF=........,ARM=0
```

Fields:

- `CNT`
  - queued report count
- `OVF`
  - number of reports dropped because the report FIFO was full
- `ARM`
  - `1` if a measurement interval is currently armed

`m` response:

```text
MR,S=..,E=..,TK=........,EV=........,AU=........
...
MEND
```

Fields:

- `S`
  - start tag byte
- `E`
  - stop tag byte
- `TK`
  - elapsed FPGA ticks at `100 MHz`
  - convert to time with `ns = TK * 10`
- `EV`
  - CE event count delta
- `AU`
  - address-UART emission count delta

`m!` response:

```text
OK
```

## CE6 Special Control Page

The FPGA treats CE6 low16 `0xFFF0..0xFFFF` as a special write-only control page.

Important properties:

- CE6 is active when `low`
- address decode uses only the low 16 bits
- reads from this page are passive
  - the FPGA does not drive the data bus
- writes to this page use the separate `cNN` delay
  - not `tNN`

Because low16 decoding is used, both aliases match:

- `0x0FFF0..0x0FFFF`
- `0x1FFF0..0x1FFFF`

From calculator software, use the logical CE6 addresses in the `0x01xxxx` range.

### Register Map

| Logical address | Low16 | Name | Access | Meaning |
| --- | --- | --- | --- | --- |
| `0x01FFF0` | `0xFFF0` | `MARK_START` | write-only | arm measurement and snapshot counters |
| `0x01FFF1` | `0xFFF1` | `ECHO` | write-only | send written byte to USB-UART |
| `0x01FFF2` | `0xFFF2` | `MARK_STOP` | write-only | stop measurement and queue report |
| `0x01FFF3` | `0xFFF3` | `MARK_ABORT` | write-only | clear armed measurement without report |
| `0x01FFF4..0x01FFFF` | `0xFFF4..0xFFFF` | reserved | write-only | currently no action |

### `ECHO` Register

Writing a byte to `0x01FFF1` sends that byte directly to the FPGA USB-UART.

Example calculator-side use:

```basic
POKE &H1FFF1,65
```

Expected host output:

```text
A
```

If the USB-UART is busy when the byte arrives:

- the byte is dropped
- the FPGA later prints:

```text
!OVERRUN
```

### Measurement Registers

The measurement path is meant for profiling instruction timing and bus activity.

#### `MARK_START`

Write a tag byte to `0x01FFF0`.

Effect:

- arms the profiler
- snapshots:
  - current tick counter
  - current CE event count
  - current address-UART count

The baseline is taken after the start marker's same-cycle bookkeeping, so the interval starts after the marker write itself.

#### `MARK_STOP`

Write a tag byte to `0x01FFF2`.

Effect:

- if armed, computes deltas from the stored baseline
- enqueues one report in the report FIFO
- clears `ARM`

#### `MARK_ABORT`

Write any byte to `0x01FFF3`.

Effect:

- clears `ARM`
- does not enqueue a report

### Measurement Example

Calculator-side:

```basic
POKE &H1FFF0,1
REM code under test
POKE &H1FFF2,2
```

Host-side:

```text
m
MR,S=01,E=02,TK=0000002D,EV=00000005,AU=00000003
MEND
```

Interpretation:

- start tag `0x01`
- stop tag `0x02`
- elapsed time `0x2D` ticks = `45 * 10 ns = 450 ns`
- `5` CE events
- `3` address-UART emissions

## Error and Busy Responses

Common FPGA USB-UART responses:

| Response | Meaning |
| --- | --- |
| `OK` | command accepted |
| `BUSY` | command collided with active internal work and was not completed |
| `ERR` | parse or syntax error |
| `!OVERRUN` | CE6 `ECHO` byte was dropped because USB-UART output was busy |

## Practical Notes

### RAM and ROM Sizes

- CE1 RAM backing store: `2 KiB`
- CE6 ROM backing store: `2 KiB`
  - low16 `0x0000..0x07FF` only
  - reads above that range remain passive

### CE6 ROM vs CE6 Control Page

These are different mechanisms:

- CE6 ROM low window:
  - read-backed from FPGA ROM storage
  - programmed over USB-UART with `R/W`
- CE6 control page `0xFFF0..0xFFFF`:
  - write-only special registers
  - separate `cNN` timing
  - not normal ROM

### Low16 Aliasing

For CE6:

- ROM low-window decode uses low16 bits
- control-page decode uses low16 bits

So these pairs alias internally:

- `0x10000` and low16 `0x0000`
- `0x1FFF1` and low16 `0xFFF1`

For calculator-side code, prefer the logical `0x01xxxx` addresses.

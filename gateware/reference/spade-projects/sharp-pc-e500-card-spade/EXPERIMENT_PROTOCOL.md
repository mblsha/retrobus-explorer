# PC-E500 Experiment Protocol

This document defines the fixed host/device protocol for continuous experiment
iteration on the PC-E500 using only the reliable FPGA-backed CE6 ROM and CE6
write-only control page.

Implemented host-side components:

- daemon:
  - [scripts/pc-e500-expd.py](./scripts/pc-e500-expd.py)
- CLI:
  - [scripts/pc-e500-expctl.py](./scripts/pc-e500-expctl.py)
- default device image:
  - [asm/card_rom_supervisor_safe.asm](./asm/card_rom_supervisor_safe.asm)

It is intentionally small and rigid:

- low CE6 ROM contains the supervisor
- high CE6 ROM contains the host-written command block
- the experiment entry point is fixed
- results come back through:
  - `MARK_START` / `MARK_STOP` measurement reports
  - sparse `XR,...` lines via `ECHO`

## Device Layout

### CE6 ROM Regions

- `0x10000..0x100FF`
  - supervisor image
- `0x10100..0x106FF`
  - experiment payload
- `0x107E0..0x107FF`
  - command block

The host may rewrite the experiment payload and command block while the
supervisor sits idle in its low-ROM polling loop.

## Fixed Entry Points

- user bootstrap:
  - `CALL &10000`
- experiment entry:
  - `0x10100`

The supervisor always executes the experiment by calling the fixed experiment
entry. There is no dynamic entry-point lookup in v1.

## Command Block

The command block lives at `0x107E0..0x107FF`.

| Address | Meaning |
| --- | --- |
| `0x107E0` | magic byte `'X'` (`0x58`) |
| `0x107E1` | magic byte `'R'` (`0x52`) |
| `0x107E2` | protocol version (`0x01`) |
| `0x107E3` | flags |
| `0x107E4` | measurement start tag |
| `0x107E5` | measurement stop tag |
| `0x107E6..0x107EF` | experiment argument bytes `arg0..arg9` |
| `0x107F0..0x107FE` | reserved |
| `0x107FF` | sequence / commit byte |

Rules:

- the host writes the full block first
- the host writes `0x107FF` last
- the supervisor treats a new non-zero `sequence` value as a new command
- the supervisor ignores a command if the sequence matches the last-seen value

The host owns the meaning of `flags` and `arg0..arg9`.

## CE6 Control Page Usage

Use the existing write-only control page:

- `0x01FFF0` = `MARK_START`
- `0x01FFF1` = `ECHO`
- `0x01FFF2` = `MARK_STOP`
- `0x01FFF3` = `MARK_ABORT`

The supervisor writes:

- `MARK_START` immediately before calling the experiment
- `MARK_STOP` immediately after the experiment returns

Experiments may also write their own nested markers and sparse `ECHO` bytes.

## UART Line Protocol

All structured UART output for the host supervisor uses ASCII lines beginning
with `XR,`.

### Supervisor-generated lines

- `XR,READY,<proto>,<build>`
  - emitted once when the supervisor starts after `CALL &10000`
- `XR,BEGIN,<seq>`
  - emitted immediately before the supervisor issues the outer `MARK_START`
- `XR,END,<seq>,OK`
  - emitted immediately after the experiment returns and the outer `MARK_STOP`
  is issued

### Experiment-generated lines

Experiments may emit their own lines, but they must also begin with `XR,`.

Recommended forms:

- `XR,NOTE,<text>`
- `XR,VALUE,<key>,<value>`
- `XR,CHECK,<name>,OK`
- `XR,CHECK,<name>,FAIL`

Keep experiment UART output sparse. The primary numeric timing data should come
from the measurement FIFO, not from large UART dumps.

## Host Supervisor States

The host daemon models the device as one of:

- `waiting_for_call`
- `idle`
- `running`
- `needs_reset`

State transitions:

- `waiting_for_call -> idle`
  - when `XR,READY,...` is seen
- `idle -> running`
  - when a job is committed
- `running -> idle`
  - when `XR,END,<seq>,OK` is seen and the measurement dump succeeds
- `running -> needs_reset`
  - on timeout or unrecoverable protocol error

## Timeout Handling

If an experiment times out:

1. the host marks the current session as `needs_reset`
2. the host attempts to reprogram the safe supervisor image into CE6 ROM
3. the host reports `needs_reset=true`
4. the user must reset the calculator and run `CALL &10000` again

Important caveat:

- reprogramming CE6 ROM does not recover the already-running stuck CPU
- it only ensures that the next reset + `CALL` returns to the safe supervisor

## Experiment Script Contract

An experiment script is a Python program used by the host daemon.

It must support:

```text
python experiment.py plan [script-args...]
```

which prints a JSON object describing the run.

Optional:

```text
python experiment.py parse /path/to/raw-result.json [script-args...]
```

which prints parsed JSON derived from the raw daemon result.

### `plan` JSON

Required fields:

- `name`
- one of:
  - `asm_source`
  - `asm_text`

Optional fields:

- `timing`
- `control_timing`
- `timeout_s`
- `start_tag`
- `stop_tag`
- `flags`
- `args`

The CLI forwards extra arguments after `--` to both the `plan` and `parse`
subcommands. That makes it possible to inject parameterized experiments without
editing the daemon.

### Raw result JSON

The daemon returns a JSON object containing:

- daemon/device status
- measurement records
- captured `XR,...` lines
- metadata such as run id and timing configuration

The optional `parse` step can turn that into a smaller experiment-specific
result.

# PC-E500 Experiment Protocol

This document defines the fixed host/device protocol for continuous experiment
iteration on the PC-E500 using only the reliable FPGA-backed CE6 ROM and CE6
write-only control page.

Implemented host-side components:

- daemon:
  - [scripts/pc-e500-expd.py](./scripts/pc-e500-expd.py)
- CLI:
  - [scripts/pc-e500-expctl.py](./scripts/pc-e500-expctl.py)
- sweep helper:
  - [scripts/pc-e500-expfit.py](./scripts/pc-e500-expfit.py)
- default device image:
  - [asm/card_rom_supervisor_safe.asm](./asm/card_rom_supervisor_safe.asm)

It is intentionally small and rigid:

- low CE6 ROM contains the supervisor
- high CE6 ROM contains the host-written command block
- the experiment entry point is fixed
- results come back through:
  - `MARK_START` / `MARK_STOP` measurement reports
  - sparse `XR,...` lines via `ECHO`

Current default:

- the standard supervisor image enables FT sampled-bus capture during startup
- the host daemon drains FT600 during experiment runs by default
- experiments may opt out only for explicit fallback/debug cases

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

Current flag assignments:

- `bit0`
  - reserved for FT sampled-bus capture enable signalling in the command block
    if a future per-run gating variant is needed

## Supervisor Scratch State

The current supervisor keeps scratch state in internal memory:

- `0x30`
  - last executed sequence
- `0x31`
  - current sequence scratch

Experiment payloads must not clobber those bytes unless they also restore them
before returning. In practice, avoid `0x30` and `0x31` as temporary internal
RAM destinations in measurement probes.

When a probe needs scratch space that should not overlap the supervisor's fixed
internal-memory state, prefer reserving a temporary window from a live external
stack pointer and restoring the pointer before return, rather than hard-coding
an absolute external RAM address.

Observed hardware note:

- a single-step `U`-backed probe at `0x3F880` was useful because FT600 showed
  the real write-data bytes there
- the same hard-coded `U = 0x3F880` target was not safe for repeated runs and
  wedged the session
- so fixed external stack-window addresses should be treated as exploratory
  only; reusable probes should derive and restore their scratch window from the
  live stack state

Recommended use of stack-backed windows:

- use a reserved `U`- or `S`-backed external RAM window when a probe needs
  trustworthy write-data observation on the FT stream
- this is better than passive CE6 ROM-write targets, which often preserve
  timing and address order but can show unreliable write-data bytes
- good candidates include:
  - multi-byte writes (`MVW`, `MVP`)
  - read-modify-write probes where writeback value matters
  - stack-order probes (`PUSH*`, `POP*`, `CALL*`, `RET*`)
- derive the scratch window from the live stack pointer, use it briefly, then
  restore the pointer before `RETF`

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

## Host-Side Parsing Notes

These are not protocol goals; they are observed realities of the current shared
UART path and the host implementation must tolerate them.

- Once the supervisor is alive, unsolicited `XR,...` lines can legally arrive
  immediately after host command replies such as `W...` and `m!`.
- Host helpers should therefore treat a reply as successful if the expected
  acknowledgement line appears anywhere in the captured reply block, not only as
  the final line.
- Raw-byte waits used for smoke tests must start from a fresh UART boundary
  after host programming traffic settles. Otherwise late bytes from the previous
  transaction can be mistaken for experiment output.

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
- `ft_capture`
- `ft_read_size`
- `ft_read_timeout_ms`
- `ft_post_stop_idle_s`
- `ft_post_stop_hard_s`
- `ft_max_retained_words`

If `ft_capture=true`, the daemon starts a capture session on top of an already
running FT600 drain thread and returns decoded sampled-bus words in the raw
result. The reader keeps draining until either:

- no new FT bytes arrive for `ft_post_stop_idle_s`, or
- `ft_post_stop_hard_s` elapses after stop

That models the expected bursty FT delivery and in-flight buffering on the
separate channel.

The FT path now uses a bounded ring buffer:

- old words are discarded from the head once retained history exceeds
  `ft_max_retained_words`
- the primary goal is to avoid FPGA overflow by keeping the host-side drain
  thread running continuously
- bounding the retained history is a separate memory-management decision and
  should not interfere with draining

Default:

- `ft_max_retained_words = 262144`

The intended default is `ft_capture=true`. Use `ft_capture=false` only when
explicitly validating the non-FT fallback path.

The CLI forwards extra arguments after `--` to both the `plan` and `parse`
subcommands. That makes it possible to inject parameterized experiments without
editing the daemon.

### Raw result JSON

The daemon returns a JSON object containing:

- daemon/device status
- measurement records
- captured `XR,...` lines
- metadata such as run id and timing configuration
- raw FT600 sampled-bus words when `ft_capture=true`
- `ft_capture.preview`: decoded first-word preview
- `ft_capture.compact_preview`: a simplified event stream that drops most
  synthetic followups and collapses repeated adjacent samples
- `ft_capture.execution_preview`: a compacted inferred execution window from
  first experiment-ROM activity through the first supervisor fetch after return
- `ft_capture.measurement_preview`: a compacted window bracketed by
  `MARK_START`/`MARK_STOP` when those control writes are present in the FT
  stream
- `ft_capture.max_retained_words`: configured ring-buffer retention limit
- `ft_capture.retained_words`: currently retained word count after trimming
- `ft_capture.total_words_seen`: total sampled words seen during the session
- `ft_capture.truncated_head`: whether the oldest part of the per-experiment
  capture had already been dropped by the retention limit

The optional `parse` step can turn that into a smaller experiment-specific
result.

### FT decode helper

For saved result JSON, use:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-ftdecode.py \
  path/to/result.json \
  --compact
```

This reads `ft_capture.words` and prints a readable bus-event table with
address, data, event kind, region labels, and status flags.

Useful options:

```sh
# inferred experiment execution window only
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-ftdecode.py \
  path/to/result.json \
  --window execution --compact

# MARK_START..MARK_STOP window only, exported as Markdown
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-ftdecode.py \
  path/to/result.json \
  --window measurement --compact --markdown
```

### Sweep helper

For count-based timing rows, use the sweep helper instead of manually running a
series of `expctl run` commands and fitting the line afterward.

The count-based chain probes now live behind the generic catalog runner:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/experiments/catalog_experiment.py list
```

Example:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expfit.py \
  --pretty \
  --counts 64,128,192,224,255,256 \
  ./spade-projects/sharp-pc-e500-card-spade/experiments/catalog_experiment.py \
  -- --experiment mvp_imem_imem_chain --no-ft-capture
```

It returns:

- raw per-count results
- retry count per point
- linear fits for `ticks`, `ce_events`, `addr_uart`, and `ft_overflow`
- `ticks.slope_over_quantum`, which normalizes the measured slope to the
  current `NOP` baseline

If any successful run reports `measurement.ft_overflow > 0`, the helper marks
that in the JSON result and emits a note explaining that the point should be
treated as degraded. Those runs are useful as a prompt to improve the
host-side FT600 draining path so future captures can keep up without overflow.

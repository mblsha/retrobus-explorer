# Continuous Experiment Plan

This is the implemented plan for running many small SC62015 experiments on a
real PC-E500 with only one human action after each reset.

## Goal

Make it possible to iterate on tiny CE6 ROM experiments from the host by using
only:

- the FPGA-backed 2 KiB CE6 ROM window
- the CE6 write-only control page:
  - `0x01FFF0` = `MARK_START`
  - `0x01FFF1` = `ECHO`
  - `0x01FFF2` = `MARK_STOP`
  - `0x01FFF3` = `MARK_ABORT`
- the Au1 USB-UART

The calculator should stay inside a resident CE6 supervisor loop after one
manual `CALL &10000`.

## Constraints

- The current FPGA-backed CE1 RAM path is not reliable enough to use as shared
  host/device state.
- The reliable bidirectional control plane is the host-programmable CE6 ROM
  plus the host-visible USB-UART.
- The shared UART must not carry host `R...` / `W...` commands while the
  calculator is still echoing experiment output.
- If an experiment wedges the machine, there is no live recovery. The only
  recovery is:
  - reprogram a safe ROM image for the next boot
  - ask the user to reset
  - ask the user to run `CALL &10000` again

## Architecture

There are two supervisors.

### Device Supervisor

The calculator runs a fixed CE6 ROM image:

- [asm/card_rom_supervisor_safe.asm](./asm/card_rom_supervisor_safe.asm)

Responsibilities:

- disable interrupts
- emit `XR,READY,01,SAFE` once after `CALL &10000`
- poll the high-ROM command block
- detect a new non-zero sequence byte
- emit `XR,BEGIN,<seq>`
- write outer `MARK_START`
- `CALLF 0x10100`
- write outer `MARK_STOP`
- emit `XR,END,<seq>,OK`
- return to the idle loop

### Host Supervisor

The host owns the serial port through:

- [scripts/pc-e500-expd.py](./scripts/pc-e500-expd.py)

Responsibilities:

- continuously monitor UART traffic
- wait for a quiet line before issuing FPGA commands
- assemble and program CE6 experiments into `0x10100..0x106FF`
- write the fixed command block at `0x107E0..0x107FF`
- wait for `XR,BEGIN` / `XR,END`
- dump measurement records with `m`
- return structured JSON results
- on timeout, reprogram the safe supervisor image and mark the session as
  `needs_reset`

The human or automation talks to the daemon through:

- [scripts/pc-e500-expctl.py](./scripts/pc-e500-expctl.py)

## Memory Layout

- `0x10000..0x100FF`
  - safe supervisor code and string tables
- `0x10100..0x106FF`
  - experiment payload region
- `0x107E0..0x107FF`
  - command block

The safe supervisor image also zeros the command block so the post-timeout
reset path starts in a known idle state.

## Workflow

1. Start the daemon and program the safe image.
2. User resets the PC-E500.
3. User runs `CALL &10000`.
4. Daemon sees `XR,READY,01,SAFE` and moves to `idle`.
5. CLI submits an experiment script.
6. Daemon assembles and programs the experiment region.
7. Daemon writes the command block body, then commits the sequence byte last.
8. Device supervisor runs the experiment and returns to idle.
9. Daemon collects timing records plus `XR,...` lines and returns JSON.
10. Repeat from step 5 until the device wedges or is reset.

## Current Status

The following pieces are now verified on real hardware:

- `CALL &10000` can enter the CE6 supervisor and stay in the idle loop
- the supervisor emits `XR,READY,01,SAFE`
- the host daemon can observe that ready line while owning the shared UART
- the trivial experiment
  [experiments/return_immediately.py](./experiments/return_immediately.py)
  runs end-to-end and returns to the idle supervisor loop
- direct calculator-side `ECHO` also works through the shared UART using
  [asm/card_rom_echo_short_retf.asm](./asm/card_rom_echo_short_retf.asm)

The main remaining limitation is experiment safety, not the host/device control
plane. A bad experiment can still wedge the calculator and force the reset path.

## Operational Notes

- Do not assume host command replies end with the last line being `OK`. Once
  the supervisor is running, unsolicited `XR,...` lines may appear after a
  `W...` or `m!` reply on the same UART.
- For raw-byte waits such as the debug echo smoke test, the host must
  synchronize to a fresh UART boundary after programming. Otherwise delayed
  bytes from the previous host transaction can become false positives.
- Early writes to `IMR` were removed from the startup path because they caused
  unstable behavior on hardware during supervisor entry.

## Experiment Scripts

Experiment scripts are small Python files that define the next run.

Implemented examples:

- [experiments/return_immediately.py](./experiments/return_immediately.py)
- [experiments/wait_probe.py](./experiments/wait_probe.py)

Each script supports:

- `plan`
  - prints JSON describing the next experiment
- `parse RESULT.json`
  - optionally turns the raw daemon result into a smaller parsed JSON object

Reference assembly payloads:

- [asm/card_rom_experiment_return.asm](./asm/card_rom_experiment_return.asm)
- [asm/card_rom_wait_probe.asm](./asm/card_rom_wait_probe.asm)

## Timeout Behavior

If `XR,BEGIN` or `XR,END` never arrives before the configured timeout:

1. the daemon marks the session `needs_reset`
2. the daemon reprograms the safe supervisor image into CE6 ROM
3. the daemon returns JSON with:
   - `status = "timeout"`
   - `needs_reset = true`
4. the user resets the calculator and runs `CALL &10000` again

Reprogramming the ROM does not recover the already-running stuck CPU. It only
guarantees that the next reset returns to the supervisor loop.

## Accuracy-Plan Fit

This setup is enough to iterate on the highest-value hardware questions:

- `WAIT` timing and bus idleness
- fixed instruction microbenchmarks
- branch taken vs not-taken fetch patterns
- `CALLF` / `RETF` sequencing
- read/modify/write and multi-byte transfer ordering

The primary numeric result channel remains the measurement FIFO. `ECHO` is used
only for sparse framed `XR,...` lines and experiment-specific checkpoints.

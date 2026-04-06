# SHARP PC-E500 Card Spade

This project emulates a SHARP PC-E500 card with FPGA-backed CE1 RAM, CE6 ROM,
and a CE6 control page exposed through the onboard USB-UART.

## Expected Host Interface

Use the Au1 onboard USB-UART as the host control path. Optional bulk capture of
sampled bus words can also be routed through the Alchitry Ft Element FT600
interface when the measurement window is armed.

- Control, RAM/ROM access, and measurement dump: Au1 onboard USB-UART
- Timing and bus visibility: Saleae debug header outputs
- Measurement-gated sampled-bus bulk capture: Au + Ft Element FT600 path

FT600 sampled-bus capture is now the default experiment mode. The stable
supervisor enables the calculator-side FT stream, and the host daemon now keeps
a persistent FT600 drain thread alive by default. Per-experiment captures are
cut out of that continuously drained stream instead of repeatedly opening and
closing the FT side channel.

## Au1 USB-UART

The Alchitry Au1 exposes two macOS serial ports. The slow control UART for this
project is the second `/dev/cu.usbserial-*` device, which
`sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py` auto-selects by
default.

For long-lived experiment sessions on the shared USB-UART, use:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-experiment-session.py
```

That tool continuously monitors UART output and waits for a quiet line before
sending FPGA control/programming commands, which helps avoid collisions with
calculator-side `ECHO` traffic.

For the complete FPGA command and CE6 control-register reference, see
[FPGA_PROTOCOL.md](./FPGA_PROTOCOL.md).

For long-lived experiment sessions on the shared USB-UART, use:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-experiment-session.py
```

That tool continuously monitors UART output and waits for a quiet line before
sending FPGA control/programming commands, which helps avoid collisions with
calculator-side `ECHO` traffic.

For the approved FT capture implementation shape, see
[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md).

For the fixed continuous-experiment host/device protocol and CE6 ROM layout,
see [EXPERIMENT_PROTOCOL.md](./EXPERIMENT_PROTOCOL.md).

From `gateware/reference`:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py probe
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py timing 5
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py control-timing 10
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py read 0x10000
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py write 0x10000 0x5A
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py \
  program rom.bin --start 0x10000
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py \
  program rom.bin --start 0x10000 --fast
```

Read and write commands target the 2 KiB FPGA-emulated card-ROM window. The
window starts at calculator address `0x10000` and maps to UART offsets
`000..7FF`, so `read 0x10000` and `read 000` address the same byte.

For bulk ROM programming, `--fast` concatenates all `Wxxx=xx` commands into one
UART payload. On the current Au1 build this gets the write-only path to roughly
the full 1,000,000 baud wire rate; use `--verify` only when you need readback
validation in the same session.

Before executing code directly from the FPGA-backed card ROM, set the normal
read/classify timing and the CE6 control-page write timing explicitly:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py timing 5
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py control-timing 10
```

`tNN` controls normal CE1/CE6 memory classify timing, while `cNN` controls only
CE6 control-page writes in `0x1FFF0..0x1FFFF`.

## Card-ROM Assembly

The helper below assembles SC62015 code through the local
`~/src/github/binja-esr-tests/public-src` checkout and can program the result
into the FPGA-backed card ROM.

Smoke test:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-card-asm.py \
  ./spade-projects/sharp-pc-e500-card-spade/asm/card_rom_smoke_sentinel.asm \
  --program
```

That helper emits a binary image, sets `t05` and `c10` by default when
programming, and prints the calculator entry point. The smoke payload lives at
`0x10000`, so the PC-E500 command to execute it is:

```basic
CALL &10000
```

The current bitstream aliases CE1 card accesses into the 2 KiB ROM window, so
the smoke test uses a sentinel byte inside that window instead of a special
print-char register. Right after programming, `0x107F1` is initialized to
`0x00`. After `CALL &10000`, it should read back as `0xA5`:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py read 0x107F1
```

## Glasgow UART

The Glasgow wrappers in `sharp-pc-e500-card-spade/scripts/` call the local
Glasgow checkout via `uv run --directory ~/src/github/glasgow/software`.

From `gateware/reference/spade-projects`:

Port-B wiring:

- `B0`: device-ready-to-receive, mapped to `--cts B0#`
- `B1`: host-ready-to-receive, mapped to `--rts B1#`
- `B2`: device TX, mapped to `--rx B2#`
- `B3`: host TX, mapped to `--tx B3#`

The `#` suffix inverts the signal, which matches the PC-E500 wiring here.

Receive a BASIC listing from the calculator:

```sh
uv run ./sharp-pc-e500-card-spade/scripts/pc-e500-get.py
```

Then run this on the PC-E500:

```basic
SAVE"COM:1200,N,8,1,A,L,&1A,X,N"
```

The receiver stops automatically when the calculator sends the configured
`0x1A` terminator byte.

Send a BASIC listing to the calculator:

```sh
uv run ./sharp-pc-e500-card-spade/scripts/pc-e500-send.py path/to/program.bas
```

If no path is given, the sender reads the listing from stdin. It normalizes line
endings to CRLF and appends `0x1A` at the end of the transfer.

Then run this on the PC-E500:

```basic
LOAD"COM:"
```

## Notes

Host control remains centered on the USB-UART command set documented in
[FPGA_PROTOCOL.md](./FPGA_PROTOCOL.md). The FT600 path, when enabled through the
CE6 control page, mirrors the existing `saleae[4]` sampled-bus words and is
intended for bulk capture during a measurement window rather than for general
interactive control.

For the current "single CALL after reset, then keep iterating from the host"
approach, see [CONTINUOUS_EXPERIMENT_PLAN.md](./CONTINUOUS_EXPERIMENT_PLAN.md).

## Continuous Experiment Supervisor

The implemented continuous-test path splits responsibilities between:

- a CE6 ROM supervisor image:
  - [asm/card_rom_supervisor_safe.asm](./asm/card_rom_supervisor_safe.asm)
- a long-lived host daemon that owns the shared USB-UART:
  - [scripts/pc-e500-expd.py](./scripts/pc-e500-expd.py)
- a small JSON CLI for injecting experiment scripts:
  - [scripts/pc-e500-expctl.py](./scripts/pc-e500-expctl.py)
- a sweep/fitting helper for repeated count experiments:
  - [scripts/pc-e500-expfit.py](./scripts/pc-e500-expfit.py)

Typical flow from `gateware/reference`:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expd.py \
  --arm-safe-on-start \
  --monitor-uart
```

Reset the calculator once, then run:

```basic
CALL &10000
```

After `XR,READY,01,SAFE` appears, use the CLI from another shell:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expctl.py \
  wait-ready --timeout 30

uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expctl.py \
  --pretty \
  run ./spade-projects/sharp-pc-e500-card-spade/experiments/return_immediately.py

uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expctl.py \
  --pretty \
  run ./spade-projects/sharp-pc-e500-card-spade/experiments/wait_probe.py -- 0x0400
```

For the common timing-sweep workflow, use the fitting helper instead of
hand-running six counts and computing the line manually:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expfit.py \
  --pretty \
  --counts 64,128,192,224,255,256 \
  ./spade-projects/sharp-pc-e500-card-spade/experiments/mvp_imem_imem_chain.py \
  -- --no-ft-capture
```

That returns:

- one entry per count
- retry count per point
- linear fits for `ticks`, `ce_events`, `addr_uart`, and `ft_overflow`
- `ticks.slope_over_quantum` normalized to the current `NOP` quantum

If any run reports `ft_overflow > 0`, treat that point as degraded rather than
as a valid timing result. The sweep helper now surfaces that explicitly so we
can use those runs as a prompt to make the host-side FT600 capture path faster
and avoid future overflow.

Timeout recovery is explicit:

- the daemon reprograms the safe supervisor image
- the daemon returns JSON with `needs_reset=true`
- the user resets the PC-E500 and runs `CALL &10000` again

The stable supervisor image writes `0x01` to `0x1FFF4` during startup so the
calculator-side FT sampled-bus stream stays enabled by default. The host-side
pairing is now a persistent FT reader thread plus a bounded ring buffer.
Very old FT words are discarded from the head once the configured retention
limit is exceeded, which keeps the host draining aggressively without trying to
retain unlimited history.

The daemon now returns two FT views for each captured run:

- raw `ft_capture.words` for exact post-processing
- `ft_capture.compact_preview` for a simplified first-pass event sequence that
  hides most synthetic followups
- `ft_capture.execution_preview` for the inferred experiment execution window
- `ft_capture.measurement_preview` for the `MARK_START` / `MARK_STOP` window
  when visible in FT capture
- retention metadata:
  - `ft_capture.max_retained_words`
  - `ft_capture.retained_words`
  - `ft_capture.total_words_seen`
  - `ft_capture.truncated_head`

Experiment plans may override the default retention window with:

- `ft_max_retained_words`

Use that when you want to keep only the newest portion of a long FT capture
while still ensuring the host drains the always-on FT stream fast enough to
avoid FPGA overflow.

For saved results, decode them with:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-ftdecode.py \
  path/to/result.json \
  --compact
```

The decoder also supports:

```sh
# focus on the first experiment execution window
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-ftdecode.py \
  path/to/result.json \
  --window execution --compact

# emit a Markdown table suitable for docs
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-ftdecode.py \
  path/to/result.json \
  --window execution --compact --markdown
```

## Current Verified Flow

This path is now proven on hardware with the current bitstream and ROM images:

1. Start the daemon:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expd.py \
  --monitor-uart
```

2. Program the safe supervisor image:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expctl.py \
  --pretty \
  arm-safe
```

3. Reset the calculator and run:

```basic
CALL &10000
```

4. Wait for the supervisor ready line:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expctl.py \
  --pretty \
  wait-ready --timeout 30
```

Expected UART line:

```text
XR,READY,01,SAFEFT
```

5. Run the smallest verified experiment:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expctl.py \
  --pretty \
  run ./spade-projects/sharp-pc-e500-card-spade/experiments/return_immediately.py
```

That path is verified end-to-end:

- supervisor enters idle after `CALL &10000`
- daemon observes `XR,READY,01,SAFE`
- experiment emits `XR,BEGIN,<seq>` and `XR,END,<seq>,OK`
- experiment returns to the idle supervisor loop
- daemon returns measurement JSON

More aggressive experiments may still wedge the calculator and require reset.

## UART Smoke Tests

Use these when you want to prove the calculator-side `ECHO` path separately
from the continuous supervisor.

Direct raw UART listener:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py \
  listen --duration 5 --expect "OK\r\n"
```

That `--expect` argument now decodes `\r`, `\n`, and `\xNN` escapes directly,
so it works as shown in fish, zsh, and bash.

Daemon-owned UART smoke test:

```sh
uv run ./spade-projects/sharp-pc-e500-card-spade/scripts/pc-e500-expctl.py \
  --pretty \
  debug-echo-short --timeout 10
```

While that command is waiting, run:

```basic
CALL &10100
```

The daemon programs
[asm/card_rom_echo_short_retf.asm](./asm/card_rom_echo_short_retf.asm), waits
for a fresh post-programming UART boundary, and then waits for the calculator
to emit `OK\r\n` and `RETF` back to BASIC.

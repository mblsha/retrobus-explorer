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

Timeout recovery is explicit:

- the daemon reprograms the safe supervisor image
- the daemon returns JSON with `needs_reset=true`
- the user resets the PC-E500 and runs `CALL &10000` again

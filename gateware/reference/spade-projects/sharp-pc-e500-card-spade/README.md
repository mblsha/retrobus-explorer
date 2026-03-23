# SHARP PC-E500 Card Spade

This project captures SHARP PC-E500 card-bus activity and streams FT records
over the same Alchitry Au + Ft Element USB3 interface used by the original
PC-G850 tooling.

## Expected Host Interface

Use the Alchitry Ft Element board as the bulk capture path.

- Data capture: FT600-class USB3 FIFO interface via the repository `py/d3xx` wrapper
- Control and arming: Au onboard USB-UART

Do not use `pyftdi` against the Au board's FT2232 USB-UART interface for FT
capture; the expected host path for this project is the Ft Element USB3 board.

## Capture Command

From `gateware/reference/spade-projects`:

```sh
uv run ./sharp-pc-e500-card-spade/scripts/capture_ft.py \
  --device-index 0 \
  --channel 0 \
  --raw-out /tmp/e500.ft16 \
  --vcd-out /tmp/e500.vcd \
  --duration 10 \
  --idle-timeout 10
```

The raw capture format is 16-bit little-endian FT words written to `.ft16`.
Use the USB-UART console to send `f1` when you want to enable FT streaming, and
then decode the capture with `scripts/e500_ft.py` or convert it to VCD with
`scripts/ft_to_vcd.py`.

## Au1 USB-UART

The Alchitry Au1 exposes two macOS serial ports. The slow control UART for this
project is the second `/dev/cu.usbserial-*` device, which
`sharp-pc-e500-card-spade/scripts/au1_usb_uart_probe.py` auto-selects by
default.

For the complete FPGA command and CE6 control-register reference, see
[FPGA_PROTOCOL.md](./FPGA_PROTOCOL.md).

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

## Host Implementation

The `scripts/capture_ft.py` and `scripts/ft_to_vcd.py` entrypoints now build
and execute C++ implementations by default. The Python modules remain in-tree
as the semantic reference and for unit tests, but normal CLI use goes through
the C++ binaries in `.cpp-build/`.

If you need to force the legacy Python path for debugging, set:

```sh
RETROBUS_E500_USE_PYTHON=1
```

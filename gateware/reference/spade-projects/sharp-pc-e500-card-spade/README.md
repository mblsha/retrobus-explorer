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

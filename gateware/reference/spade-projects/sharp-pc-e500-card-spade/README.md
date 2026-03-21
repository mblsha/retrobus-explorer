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

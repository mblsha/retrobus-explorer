# PC-E500 Live Display (Rust)

Standalone macOS app that:

- opens the Au1 USB-UART control port
- opens the FT600 bulk stream
- sends `F1` / `F0` / `F?`
- decodes sampled-bus words
- replays LCD controller writes into a local PC-E500 framebuffer

## Run

```sh
cargo run --release
```

Optional flags:

```sh
cargo run --release -- \
  --serial-port /dev/cu.usbserial-XXXXX \
  --ftd3xx /absolute/path/to/libftd3xx.dylib \
  --baud 1000000
```

FT-only mode with a Rust daemon control plane:

```sh
cargo run --release -- --no-uart --daemon-socket /tmp/pc-e500-expd-rs.sock
```

Defaults:

- serial port: auto-detect the second `/dev/cu.usbserial-*`
- FT600 dylib: `py/d3xx/libftd3xx.dylib` from the repo
- baud: `1000000`

## Notes

- The app assumes the FT600 stream is carrying sampled-bus words sourced from the UART FT stream path introduced in PR 148.
- If `F?` shows `SOVF` or `OVF` increasing, the display should be treated as desynced until the calculator redraws the screen.
- This app does not own calculator-side `FT_STREAM_CFG` programming. It enables continuous streaming with `F1` directly over UART, or through `--daemon-socket` in FT-only mode, but it still depends on the FPGA/calculator side being configured to mirror the desired source into FT600.

## Tests

```sh
cargo test
```

Current automated coverage is pure unit coverage only:

- FT word packing/status decode
- LCD controller write replay into the local framebuffer

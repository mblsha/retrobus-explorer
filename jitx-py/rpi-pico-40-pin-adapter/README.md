# rpi-pico-40-pin-adapter

Python JITX port scaffold for the legacy `jitx/rpi-pico-40-pin-adapter.stanza`
board.

Current goals:

- preserve the Stanza connectivity and placement intent
- preserve the `52.0 mm x 29.78 mm` rounded board outline
- preserve the dual `1x20` Pico headers, `2x20` Raspberry Pi GPIO header, and
  centered board label
- keep JITX-side geometry explicit while leaving copper pours to
  KiCad/post-process tooling

## Run

```bash
cd /home/mblsha/src/jitx/retrobus-explorer/jitx-py/rpi-pico-40-pin-adapter
uv sync
uv run python -m jitx build --dry src.main.RpiPico40PinAdapterDesign
```

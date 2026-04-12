# sharp-pc-g850-bus

Python JITX port scaffold for the legacy `jitx/sharp-pc-g850-bus.stanza` board.

Current goals:

- preserve the Stanza connectivity and placement intent
- preserve the 50 mm x 21 mm rounded board outline
- preserve the 60-pin FFC, PC-G850 edge connector, corner GND test pads, and board label
- keep JITX-side routing and geometry explicit while leaving ground pours to KiCad/post-process tooling

## Run

```bash
cd /home/mblsha/src/jitx/retrobus-explorer/jitx-py/sharp-pc-g850-bus
uv sync
uv run python -m jitx build --dry src.main.SharpPcG850BusDesign
```

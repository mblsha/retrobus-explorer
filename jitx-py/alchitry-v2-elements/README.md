# alchitry-v2-elements

Python JITX import of the published Alchitry V2 KiCad element library.

Source reference:
- `https://cdn.alchitry.com/elements/Alchitry%20V2%20Elements%20KiCAD.zip`
- `https://alchitry.com/tutorials/references/pinouts-and-custom-elements/`

The original KiCad symbol and footprint files are vendored under [`vendor/`](vendor).
`src/components.py` parses those sources and builds reusable JITX components for:

- `AlchitryV2TopElement`
- `AlchitryV2BottomElement`
- `AlchitryV2BothElement`

Signal naming:
- Most ports keep the published Alchitry names directly, for example `A3`, `B42`, `L0`, `RESET`.
- `3.3V` is exposed as `V3V3`.
- `~{PROG}` is exposed as `PROG_N`.

Every component also exposes `port(signal_name: str)` for access by the original KiCad signal name, for example:

```python
element.port("3.3V")
element.port("~{PROG}")
element.port("A3")
```

One upstream quirk is preserved intentionally: the published `V2_BOTTOM` symbol labels `C30` as `GND`, while `V2_TOP` and `V2_BOTH` label the corresponding signal as `L4`.

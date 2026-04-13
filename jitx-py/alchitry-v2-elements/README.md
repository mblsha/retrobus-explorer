# alchitry-v2-elements

Python JITX import of the published Alchitry V2 KiCad element library.

## Primary Sources

- `https://alchitry.com/tutorials/references/pinouts-and-custom-elements/`
  - Alchitry's reference page for custom elements. This is the primary source for the V2 element connector roles, pin-1 orientation, and the exact Hirose part numbers used on the top and bottom sides.
- `https://cdn.alchitry.com/elements/Alchitry%20V2%20Elements%20KiCAD.zip`
  - The KiCad element library linked from the reference page above. This project's checked-in signal map data was generated from that symbol library, and the shared DF40 geometry was fitted against its published footprints.
- `https://www.hirose.com/en/product/series/DF40/`
  - Hirose's DF40 family page for the 0.4 mm board-to-board / board-to-FPC connector series referenced by Alchitry.
- `https://www.hirose.com/product/en/products/DF40/DF40C-50DP-0.4V%2851%29/`
  - One of the exact bottom-side mating connector part pages cited by Alchitry. The Alchitry reference page also names `DF40HC(4.0)-50DS-0.4V(51)`, `DF40HC(4.0)-80DS-0.4V(51)`, and `DF40C-80DP-0.4V(51)`.

## Provenance

The runtime model no longer reads a vendored KiCad library from this repo. Instead:

- the published Alchitry symbol data was converted once into [`src/generated_data.py`](src/generated_data.py)
- the reusable connector footprints live in [`shared-components`](../shared-components/src/shared_components/hirose_df40.py)
- [`src/components.py`](src/components.py) composes those shared Hirose DF40 connectors into the published `V2_TOP`, `V2_BOTTOM`, and `V2_BOTH` Alchitry element footprints

This keeps the source provenance explicit while removing the large vendored KiCad snapshot from the project tree.

`src/components.py` builds reusable JITX components for:

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

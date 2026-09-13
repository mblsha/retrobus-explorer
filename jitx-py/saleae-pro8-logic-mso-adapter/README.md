# saleae-pro8-logic-mso-adapter

JITX breakout that maps all eight Saleae Logic Pro 8 channels to two Logic MSO
single-ended Digital Probe connectors. The Logic Pro 8 side uses the same
shared `Saleae8` paired assembly as the Au1 level-shifter element: male 2x4
headers on an exact 2.54 mm grid, with their centers fixed 13.462 mm (0.53 inch)
apart. The entire paired assembly is quarter-turned as one rigid unit, putting
both headers on one horizontal centerline above their corresponding MSO
connectors. The Logic MSO side uses two
keyed **Nextron Z-231011810106** 2x5 through-hole headers, **LCSC C93713**.
The shared C93713 component defines the correct mating-face row order by
default: GND is on the row nearest the Pro 8 headers and the channel signals
are on the outer row.

## Channel mapping

| Logic Pro 8 | Logic MSO probe | C93713 signal pin | C93713 ground pin |
|---:|---:|---:|---:|
| CH0 | left D0 | 2 | 1 |
| CH1 | left D1 | 4 | 3 |
| CH2 | left D2 | 6 | 5 |
| CH3 | left D3 | 8 | 7 |
| CH4 | right D0 | 2 | 1 |
| CH5 | right D1 | 4 | 3 |
| CH6 | right D2 | 6 | 5 |
| CH7 | right D3 | 8 | 7 |

Pins 9 and 10 on both C93713 headers are **DNC** and remain unconnected. All
eight ground positions on the two Logic Pro 8 headers and all eight used ground
positions on the two Logic MSO headers share one GND net.

## Mechanical clearance

C93713 is not treated as a bare 2x5 pin field. Its footprint models the full
20.3 mm x 9.0 mm shroud and reserves a 21.3 mm x 10.0 mm courtyard. The measured
EasyEDA model interior is approximately 18.0 mm x 6.7 mm, exceeding Saleae's
required 17.3 mm x 6.0 mm minimum opening for the Digital Probe connector.

The board is 47 mm x 22 mm. Both C93713 courtyards have clearance to the board
edge and to each other.

All eight data channels use reproducible JITX bottom-layer route definitions.
GND pours cover both copper layers;
the sixteen plated ground positions across the four connectors and 26 dedicated
stitching vias tie the layers together throughout both channel banks. All 36
connector annular rings are exposed on both soldermask layers.
Every connector pad is identified with the same short `0`-`7`, `G`, or `·`
label on both silkscreen faces; bottom labels are mirrored for reading from the
bottom of the assembled board.

## Manufacturing release

Gerbers, Excellon drills, job manifests, KiCad boards, rendered images,
and upload ZIPs are generated local outputs, not repository files.
Regenerate and verify a complete manufacturing release before fabrication.

> **Regeneration required:** the earlier manufacturing release predates the
> corrected MSO row mapping. Rebuild/export it from JITX before fabrication.

## References

- [Saleae Digital Probe data sheet](https://downloads.saleae.com/specs/digital_probe_single_ended_data_sheet.pdf)
- [Saleae Logic MSO connector guidance](https://www.saleae.com/logic-mso)
- [LCSC C93713](https://www.lcsc.com/product-detail/C93713.html)

## Build

```bash
uv sync --extra dev
uv run python -m jitx build --dry --no-dependency-check src.main.SaleaePro8LogicMsoAdapterDesign
```

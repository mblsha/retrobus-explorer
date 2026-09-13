# alchitry-au2-level-shifter

JITX design for a bottom companion element for the Alchitry Au V2. It preserves
the Au1 level-shifter's two 60-pin RetroBus FFC connectors, 48 TXB0108-shifted
signals, eight Saleae probe outputs, and selectable bus supply.

The Au2 interface uses the published `V2_BOTTOM` mating-connector geometry on
the element's bottom face. The Au2 connectors and TXB0108 level shifters are on
the bottom; the FFC, Saleae, and supply-select connectors remain accessible on
the top. The interface excludes every Bank A signal occupied by an Ft V2 on the
opposite side. The resulting interface has 78 safe signals: 26 on Bank A and 52
on Bank B.

The four official V2 mounting-hole centers are implemented with the shared
grounded-corner component: 3.0 mm plated GND pads with 2.2 mm holes. The
canonical `V2_BOTTOM` component therefore omits only its duplicate NPTH holes;
its connector and mounting-pad geometry remains unchanged.

The adapter outline is 59.5 x 45 mm. It preserves the official Au2 top, right,
and bottom bounds in the mirrored bottom assembly view and adds only a 4.5 mm
left extension for the FFC connector courtyard. The two Saleae headers occupy
the clear top-side interior column, while the power-selection GPIO sits in the
bottom-right pocket beside connector C and clear of the grounded mounting hole.

Connector geometry, pin roles, and supply definitions come from Alchitry's
[Pinouts and Custom Elements](https://alchitry.com/tutorials/references/pinouts-and-custom-elements/)
reference and the official V2 KiCad element library linked there.

The 48 shifted channels use a layer-aware allocation split between Bank B and
Ft-safe Bank A. Eight additional safe Bank B pins feed the Saleae headers
without intersecting the data fanout. Mapping tests pin the approved allocation
and assert that it is unique and never includes Ft or ground pins.
Copper routing and verification exports are generated locally.
The two probe headers carry the same `0..3` and `4..7` silkscreen labels and
physical ordering as the Au1 level-shifter. The supply selector mirrors the Au1
labeling style with `NC`, `VDD`, and `3V3` opposite three `VBus` labels.

## Supply warning

The Au2 `VDD` pins carry the board input supply and may be 5–12 V. The TXB0108
high-side supply must not exceed 5.5 V. Only install the `VDD` selector jumper
when the Au2 is USB-powered or `VDD` has otherwise been verified at 5.5 V or
below. The 3.3 V selector position is safe for 3.3 V bus operation.

## Build

```bash
uv run python -m jitx build --dry src.main.AlchitryAu2LevelShifterDesign
```

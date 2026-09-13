# sd-glasgow-breakout

JITX design for a PCB that plugs into a full-size SD card socket and brings all
six SD/SDIO signals to a Glasgow Interface Explorer port. The board uses the
bottom-mounted **HCTL PM254-2-10-Z-8.5** 2x10 female socket, **LCSC C2897411**,
so it can mate directly with a Glasgow port A or B header. Align the pin-1
markers before plugging it in; this 2.54 mm connector is not keyed.

The SD edge fingers, pinout, pad centers, and inserted-card outline come from
the reusable `shared_components.full_size_sd` module. The connector footprint
and Glasgow A/B port pinout come from `shared_components.glasgow`.

## Safe voltage sensing

SD pin 4 (`VDD`) is driven by the SD host. It connects to Glasgow `SENSE`
(physical pin 1), not Glasgow `VIO` (physical pin 2). `VIO` is intentionally
left isolated so the host supply and Glasgow's programmable regulator are never
tied together. Configure Glasgow to sense and follow the host rail:

```bash
glasgow run spi-controller -V A=SA --cs A6 --sck A2 --copi A5 --cipo A1
```

For port B, use `-V B=SB` and replace the `A` pin prefixes with `B`.

## Signal map

| SD contact | SDIO / SPI role | Glasgow I/O | Glasgow physical pin |
|---:|---|---:|---:|
| 1 | `DAT3` / `CS` | `IO6` | 15 |
| 2 | `CMD` / `COPI` | `IO5` | 13 |
| 3 | `VSS1` | GND | 4, 6, 8, 10, 12, 14, 16, 18 |
| 4 | `VDD` (host 3.3 V) | `SENSE` | 1 |
| 5 | `CLK` / `SCK` | `IO2` | 7 |
| 6 | `VSS2` | GND | 4, 6, 8, 10, 12, 14, 16, 18 |
| 7 | `DAT0` / `CIPO` | `IO1` | 5 |
| 8 | `DAT1` | `IO0` | 3 |
| 9 | `DAT2` | `IO7` | 17 |

SD pin 9 (`DAT2`) is fixed to `IO7`; the other five signals use the shortest
distinct pad-to-pad assignment across `IO0..IO6`. `IO3`, `IO4`, `VIO`, and
pins 19/20 are unconnected. The six bottom-layer signal polylines were generated
with JITX's live autorouter at 0.20 mm width and clearance, then captured in the
design source for reproducible builds. The host 3.3 V-to-SENSE trace is also
routed entirely on the bottom layer, leaving the top layer free of non-ground
traces. All eight Glasgow ground
contacts and both SD ground contacts connect to board-wide ground pours on both
layers; the two SD VSS contacts have vias immediately behind their fingers.

The Glasgow port numbering and sense/VIO behavior follow the official
[revC3 technical description](https://glasgow-embedded.org/latest/revisions/revC3.html).
The selected connector dimensions and ordering details come from the
[LCSC C2897411 listing](https://www.lcsc.com/product-detail/C2897411.html).

## Fabrication notes

- Use a 1.6 mm two-layer PCB.
- Specify hard gold or ENIG on the SD fingers; hard gold is preferable for
  repeated insertions.
- Remove solder paste and solder mask from all nine fingers.
- Keep all 20 Glasgow through-hole annular rings exposed on both soldermask
  layers.
- A 30-degree bevel on the SD insertion edge is recommended when supported.
- Mount the HCTL female connector on the SD-contact side so its receptacles face
  Glasgow when the boards are stacked.

Gerbers, Excellon drills, job manifests, KiCad boards, rendered images,
and upload ZIPs are generated local outputs, not repository files.
Regenerate and verify a complete manufacturing release before fabrication.

## Build

```bash
uv sync
uv run python -m jitx build --dry --no-dependency-check src.main.SdGlasgowBreakoutDesign
```

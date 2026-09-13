# full-size-sd-ffc-breakout

JITX design for a PCB that plugs directly into a full-size SD card socket and
brings the SD bus to the RetroBus 60-pin, 0.5 mm FFC connector. The card-edge
outline and nine exposed copper fingers follow SparkFun's open-source
[SD Sniffer](https://github.com/sparkfun/SD_Sniffer) reference design. There is
no SD socket on this board. The FFC connector is mounted on the same side as
the SD contacts and rotated to keep the six SD signal routes ordered and free
of crossings. Both faces carry board-wide ground pours; the contact-side pour
clears the SD signal routing and exposed fingers. Every grounded FFC contact
and both grounded connector hold-downs have dedicated stitching vias.
The SD-contact face labels all nine SD pins with their SDIO and SPI meanings.
Those labels sit immediately behind the exposed fingers. The constant-width
FFC tail is 9 mm deep, one third of the initial 27 mm layout.

The edge-finger component, SD/SDIO/SPI pinout, global pad centers, and open
inserted-card outline now live in `shared-components/full_size_sd.py` so other
SD-shaped breakout projects can reuse the same verified geometry.

The board is passive: it does not level-shift, regulate, buffer, or terminate
the SD signals. The host socket supplies `SD_VDD`, nominally 3.3 V, on SD pin 4.

## Power-pin compatibility

FFC pin 1 is the RetroBus position named `VCC5V`. This breakout connects the SD
host's `SD_VDD` rail, nominally 3.3 V, directly to that position. The Au1/Au2
level-shifter elements tolerate receiving 3.3 V on their `VCC5V` card pin, so
this mapping can be used directly without an alternate power jumper. `SD_VDD`
remains a host-supplied 3.3 V rail; the breakout does not generate or regulate
5 V.

## Signal map

| SD contact | SDIO / SPI role | FFC physical pin | RetroBus data index |
|---:|---|---:|---:|
| 1 | `DAT3` / `CS` | 14 | 10 |
| 2 | `CMD` / `MOSI` | 24 | 18 |
| 3 | `VSS1` | all GND pins | - |
| 4 | `SD_VDD` (3.3 V) | 1 | - |
| 5 | `CLK` / `SCK` | 36 | 27 |
| 6 | `VSS2` | all GND pins | - |
| 7 | `DAT0` / `MISO` | 46 | 35 |
| 8 | `DAT1` | 56 | 43 |
| 9 | `DAT2` | 4 | 2 |

The six SD signal wires are spread almost evenly from FFC pin 4 through pin 56.
Each one borders a dedicated RetroBus ground position: pins 5, 15, 25, 35, 45,
or 55. FFC pin 1 is `SD_VDD`; every other FFC contact is tied to ground and has
its own staggered stitching via into the opposite-side plane. Both connector
hold-down pads are grounded as well.

## Fabrication notes

- Use a 1.6 mm two-layer PCB, matching the SparkFun reference construction.
- Specify hard gold or ENIG on the SD fingers; hard gold is preferable for
  repeated insertions.
- Remove solder paste and solder mask from all nine fingers.
- A 30-degree bevel on the SD insertion edge is recommended when the board
  house supports selective edge beveling.
- The two SD ground-finger vias sit immediately behind the VSS1 and VSS2 pads.
  Tent these vias and confirm socket and silkscreen clearance with the
  fabricator; the contact-side legend also sits directly behind the fingers.
- The two outside corners at the widened FFC end use a 3 mm radius.
- KiCad's generic board-edge rule flags all nine SD fingers because connector
  contacts intentionally reach the insertion edge; review these as edge-
  connector exceptions rather than moving the fingers inward.

## Build

```bash
uv sync
uv run python -m jitx build --dry --no-dependency-check src.main.FullSizeSdFfcBreakoutDesign
```

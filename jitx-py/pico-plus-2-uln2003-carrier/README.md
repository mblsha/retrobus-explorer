# Pico Plus 2 to 3x ULN2003 carrier

Two-layer carrier for a Pimoroni Pico Plus 2 and three measured ULN2003 driver
modules.

## Electrical mapping

| Driver | Pico GPIO / physical pin | ULN input |
|---|---|---|
| 1 | GP0 / 1, GP1 / 2, GP2 / 4, GP3 / 5 | IN1, IN2, IN3, IN4 |
| 2 | GP10 / 14, GP11 / 15, GP12 / 16, GP13 / 17 | IN1, IN2, IN3, IN4 |
| 3 | GP20 / 26, GP21 / 27, GP22 / 29, GP26 / 31 | IN1, IN2, IN3, IN4 |

- Driver 1/2/3 grounds include Pico physical pins 13/18/23 respectively on a
  common GND net.
- Each driver's H1 and H2 pads are bridged locally.
- H3 is 5 V from Pico physical pin 40 (`VBUS`).
- H4 is GND.

## Mechanical geometry

- Reuses the repository's standard 40-pin Pico footprint, now factored into
  `shared-components` with physical pins 1-40 exposed.
- Pico Plus 2 outline: 51 x 21 mm; row spacing: 17.78 mm.
- The carrier is continuous between the Pico header rows; there is no Pico
  underside cutout.
- ULN electrical pin drills: 1.30 mm in 2.00 mm pads.
- ULN H1-to-V1 offset: 10.7045 x 19.4094 mm. The footprint is mirrored into
  the supplied top-view orientation, with IN1-IN4 along the module's bottom
  edge and H1-H4 along its right edge.
- The carrier does not reproduce the ULN modules' four corner mounting holes.
- Every ULN position includes a rounded 25.7045 x 23.6 mm
  component-clearance cutout. Its connector-side edges preserve the supplied
  OpenSCAD template's exact 3.0 mm-wide L-shaped strip around both connector
  rows. The opposite side retains a 1.5 mm rim; the measured far/top edge has
  an additional 1.0 mm clearance and retains a 0.5 mm rim.
- The Pico is rotated 90 degrees. Driver 3 is centered above it; drivers 1 and
  2 form a centered, aligned row below it. All three input rows face the Pico,
  and each four-signal bank uses the nearest available GPIOs for mostly direct
  routing.
- Overall carrier outline: 76 x 100 mm.

The cross-connector and module-hole locations come from the supplied calibrated
photograph and retain its approximately +/-0.20 mm uncertainty. Print a 1:1
fit check before fabrication.

## Build

```bash
uv sync --extra dev
uv run python -m unittest discover -s tests
uv run ruff check .
uv run ty check .
uv run python -m jitx build --dry src.main.PicoPlus2Uln2003CarrierDesign
```

Copper routing must be generated and verified locally before fabrication.

Top silkscreen labels identify every used Pico pin (`GPx`, `GND`, or `5V`).
They are generated from the same GPIO and physical-pin mapping constants as
the nets, while each reusable ULN footprint labels all eight interface pins.

## Printable copper-tape version

The [mechanical generator](mechanical/README.md) uses CadQuery to produce a
PCB Forge-style printable substrate, companion press form, top-copper layout,
and bottom-ground copper-foil mask from the same checked-in board geometry.

```bash
uv run --extra mechanical python -m mechanical.generate_pcb_forge
```

# Full-size SD to PMOD cable adapter

This JITX board is a cable-connected variant of `sd-glasgow-breakout`. It presents a full-size SD card edge on one end and a generic 2x6, 2.54 mm through-hole PMOD header footprint on the other. It accepts straight or unshrouded right-angle male headers. Use a marked or keyed 12-wire PMOD cable and align pin 1 at both ends.

## Electrical contract

This is a **host-to-host signal adapter**, not a normal bus-powered PMOD peripheral. Use only with 3.3 V logic.

- PMOD pins 5/11 (GND) and 6/12 (VCC) are deliberately unconnected.
- SD VDD is deliberately unconnected.
- The PMOD and SD hosts must already power themselves and must share ground elsewhere.
- Never use this board to back-power either host.

All eight PMOD GPIO positions are treated as electrically fungible. A global
optimizer exhaustively evaluated all 20,160 six-of-eight assignments, first
minimizing direct-path crossings and then maximum and total direct length. The
selected public cable mapping is:

| SD contact | SPI role | PMOD pin | PMOD name |
|---|---|---:|---|
| DAT2 | — | 1 | IO1 |
| CMD | MOSI | 2 | IO2 |
| DAT3 | CS | 7 | IO5 |
| CLK | SCK | 8 | IO6 |
| DAT0 | MISO | 9 | IO7 |
| DAT1 | — | 10 | IO8 |
| VSS1/VSS2 | isolated | — | — |
| VDD | isolated | — | — |

PMOD data pins 3/IO3 and 4/IO4 are unused. All four PMOD power contacts—5/11 GND and 6/12 VCC—remain unconnected. See the [Digilent Pmod Interface Specification 1.3.1](https://digilent.com/reference/_media/reference/pmod/pmod-interface-specification-1_3_1.pdf) for the connector convention.

Both board sides label every header position with its canonical PMOD pin name;
each connected data position also carries its corresponding SD signal name on
a second line.

For right-angle mating clearance, the rear board edge stops 1.40 mm beyond the
outboard pad center: 0.60 mm beyond its copper and just 0.17 mm beyond the
nominal 5.0 mm connector body. Both PMOD label columns are kept on the inboard
side. This mechanical allowance targets ordinary unshrouded headers; verify a
shrouded or unusually deep part against its own datasheet.

## Build and render

```bash
uv sync --extra dev
uv run pytest
node ../../../jitx-tooling/tools/jitx_live.js ensure \
  --workspace "$PWD" \
  --design src.main.SdPmodBreakoutDesign \
  --fix --json
node ../../../jitx-tooling/tools/jitx_render.js render-set \
  --workspace "$PWD" \
  --design src.main.SdPmodBreakoutDesign
```

Copper routing must be generated and verified locally before fabrication.

# shared-components

Shared reusable JITX Python parts for the `jitx-py` board projects.

Included shared modules:
- `ffc`: RetroBus 60-pin FFC footprints and connector wrappers
- `hirose_df40`: reusable Hirose DF40 50-pin and 80-pin bank/control connector geometry
- `alchitry_v2`: provenance-backed Alchitry V2 Ft / Ft+ pin-usage profiles plus profile-aware Bank A / Bank B wrappers that hide reserved onboard FTDI pins from external PCB designs
- `sharp_organizer`: shared Sharp organizer-family bus connectors
- `saleae`: shared Saleae-style probe headers
- `testpads`: reusable signal and ground testpads

The Alchitry V2 usage profiles derive their reserved-pin provenance from Alchitry's primary reference:
- `https://alchitry.com/tutorials/references/pinouts-and-custom-elements/`

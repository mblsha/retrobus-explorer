# shared-components

Shared reusable JITX Python parts for the `jitx-py` board projects.

Included shared modules:
- `fabrication`: JLCPCB two- and four-layer rigid-FR4 stackups and fabrication constraints, replacing JITX's experimental sample defaults
- `ffc`: RetroBus 60-pin FFC footprints and connector wrappers
- `flex_fabrication`: JLCPCB's standard approximately 0.11 mm two-layer polyimide FPC stackup and flex-specific fabrication constraints
- `full_size_sd`: reusable full-size SD edge-finger component, SD/SDIO/SPI pinout, pad centers, and SparkFun-compatible inserted-card outline helper
- `pmod`: protocol-neutral generic 2x6 2.54 mm through-hole PMOD header footprint for straight or right-angle male headers, canonical IO1–IO8/GND/VCC numbering and roles, and physical/GPIO accessors
- `glasgow`: Glasgow A/B port pinout on the HCTL PM254-2-10-Z-8.5 2x10 female socket (LCSC C2897411)
- `hirose_df40`: reusable Hirose DF40 50-pin and 80-pin bank/control connector geometry
- `alchitry_v2`: provenance-backed Alchitry V2 Ft / Ft+ pin-usage profiles plus profile-aware Bank A / Bank B wrappers that hide reserved onboard FTDI pins from external PCB designs
- `sharp_organizer`: shared Sharp organizer-family bus connectors
- `saleae`: shared Saleae-style probe headers
- `testpads`: reusable signal and ground testpads

The Alchitry V2 usage profiles derive their reserved-pin provenance from Alchitry's primary reference:
- `https://alchitry.com/tutorials/references/pinouts-and-custom-elements/`

The fabrication defaults follow JLCPCB's published rigid-PCB capabilities and
the `JLC04161H-7628` 1.6 mm four-layer stackup:

- `https://jlcpcb.com/capabilities/Capabilities?type=1`
- `https://jlcpcb.com/impedance`

Use the paired factories in every board substrate:

```python
from shared_components.fabrication import jlcpcb_fab_constraints, jlcpcb_stackup


class MySubstrate(Substrate):
    stackup = jlcpcb_stackup(4)
    constraints = jlcpcb_fab_constraints(4)
```

Flexible boards use separate factories because the 12 µm copper, 25 µm
polyimide core, coverlay, laser-cut outline, and via limits differ from rigid
FR-4. The defaults use JLCPCB's regular 3/3 mil capability, not its discouraged
extra-cost 2/2 mil absolute limit:

- `https://jlcpcb.com/capabilities/flex-pcb-capabilities`
- `https://jlcpcb.com/resources/flexible-pcb`

```python
from shared_components.flex_fabrication import jlcpcb_flex_fab_constraints, jlcpcb_flex_stackup


class MyFlexSubstrate(Substrate):
    stackup = jlcpcb_flex_stackup(2)
    constraints = jlcpcb_flex_fab_constraints(2)
```

The stackup model does not replace manufacturing annotations for bend regions
or stiffeners. JLCPCB requires stiffener outlines, material, and thickness to
be supplied separately when exporting from EDA tools other than EasyEDA.

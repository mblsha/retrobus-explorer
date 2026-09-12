# JLCPCB manufacturing exports

These archives contain the two microSD-card-shaped emulator variants, not the
superseded socket breakout.

## Required order settings

- 2 layers, 1 oz copper
- **0.8 mm PCB thickness**
- **ENIG surface finish** for the exposed microSD fingers
- no assembly and no castellated holes
- verify the insertion fit in the target socket before ordering quantity

The nominal microSD card is 15 x 11 x 1.0 mm. This implementation uses a
widely available 0.8 mm PCB stackup; the source SparkFun sniffer pattern notes
a thinner board requirement, so socket-specific prototype fit remains a
mechanical acceptance gate.

## Archives

| Variant | Live JITX copper | Total GND stitches | Insertion-tongue stitches | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Bottom header | 6 direct routes, 0 signal vias | 99 | 21 | `ac1de629b440808fe686e5c0b2ddc9f7114cb14cb2bb5046c71a645ce861c831` |
| Top header R180 | 6 direct routes, 0 signal vias | 108 | 30 | `81b521d84eb565455522ea6be2eb74a8ad329a1c582767441e26773f3e10ee63` |

Upload:

- `microsd-pmod-emulator-bottom-header-jlcpcb.zip`
- `microsd-pmod-emulator-top-header-r180-jlcpcb.zip`

Each archive contains F/B copper, mask, paste, and silkscreen, Edge.Cuts,
Excellon drill data, drill map, and Gerber job metadata.

## Fill, stitching, and verification

Both manufacturing PCBs have full-board GND zones on `F.Cu` and `B.Cu` with
0.2 mm clearance. A dense 1.25 mm `hex-fill` lattice uses 0.6/0.3 mm stitching
vias, 0.6 mm edge clearance, and 0.15 mm additional item clearance. There is no
blanket exclusion over the 15 x 11 mm insertion tongue: every candidate via
must fit completely inside the actual overlap of the filled top and bottom GND
planes, so signal fingers, routed copper, and board-edge clearances reject
unsafe sites while the remaining tongue area is stitched densely.

Filled-board KiCad DRC reports zero errors and zero unconnected items for both
variants. The remaining warnings are only minimum text-height and generated
library-footprint-mismatch notices. Raw-versus-filled comparison reports
record zero added findings, and post-export live-JITX topology checks pass.
[Archived raw reports and hashes](../../../../gateware/docs/hardware/README.md)
preserve the original checks.

Electrical warning: microSD VDD and all PMOD VCC/GND positions are intentionally
NC. The fills are referenced only to the microSD VSS finger.

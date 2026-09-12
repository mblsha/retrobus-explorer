# microSD emulator to PMOD

This is a card-shaped microSD emulator: the 15 x 11 mm nose inserts into a
microSD host socket and the widened tail exposes a generic 2x6 PMOD header.
It does **not** carry a microSD socket.

Two board variants support either host/card orientation:

| Variant | PMOD body side | PMOD rotation | JITX signal copper |
| --- | --- | ---: | --- |
| `MicroSdPmodEmulatorDesign` | bottom | 0 degrees | 6 direct bottom routes, 0 signal vias |
| `MicroSdPmodEmulatorTopHeaderDesign` | top | 180 degrees | 6 direct bottom routes into plated through-hole pads, 0 signal vias |

The six microSD data contacts are fungible. All 20,160 complete assignments
to six of the eight PMOD GPIO positions were ranked, then the selected
zero-crossing mappings were routed and settled in live JITX:

| microSD signal | Bottom-header PMOD pin | Top-header R180 PMOD pin |
| --- | ---: | ---: |
| DAT2 | 7 / IO5 | 4 / IO4 |
| DAT3 | 8 / IO6 | 10 / IO8 |
| CMD | 9 / IO7 | 3 / IO3 |
| CLK | 3 / IO3 | 9 / IO7 |
| DAT0 | 10 / IO8 | 8 / IO6 |
| DAT1 | 4 / IO4 | 7 / IO5 |

Power isolation matches the full-size SD emulator: microSD VDD, PMOD VCC
(6/12), and PMOD GND (5/11) are intentionally NC. Only the microSD VSS finger
owns the board's stitched GND planes. This avoids directly joining the two
supplies, but does not prevent back-powering through signal pins. A verified
common ground/reference between host and FPGA is required for this direct
single-ended interface; the header alone does not provide it. The PCB has no
VDD sensing or powered-off signal isolation.

For the Arty A7-35T Spade implementation and small-image bring-up plan, see
[the gateware guide](../../gateware/projects/microsd-emulator/README.md). The photographed assembled bottom header measures with swapped rows; use
the gateware guide’s verified JD mapping for that assembly. In the nominal PCB
numbering, bottom-header CLK is on Pmod pin 3, while top-header CLK is on
pin 9; the latter is not a dedicated clock input on any Arty A7 Pmod. Both
orientations therefore need an explicit, verified clocking strategy.

The board uses a nominal 0.8 mm two-layer stackup and exposed bottom-side card
fingers. Order it with ENIG. The mechanical pattern is derived from the
[SparkFun MicroSD Sniffer](https://github.com/sparkfun/MicroSD_Sniffer); verify
fit in the intended socket before a production order.

Build either public JITX design normally:

```bash
uv run jitx build src.main.MicroSdPmodEmulatorDesign
uv run jitx build src.main.MicroSdPmodEmulatorTopHeaderDesign
```

Ready-to-upload archives and manufacturing settings are under
`manufacturing/jlcpcb/`. Raw DRC evidence is linked from that guide. These are the previously exported board revisions;
rebuilding source does not automatically refresh the manufacturing archives.

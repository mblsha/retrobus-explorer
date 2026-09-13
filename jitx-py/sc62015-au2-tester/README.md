# SC62015 Au2 tester element

This is an Au2-only cycle-accurate research fixture for the 100-pin SHARP
SC62015B02. The CPU is soldered directly to the top of the element. Five
SN74LVC16T245DGGR bus transceivers and five TXS0108EPWR auto-bidirectional
translators connect all 98 non-power CPU pins between the Au2's 3.3 V I/O and
the target-side rail.

The design deliberately does **not** support an Ft/Ft+ in the same stack. It
carries 103 FPGA-visible nets:

- 98 translated CPU signals, including the four oscillator and two reserved
  `VDISP`/`VA` pins
- five translator control signals

Au2 element pins `B46` and `B48` are the DDR3L bank's 1.35 V `D9_1V35` and
`D10_1V35` nets. The Alchitry pinout legend states the 1.35 V pins are not
3.3 V tolerant, so this design never connects them. That leaves exactly 102 usable Bank A/B
GPIOs, which carry the 98 CPU signals and four of the control nets. The fifth
control net, `E_OE`, terminates on the control connector's `LED0` pin
(element signal `L0`). The Au2 loads that FPGA pin with 330 ohm + LED to GND,
which reinforces `E_OE`'s safe-state pull-down and lights the on-board LED
whenever the E port is enabled. `LED4` would not work: the published element
library ties its `C30` pad to GND.

The CPU pins connect directly to the translators without series resistor
arrays, keeping the target-side paths short. Direction-controlled output
enables have 10-kohm safe-state pulls. The three perimeter TXS0108E banks are
always enabled, so the corresponding FPGA pins must remain high impedance
during configuration; the RESET pull-up independently holds the CPU reset.
`D[7:0]` has dedicated cycle-accurate `DIR` and `OE` controls. `E[15:0]` uses
two auto-bidirectional byte translators, allowing each FPGA I/O cell to sense,
drive, or release its E pin independently. The fixed CPU-output banks are
permanently enabled toward the FPGA; their direction cannot drive the CPU.

## Spacious Au2 geometry

The reusable `Sc62015B02` component now accepts an
`include_body_cutout` geometry option. It defaults to `True`, preserving the
opening used when the footprint is an interposer over an existing processor.
This tester instantiates it with `include_body_cutout=False`, because the CPU
is soldered directly to this PCB. The generated board therefore has no central
opening. The canonical Au2 mounting holes are suppressed; four GND-connected
plated mounting holes instead sit 5 mm in from the adapter board's own corners.
Each has a 2.2 mm finished drill inside a 3.6 mm copper pad with solder-mask
openings expanded 0.05 mm beyond the copper on both sides. Each corner is
marked `GND` on both silkscreen faces.

The board is 90 × 72 mm. Placement and owner-relative decoupling geometry
are defined in `src/physical.py`; selected signal/channel/Au2 connections are
in `src/assignment.py`. `src/pinmap.py` validates the final safe GPIO pool
and clock restrictions. CPU-sourced DCLK, ACLK, X1, and X3 use clock-capable
P pins; FPGA-driven X2 and X4 use ordinary GPIOs.

## E-port correction

The current `mblsha/binja-esr` register and instruction definitions identify
`EOL` (`F3h`) and `EOH` (`F4h`) as output buffers for all `E0-E15` pins, and
`EIL` (`F5h`) and `EIH` (`F6h`) as input buffers for those same pins. The ISA
also permits direct internal-memory writes and per-bit logical changes to the
two output bytes. Therefore the PC-E500 service manual's input/output labels
describe that product's use of each pin; they are not fixed SC62015 package
directions.

The TXS0108E does not use a shared `DIR` signal, so mixed input/output use
within either E-port byte remains observable. Its specified open-drain data
rate is 1.2 Mbps. At the PC-E500's 2.304-MHz CPU clock, the fastest documented
three-cycle internal-memory write can change an E output at no more than
768 ktransitions/s. Characterization above the standard clock must account for
the translator's lower open-drain speed limit. The Au2 side is the TXS0108E
`VCCA` domain at 3.3 V and the CPU side is the Au2-provided 5 V target rail,
which satisfies TI's `VCCA <= VCCB` requirement.

## Direct Au2 power

The target rail connects directly to all eight Au2 control-connector `VCC`
contacts in the local element model. It powers the SC62015 VCC pin and every
level translator B side, so the CPU is on whenever the Au2 supplies that rail.
There is no separate target-power connector, switch, or link. A dedicated
10-uF 0805 capacitor provides bulk decoupling near the CPU, and TP1 exposes
the resulting 5 V rail.

Alchitry's public pinout calls this board-power rail `VDD`: it is 5 V when the
Au2 is USB-powered, but it can follow a 5-12 V external board-power input. This
tester must therefore be used only when that connector rail is 5.0 V. Do not
apply an Au2 external supply above 5.5 V while the tester is installed; doing
so would overvoltage the SC62015 and the translators.

The PC-E500 service manual identifies `VCC` and `GND` as the CPU's power pins
and specifies a 5 V system supply. It identifies `VDD` as a display-converter
control output, not a supply, and lists `VDISP` and `VA` as reserved. `VDD`,
`VDISP`, and `VA` remain high-impedance translated signals with test pads.
Confirm the SC62015B02 donor-board voltage before installing it; there is no
intervening regulator or disconnect.

## Reset startup state

The current `binja-esr` `SSR.RSF` definition identifies a high level on the
SC62015 `RESET` pin as the reset-start condition. A 10-kohm target-side pull-up
therefore holds RESET asserted as soon as the Au2 5 V rail is present,
including while the FPGA is unconfigured. RESET now passes through an
always-enabled TXS0108E channel.

To start the CPU, configure the FPGA's `RESET` pin as a low output. Driving it
high later reasserts hardware reset; releasing it also lets the target-side
pull-up reassert reset. The pull-up draws 0.5 mA when RESET is held low from
the 5 V target rail.

The oscillator pins are translated as digital research signals: X1/X3 are
observed and X2/X4 are driven. When reproducing the original resonator circuit,
keep the FPGA-side X2/X4 pins high impedance—the south TXS0108E has no separate
disable control—and validate the analog oscillator requirements first.

## Direction controls

For SN74LVC16T245, `DIR=0` means CPU/B to FPGA/A and `DIR=1` means FPGA/A to
CPU/B. All `OE_N` controls are active low. The direct controls are
`CTRL_OE_N`, `KEY_OE_N`, `D_OE_N`, `D_DIR`, and `E_OE`.
`CTRL_OE_N` now controls the reserved empty half of U4; no CPU signal depends
on it after IRQ moved to U9. The two south TXS0108Es and U8 are enabled
directly from V3V3. `E_OE` is
active high and enables the two E-port TXS0108E devices; its 10-kohm pull-down
keeps the complete E port disconnected during FPGA configuration.

The board retains the translator safe-state resistors required to define the
control inputs before FPGA configuration: 10-kohm pull-ups on the three
active-low `OE_N` signals, a 10-kohm pull-down on `E_OE`, and a 100-kohm
pull-down on `D_DIR`. These are control pulls, not CPU-signal series
resistors. `E_OE`'s pull sits beside the control connector because that net
now terminates on the Au2 `LED0` pin, whose 330 ohm + LED load to GND also
holds the net low while the FPGA is unconfigured.

When changing a dynamic bank, disable `OE_N`, wait at least 20-30 ns, change
`DIR` and preload data, then enable the bank.

## Decoupling

Every physical translator supply-pin site now owns a source-derived 100-nF
0402 capacitor. Each SN74LVC16T245 has four sites because VCCA and VCCB each
appear at two separated package pins; each TXS0108E has two sites. Capacitor
pad 1 faces its supply pin and pad 2 faces outward toward ground. The cluster
is calculated in the translator's local frame, so a
translator move or rotation cannot leave its capacitors at stale absolute
coordinates. The 10-uF target bulk part remains separate in 0805.
The two VCCA and two VCCB pins on every 48-pin translator are also distinct
logical JITX ports, so each physical supply pin can receive its own ordinary
source-level `Route`. Those route declarations intentionally omit sketches,
leaving final copper geometry to JITX.

## Project status

The JITX circuit, static 98-signal assignment, component footprints,
four-layer substrate, and spacious placement are maintained directly in
`src/`. The design uses ordinary public JITX construction APIs; development
automation and generated routing evidence are intentionally maintained outside
this project.

Source tests do not qualify routed copper or hardware. Generate and verify
routing and fabrication outputs before building a board.

Build and verify with:

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ty check
uv run jitx build src.main.Sc62015Au2TesterDesign
```

## Design references

- [SHARP PC-E500 service manual](https://manualzz.com/doc/6409473/sharp-pc-e500-calculator-service-manual)
- [mblsha/binja-esr SC62015 register and instruction definitions](https://github.com/mblsha/binja-esr/tree/6e311bb3c87c2e83fa3b83a4b11599900c6eed10/sc62015)
- [TI SN74LVC16T245 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc16t245.pdf)
- [TI TXS0108E datasheet](https://www.ti.com/lit/ds/symlink/txs0108e.pdf)
- [Alchitry Au2 element pinout](https://alchitry.com/tutorials/references/pinouts-and-custom-elements/)

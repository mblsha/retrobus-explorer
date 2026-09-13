# Printable PCB and press form

`generate_pcb_forge.py` turns the complete routed carrier into a parametric
CadQuery implementation of [PCB Forge's copper-tape pressing
method](https://castpixel.itch.io/pcb-forge). It produces:

- `pcb-forge/pico-plus-2-uln2003-forge-pcb-base.stl`: the 76 x 100 x 1.6 mm
  printable PCB substrate, including all three ULN component openings, 64
  connector holes, 23 GND stitching-via holes, and 0.30 mm-deep top-copper
  channels;
- `pcb-forge/pico-plus-2-uln2003-forge-press-form.stl`: the 4 mm companion
  press with 0.25 mm relief, 0.15 mm total lateral clearance, and tapered
  alignment/punching spikes;
- `pcb-forge/pico-plus-2-uln2003-forge-top-layout.svg`: a real-size inspection
  drawing of the top signal and 5 V copper;
- `pcb-forge/pico-plus-2-uln2003-front-ground-foil-mask.svg`: a real-size
  cutting mask for the front GND fill, with clearance around every other net;
  and
- `pcb-forge/pico-plus-2-uln2003-bottom-ground-foil-mask.svg`: a real-size
  cutting mask for the continuous bottom GND foil, including antipads around
  every non-GND connector hole.

The bottom of the printed PCB is intentionally flat. A second molded copper
face would leave a 0.30 mm-deep cavity against the print bed and make this
large, thin part impractical to print flat. Instead, cut a single bottom copper
foil sheet with the supplied mask and adhere it to the flat underside. The
three Pico GND pins and three driver GND pins remain connected to that plane;
all other holes have 0.25 mm electrical clearance from their pad edge. Apply
the matching front foil around the recessed signal/5 V copper, then join the
two GND faces through the 0.8 mm stitching holes with wire or eyelets.

Regenerate the complete set with:

```bash
uv run --extra mechanical python -m mechanical.generate_pcb_forge
```

The CadQuery source is the editable model. Add `--include-step` only when STEP
copies are useful; they are large because the press contains the complete
rounded trace and pad relief.

Suggested fabrication sequence:

1. Print the PCB channel-side up. Print the press with its relief and spikes
   facing up. The press relief is pre-mirrored: flip it left-to-right around
   its long vertical centerline before mating it to the PCB. Start at 100%
   scale.
2. Cover the PCB top with copper tape that has conductive adhesive. Overlap
   strips where needed, as in PCB Forge.
3. Align the press by its spikes and clamp it evenly to push the tape into the
   recessed pads and traces.
4. Remove the press and sand only the PCB's top lands until copper remains in
   the channels but is removed between nets.
5. Cut the bottom GND foil using the supplied SVG, adhere it to the flat
   underside, and verify every signal/5 V/H1-H2 hole has a clear antipad.
6. Insert and solder the connectors: signals, 5 V, and H1-H2 on top; GND on
   the bottom plane. Check isolation and continuity before fitting the Pico or
   ULN2003 modules.

Default dimensions can be changed from the command line; run
`uv run --extra mechanical python -m mechanical.generate_pcb_forge --help` for the complete list.

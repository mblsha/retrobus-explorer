# JITX Python Migration Plan

This plan is grounded in the current Stanza code under `jitx/` and in the working Python JITX project structure used in `~/src/jitx/ld2450-radar-adapter`.

## Goal

Port the PCB/component definitions in `~/src/jitx/retrobus-explorer/jitx` from Stanza to Python JITX in a way that:

- preserves the existing board designs and connector pin mappings
- keeps KiCad export working through the current `jitx-tooling` flow
- avoids a direct 1:1 transliteration where Stanza depends on `ocdb/...` helpers that do not map cleanly to the Python style we are already using
- gives us a staged path with early end-to-end wins before touching the highest-risk boards

## Current Progress

Merged progress as of `2026-04-12`:

- the new Python JITX surface now lives under `jitx-py/`
- six migrated boards now live there:
  - `jitx-py/pin-tester/`
  - `jitx-py/sharp-pc-g850-bus/`
  - `jitx-py/rpi-pico-40-pin-adapter/`
  - `jitx-py/saleae-dslab-adapter/`
  - `jitx-py/espi-debug-breakout/`
  - `jitx-py/sharp-organizer-card/`
- the obsolete top-level `saleae-dslab-adapter-py/` tree has now been removed, so the Python migration surface is consolidated under `jitx-py/`
- the merged board entry points are now buildable as:
  - `src.main.PinTesterDesign`
  - `src.main.SharpPcG850BusDesign`
  - `src.main.RpiPico40PinAdapterDesign`
  - `src.main.SaleaeDslabAdapterDesign`
  - `src.main.EspiDebugBreakoutDesign`
  - `src.main.SharpOrganizerCardDesign`
- the first required shared Python component set now exists in working form:
  - `FFCConnector`
  - `_0_5K-1_2X-60PWB`
  - `PCG850Bus`
  - shared `GndTestpads`
  - the generic headers needed by `pin-tester`
- Python CI now treats `py/` and `jitx-py/` as the two repo-level Python roots
- `jitx-tooling` now includes `tools/compare_kicad_gold.py` for KiCad-vs-KiCad parity checks, including copper-geometry placement matching and blank-reference KiCad footprint handling

Current status of `pin-tester`:

- board outline, connector placement, power-net naming, pin labeling, and corner GND probe holes are in good shape
- the board now uses the shared corner PTH GND testpad component rather than one-sided circular SMD pads
- JITX-side ground pours were intentionally removed; planes should be added later in KiCad/post-process tooling
- connector-placement parity is now checked by realized copper geometry rather than KiCad footprint instance angle

Known remaining parity gaps for `pin-tester` if we want stricter than functional equivalence:

- `VCC` copper topology still differs from the archived Stanza route summary
- some KiCad artifact structure still differs even where the physical geometry is acceptable

Current status of `sharp-pc-g850-bus`:

- the board is now merged and buildable as `src.main.SharpPcG850BusDesign`
- the custom `PCG850Bus` connector geometry now matches the archived KiCad placement by realized copper geometry
- the board uses the shared PTH `GndTestpads` component from current Stanza source rather than the older dual-side SMD corner testpads found in the archived gold KiCad
- live JITX routing on the signal set works cleanly on top copper
- JITX-side ground pours are intentionally omitted here too; planes should be added later in KiCad/post-process tooling

Known remaining parity gaps for `sharp-pc-g850-bus` if we want stricter than functional equivalence:

- `GND-DATA0` still differs from the archived KiCad because the archived board uses the older SMD corner probe pads while current source uses the newer shared PTH corner component
- exported KiCad copper still differs from the archived routed board because live ws routing is not being serialized back into the exported `.kicad_pcb`

Current status of `rpi-pico-40-pin-adapter`:

- the board now exists in `jitx-py/rpi-pico-40-pin-adapter/` and builds as `src.main.RpiPico40PinAdapterDesign`
- connector placement parity against the archived KiCad board is clean by realized copper geometry
- net membership parity against the archived KiCad board is clean; there are no remaining current-only or gold-only net signatures
- the root `jitx-py/run-ruff.sh` and `jitx-py/run-ty.sh` flows both pass with the new child project included
- JITX-side ground pours are intentionally omitted here too; planes should be added later in KiCad/post-process tooling

Known remaining parity gaps for `rpi-pico-40-pin-adapter` if we want stricter than functional equivalence:

- exported KiCad copper still differs from the archived routed board because live ws routing is not being serialized back into the exported `.kicad_pcb`
- the current gold compare reports copper-summary mismatches on the routed BCM nets for that reason even though placement and net membership are at parity

Current status of `saleae-dslab-adapter`:

- the board now exists in `jitx-py/saleae-dslab-adapter/` and builds as `src.main.SaleaeDslabAdapterDesign`
- connector placement parity against the archived KiCad board is clean by realized copper geometry
- net membership parity against the archived KiCad board is clean; there are no current-only or gold-only net signatures
- live JITX routing on the eight Saleae signal nets works cleanly on bottom copper
- after live routing and export, `tools/compare_kicad_gold.py` now reports a full `PASS` against the archived KiCad reference
- that full KiCad-vs-gold `PASS` has now been re-verified from the committed `jitx-py/saleae-dslab-adapter/` project state
- the old standalone `saleae-dslab-adapter-py/` project has been deleted now that the `jitx-py/` port is the canonical version
- JITX-side ground pours are intentionally omitted here too; planes should be added later in KiCad/post-process tooling

Known remaining parity gaps for `saleae-dslab-adapter` if we want stricter than functional equivalence:

- the current version is at practical KiCad parity with the archived reference; only date-string drift should be expected over time


Current status of `espi-debug-breakout`:

- the board now exists in `jitx-py/espi-debug-breakout/` and builds as `src.main.EspiDebugBreakoutDesign`
- connector placement parity against the archived KiCad board is clean by realized copper geometry
- net membership parity against the archived KiCad board is clean; there are no remaining current-only or gold-only net signatures
- live top-layer routing now works for the VCC net and the eight eSPI signal nets
- JITX-side ground pours are intentionally omitted here too; planes and stitching should be added later in KiCad/post-process tooling

Known remaining parity gaps for `espi-debug-breakout` if we want stricter than functional equivalence:

- exported KiCad copper still differs from the archived routed board on `GND` and six routed eSPI nets
- the remaining mismatch is route-shape/topology parity, not connector placement or net membership

Current status of `sharp-organizer-card`:

- the board now exists in `jitx-py/sharp-organizer-card/` and builds as `src.main.SharpOrganizerCardDesign`
- connector placement parity against the archived KiCad board is clean by realized copper geometry
- net membership parity against the archived KiCad board is clean; there are no current-only or gold-only net signatures
- the custom organizer connector family is now ported in working form via `JC20-C45S-F1-A1` / `sharp-organizer-component` semantics
- live JITX routing now works cleanly for the 44 non-GND organizer signal nets on top copper
- JITX-side ground pours are intentionally omitted here too; planes and stitching should be added later in KiCad/post-process tooling

Known remaining parity gaps for `sharp-organizer-card` if we want stricter than functional equivalence:

- exported KiCad copper still differs from the archived routed board because the live ws routing is not being serialized back into the exported `.kicad_pcb`
- the remaining mismatch is route-shape/topology parity, not connector placement or net membership

## Golden Output Reference

We now have a concrete reference archive at `/tmp/kicad.zip`. This should be treated as the primary migration target for exported outputs.

What the archive contains:

- Stanza-generated KiCad project exports for many boards
- Gerber zip bundles for multiple revisions of several boards
- a mix of current and historical revisions, including some `-old` directories and duplicate gerber zips
- a small amount of archive noise such as `__MACOSX/` entries and `.DS_Store` files

This means the migration should not be judged only by whether the Python port builds. It should be judged by how closely the Python-generated KiCad and Gerber outputs match these archived Stanza outputs.

### Canonical Reference Targets

The archive is broad, but the cleanest initial golden references appear to be:

- `kicad/pin-tester/`
- `kicad/sharp-pc-g850-bus/`
- `kicad/rpi-pico-40-pin-adapter/`
- `kicad/sharp-organizer-card/`
- `kicad/sharp-organizer-host/`
- `kicad/sharp-pc-e500-ram-card/`
- `kicad/sharp-sc61860-interposer/`
- `kicad/sharp-sc62015-interposer/`
- `kicad/saleae-dslab-adapter/`
- `kicad/espi-debug-breakout/`
- `kicad/alchitry-level-shifter-au1-v2/` for the newer level-shifter reference

Historical references still matter, but should be treated as secondary unless we explicitly decide to target them:

- `kicad/alchitry-level-shifter/`
- `kicad/alchitry-level-shifter-au1-v2-old/`
- `kicad/sharp-sc62015-interposer-old/`

## Output Parity Standard

For each migrated board, the Python port should be compared against the Stanza-generated reference export at three levels:

1. Design structure parity
- board outline dimensions and corner radii
- connector count and placement
- reference designator set
- named nets / pin mappings

2. KiCad PCB parity
- footprint selection or equivalent landpattern geometry
- pad counts, ordering, drill sizes, and key pad dimensions
- board text / silkscreen placement where intentionally preserved
- copper layer count and obvious pours
- overall bounding box and component placement relationships

3. Gerber parity
- same exported layer set
- same board outline
- same drill count and general drill map
- close copper/silkscreen/mask geometry

The goal is not byte-for-byte identity. The goal is manufacturing-equivalent output that is visually and structurally close to the Stanza result.

## Audit of `/tmp/kicad.zip`

Important findings from the archive:

- the archive contains reference KiCad PCBs for nearly all of the top-level Stanza boards we care about
- several boards also include zipped gerber outputs either inside the board directory or as top-level `gerber-*.zip` files
- `alchitry-level-shifter-au1-v2/` also includes `F_Paste` and `B_Paste` SVG exports, which may be useful later for stencil-style parity checks
- multiple revisions exist for some boards, especially organizer-card, level-shifter, and interposer work
- because of those duplicates, we should explicitly record which archived revision is the target before porting each board

## Migration Rule Change

The original migration plan focused on porting order and buildability. The archive changes the standard:

- every completed Python board should produce a KiCad export and a Gerber export
- those outputs should be diffed against the chosen Stanza reference before the port is considered complete
- if the Python board diverges intentionally from the Stanza version, that deviation should be recorded explicitly

## Current Surface Area

### Shared infrastructure

- `helpers.stanza`
- `pose-helpers.stanza`
- `stackups/`

### Reusable components

Representative component files under `components/`:

- `AlchitryAu.stanza`
- `FFCConnector.stanza`
- `FPGAHeader.stanza`
- `GndTestpads.stanza`
- `HED40LP03BK.stanza`
- `JC20-C45S-F1-A1.stanza`
- `JUSHUO/AFA01-S10FCA-00.stanza`
- `LevelShifter.stanza`
- `PCG850Bus.stanza`
- `RPiPico.stanza`
- `Saleae.stanza`
- `SC61860D4x.stanza`
- `SC62015B02.stanza`
- `SharpOrganizerHostDBZ.stanza`
- `TXB0108PWR.stanza`
- `TXS0108EQPWRQ1.stanza`
- `VccSelectHeader.stanza`
- `_0_5K-1_2X-60PWB.stanza`

### Top-level board designs

- `alchitry-au1-level-shifter.stanza`
- `espi-debug-breakout.stanza`
- `pin-tester.stanza`
- `rpi-pico-40-pin-adapter.stanza`
- `saleae-dslab-adapter.stanza`
- `sharp-organizer-card.stanza`
- `sharp-organizer-host.stanza`
- `sharp-pc-e500-ram-card.stanza`
- `sharp-pc-g850-bus.stanza`
- `sharp-sc61860-interposer.stanza`
- `sharp-sc62015-interposer.stanza`

## Audit Summary

### Shared bootstrap

`helpers.stanza` is the main design bootstrap. It currently owns:

- board setup
- stackup selection
- rule selection
- BOM setup
- part-query defaults
- KiCad export defaults

This should become a small Python helper module, not a huge compatibility layer.

### Utility code

`pose-helpers.stanza` contains helper routines for:

- pin ordering by physical location
- pad pose lookup
- pad type lookup
- net naming / lookup helpers

Some of this may be unnecessary in Python for the first porting wave. It should be ported only when a board actually needs it.

### Low-risk component patterns

These files are mostly wrappers or straightforward modules and are good early port targets:

- `FFCConnector.stanza`
- `GndTestpads.stanza`
- `VccSelectHeader.stanza`
- `Saleae.stanza`
- `FPGAHeader.stanza`

### Medium-risk component patterns

These are custom connectors or parts with nontrivial pin naming or landpatterns:

- `PCG850Bus.stanza`
- `RPiPico.stanza`
- `SharpOrganizerHostDBZ.stanza`
- `HED40LP03BK.stanza`
- `JC20-C45S-F1-A1.stanza`
- `JUSHUO/AFA01-S10FCA-00.stanza`

### High-risk component patterns

These are the real custom-landpattern / platform-enabling files:

- `AlchitryAu.stanza`
- `SC61860D4x.stanza`
- `SC62015B02.stanza`
- `_0_5K-1_2X-60PWB.stanza`
- `TXB0108PWR.stanza`
- `TXS0108EQPWRQ1.stanza`
- `LevelShifter.stanza`

### Low-risk full-board ports

These should be the first complete boards we port because they validate the workflow with limited geometry risk:

- `pin-tester.stanza`
- `sharp-pc-g850-bus.stanza`
- `rpi-pico-40-pin-adapter.stanza`

### Highest-risk board

`alchitry-au1-level-shifter.stanza` is the highest-risk and should not be first.

Reasons:

- depends on `AlchitryAu`
- depends on `FFCConnector`
- depends on `LevelShifter`
- includes repeated placement / mapping logic
- includes board text and custom power selection wiring
- is central enough that mistakes here will compound quickly

## Main Porting Constraint

The largest difficulty is not Stanza syntax. It is replacement of Stanza/OCDB helper usage.

The Stanza code uses helpers such as:

- `ocdb/utils/box-symbol`
- `ocdb/utils/generic-components`
- `ocdb/utils/landpatterns`
- `ocdb/artwork/board-text/text`
- cookbook-style placement / pose helpers

The Python style already proven in `ld2450-radar-adapter` is much more explicit and self-contained. The migration should follow that style instead of trying to preserve every helper abstraction.

## Recommended Python Project Shape

Inside `retrobus-explorer`, use `jitx-py/` as the Python JITX root. Each migrated board should live in its own child project:

- `jitx-py/<board>/pyproject.toml`
- `jitx-py/<board>/main.py`
- `jitx-py/<board>/src/`
- `jitx-py/<board>/.vscode/` as needed
- shared repo-level CI rooted at `jitx-py/`

This is now the direction already in use for `jitx-py/pin-tester/`. The existing Stanza tree stays as reference during the migration.

## Phased Migration Plan

### Phase 0: Project scaffold

Use `~/src/jitx/ld2450-radar-adapter` as the template and create a working Python JITX project structure in `retrobus-explorer`.

Deliverables:

- root `main.py`
- package directory for hardware modules
- VS Code JITX files
- buildable placeholder design

### Phase 1: Shared bootstrap

Port only the minimum useful subset of `helpers.stanza`:

- `setup_design()` equivalent
- KiCad export defaults
- board/rules defaults for rigid boards
- optional board text/date helper

Do not try to port all BOM/query behavior at first unless Python JITX actually needs it for these designs.

### Phase 2: First reusable components

Port the smallest components that unlock several boards:

- `FFCConnector`
- `GndTestpads`
- `VccSelectHeader`
- `Saleae`

This is the lowest-friction foundation layer.

### Phase 3: First end-to-end board

Port `pin-tester.stanza` first.

Why:

- simple board outline
- repeated headers
- one FFC-based mapping path
- board text
- good validation of the overall Python design pattern

Success criteria:

- Python build works
- KiCad export works
- Gerber export works
- board can be inspected with current `jitx-tooling`
- output is compared against the Stanza reference in `/tmp/kicad.zip`
- any remaining differences are understood and recorded as either acceptable or still open

### Phase 4: First connector-driven adapter

Port `PCG850Bus` and then `sharp-pc-g850-bus.stanza`.

Why:

- validates a custom bus connector
- reuses the already ported FFC path
- has straightforward mapping logic
- still much simpler than the Alchitry board
- has a clean archived KiCad reference to compare against

### Phase 5: Level shifter platform pieces

Port the platform-enabling parts in this order:

1. `TXB0108PWR`
2. `LevelShifter`
3. `AlchitryAu`
4. `alchitry-au1-level-shifter`

This sequence keeps the high-risk board until after all major dependencies exist and have been exercised elsewhere.

### Phase 6: Remaining adapters and interposers

Once the platform parts are stable, port the remaining boards:

- `sharp-organizer-card`
- `sharp-organizer-host`
- `sharp-pc-e500-ram-card`
- `sharp-sc61860-interposer`
- `sharp-sc62015-interposer`
- `espi-debug-breakout`

### Phase 7: Flex stackups and advanced rules

Only after the rigid-board path is stable, port:

- `stackups/materials-flex.stanza`
- `stackups/vias-flex.stanza`
- `stackups/rules-flex.stanza`
- `stackups/JLC-Flex-2L.stanza`

These are valid migration targets, but they should not be on the critical path for the first successful Python boards.

## Proposed Initial Port Order

Recommended order of actual implementation:

1. scaffold Python hardware package
2. port minimal `helpers`
3. port `FFCConnector`
4. port `GndTestpads`
5. port `VccSelectHeader`
6. port `Saleae`
7. port `pin-tester`
8. port `PCG850Bus`
9. port `sharp-pc-g850-bus`
10. port `TXB0108PWR`
11. port `LevelShifter`
12. port `AlchitryAu`
13. port `alchitry-au1-level-shifter`
14. port remaining adapters/interposers
15. port flex stackups

## Immediate Grounding Milestone

The first three grounding milestones have effectively been reached:

- `jitx-py/pin-tester/` exists, builds, and exports
- `jitx-py/sharp-pc-g850-bus/` exists, builds, and exports
- `jitx-py/rpi-pico-40-pin-adapter/` now exists, builds, and exports
- `jitx-py/saleae-dslab-adapter/` now exists, builds, exports, and matches the archived KiCad reference
- `jitx-py/espi-debug-breakout/` now exists, builds, exports, and matches the archived KiCad reference structurally; only copper-topology parity remains
- `jitx-py/sharp-organizer-card/` now exists, builds, exports, and matches the archived KiCad reference structurally; only copper-topology parity remains
- the required first-wave connector/component ports now exist in working form
- KiCad export works through `jitx-tooling`
- the boards can be compared against archived Stanza KiCad output with `tools/compare_kicad_gold.py`

The next milestone should be:

- build on the first organizer-family board by porting the matching host-side board and shared organizer connector surface
- use `sharp-organizer-host` as that next board

## Practical Notes

- Do not attempt a mechanical transliteration of every Stanza helper into Python.
- Prefer explicit Python component definitions and explicit placement logic.
- Keep Stanza files as reference until the equivalent Python design builds and exports successfully.
- Use one board as a porting harness at a time; avoid partially porting many boards in parallel.
- Reuse the current `jitx-tooling` scripts for build/export/render/status checks as soon as each Python board is alive.
- Do not model ground planes in JITX unless there is a strong reason; prefer adding pours and stitching later at the KiCad/post-process stage for faster JITX iteration.

## Recommended Next Step

Use `pin-tester`, `sharp-pc-g850-bus`, `rpi-pico-40-pin-adapter`, `saleae-dslab-adapter`, `espi-debug-breakout`, and `sharp-organizer-card` as the reference harnesses, but move the implementation focus to `sharp-organizer-host` as the next full board port.

## Board-by-Board Acceptance Workflow

For each board we port, use this workflow:

1. Choose the canonical archived reference directory or gerber zip from `/tmp/kicad.zip`.
2. Build the Python JITX design.
3. Export KiCad from Python JITX.
4. Export Gerbers from the Python JITX KiCad output.
5. Compare against the archived Stanza reference:
   - board dimensions
   - component placements
   - footprint geometry and drills
   - silkscreen and board text
   - copper layers and pours
   - Gerber layer set and obvious visual differences
6. Record any intentional deviations before calling the port complete.

## Updated Recommended Starting Sequence

Given the existence of `/tmp/kicad.zip`, the practical starting order should be:

1. `pin-tester`
2. `sharp-pc-g850-bus`
3. `rpi-pico-40-pin-adapter`
4. `saleae-dslab-adapter`
5. `espi-debug-breakout`
6. `sharp-organizer-card`
7. `sharp-organizer-host`
8. `sharp-pc-e500-ram-card`
9. `sharp-sc61860-interposer`
10. `sharp-sc62015-interposer`
11. `alchitry-au1-level-shifter`

This order is now preferred not just because of technical risk, but because these boards have concrete archived outputs that can be used as migration acceptance tests.

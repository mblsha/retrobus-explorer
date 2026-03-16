# saleae-dslab-adapter-py

Minimal Python-based JITX migration scaffold for the legacy
`jitx/saleae-dslab-adapter.stanza` design.

## What was migrated

- Board outline intent: 25 mm x 12 mm rounded rectangle
- Main connectivity intent:
  - Two Saleae 2x4 probe headers grouped as an 8-channel connector bank
  - Two 1.27 mm 2x4 DSLogic/DSLab headers
  - Ground bussed across both sides
  - Channel mapping preserved as `0-3 -> left header`, `4-7 -> right header`
- Relative placement intent from the legacy design:
  - Saleae connector bank centered and rotated on the board bottom
  - DSLogic headers placed left/right on the board bottom
- VS Code JITX task scaffolding using `uv run`

Legacy files inspected during the scaffold:

- `jitx/saleae-dslab-adapter.stanza`
- `jitx/helpers.stanza`
- `jitx/components/Saleae.stanza`
- `jitx/pose-helpers.stanza`

## What remains legacy or unported

- Exact legacy JLCPCB setup from `helpers.stanza`
  - The Python scaffold currently uses `jitx.sample.SampleDesign` substrate/fab defaults.
- Exact custom DSLab footprint geometry
  - The legacy design used a hand-written 1.27 mm footprint and explicit pad/mask sizing.
  - This scaffold currently uses a generic through-hole header generator at the correct pitch and pin mapping.
- Saleae silkscreen numbering and dynamic date label text
- Any CAD export artifacts from the Stanza flow
- Legacy helper/export commands such as `view-board()`, `view-schematic()`, and `export-to-cad()`

## Key dependencies and components

Python dependencies:

- `jitx`
- `jitxlib-standard`
- `jitxlib-parts`
- `jitxexamples-components`

Project-local components:

- `saleae_dslab_adapter.components.SignalGroundHeader2x4`
- `saleae_dslab_adapter.components.SaleaeProbeHeader2x4`
- `saleae_dslab_adapter.components.DSLabFemaleHeader2x4`
- `saleae_dslab_adapter.main.SaleaeConnectorBank`
- `saleae_dslab_adapter.main.SaleaeDSLabAdapter`

## Open and run in VS Code JITX

1. Open `/home/mblsha/src/jitx/retrobus-explorer/saleae-dslab-adapter-py` in VS Code.
2. Create the environment with `uv sync`.
3. Select the interpreter at `.venv/bin/python` if VS Code does not pick it automatically.
4. Open the JITX extension.
5. Run the build task:
   - `Run saleae_dslab_adapter.main.SaleaeDSLabAdapter`

Equivalent command line build:

```bash
uv run python -m jitx build saleae_dslab_adapter.main.SaleaeDSLabAdapter --port <jitx-port>
```

Dry-run validation without the JITX websocket server:

```bash
uv run python -m jitx build --dry saleae_dslab_adapter.main.SaleaeDSLabAdapter
```

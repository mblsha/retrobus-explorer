# saleae-dslab-adapter

Python JITX port scaffold for the legacy `jitx/saleae-dslab-adapter.stanza`
board.

Current goals:

- preserve the Stanza connectivity and placement intent
- preserve the `25.0 mm x 12.0 mm` rounded board outline
- preserve the Saleae `8x2` probe header bank and the two DSLab `1.27 mm`
  `2x4` female headers
- keep JITX-side geometry explicit while leaving copper pours to
  KiCad/post-process tooling

## Run

```bash
cd /home/mblsha/src/jitx/retrobus-explorer/jitx-py/saleae-dslab-adapter
uv sync
uv run python -m jitx build --dry src.main.SaleaeDslabAdapterDesign
```

# pin-tester-py

First Python JITX port scaffold for the legacy `jitx/pin-tester.stanza` board.

Current goals:

- preserve the Stanza connectivity and placement intent
- preserve the 50 mm x 40 mm rounded board outline
- preserve the six `2x8` data headers, two `2x4` power headers, 60-pin FFC,
  signal test pad, and GND corner test pads
- use a 4-layer sample stackup so the board can carry the same full-board GND
  pours as the archived KiCad reference

This is the initial grounding port. It is intentionally self-contained under a
small dedicated JITX Python subproject so it can be built and compared against
the archived Stanza KiCad exports before a wider repo-level package layout is
locked in.

## Run

```bash
cd /home/mblsha/src/jitx/retrobus-explorer/pin-tester-py
uv sync
uv run python -m jitx build --dry pin_tester.main.PinTesterDesign
```

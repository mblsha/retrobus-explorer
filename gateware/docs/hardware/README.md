# Qualified hardware evidence

The measured JD pinout remains in [the pinout report](gkd-arty-jd-pinout-2026-09-07.md).
The Arty A7-35T SD-only qualification used 256 MiB DDR3, a requested 13 MHz
SD clock (12,913,043 Hz actual), and nextpnr 0.9.4 with the negative-edge patch.
Full-memory BIST, three complete SD readbacks, 512 mixed updates and FAT16
checks passed without controller reinitialization. Reads measured 4.261–4.277 MB/s
and writes 4.543 MB/s. Fabric/DDR timing estimates were 106.62/80.80 MHz.

Qualified bitstream SHA-256:
`f17bb7a5c60b467dae1c19712f55b2edbd0d1d806b11c8d1583b4122280f2ef0`.
This records prior hardware qualification, not a new hardware run for this PR.

Both manufactured PCB variants had zero filled-board DRC errors and zero
unconnected items; fill added no findings. Warnings were text-height and
generated footprint-library mismatch notices. Post-export topology checks passed.
The [manufacturing archives and their hashes](../../../jitx-py/microsd-pmod-breakout/manufacturing/jlcpcb/README.md)
remain in this branch.

## Raw records

The original records are preserved at commit `eb557e22f8f2cb21f0bfaefe6714137f34d9fd40`,
retained by the `codex/arty-microsd-evidence` archive branch. Links below use the
immutable commit, so later source cleanup cannot change their contents.

| Record | SHA-256 |
| --- | --- |
| [arty-nextpnr-0.9.4-timing-refactor-2026-09-10.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/gateware/docs/hardware/arty-nextpnr-0.9.4-timing-refactor-2026-09-10.json) | `7cffeabfe90c23b38f9528968052ee008e9471f3db636a356ef4c2efe542292f` |
| [emulator-bottom.filled-drc.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-bottom.filled-drc.json) | `2e6edc094852b65ff1bf7f4f78ea5ac1f64af7f74cbd0c6d8a274437476977f4` |
| [emulator-bottom.gnd-fill.drc-diff.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-bottom.gnd-fill.drc-diff.json) | `f2b350700001cb767ea5727f22941448c3706d1c81caf15b9b474e26142d4a34` |
| [emulator-bottom.raw-drc.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-bottom.raw-drc.json) | `e26255f3cdf88e170131796b6c3c42eacfadf3e77d5e4cafb1dc26627d2b89b1` |
| [emulator-bottom.topology-continuity.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-bottom.topology-continuity.json) | `eb20f4f61cdf92beec519077a12558af892ea90d4acae706114e0c0721d10ccf` |
| [emulator-top.filled-drc.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-top.filled-drc.json) | `640d018debdbedf6410afc08633ecbbcaf2850f4dcffc0e7f95fa35d6b0d24bb` |
| [emulator-top.gnd-fill.drc-diff.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-top.gnd-fill.drc-diff.json) | `755eed8a3e896f38faef228e83e040cb23ba47811119810cc650981e668454a1` |
| [emulator-top.raw-drc.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-top.raw-drc.json) | `619d9cecf2c71c682ade3f8a3f72bd70f533b18794706724fd2de195790faee7` |
| [emulator-top.topology-continuity.json](https://github.com/mblsha/retrobus-explorer/blob/eb557e22f8f2cb21f0bfaefe6714137f34d9fd40/jitx-py/microsd-pmod-breakout/verification/emulator-top.topology-continuity.json) | `90c81556eb7ce97ef1b07180d6f0cef8dcab54136227465cec758356e89887ec` |

The historical mapping search recorded SHA-256 identifiers
`165ca88c1986bf63e14639bda5ad679d3f64fa23510b492b782cab3410027ee7`
(bottom) and `3c9dcf15a74e1d2dd39a2259fb427a3ec857f8f7ad2a3092657fe4a7256f2151`
(top). These describe search provenance; physical correctness is checked against
explicit pin maps and measured continuity, not copies of these identifiers.

## Cleanup build verification (2026-09-13)

The fixed DDR build was compared with the previous qualified-mode generator
from `54452cb` using the same local dependencies. Generated DDR logic matched
excluding comments, and the BIOS ROM matched byte-for-byte. The explicit board
wrapper and XDC also matched the prior hardware build byte-for-byte (wrapper
SHA-256 `88689e843e08c461828efed3e02f8e75734b9572f5f5ebd3e55779ac54b302a3`).
Both manufacturing ZIP hashes above remain unchanged.

A fresh seed-8 build passed the negative-edge probe, all clock checks
(106.62 MHz / 100 MHz SD fabric; 80.80 MHz / 80 MHz DDR), six CDC checks,
five direct-output checks, and a 604397-bit configuration-frame round trip.
Its bitstream SHA-256 was
`a530cfdc4099d7ad1f66a925e02a213029c5c3c005679e79b559dfe1edb03202`.
The local nextpnr 0.9.4 copy was relinked to its original Boost 1.90 libraries
after a Homebrew upgrade; its timing patch was unchanged. This was build and
simulation validation only; the new image was not programmed or hardware-qualified.

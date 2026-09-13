# Qualification provenance

The current PR is an integration with the reviewed SD/DDR implementation.
It has not been programmed or requalified on hardware. Historical results below
apply only to the explicitly identified older bitstreams, not to a fresh build.

## Current integration, 2026-09-13

All six Ethernet Spade/Verilator configurations passed, including the complete
SD write/readback and stalled-write ownership test. Sixteen host/benchmark
unit tests pass normally and under optimized Python; all 33 DDR support tests
pass. Ethernet header validation and native address validation now have
explicit register stages before dispatch; the SD/DDR implementations are reused.

A fresh synthesis with local Yosys 0.68+ and patched nextpnr-xilinx 0.9.4 passed,
but timing remains open. Seed 4 encountered a routing failure. With the same
synthesized design, seed 2 reached 97.59 MHz fabric / 83.44 MHz DDR and seed 6
reached 99.38 MHz fabric / 85.33 MHz DDR. The requirements remain 100 MHz and
80 MHz respectively; they have not been relaxed. Both MII clock domains and
the IDELAY clock passed in seed 6. Its 18 Gray-pointer crossing checks and all
five direct SD output checks passed.

No success manifest or new programming image was published. These checks do
not qualify the current image for hardware, and the attached Arty/GKD card was
not reprogrammed or modified during this PR's validation.

## Bulk-read image, 2026-09-09

Bitstream SHA-256:
`7f8a21dad8f7640e431d3fbb15c032c8f80f0ffbd6d9094842fd962afd7ae89a`

Setup: Arty A7-35T; JD bottom-header adapter with common ground; GKD external
SD host at 12,913,043 Hz actual, four-bit; direct AX88179B 100 Mbps full duplex.
Placement seed 4 passed 100 MHz fabric and 80 MHz DDR timing; 18 registered
Gray-pointer crossings passed the routed-delay check.

- Three 4 MiB downloads, window 10: 90.32–91.38 Mbps validated image payload.
- Complete 256 MiB Ethernet download: 90.70 Mbps, 23.68 seconds, 20 recovered
  requests, hash matched the independently SD-written pattern.
- After host-client cleanup, another complete read: 90.54 Mbps, 23.72 seconds,
  17 recovered requests, SHA-256
  `89858a9d846127d37009eb9ef53554d90e7aa8ed0581f696f31586bb8b62d1e0`.
- Full 256 MiB SD write, three full readbacks, and 512 mixed updates passed
  with zero controller errors or unexpected kernel messages.
- Odd-LBA and final-sector Ethernet checks passed; concurrent ping: 300/300.

The calculated downstream wire use was about 99 Mbps, including framing.
This was not a direct wire capture. Window 16 increased retries and reduced
throughput. Writes remain single-sector ordered operations; these download
rates do not describe uploads.

These results are transcribed from the local development archive at commit
`f993db1be03baefa37b5dc3eac61ffe2704d5625`, file
`gateware/docs/hardware/arty-ethernet-bulk-2026-09-09.json`.
That archive is not part of this PR; generated reports and bitstreams are not
copied into the source tree.

## Earlier cross-interface qualification

Bitstream SHA-256:
`7523d5a909da1e442e8939b3326a372f22f3095fde9ec448c002bfa98053548f`

A 64 KiB Ethernet upload and complete readback, 4 KiB SD modification, and
Ethernet download matched the expected bytes. Full-memory SD stress and FAT16
write/rename/delete/remount/fsck checks passed. Armed network writes and
conflicting retries were rejected; identical retries recovered lost replies.

The same local archive contains the cross-interface record at
`gateware/docs/hardware/arty-ethernet-sd-2026-09-09.json`.

## Requalifying a new image

Record the new `result.json` and bitstream hash, then follow the README's
small-image round trip and the DDR guide's full-memory and filesystem checks.
Measure bulk downloads only after safe detachment/disarm, with an independent
expected image hash. Retain retry counts and MMC qualification output, and
restore arm/bind/clock settings afterward. Never attribute these historical
measurements to a changed bitstream without repeating the hardware checks.

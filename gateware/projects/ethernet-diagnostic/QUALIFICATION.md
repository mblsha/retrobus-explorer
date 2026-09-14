# Qualification provenance

## Review revision, 2026-09-14

The functional source at `f3bbd19` adds client recovery/verification guards,
intended-domain and two-stage CDC validation, named protocol states, and
per-PHY-clock reset release. It has **not been programmed or requalified on
hardware**. The measurements below remain attached to `805c5f7`; they are not
measurements of this revision.

Local validation includes 25 host tests and 20 CDC-fixture tests, each normally
and under `python -O`. All six Ethernet Spade/Verilator configurations pass
(12 test cases), including cached errors, sequence wrap, memory-error
completion, clock-phase/reset cases, and accepted SD reads and writes draining
across DISARM. Six manifest tests and five direct-output timing tests also pass
under optimized Python. Packet builders and SD/DDR behavioral peers moved into
test-support modules; their independent protocol construction is retained.

The full fast-SD suite passed 45 cases across 27 configurations; the ordinary
SD read/write/busy tests passed six cases across three configurations. All 43
DDR support tests passed. Ruff and project inventory checks passed.

The normal patched-nextpnr 0.9.4 builder passed with seed 12: fabric
108.96/100 MHz, DDR 85.30/80 MHz, and both MII and IDELAY clocks passed.
All 18 Gray-pointer checks, five direct SD output checks, FIFO register-storage
checks, negative-edge preflight, and bitstream round-trip verification passed.
A repeated synthesis produced the identical netlist. The earlier seed-4 attempt
failed fabric timing at 86.10 MHz and correctly published no success manifest;
the documented Ethernet command now uses seed 12.

Unprogrammed build bitstream SHA-256:
`9543d005769dc189a36954044be7003cee3da6a87ca2aaf7df3b140cca31a2ee`

The round trip verified 675,769 configuration bits. Generated artifacts remain
local, outside Git.

The host verification marker certifies only the initial upload. It is not a
hardware interlock and does not prevent subsequent legitimate SD writes.
PHY clocks must run during the held reset interval; see the reset boundary in
the README. Digital reset tests do not model metastability.

## Hardware-qualified integration, 2026-09-14

Hardware qualification used the implementation at `805c5f7` on an Arty A7-35T,
JD bottom-header adapter with common ground, and the GKD external SD host at
12,913,043 Hz actual, four-bit. The AX88179B negotiated 100 Mbps full duplex.

Programmed bitstream SHA-256:
`a0e0b2bc5069a6ad743efd48dd867911aaea7e5a9665224c09fec1393f32735f`

The normal builder repeated seed 4 with an identical synthesized netlist,
FASM, frames, and 670,797 decoded configuration bits. Its bitstream SHA-256 was
`939c6e5b83b14bf64e17e3c92085a36bc220c6cb6674e748908d2ff4f61db176`;
the only four differing bytes were in the `.bit` timestamp header. The decoded
configuration listing SHA-256 was
`b84553ae8415f6414515b87a62975add45dcfaa5247c6745d822e731fb1a2084`.

Build: local Yosys 0.68+ and patched nextpnr-xilinx 0.9.4, seed 4. The combined
build uses ABC9 register-aware mapping and the shared native-DDR register
stage. Fabric timing reached 103.61 MHz against 100 MHz; DDR reached 83.47 MHz
against 80 MHz. Both 25 MHz MII domains and 200 MHz IDELAY passed. All 18
registered Gray-pointer crossings, five direct SD output checks, native FIFO
register-storage checks, and bitstream round-trip verification passed.

- All six Ethernet Spade/Verilator configurations passed, including SD
  read/write and stalled-write ownership. Sixteen host/benchmark tests passed
  normally and under optimized Python; all 33 DDR support tests passed.
- A 64 KiB Ethernet upload/readback, 4 KiB SD modification, and Ethernet
  download matched byte-for-byte. Armed Ethernet reads and writes returned
  refusal status 4. Unwritten neighboring and final DDR pages stayed unchanged.
- Full 256 MiB SD write: 58.87 seconds. Three complete readbacks took
  63.15, 63.36, and 63.43 seconds. Two rounds of 256 random updates and their
  neighboring-block checks passed. MMC error counters stayed zero, with no
  recovery or unexpected kernel messages. Concurrent ping: 300/300 replies.
- Full 256 MiB Ethernet download: 23.91 seconds, 89.83 Mbps validated payload,
  seven recovered requests. Its hash matched the independently generated SD
  pattern: `89858a9d846127d37009eb9ef53554d90e7aa8ed0581f696f31586bb8b62d1e0`.
- Three 4 MiB bulk reads, window 10: 89.25, 90.84, and 90.84 Mbps, with
  two, one, and one recovered requests. Odd-LBA and final-sector reads passed.
- FAT16 format, write/rename/delete, read-only remount/hash checks, and
  `fsck.fat -n` passed. The filesystem was unmounted afterward.

The original 256 MiB image was backed up before programming and restored after
qualification. Complete SD and Ethernet readbacks matched the backup. Restoring
the partition table produced the expected `mmcblk1: p1` discovery message, which
the strict raw-transfer monitor flagged; an additional full read-only
qualification then passed with zero errors and no new kernel messages. The card
was left armed, bound to the GKD at the settings above, and unmounted.

The installed nextpnr binary on the qualification Mac was linked against Boost
1.90. Its build invocation needed
`DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib` because the current
Homebrew default was 1.92; this was scoped to the command, not set globally.

These are measured application payload rates; recovered UDP requests are
included in elapsed time. They do not describe upload throughput. Generated
build outputs, raw images, and test logs are retained locally, not in Git.

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

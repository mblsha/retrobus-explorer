# Arty USB TTY retest — 2026-10-01

## Artifact and scope

Observed from 08:05:27 to 08:05:41 UTC on the connected Arty A7-35T and
RG35XX Plus microSD-Pmod bench, with Ethernet disconnected and target PSU2
OFF. The FPGA was already running the qualified combined bitstream:

`c2561a978724c9bbcf69659d3f3b5515d0ea089c73fee0fb16043e3b91393bf7`

This checks the host timeout fix against that artifact. It does not qualify
the subsequent INFO mux or console-activation source changes, a new
bitstream, a TTY upload, or another RG35XX boot.

## Procedure and results

Under `lab lease --device anbernic-rg35xx-plus --sd-emulator`, use the revised
`scripts.images.Images` with `build_manifest=<candidate>/result.json`.
For direct FTDI, TTY, then direct FTDI again: read INFO 100 times, read the
first 256 sectors with `bulk_download(256, window=1)`, and read sector 524287.
Require an initialized, disarmed, quiescent card before reads and no retries.
Use the existing session only for independent BULK_READ tokens; create no
journal and issue no ordered request, upload, ARM, or FPGA reload.

| Backend | Prefix bytes | Whole probe elapsed | Retries |
| --- | ---: | ---: | ---: |
| Direct FTDI before | 131072 | 2.200 s | 0 |
| macOS TTY, fixed 5 ms read timeout | 131072 | 2.253 s | 0 |
| Direct FTDI after | 131072 | 2.192 s | 0 |

Every reply passed the existing framing, identity and CRC checks. All three
prefixes had SHA-256
`9eedf809ffdba14c72924561c785de5aae22f777697ee5418670c2b20e19a524`.
Sector 524287 matched the SHA-256 of a zero-filled 512-byte sector.
INFO remained unchanged, including sequence, cache, written prefix and ARM.

Keeping the TTY timeout fixed removes the receive path's repeated pySerial
terminal reconfiguration. This successful retest supports that explanation
for the earlier corruption; it is not a controlled comparison against the
old host code. The elapsed times include INFO queries and the last-sector
probe, so they are not standalone transfer-throughput measurements.

## End state

The lab read channel 1 as P906, online and output OFF before and after the
probe; setpoints remained 5.0 V and 1.2 A. Final INFO showed the FPGA disarmed
and quiescent. The existing volatile Linux image remained in DDR. Both leases
were released; PSU1 was untouched. Raw reports and readbacks remain private.

# Au1 card probe bring-up — 2026-10-05

The Au1 was found on USB with FTDI serial `FT4ZS6I3` and JTAG IDCODE
`0x0362d093` (Artix-7 35T). The initial read-only Spade/nextpnr bitstream was
`build/nextpnr-au1/design.bit`, SHA-256
`a5996811675413ec9d01b9781325dcbc649bd3533d4bc56c286904096cafad8a`.
It was loaded into FPGA SRAM with `openFPGALoader -b alchitry_au
--ftdi-serial FT4ZS6I3 -m`. This is volatile; a power cycle needs a reload.
The Au1 USB-UART was `/dev/cu.usbserial-FT4ZS6I31` and `identify` returned
`OBP2`.

Before any outputs were enabled, twelve snapshots over 0.6 seconds were
identical: address `0xF17C1`, data `0xAA`, control `0xFD`, protected `0x7B`,
both output-enable masks zero, and disarmed. Those were undriven bus levels,
not card content.

The inserted card is marked **IQ-704B**. A single read at address zero using
idle control `0xff`, active control `0x7d`, and control mask `0xff` returned
`0x10`. The next 64 bytes matched on two host-timed passes and contained
`thesaurus` in the header. A 64-byte FPGA burst with 5 µs idle/setup and 5 µs
selected phases matched that slow image exactly, including its SHA-256
`72a7d60d707ae4f529b32b2956bc5a10ea882713cc6a0382c76824d9a9b6309c`.

A full 20-bit address scan (1 MiB) matched on two burst passes. Its SHA-256 is
`240c7a6a22a9e375c26d675e65be13217ef2a73d50cf65b95e458ddd668d8bf5`.
Four consecutive 256 KiB windows were byte-identical. The first window was
saved as `build/iq704b_256k.bin`, SHA-256
`488aad27af5666746b27fb7db262f5a07bbc6b65e82b4ab70cb3242df1c70759`.
The 64 KiB range `0x10000–0x1ffff` in each window read as `0xff` throughout;
the other ranges contain varied data. This establishes a 256 KiB *observed
address period*, not an independent measurement of the physical ROM capacity.

The two-pass raw scan is `build/iq704b_full_20bit.bin`; each binary has an
adjacent JSON manifest. All files in `build/` are generated and ignored by Git.
The generic named-bank tool also produced `build/iq704b-attributed/` using the
checked-in `plans/iq704b-eprom.json`; its two-pass 256 KiB image has the same
SHA-256 as the earlier image. Its manifest binds the image to the exact plan
hash and records the observed active control and protected pin states.
The read profile keeps RW high, asserts OE and EPROM low for the selected
phase, and never drives data or VPP. The bitstream releases all driven pins
after each burst and on reset, `Z`, or watchdog expiry.

## OZ-707 Basic card

After the powered-down card swap, the Au1 still identified as `OBP2`; an
input-only snapshot showed both output-enable masks zero. The card is marked
OZ-707. Its [operation manual](https://www.wass.net/othermanuals/Sharp%20OZ-707.pdf)
lists a 128 KiB system ROM and battery-backed program/data memory.

Read-only 256-byte discovery samples used RW high, OE low, and one low select
at a time, with other selects high. EPROM returned a header containing `Basic`;
SRAM2 returned one containing `DATA    BAS`. MSKROM and SRAM1 each returned a
constant `0xa5` over the sampled range, so neither was used as an image bank.
The discovery plan and its raw samples are retained in ignored `build/`.

The checked-in `plans/oz707-eprom-sram2.json` drives EPROM low for a 128 KiB
ROM read and SRAM2 low for a separate 32 KiB RAM read. Both ranges matched on
two FPGA-timed passes. The attributed bundle is `build/oz707-attributed/`:

| Bank | Length | SHA-256 |
| --- | ---: | --- |
| `basic_rom` | 131,072 bytes | `a8a1afb91bf39f07f528a9690a60d45c6cc61232a126fb0fe1ccff95ec112d9d` |
| `basic_sram2` | 32,768 bytes | `7696709926e45a3af54e583f03e0bb6f1ea54fc626890529aa548b9948a7dad1` |

Read-only 256-byte spot checks above the captured ranges matched the first
256 bytes of their respective images: EPROM at `0x20000`, `0x40000`, and
`0x80000`; SRAM2 at `0x08000`, `0x10000`, `0x20000`, and `0x80000`. These
checks support address mirroring but do not establish every higher byte.

`manifest.json` and the per-bank sidecars record commanded electrical levels,
the live active-cycle snapshots, addresses, pass count, hashes, and the exact
source-plan hash. The SRAM image is a snapshot of this particular card's
battery-backed contents, not a generic blank RAM image. The bundle is generated
and ignored by Git.

## OBP3 SRAM write qualification — 2026-10-05

Before enabling data-bus output, a fresh read of the inserted OZ-707 captured
128 KiB EPROM and 32 KiB SRAM2 on two matching passes. The SRAM image SHA-256
was `7696709926e45a3af54e583f03e0bb6f1ea54fc626890529aa548b9948a7dad1`.
The capture is committed in `binja-esr-tests` as `cccdbc2` at
`roms/cards/sharp-organizer/20261004T234306Z/`.

The bounded OBP3 write bitstream was built with Spade and nextpnr-xilinx seed 2.
It passed the 100 MHz timing target at 100.46 MHz and the Project X-Ray
bitstream decode check. The bitstream SHA-256 is
`7c32b4e24bee9d8b3360cc186bce88421ebd9c250b71d14b94b88358c7b4666c`.
The Au1 identified as `OBP3` after volatile SRAM loading.

`dump-card` selected the OZ-707 plan automatically and produced the same ROM
and SRAM hashes. The write test confirmed the entire live SRAM still matched
the committed backup before any write. At SRAM2 address `0x7fff`, it changed
`0x9f` to `0xc5` and read back `0xc5`. It then restored `0x9f`; a two-pass
32 KiB post-restore read had the exact pre-write SHA-256. Raw before/after
images and the result JSON are under `build/oz707-sram-write-test-20261005/`.

## UART read throughput — 2026-10-05

Read-only EPROM benchmarks on the connected OZ-707 used the same OBP3 bitstream,
1 Mbaud UART, and 5 µs setup plus 5 µs selected read phases. Every 128 KiB
pass matched the committed ROM image byte for byte. The timings include host
unlock/release commands but exclude device opening and archival work.

| UART request size | Requests per 128 KiB | Elapsed | Effective rate |
| ---: | ---: | ---: | ---: |
| 4 KiB | 32 | 2.88 s | 44.4 KiB/s |
| 16 KiB | 8 | 1.70 s | 75.5 KiB/s |
| 32 KiB | 4 | 1.50 s | 85.3 KiB/s |
| 65,535 bytes | 3 | 1.45 s | 88.2 KiB/s |

The host now uses 32 KiB requests by default. This keeps the card cycle
unchanged and makes a 1 MiB scan approximately 12 seconds per pass, or 24
seconds for two passes, if the larger address range behaves like this ROM.

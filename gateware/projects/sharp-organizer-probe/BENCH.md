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
The fresh backup was committed before the write trial.

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

With 32 KiB requests, a later full 1 MiB scan at this 1 Mbaud/5 µs setting
took 26.6 seconds for two passes, including device and file overhead.

## Faster UART and read-cycle experiment — 2026-10-05

A two-pass 1 MiB EPROM baseline at 1 Mbaud, 5 µs phases, and 32 KiB requests
took 26.6 seconds end to end. Its SHA-256 was
`af5b0cfe5370f79e16dcb2d6439bc573289d992a56723f13c67b1cbb859dae14`;
all eight 128 KiB windows matched the separately archived OZ-707 ROM.

The project-local 4 Mbaud variant, built with Spade and nextpnr seed 2, met
the 100 MHz FPGA target at 105.59 MHz. Two 128 KiB ROM passes matched at every
read phase tested from 2000 ns down to 200 ns. At 1000 ns, three full 1 MiB
passes matched the baseline in 12.2 seconds; three full SRAM2 passes matched
the committed SRAM image at both 1000 ns and 200 ns. The 4 Mbaud bitstream
SHA-256 was `da547118af92aad49658e831e5fe1d6522153a6bf36e59bc04b619358601fc99`.

The selected 5 Mbaud variant uses an exact 20-cycle UART bit period at
100 MHz. It passed Cocotb tests and nextpnr timing at 100.84 MHz with seed 3;
its bitstream SHA-256 is
`39371387652ecbd5c87536925df3493bcc0e310cb1255395c08038908ed05f61`.
At 500 ns read phases, the normal card capture matched the archived 128 KiB
ROM and 32 KiB SRAM2 on three passes each. A 16-pass 1 MiB stress run using
32 KiB UART requests matched the baseline in 50.5 seconds. With 65,535-byte
requests, 16 passes matched in 42.3 seconds and a further 32 passes matched
in 84.8 seconds. That is 48 MiB checked at the selected request size with no
byte mismatch or timeout, about 2.65 seconds per MiB pass. A normal two-pass
ROM/SRAM2 card capture completed in 2.0 seconds. These results qualify this
OZ-707 and connected bench, not every card or USB adapter.

The host requested 8 Mbaud in a separate variant; its 12-cycle FPGA bit
period at 100 MHz is about 8.33 Mbaud. Seed 2 passed timing at 100.87 MHz.
Short ROM and SRAM2 reads matched, and one 16-pass 1 MiB run with 32 KiB
requests completed. A 65,535-byte stress run then lost 3,813 bytes in a
response during pass 13. An otherwise equivalent rebuilt bitstream lost
bytes during pass 7 even with 32 KiB requests. The serial adapter then
returned continuous zero bytes, including with the original 1 Mbaud probe
bitstream, until a software USB-device reset restored it. The 8 Mbaud link
was therefore rejected despite its faster short-run results.

A 10 Mbaud variant passed simulation but missed the required 100 MHz FPGA
clock after routing with nextpnr seeds 2, 3, and 4 (96.01, 89.89, and
95.17 MHz respectively). It was not loaded onto the Au1.

## OBP4 generic discovery and SRAM qualification — 2026-10-05

OBP4 keeps the 5 Mbaud read protocol and adds CI/E2 state to the bounded `W`
configuration byte. The seed-2 Spade/nextpnr-xilinx build passed the 100 MHz
target at 102.28 MHz and the bitstream decode check. Its bitstream SHA-256 is
`c8729120bda58dcbc5d8e2a940add9de9e6b03a72712c42943b8367def476a30`.
The Au1 identified as `OBP4` after the volatile load.

With the OZ-707 still inserted, the read-only discovery scanned all 16
single-select CI/E2 states over 1 MiB at the conservative 5 µs read phase.
Two passes matched in each view. Deduplication produced three images: 128 KiB
EPROM (`a8a1afb9…112d9d`), 32 KiB SRAM2
(`76967099…a7dad1`), and a one-byte bus-echo image for SRAM1/MSKROM views.
The EPROM and SRAM2 hashes exactly match the previously archived OZ-707
images. All four CI/E2 states expose identical EPROM and SRAM2 data; all
SRAM1 and MSKROM states track bus hold in the priming test. The full capture
was committed before any OBP4 write probe.

The automatic probe then skipped SRAM1 and tested two addresses in each of
the four SRAM2 CI/E2 views. Each trial persisted after priming the data bus
from EPROM, was visible through the other three SRAM2 views, and restored to
the committed backup. Full 32 KiB checks passed for every view after each
trial. The four SRAM2 views therefore form one confirmed physical alias group.
The result is committed as `8a8707b`.

The general `write-sram` command changed SRAM2 `0x7fff` from `0x9f` to
`0xc5`, verified the full bank, and committed its before/after images as
`a19ea8e`. A second transaction used that committed post-write image as its
expected state, restored `0x9f`, and verified the original 32 KiB SHA-256
`7696709926e45a3af54e583f03e0bb6f1ea54fc626890529aa548b9948a7dad1`.
The restore transaction is committed as `d3fa389`. A final bus snapshot
showed zero address/control drive masks and disarmed state.

## PA-7C18 speed experiments — 2026-10-05

A conservative PA-7C18 capture scanned all 16 single-select CI/E2 views over
1 MiB on two passes, at 5 Mbaud, 5 µs phases and 8 KiB requests. Including
backup commits and reversible SRAM probes it took 509.5 seconds. The unique
memory data was 32 KiB MSKROM and 8 KiB SRAM2; each repeated throughout its
full 1 MiB scan in all four CI/E2 states. EPROM and SRAM1 tracked bus priming.

The read-only benchmark compared whole ROM/SRAM images at 5000, 1000, 500,
and 200 ns against that committed capture. Every short qualification matched.
Each completed throughput case then checked 4 MiB: two full 1 MiB mirror
passes for both ROM and SRAM, comparing every byte against the backup.

| Baud | Phase | Request bytes | Elapsed for 4 MiB | KiB/s | Recovered short reads |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5,000,000 | 5000 ns | 65,535 | 44.093 s | 92.9 | 0 |
| 5,000,000 | 1000 ns | 32,768 | 12.598 s | 325.1 | 0 |
| 5,000,000 | 1000 ns | 65,535 | 10.636 s | 385.1 | 0 |
| 5,000,000 | 500 ns | 8,192 | 24.683 s | 165.9 | 0 |
| 5,000,000 | 500 ns | 32,768 | 15.834 s | 258.7 | 3 |
| 5,000,000 | 500 ns | 65,535 | 11.781 s | 347.7 | 1 |
| 4,000,000 | 1000 ns | 65,535 | 12.764 s | 320.9 | 0 |
| 4,000,000 | 500 ns | 65,535 | 13.877 s | 295.2 | 1 |
| 4,000,000 | 200 ns | 65,535 | 12.793 s | 320.2 | 0 |

At 5 Mbaud/200 ns the long benchmark stalled after a recovered short read.
A subsequent complete capture at 5 Mbaud/1000 ns also stalled in view 11,
after three recovered short reads. Neither failed discovery was published,
committed as a backup, or used for writes. The link then returned zero bytes
until a USB reset targeted only the Au1's FTDI serial restored it; a parked
snapshot was verified afterward. These results reject the 5 Mbaud fast
profile for this bench despite its successful short benchmark. Delivered
bytes matched the backup; the experiment does not isolate whether the
transport failure originates in FPGA UART, USB bridge, driver, or host.

The 4 Mbaud OBP4 variant passed all four Cocotb tests. Nextpnr seeds 2–6
missed the 100 MHz target; seed 7 passed at 102.29 MHz. The bitstream decoded
51,391 configuration bits and its SHA-256 is
`2554ffe371f91a97ed1ed5c5d34906e2d78162d86268516649e248a172e4bab4`.
All complete ROM/SRAM images matched at each tested phase. Shorter phases
provided no throughput gain; the 1 µs profile was chosen for the full capture.

The UART path has a one-byte read pipeline. UART transmission overlaps the next card read and gates progress
when busy. At 4 Mbaud, 8N1 has a 400,000 byte/s payload ceiling; the observed
320.9 KiB/s is about 82% of it. A block buffer would support retained chunks
and retransmission but cannot increase sustained UART bandwidth. FPGA
hashing/comparison could reduce duplicate traffic in a future protocol.

Complete 4 Mbaud/1000 ns captures also failed: the 65,535-byte run stalled
in view 11 after 82.65 seconds, and the 32 KiB run stalled in view 6 after
48.66 seconds. Neither produced an archival capture or reached a write probe.
Thus the short 4 MiB benchmarks do not qualify sustained UART capture.

A first project-local libftdi prototype incorrectly treated status-only USB
packets as the end of a UART response. Its apparent short reads are invalid
transport evidence. The implementation now reuses the existing
`ethernet-diagnostic` backend, which continues reading those packets until
the requested byte count or deadline.

The mature backend's complete 4 Mbaud/1000 ns UART capture still failed in
view 13 after 83.42 seconds, with a final 64,430/65,535-byte response after
two retries. Completed memory scans matched their references. This was a
real short UART response, unlike the rejected prototype's false EOF result.
No backup was published and no write probe ran. Direct libftdi alone did not
qualify sustained high-rate UART capture.

## OBP5 buffered FT600 qualification — 2026-10-05

The connected element was confirmed as Ft/F1 v1 for Au1. It enumerated as an
FT600 with serial `000000000001` and SuperSpeed flag set. Its existing
configuration was read, not changed: 100 MHz FIFO clock, FT245 mode, one
bidirectional channel. The level shifter mapping leaves the Ft pins available.
The implementation reuses `au_ft_tap_u16`, its shared asynchronous FIFO/vendor
HDL, the repository's D3XX bindings, and the existing direct-UART backend.

The initial FT prototype lost or malformed words, and a trial with
falling-edge output registers returned no payload. Buffering entire chunks
alone still gave 8,262/16,382 bytes in an 8 KiB SRAM request. Those variants
were rejected. The final connector wrapper drives the fixed `0xa5` upper byte
and both byte enables as constants; the FIFO carries sampled low bytes.
With this change, both complete SRAM passes, all timing qualifications and the
complete capture passed the exact word count, marker and memory checks.
The experiment does not isolate the cause of the earlier metadata failures.

OBP5 command `F` buffers at most 8,191 sampled card bytes in the shared
8,192-word FIFO. The card is released before the FT clock consumes the chunk.
USB backpressure then retains data without leaving card outputs enabled.
UART remains at 4 Mbaud for commands and acknowledgements. FT reads are not
automatically replayed; failures abort and a new operation parks and drains
stale payload before reading. Generic card timing remains 5 µs.

The seed-7 Spade/nextpnr build passed both 100 MHz clocks: core 109.15 MHz,
FT 161.73 MHz. The bitstream decode checked 60,679 configuration bits;
SHA-256 `934e925600aef6da99aa0b6a573b23171d58222f774ce6749b9db409a53e4be5`.
All six Cocotb tests passed, including the full 8,191-word blocked-USB test
and release before transmission. All 34 host tests passed.

After the earlier USB reconnect, a new two-pass 5 µs SRAM read differed from
the original snapshot. It was committed before any write probe. No SRAM
writes had run between the original capture and this read; the cause of the
change was not isolated. The current 8 KiB SRAM SHA-256 is
`3599e39805600f5e088832b10d523a6e6eda49f4347b3a4519d959f02c532e91`.
All subsequent SRAM qualifications compare against this current snapshot.
The ROM still matches the original 32 KiB image, SHA-256
`d276e259045216fc6f93b7939ec7fabfc12d000f9b427cd10c863166400fa8d6`.

Each timing first checked two complete canonical ROM/SRAM passes, then two
full 1 MiB mirrored passes for each memory (4 MiB per row). Every byte matched
the committed references, including the conservative 5 µs full mirror check.

| FT read phase | Chunk bytes | Elapsed for 4 MiB | KiB/s | Retries |
| ---: | ---: | ---: | ---: | ---: |
| 5000 ns | 8191 | 43.138 s | 95.0 | 0 |
| 1000 ns | 8191 | 10.494 s | 390.3 | 0 |
| 500 ns | 8191 | 6.446 s | 635.4 | 0 |
| 200 ns | 8191 | 2.590 s | 1581.7 | 0 |

The successful full capture used 200 ns phases: all 16 views, two full 1 MiB
passes each (32 MiB total), committed backup, eight SRAM presence outcomes,
and reversible write/restore trials finished in **33.192 seconds**. No framing
error, timeout or retry occurred. All four MSKROM views match the conservative
ROM and all four SRAM2 views match the current committed SRAM snapshot.
EPROM and SRAM1 still track bus priming; their retained one-byte echo differs
from the earlier echo value and is not a memory image. Two trials in each
SRAM2 view confirmed the four-view physical alias group and restored every
8 KiB image. A separate two-pass 5 µs read again matched current SRAM exactly.

This is about 15.4 times faster than the 509.5-second conservative capture.
One full 1 MiB pass at 200 ns took 0.59–0.68 seconds in the benchmark.
The 1.54 MiB/s effective payload exceeds the UART ceiling by a factor of 4.05;
USB-UART is therefore no longer the payload bottleneck. Card cycles, chunk
command overhead and host work remain. The run does not measure the maximum
FT600 USB throughput, qualify other cards, or cover card-specific bank
registers. The final probe is parked with zero drive masks and 5 µs timing.

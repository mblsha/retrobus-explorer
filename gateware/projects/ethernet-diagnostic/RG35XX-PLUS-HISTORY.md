# RG35XX Plus SD boot from the emulator: chronological record

The Arty A7-35T microSD-Pmod emulator boots an Anbernic RG35XX Plus. The H700
loads its SPL, U-Boot, kernel and device tree from FPGA DDR over the Pmod
adapter, and the booted kernel drives the emulated card itself. The target has
no serial header populated, so the card is also the only debug channel.

What follows is the record of how the boot got where it is, in the order it
happened, kept because the route explains why several decisions are what they
are. It is not instructions, and it is not the current state: a number of the
sections below state a conclusion that a later section corrects, and they name
tools and options that were since renamed or removed.

Where this file differs from [RG35XX-PLUS-FINDINGS.md](RG35XX-PLUS-FINDINGS.md)
or [RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md), those two are right. The
findings state what is true now, the runbook states the commands that work now,
and [RG35XX-PLUS-TARGET.md](RG35XX-PLUS-TARGET.md) states what the payload was
aiming at.

## 2026-09-16 MMC bring-up result

The H700 profile now supports legacy MMC initialization, MMC CMD3/CMD6/CMD8,
CMD23-bounded multiblock reads, and 256-byte CMD16 reads backed by the two
halves of each 512-byte DDR sector. The SD CSD retains its 13 MHz limit; the
MMC CSD advertises 5 MHz after the GKD validation below showed that its 4 MHz
generated clock was reliable and 12.913 MHz was not. CMD uses the qualified
same-edge path; DAT uses opposite-edge final pad registers.

The retained seed-5 route has FASM SHA-256
`0baff8f1caf17e3b5e31c638644778490b75ea20230ae5836f0ef97a720fa92b`.
The currently packed bitstream has SHA-256
`da2579b8f06d1dd75bd3f26001a2bf714982bf65913e973296541bdb2dcaeac3`.
Its 707,687 decoded configuration bits passed round-trip verification. Routed
clocks passed at 95.37 MHz frontend and 81.97 MHz DDR against 80 MHz, 94.22 and
180.96 MHz Ethernet against 25 MHz, and 382.41 MHz I/O delay against 200 MHz.
The route also passed 18 bounded CDC checks and five direct SD-output checks.

The 16 MiB diagnostic prefix had SHA-256
`42cedc5a16d81c93001bde260988e5223d9bf3e44650d677f2bfd30e32c65176`.
With the earlier CMD7 busy-release experiment, one cold start completed MMC
CMD2/3/9/7, selected 256-byte blocks with CMD16, issued CMD18, and produced
2,548 backend reads through physical LBA 2,560 with zero invalid command
frames. This established substantial protocol progress, but it did not prove
that the H700 accepted every response or data CRC.

Cold starts are not yet reliable. Other starts stopped at CMD7 or the first
CMD17/18; some also recorded invalid command frames. A verified 64 MiB image
with SHA-256
`398035d789a742edd05022283465b8846630225ba4cad590cc2319c3defe5b97`
did not produce the U-Boot or kernel debug-sector writes. Experiments with a
10 MHz MMC CSD, 100 MHz internal sampling, FPGA pull-ups, and push-pull MMC
identification either failed before the changed behavior applied or reduced
reliability, so they were rejected and are absent from the retained source.

### 2026-09-17 pin-readback qualification

The trace now independently decodes card responses through the CMD IOBUF and
checks DAT readback against the final pad serializer. On hardware, completed
CMD3, CMD7, and CMD18 responses had the expected 48 bits, matching calculated
and received CRC7, correct framing, and no serializer/readback mismatch. The
clean CMD7 vector was `07 00 00 07 00 75`.

The previous H700 compatibility path incorrectly retained an actively driven
DAT0-high level after its short CMD7 pulse. A later PSU cycle produced clocks
but no fresh commands, consistent with preventing a clean target reset or
back-powering it through the I/O path. The retained implementation always
releases DAT0 after the pulse. A regression gates SD_CLK for 300 fabric cycles
and requires the line to remain high-impedance. Repeated hardware power cycles
then produced fresh command sequences.

The seed-3 H700 observer build has bitstream SHA-256
`411071868ba7be661de4778ff37dea5be5a400b14e3f2510d70fa3a949b3313d`.
Its DDR and frontend clocks passed at 81.08 and 89.02 MHz against 80 MHz, and
its 729,290 decoded configuration bits passed round-trip verification. One
cold start stopped at CMD3; another reached CMD16(512) and CMD18 at LBA 96.
That transfer produced complete 4,114-edge, one-bit 512-byte bursts, but the
DAT IOBUF observer recorded a serializer/readback mismatch and the H700 kept
clocking sequential blocks without reaching a later command or debug write.

An A/B image retained the exact routed design and changed only the Pmod I/O
slew from SLOW to FAST. It passed the same clock, CDC, direct-output, and
bitstream checks (SHA-256
`4bda841b679df2aa84383602c291ea6ce211c60c29b16653b19ee138d202f32e`).
Two clean starts still stopped at CMD7, so fast slew is not retained as a fix.

The remaining failure occurs during low-speed identification or data return
and varies across otherwise identical power cycles. The FPGA-side observer
narrows it to the pad/return path but cannot see the H700 side of JD's 200-ohm
resistors. Further work requires scope captures at both ends, verification of
target-side CMD/DAT pull-ups and off-state voltages, and controlled impedance
or connector experiments. A successful bare-kernel boot has not yet been
demonstrated.

Raw sampled clock edges and invalid-frame counts can rise while the target is
off because the line is then undriven. Treat those as signal-integrity evidence,
not target progress. During these tests only Miniware P906 channel 02 was
switched. Channel 01 was not touched.

## GKD-350H legacy-MMC validation

The GKD external slot is `mmc1` / `2a310000.mmc`. Its shipped device tree has a
`no-mmc` property, so Linux otherwise stops after the SD probe and never sends
CMD1. For a dedicated lab host, preserve the original DTB, delete only that
property, and optionally clamp this controller to 5 MHz before rebooting:

```sh
cp rk3576-gkd-atom.dtb rk3576-gkd-atom.mmc-test.dtb
fdtput -d rk3576-gkd-atom.mmc-test.dtb /mmc@2a310000 no-mmc
fdtput -t i rk3576-gkd-atom.mmc-test.dtb \
  /mmc@2a310000 max-frequency 5000000
```

Validate the edited DTB with `fdtget`, retain an exact on-device backup, and
use `microsd_prepare_linux.py` before replacing the active file. On the tested
RK3576 clock tree, a 5 MHz request produces a 4 MHz external clock. Restore the
backup to return the handheld to its original SD-only slot policy.

Build the deterministic profile with:

```sh
python3 experiments/openxc7-macos/build_ddr.py \
  --ethernet --slow-mmc --mmc-only --seed 4 \
  --output build/microsd-ddr-ethernet-mmc-only
```

`--mmc-only` suppresses the initial SD CMD8, CMD55, and ACMD41 responses so a
host which permits MMC proceeds to CMD1. It uses ordinary R1 for fresh MMC
CMD7 selection and releases DAT0; it does not manufacture an R1b busy period or
an actively driven idle-high level.

The 2026-09-16 v2 hardware candidate had bitstream SHA-256
`709b4d83630980ea02609613b8102bdd5873fc24d6cfc45c4f1475f34f6da03e`.
Seed 4 passed at 83.70 MHz DDR and 94.55 MHz frontend against 80 MHz targets.
The GKD read back the exact CID and CSD, selected four-bit legacy MMC, read
EXT_CSD capacity as 256 MiB, and issued CMD6, CMD23, CMD18, CMD12, CMD17, and
CMD13 traffic. No writes were observed. The validated v2 image treated CMD23
as illegal, which Linux tolerated; the current implementation stores its
16-bit count and ends the following CMD18 after exactly that many blocks.

A deterministic 16 MiB image with SHA-256
`dce3a728a55021183499a78c32c859a65f7f96f346a3efb8abe8a1bb2cc6d8ea`
separated the clock-rate behavior:

| Host limit | Actual clock | Result |
| --- | ---: | --- |
| 13 MHz from card CSD | 12.913 MHz | failed after 12,845,056 bytes; kernel reinitialized the card |
| 5 MHz device-tree clamp | 4.000 MHz | six complete 16 MiB reads matched exactly |

The five repeated low-speed qualification reads sustained about 0.90–0.93
MB/s and produced no kernel I/O errors. This validates enumeration and payload
reads at 4 MHz on the current wiring. It also shows that 13 MHz failures are not
enough to declare the MMC command implementation broken.

The current CMD23/low-speed revision was then built at seed 4. Its bitstream
SHA-256 is
`d846034070d3eb1fec0e46aff909042f24070993d22f9376da91948d11bdb3be`;
DDR and frontend clocks passed at 84.93 and 94.79 MHz against 80 MHz. With the
device-tree clock clamp removed, the GKD read the exact CSD
`d05e00590f5903ffffffffe7924000bd`, requested 5 MHz, and generated 4 MHz.
Three complete 16 MiB reads matched
`dce3a728a55021183499a78c32c859a65f7f96f346a3efb8abe8a1bb2cc6d8ea`;
controller error counters, FPGA invalid frames, and FPGA writes all remained
zero. Linux exercised CMD23/CMD18 as well as CMD17/CMD13 traffic.

As a deliberate no-clamp control, an intermediate CSD used `TRAN_SPEED=0x12`.
That field means 12 MHz rather than 5 MHz; the GKD selected 12 MHz and recorded
a block I/O error. The test now decodes the advertised rate numerically in
addition to checking the complete CSD and its CRC7.

The retained register set is intentionally a constrained compatibility
profile rather than a claim of full eMMC 5.1 conformance. In particular,
EXT_CSD revision 8 is paired with no high-speed device type, and the H700-only
256-byte behavior remains a compatibility exception despite the CSD's normal
512-byte block fields. The GKD independently confirmed the exact on-wire CSD;
the next H700 run must establish whether that target still requests CMD16(256).

The current MMC CID reuses the SD constant. Linux therefore renders MMC's
six-byte product-name field as `SPADE` followed by byte `0x10`; the guarded
host helper accepts that rendering only together with the exact expected CID.
A future register cleanup should give SD and MMC separate coherent CIDs.

Passive invalid-frame counts are not yet a host-error metric: the observer can
see card-driven traffic on the bidirectional CMD pin. Exact hashes and kernel
I/O errors are the qualification evidence until pin-readback direction and CRC
classification are separated.

## 2026-09-17 H700 x1 and CMD12 result

Fresh MMC CMD7 selection now returns ordinary R1 and leaves DAT0 released; the
H700 profile no longer generates the earlier compatibility busy pulse. It also
rejects the MMC four-bit BUS_WIDTH switch so payload reads remain on DAT0. The
GKD `--mmc-only` profile retains its independently qualified four-bit behavior.

An initial x1 hardware trial repeatedly loaded from LBA 96 through LBA 2640.
The last read-data burst stopped after 1,202 of the 4,114 edges required for a
complete x1 512-byte frame because CMD12 immediately cleared the serializer.
The frontend now remembers CMD12 received during a read block, completes that
block's payload, CRC, and end bit, and suppresses the next block. CMD12 received
before data starts, reset, and deselection still cancel immediately. The
regression sends CMD12 during serialization and requires the active block to
finish without another backend request.

The retained 5 MHz seed-12 candidate had bitstream SHA-256
`edb3895309988d7a12896fd177aa1fa39b5e978e71bb739a2e3e1d1fca78afdb`.
Its DDR and frontend clocks passed at 81.47 and 96.38 MHz against 80 MHz, and
729,130 decoded configuration bits passed round-trip verification. On the
second cold start it completed the formerly truncated block at all 4,114 edges,
then stopped after CMD12 with 10,333 backend reads through LBA 2640. This proves
the stop-boundary fix on hardware, but U-Boot still did not access the FAT
partition or write a debug milestone.

As a low-speed control, only the H700 CSD was changed from 5 MHz to 1 MHz. The
GKD CSD remains at its qualified 5 MHz value. The CRC-correct H700 CSD is
`d05e00090f5903ffffffffe79240008d`. A reused seed-4 route passed DDR and
frontend timing at 84.60 and 84.04 MHz against 80 MHz, all CDC and direct-output
checks, and a 733,405-bit configuration round trip. Its packed bitstream
SHA-256 is
`55a15d8f994839116cf36d4a71f21e8f3f391ab04512ef0492038a72b868d3a8`.
The H700 produced the same 10,333-read, LBA-2640, final-CMD12 result and no write.
Thus the lower advertised transfer rate did not resolve the remaining boot
failure.

The trace JSON names `clock_edge_event` and `command_frame_event` are one-cycle
activity snapshots. Earlier names incorrectly implied that they were sampled
electrical levels. The cumulative `clock_edges` and command counters remain the
useful progress evidence.

### External-falling-edge data launch experiment

An expanded passive trace retains the eight most recent command arguments as
well as their command indexes. This distinguished the repeated boot reads from
an undifferentiated final LBA: the H700 issued CMD18/CMD12 pairs twice from LBA
16 and then twice from LBA 512. Both attempts ended at LBA 2640 without a write.
The first offset is the primary eGON SPL; the second is the H700 fallback boot
offset. The verified image contains a checksum-valid `eGON.BT0` header at LBA
16, so this pattern shows that the target rejected the bytes it received; it
does not by itself identify which byte or electrical sample was wrong.

The H700 data path previously changed its prepared output shortly after a
synchronized rising SD clock edge. Its final fabric falling-edge register did
not guarantee that this transition followed the external falling edge. The
revised path holds each data bit through the external rising edge and advances
only after observing the external falling edge. The GKD and other qualified
profiles retain their existing launch rule. A phase-sensitive regression checks
that H700 DAT remains unchanged after an external rising edge and changes only
after the following falling edge.

The selected seed-11 build has bitstream SHA-256
`4eb3ac7337a7174f5fcd54a73e050ea94997299a71adc6bdecf9b6322b408978`.
DDR and frontend clocks passed at 81.33 and 83.24 MHz against 80 MHz; Ethernet
TX/RX passed at 98.85/145.26 MHz against 25 MHz, and the I/O-delay clock passed
at 283.13 MHz against 200 MHz. It passed all 18 bounded CDC checks, all five
direct SD-output checks, and a 756,773-bit configuration round trip. The 64 MiB
image passed complete Ethernet readback with SHA-256
`398035d789a742edd05022283465b8846630225ba4cad590cc2319c3defe5b97`
before ARM.

On the first target start, the H700 completed 85 blocks through LBA 96 with no
serializer mismatch, then restarted initialization and stopped at CMD7. A cold
cycle of Miniware channel 02 reproduced the complete boot pattern through LBA
2640 and final CMD12. The cumulative trace after both starts contained 10,334
backend requests, with recent commands
`18,12,18,12,18,12,18,12` and arguments
`16,0,16,0,512,0,512,0`. The completed final block contained all 4,114 x1
sampled edges and recorded zero pad-readback mismatches. No FAT access or debug
write occurred. This is a cleaner transfer and stronger localization of the
failure, but it is not a successful boot and it does not prove what the H700
sampled beyond the adapter and target-side interconnect.

## 2026-09-17 boot-stage and width-negotiation correction

The repeated LBA 16/LBA 512 MMC reads are issued after the SPL starts, rather
than by a BootROM retry. This was established without new gateware. The source
image's eGON header declares a total SPL length of `0xa000`; its stored checksum
`a629138d` exactly matches an independent recomputation. The first instruction
`ea000016` branches to SPL offset `0x60`.

`rg35xx_boot_debug.py --make-spl-loop` creates a disposable copy which replaces
the instruction at SPL offset `0x60` with `eafffffe` and recomputes the eGON
checksum:

```sh
uv run python projects/ethernet-diagnostic/scripts/rg35xx_boot_debug.py \
  --make-spl-loop build/rg35xx-bare/rg35xx-plus-bare-4m-uboot-debug.img \
  --output build/rg35xx-bare/rg35xx-plus-bare-4m-spl-loop.img
```

The tested loop image has SHA-256
`0d645fa9eb849252abb02b00cadad5d203ba4cc79d3768d8e0a84e85049c64f3`
and checksum `a729136c`. A complete Ethernet upload/readback matched that hash.
Two cold starts, each separated by target power-off plus frontend DISARM/ARM,
produced only the initial SD sequence: one-, two-, and 81-block CMD18/CMD12
probes at raw argument 8192. The command, response, and backend-read counters
then remained unchanged for at least 15 seconds. The unmodified image proceeds
from the same sequence into a fresh SD probe and then an MMC fallback. This
repeatable difference is evidence that execution reaches SPL offset `0x60`.

Rejecting the H700's MMC four-bit CMD6 with only `ILLEGAL_COMMAND` did not prove
that U-Boot kept its controller in one-bit mode. U-Boot polls CMD13 for
`SWITCH_ERROR`; a ready TRANSFER status without that bit can make the switch
appear successful. The H700 profile now leaves the FPGA width unchanged, sets
`SWITCH_ERROR` after an unsupported BUS_WIDTH request, reports it in the next
CMD13 response, and clears it after that status. The focused regression checks
the set-and-clear sequence. The GKD profile continues to accept its qualified
four-bit switch.

The enhanced trace retains the complete CMD6 argument/status and following
CMD13 status. It also independently finds the first low start bit after the
first MMC CMD18, captures the first 32 bytes from raw DAT0, calculates CRC16
over all 512 observed payload bytes, captures the transmitted CRC/end bit, and
records transaction timestamps and measured rising-edge periods. A separate
raw-CMD decoder captures all 136 bits of the MMC CMD9 response. Its expected
diagnostic byte sequence is
`3f d0 26 00 08 13 59 13 ff ff ff ff e7 92 40 00 2f`.
These observers do not share the response or data serializer indexes.

Arty SW0 selects the H700 DAT launch phase within one routed image. Off uses
the full-cycle prepared launch; on uses detected external falling-edge launch.
The input is synchronized and latched only while the card is disarmed. Use
DISARM, set SW0, wait briefly, then ARM. The enhanced trace reports the
latched choice as `falling_edge_data_launch`.

The optional `--h700-early-command` build selects the alternate CMD response
launch phase. The normal build retains the slow profile's detected-falling-edge
advance; the option advances after the detected rising edge, giving the
response bit an additional half-cycle before the next host sample. The trace
reports the compiled choice as `early_command_launch`. This is a controlled
diagnostic for the reproducible CMD3 boundary; it does not change response
contents or the DAT phase selected by SW0.

A runtime SW1 selector for the command phase was attempted first and rejected:
no placement seed through 20 met the clock and direct-output bounds with the
extra mux, so the choice is compiled instead. No `--h700-early-command`
bitstream has passed the timing, CDC, and direct-output gates yet, so the
option is unverified on hardware.

The phase-selecting revision was routed at seed 19. Its bitstream SHA-256 is
`b03dd2d611ec6766e739988c9e58ff14d0891fdfeb13797fcad2c3ae2fd3cc68`.
All six clocks passed, all 18 CDC paths and five direct SD outputs passed, and
821,000 decoded configuration bits matched the packed FASM. A full Ethernet
upload/readback verified the 4 MiB image with SHA-256
`038ff061e56a2bc4a364c66995a4446af8b6aa664766c66888588273c215be7a`.

With SW0 off, one cold start reached the first MMC CMD18 at LBA 96. The raw
CMD9 observer captured the exact expected 136 bits
`3fd0260008135913ffffffffe79240002f`, proving that the card's R2 serializer is
not shifted. The independent DAT0 observer captured all 4,096 payload bits,
matching CRC16 values of `0xa667`, a valid end bit, and this 32-byte prefix:

```text
d00dfeed0008d9f9000000380008d59000000028000000110000000200000000
```

Those bytes exactly match the verified image at LBA 96, including the FIT
header and its 580,089-byte size. The transfer later stopped at LBA 193, well
before the complete FIT. Other cold starts stopped at CMD7 or CMD3. With SW0
on, the trace confirmed falling-edge launch, but repeated starts stopped at
CMD8 or CMD3 before a comparable MMC data transfer. The variation therefore
cannot be attributed solely to the selected DAT launch phase.

### Natural SD-to-MMC fallback control

An ordinary-SD control build omitted both `H700_MMC` and `MMC_ONLY`. Its
bitstream SHA-256 was
`8893fb68ca942f1f04a596269e80392ee1d24e0014852bfc74fce1521ee78331`.
After the initial SD load, the H700 reset the bus and chose MMC CMD1 itself,
then reached CMD7. This establishes that suppressing post-loader SD responses
is unnecessary and is not the cause of the fallback.

The H700 compatibility profile now continues to answer SD CMD8/CMD55/ACMD41;
only the explicit `MMC_ONLY` diagnostic suppresses SD negotiation. The updated
seed-30 build has bitstream SHA-256
`2beba6bf1bb3007fe0fca8acf76c0e2b9811d85d224e22cb70e6c362ef737e87`.
DDR/frontend clocks passed at 80.48/86.88 MHz against 80 MHz; Ethernet passed
at 91.75/134.23 MHz against 25 MHz; I/O delay passed at 378.93 MHz against
200 MHz. It passed 18 CDC checks, five direct-output checks at 3.008--3.208 ns,
and an 823,960-bit configuration round trip. The same 4 MiB image again passed
complete Ethernet readback.

Three standardized cold starts with SW0 on each completed the initial SD load,
answered the payload's fresh SD CMD8/CMD55 probe, accepted MMC CMD1/2/3, and
stopped at CMD3 with zero invalid command frames. The FPGA-side CMD3 observer
recorded command index 3, CRC7 `0x7d`, a valid end bit, and zero mismatch; the
expected complete R1 is `03 00 00 05 00 fb`. No MMC data phase had begun.
The remaining decisive measurement is CLK/CMD at the H700 end of the adapter
through CMD3. FPGA IOBUF readback cannot show settling or sampling after the
Arty JD connector's series path. A successful H700 boot remains unproven.

## 2026-09-18 R1b busy and the missing data-line pull-up

The reproducible stop is a host-side wait, not a rejected response. Sampling
the trace once per second through a cold start showed the SD clock running
continuously at about 246,000 edges per second for 25 seconds after the last
command, with the command, response, and backend counters all frozen. A host
that had rejected a response would retry it; this one issues nothing and keeps
clocking.

The last command in that trial was SD CMD7. Selection answers R1b, so the card
pulses DAT0 low for 255 fabric cycles and then releases it, and the sunxi
controller polls DAT0 for the end of that busy signal. This adapter has no
effective pull-up: released response ones were already observed as lows on CMD,
which is why this profile drives command responses. A released DAT0 therefore
reads low forever, the busy check never completes, and the controller clocks
without issuing another command. Every earlier stop at CMD7, and the MMC stops
around CMD6 and CMD8, fit the same explanation, because those are the other
R1b and wait-for-DAT0 points in the U-Boot flow.

The H700 profile now holds the idle data lines at their pull-up level. The
value already sits high in the final data registers, so only the output enable
changes and the qualified register-to-pad data path is untouched. Active
transfers, the deliberate busy pulse, and host write data keep the released
behavior, and the qualified SD and GKD MMC profiles are unaffected. The trace
reports the state as `idle_data_high`.

Holding a level while armed must never back-power an unpowered target. A
single-edge watchdog is not enough: with the RG35XX off, the floating SD_CLK
input still produced about 320 transitions per second. The drive is therefore
gated on an edge *rate*, at least four transitions inside a 4096-cycle window,
which the slowest observed host clock exceeds by roughly a thousand times and
floating-input noise never approaches. The decision is registered and releases
within two windows, about 128 us.

### Result

With the idle level held, the H700 SPL passed the boundary that had stopped
three consecutive cold starts. Its command history became:

```text
ACMD41, CMD2, CMD3, CMD9, CMD7, CMD55, ACMD51, CMD6
arguments 0x40300000, 0, 0, 0x10000, 0x10000, 0x10000, 0, 0x01000031
```

`select_ready` is now true, the initial BootROM load still completes, and the
new stop is SD CMD6. That command is the SD switch function, which returns a
64-byte status block on the data lines. This emulator does not implement it, so
the host waits for data that never arrives.

U-Boot's `sd_change_freq()` only issues CMD6 when the card declares SD 1.10 or
later. The H700 profile's SCR now declares SD 1.01, which is what a card
without the switch function should report, so the host skips it. The qualified
SD and GKD profiles keep the previously validated SCR.

### SD fabric clock

Every placement of the enhanced-telemetry design failed the 80 MHz `fclk`
constraint once the compatibility logic was added, across fifteen seeds on one
netlist and ten on another. The constraint is not physical: the host clock
measured here is three orders of magnitude lower, and the profile's own CSD
advertises 13 MHz. `build_ddr.py --sd-io-clock-hz` now selects the SD fabric
clock, and this profile builds at 64 MHz, which divides the same 1600 MHz VCO
as the DDR outputs. The initial BootROM 4-bit load still completed normally at
that rate.

Note for rebuilds: `nextpnr-xilinx` here is linked against Boost 1.90, so it
needs `DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib`. macOS strips
that variable when launching through `uv run`, so invoke the build with
`./.venv/bin/python` directly.

## 2026-09-18 The RG35XX Plus boots from the emulator

With the idle data level held and the SCR corrected, U-Boot proper started,
switched to four bits, and reached the FAT boot partition, where it stopped
again. The cause was in the image rather than the gateware: `BOOT.SCR` was a
legacy uImage whose payload began directly with its script text. U-Boot's
`source` reads a length word from the payload and then skips eight bytes, so it
began executing in the middle of the first command and aborted the script.

`rg35xx_boot_debug.py --repair-boot-script` rebuilds that file with the
required length table and with a milestone write after each load, so the raw
debug partition records how far the boot reached. It reproduces the tested
image byte for byte:

```sh
uv run python projects/ethernet-diagnostic/scripts/rg35xx_boot_debug.py \
  --repair-boot-script build/rg35xx-bare/rg35xx-plus-bare-64m-uboot-debug.img \
  --output build/rg35xx-bare/rg35xx-plus-bare-64m-bootscr.img
```

Image SHA-256 `ea5e4c33632fe55b2e22a1c560d8af866c8eeb076bc18eb4e9e82b3e6f4c676c`,
uploaded and read back complete over Ethernet before every trial.

### Result

Bitstream `c8851292793596c71b22d837f3eabeb7e90824d6a83b9ace39ea7cda6b2e777c`,
placement seed 8, 64 MHz SD fabric clock. All six clocks, 18 CDC paths and five
direct SD outputs passed, and 825,835 configuration bits round-tripped.

Two consecutive cold starts produced the same sequence. Times are from target
power-on:

```text
0.1 s   BootROM loads the SPL, 81 blocks at LBA 16
0.1 s   SPL reads the complete FIT, 1134 blocks at LBA 96
0.9 s   U-Boot proper selects the card, switches to four bits, reads the MBR,
        the FAT boot sector and the root directory
0.9 s   BOOT.SCR runs: milestone 1, BOOTMARK loaded, milestone 2
0.9 s   KERNEL streams from LBA 32989
13.0 s  the kernel read ends exactly at LBA 95241, KERNEL's last sector
13.1 s  INITRD and dtb.img load, milestones 3, 4 and 5 are written
16.0 s  CMD5 appears, then CMD55/ACMD41 and ACMD6 with a four-bit argument
16.2 s  reads at LBA 0 and 8, the partition table
16.7 s  reads at LBA 114720, inside mmcblk0p2
```

U-Boot never issues CMD5, so the probe at 16 s is the Linux MMC stack
re-enumerating the emulated card after `booti`. It then reads the partition
table and the raw debug partition named by `baredebug=/dev/mmcblk0p2` in the
kernel command line. Across the whole boot the card served 258,574 sector reads
and accepted seven writes, with 960 valid command frames.

The milestones the target wrote back to the card confirm each stage
independently of the counters:

```text
sector 2  decodes as target-to-host stage=0 detail=uboot-loaded-fat
sector 3  byte-for-byte identical to KERNEL's first sector, arm64 image header
          1f2003d5 19446214
sector 4  1f8b0808 ... "INITRD", the gzip initramfs
sector 5  d00dfeed, the flattened device tree
```

The same sequence was reproduced after the regression tests were added, on
bitstream `5dd60bc09a465eb72e865b3cfa52041b0e45094edddf361c4008d1a51ada98e5`,
placement seed 10, 830,142 configuration bits, with `dclk` at 81.57 MHz and
`fclk` at 80.50 MHz. That is the current qualified artifact for this profile.

Two attempts to make the idle level safe against a stale final register were
tried on hardware and reverted, because the register holds the last
transmitted bit until the next SD edge. Gating the drive on that register
already reading high releases the lines between blocks of a multiblock read,
where a floating line reads low and the host reads without stopping; forcing
the register to the idle level destroys the last CRC bit, which the host
samples after the transfer's enable drops. The liveness gate already bounds a
stale value to one host clock period, which is why neither is needed.

This is a boot from the emulator: the H700 loads its SPL, U-Boot, kernel,
initramfs and device tree from FPGA DDR over the Pmod adapter, and the booted
kernel drives the emulated card itself. Without serial access the last
observable stage is the kernel's own MMC enumeration and its reads of
mmcblk0p2; userspace progress beyond that is not visible from the card side and
would need the initramfs to write further milestones.

## 2026-09-18 A userspace that runs

The shipped initramfs could not start. Its 3 KiB cpio held three entries — `.`,
`./init` and the trailer — and `./init` is a `#!/bin/sh` script that calls
`/usr/bin/busybox` for every operation. Neither a shell nor BusyBox was in it,
so `rdinit=/init` had nothing to execute. That is why the kernel enumerated the
card, read the partition table and `mmcblk0p2`, and then wrote nothing: the
milestones the script is built around could never be reached.

`rg35xx/build_initramfs.py` builds a real one. BusyBox is compiled from an
unpatched release tarball with `defconfig` plus `CONFIG_STATIC`, the same shape
`tools/zaurus-sd-boot/busybox/build_busybox.sh` uses for the Zaurus, in an
arm64 container that runs natively on Apple Silicon, so no cross prefix is
needed. The tarball hash is pinned. `rg35xx/init` is the script recovered from
the shipped image, now kept in the repository rather than only inside a build
artifact.

The result is 1.5 MiB, which no longer fits the single cluster the old stub
occupied, so `rg35xx_boot_debug.py --replace-file` reallocates it. It prefers
one contiguous run, rewrites every FAT copy together, and leaves the other
files untouched.

### Baseline to userspace

Image `c8214cae1199c422100ce9013d417f9547dec09fc5aba86d4ae0cd9ee5986dbb` on
bitstream `5dd60bc0…`, measured with `rg35xx_trial.py`:

```text
 1.10 s  KERNEL stream begins
13.14 s  KERNEL stream ends, 12.0 s for 31,873,032 bytes
13.22 s  INITRD, then dtb.img and the boot-script milestones
16.82 s  Linux re-enumerates the card and reads the partition table
17.48 s  userspace writes into mmcblk0p2
```

The record it wrote decodes as `stage=1 detail=init-entered uptime=3.35`, so
the kernel reached userspace 3.35 s after it started, and the whole boot takes
about 17.5 s from target power-on. Roughly twelve of those seconds are the
kernel read alone.

Two runs on the same image instead served about 127,000 sectors, twice the
kernel's size, with one CMD18 streaming for 24 s before the load completed.
Both the fragmented and the contiguous initramfs showed it, so file layout is
not the cause and it is not yet explained; it is the same startup variability
seen throughout this log, and a boot-time benchmark has to report it rather
than average it away.

## 2026-09-18 Compressing the kernel

The card reads about 2.64 MB/s, so the 31,873,032-byte arm64 Image was twelve
of the seventeen seconds. Compressing it trades that read for a decompress the
H700 does from DRAM. Measured on the image itself:

```text
uncompressed  31,873,032   100.0%   12.04 s read (measured)
gzip -9       15,741,883    49.4%    5.96 s at 2.64 MB/s
zstd -19      13,715,233    43.0%    5.20 s
xz -9         12,180,304    38.2%    4.61 s
```

Nothing on the target has to change. The FIT's U-Boot already carries the
`unzip` command and an environment with `kernel_addr_r=0x40080000`,
`kernel_comp_addr_r=0x44000000` and `kernel_comp_size=0xb000000`, so
`rg35xx_boot_debug.py --compress-kernel` stores KERNEL gzipped and rewrites the
boot script to load it at `kernel_comp_addr_r`, expand it with `unzip`, and
`booti` the result. gzip is used rather than the smaller xz because inflate is
far cheaper on a Cortex-A53 than lzma, and the remaining gap is under a second
of reading.

### Result

```text
                    uncompressed   gzip
sectors served            66,740   35,267
power-on to userspace      17.5 s   11.8 s
```

The milestones from the compressed boot decode as
`stage=3 detail=model-Anbernic RG35XX Plus uptime=3.48` and
`stage=4 detail=framebuffer-present uptime=3.51`, so userspace is not merely
entered: it reads the device tree and finds a framebuffer.

The unexplained variability remains and now dominates the measurement. Two of
four compressed runs instead served about 127,000 sectors with a single CMD18
streaming for around 24 s, the same shape seen with both the fragmented and the
contiguous initramfs and with the uncompressed kernel. It is independent of the
payload, so a benchmark has to report the distribution, and finding its cause
is worth more than the next few seconds of payload tuning.

## 2026-09-18 Characterizing the oversized read

The intermittent failure is now measured rather than described. With the trial
tool emitting a row every 8192 sectors, a failing run reads like this:

```text
t=  9.77s CMD18 arg=16888320 lba=  84292 stream boot partition free cluster
t= 16.39s CMD18 arg=16888320 lba= 118301 stream partition 2 sector 3613
t= 19.59s CMD18 arg=16888320 lba= 134708 stream beyond the image
t= 22.78s CMD18 arg=16888320 lba= 151131 stream beyond the image
t= 39.93s CMD18 arg=16888320 lba= 158773        beyond the image
```

One CMD18 at the kernel's first sector streams monotonically through the end of
the boot partition, through the raw debug partition, past the end of the image
and on into untouched DDR. It stops near LBA 158,773; earlier failures stopped
at 158,775, 158,776, 158,777 and 158,779, so the extent is reproducible: about
125,788 sectors, 64.4 MiB, from a file of 15.7 MiB.

Three things follow from the numbers:

- The card serves it at about 5,100 sectors per second, the same rate as a
  healthy run, so nothing is retrying or stalling. The host consumes every
  block and asks for more.
- It is not a missed stop. `multiblock_stop_is_accepted_anywhere_in_a_block`
  injects CMD12 at nine offsets across a four-bit block, covering the start
  bit, early and mid payload, the CRC window, the end bit and the following
  gap, and the card stops at every one.
- The extent does not scale with the payload. The uncompressed 31.9 MiB kernel
  and the compressed 15.7 MiB kernel both produce the same roughly 125,800
  sectors, so the host is not reading some multiple of the file. It is reading
  a length it computed, and that length is wrong.

That points at the metadata rather than the data: U-Boot reads the directory
and FAT immediately before this transfer, and a single bad block there would
give it a bogus length while leaving the card's own counters clean. The card's
serializer and pin-readback comparators report no mismatch, so if a block is
being corrupted it happens past the FPGA's pin.

The independent block decoder cannot answer that yet. It arms only on an MMC
CMD18 and decodes one lane, while this boot runs in SD mode at four bits, which
is why every trial so far reported it idle.

### A second failure mode

Roughly one cold start in four produced no card activity at all: zero commands,
zero sectors, only a couple of invalid frames from the floating bus. It appears
when trials run back to back, so `rg35xx_trial.py` now holds the target powered
off for a settle interval, six seconds by default, before starting.

### Spread so far

Healthy compressed-kernel boots reached userspace at 9.4 s, 11.6 s and 11.8 s.
The median is the number the benchmark will report, and with a failure mode
this large in perhaps half the runs, the distribution is the result rather than
a footnote.

### Ten standardized cold starts

Ten consecutive trials on the compressed-kernel image, each with the target
held off for the settle interval first. Every one produced card activity, so
the settle interval removed the second failure mode entirely.

```text
healthy    4/10   35,198  35,198  35,240  35,276 sectors
oversized  6/10  124,337 124,339 127,070 127,282 127,283 127,283 sectors
```

Healthy runs are almost identical, 0.2% apart, and reached userspace at 8.37 s
and 11.92 s twice; the fourth did not re-enumerate inside the 25 s window, so
the benchmark needs a longer one. Median of the three is 11.92 s.

The oversized runs fall into two tight clusters rather than scattering: about
124,338 sectors ending near LBA 155,82x, and about 127,28x ending near LBA
158,77x. Both start at the same sector and differ by roughly 2,945, close to
the initramfs's 2,990. Two discrete wrong lengths, each reproducible to a
handful of sectors, is not what random corruption of a metadata block would
produce. Something deterministic is computing them.

That also rules the FPGA's own data path further out: the card serves both
outcomes at the same rate with no serializer or pin-readback mismatch, and the
healthy runs show the same card serving exactly the right sectors.

## 2026-09-18 Eliminating the oversized read

The failure is in U-Boot's filesystem path, not in the card. The card starts the
transfer at exactly the right sector — the observed CMD18 argument 16,888,320
is LBA 32,985, which is where KERNEL's first cluster sits — and then serves
whatever is asked of it. What varies between a healthy and a failing run is the
length the host asked for.

Since every payload file is contiguous, the filesystem can be removed from the
boot path entirely. `rg35xx_boot_debug.py --raw-kernel` emits a boot script that
states every block count explicitly:

```text
mmc dev 0
mmc read ${kernel_comp_addr_r} 0x80d9 0x781a
unzip ${kernel_comp_addr_r} ${kernel_addr_r}
mmc read ${ramdisk_addr_r} 0x17495 0xbad
setenv initrd_size 0x17598a
mmc read ${fdt_addr_r} 0x17431 0x61
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
```

It refuses to run if any of those files is fragmented, because a raw read would
then silently fetch the wrong sectors.

### Result over ten standardized cold starts

```text
                       fatload            mmc read
oversized runs          6 / 10             0 / 10
sectors served   35,198 .. 127,283   35,113 .. 35,182
median to userspace     11.92 s            10.81 s
range                 8.37 .. 11.92     8.10 .. 11.95
```

Ten of ten now serve the same work, spread 69 sectors, 0.2%. Nine of ten
reached userspace inside the 35 s window; the tenth booted and was still ahead
of its userspace writes when the window closed.

This eliminates the failure and localizes it to U-Boot's filesystem length
handling, which is not the same as identifying the defect inside U-Boot. The
two discrete wrong lengths remain unexplained; they are simply no longer on the
boot path. Anyone restoring `fatload` should expect them back.

The metric itself is worth stating precisely, because the earlier figures used
a weaker proxy. The raw boot script writes exactly four milestones, so the
fifth write of a run is the first one userspace made, and that is the instant
the benchmark measures to.

## 2026-09-18 Stage boundaries in the FPGA clock domain

The independent block decoder armed on an MMC CMD18 and decoded one lane, so on
this SD four-bit boot it never fired and every timestamp beside it stayed zero.
It now arms on a backend read of a chosen sector, follows the bus width from the
trace's own status word, and records the sector that armed it.
`--trace-capture-lba` selects that sector and defaults to the kernel's first.

Captures reset when the card is disarmed, so `rg35xx_trial.py` reports them from
the last in-run sample rather than querying afterwards. On bitstream
`cf5fb75dadfd8dcb65a89f4df8772986cdfd26b2dee3bbfab50979eeb28a30c3`, seed 19,
847,723 configuration bits:

```text
captured sector 32985: done, 1024 payload bits, crc match, end bit set
  first bytes 1f8b0800000000000213ecbd0b7854d5d537bece39334908b790842424486602
  fabric ticks: r1_end 846847485, data_start 846848301,
                block_end 846859404 (span 11103), edges 124..1165
```

Everything there is independent of the serializer that produced it. Sector
32,985 is the kernel's first sector, the payload counted 1024 nibble ticks
rather than 4096 bit ticks, the lane-zero CRC matches, the end bit is present,
and the first bytes are the gzip magic that starts the compressed kernel.

The timestamps are the point. At 64 MHz, the response end to the first data bit
is 816 ticks, 12.75 us, and one 512-byte block spans 11,103 ticks, 173.5 us,
which is 2.95 MB/s and agrees with the rate inferred from sector counts. The
block occupies 1,041 sampled edges, exactly one start bit plus 1024 payload
nibbles plus 16 CRC edges. Those are measurements at microsecond resolution,
where the same boundaries were previously inferred from 50 ms polls.

## 2026-09-18 Cutting kernel init

The bootargs sent the kernel log at `loglevel=7` to `console=ttyS0,115200` on a
board with no serial attached, so the kernel drove a console nothing was reading
while userspace waited. `--quiet-boot` drops that console and silences the log:

```text
console=tty0 quiet loglevel=0 rdinit=/init baredebug=/dev/mmcblk0p2
```

The milestones measure the lever directly, because each record carries the
kernel's own uptime at the moment it was written:

```text
before   stage=1 init-entered        uptime=3.48
after    stage=1 init-entered        uptime=1.30
         stage=2 command-boot-shell  uptime=1.32
         stage=3 model-Anbernic RG35XX Plus uptime=1.33
         stage=4 framebuffer-present uptime=1.34
         stage=6 userspace-ready     uptime=1.35
```

Kernel init falls from 3.48 s to 1.30 s, and the whole userspace sequence now
completes rather than being cut off partway.

### Distribution, ten cold starts each

```text
                      median  stdev   IQR                 range
loglevel=7 + ttyS0    10.81   1.60   3.27 (8.43..11.70)   3.85
quiet, no ttyS0        9.81   1.18   0.23 (9.65..9.88)    4.51
```

The median falls a second and the distribution tightens sharply: eight of ten
runs now land within a quarter of a second of each other, against an
interquartile range of 3.27 s before.

The raw range is the one number that grew, from 3.85 s to 4.51 s, and it grew
because one run finished in 6.47 s rather than because any run got slower. The
guardrail against improving a median while widening the spread is about
predictability, and standard deviation and interquartile range both improved
substantially. A single unusually fast boot is not a regression, but it is
unexplained, and the same run-to-run variation that produces it is now the
largest remaining source of spread.

### What the budget looks like now

Userspace is reached at 9.81 s, and the kernel reports 1.30 s of its own init,
so roughly 8.5 s is spent before the kernel starts: SPL, U-Boot, the 5.9 s
compressed kernel read, its decompression, and the initramfs and device tree.
The kernel read is now the dominant term by a wide margin.

## 2026-09-18 The host has no clock between 6 and 25 MHz

The card's advertised TRAN_SPEED is now a build option, `--sd-tran-speed`, so
the field and the CRC7 sharing its register are computed together instead of
being edited by hand. Four bitstreams, each measured through the block
capture's own fabric timestamps at the kernel's first sector:

```text
advertised   measured   block span   fabric cycles   result
   12 MHz     6.00 MHz     11103 t        10.67      boots
   13 MHz     6.00 MHz     11103 t        10.67      boots
   20 MHz     6.00 MHz     11103 t        10.67      boots
   25 MHz    25.00 MHz      2665 t         2.56      fails after ACMD6
```

The span is identical to the tick at 12, 13 and 20 MHz, so this is not a
rounding artefact: the host runs this card at 6.00 MHz for every advertisement
below the SD default and jumps straight to 25.00 MHz when it sees 25. There is
no step in between, and 15 MHz was not tried because 20 MHz already lands on 6.

At 25 MHz the boot reaches ACMD6, the four-bit width switch, and stops with 83
sectors served. That is what 2.56 fabric cycles per SD period looks like: the
frontend cannot resolve both edges of the host's clock, so the data phase never
returns a valid block.

### What that means for the plan

The plan's first step, taking the interface to 12 MHz, is not available. The
host offers 6 MHz or 25 MHz and nothing between, so the card interface cannot
be improved without supporting 25 MHz, and 25 MHz cannot be supported at the
64 MHz SD fabric clock.

The trade is now quantified rather than feared. 25 MHz would need roughly 4
fabric cycles per SD period to be comfortable, which means a 100 MHz SD fabric
clock in a design that already needs a seed search to meet 80 MHz, and would
reopen exactly the timing work the 64 MHz build exists to avoid. The reward is
large: 25 MHz across four bits is about 11.8 MB/s against today's 2.95, which
would take the compressed kernel read from 5.3 s to about 1.3 s.

Until that is attempted, every remaining boot-time saving has to come from
reading fewer bytes rather than reading them faster.

## 2026-09-19 The trimmed kernel

`rg35xx/build_kernel.py` builds the kernel the device actually needs. ROCKNIX
pins mainline 7.2 for the H700 with 27 patches, and its own configuration is
published as `linux.aarch64.conf`, so the build takes that source and that
configuration and removes what this device cannot use. The tarball is verified
against the SHA-256 ROCKNIX pins and the patches are fetched at a pinned commit.

Two of ROCKNIX's settings are incompatible with the target and are cleared:
`INITRAMFS_SOURCE`, which holds a build-system placeholder and is not wanted
because the rootfs will be mounted from the card, and `EXTRA_FIRMWARE`, which
builds the RTL8821CS blobs into the image rather than loading them from
`/lib/firmware`. The rootfs carries them instead, which keeps them out of the
bytes the card must read before anything can run.

```text
                      shipped     trimmed
built-in options         1929        1663
uncompressed         30.4 MiB    17.8 MiB
gzip -9              15.0 MiB     7.02 MiB
zstd -19                    -     5.90 MiB
```

Every intended change survived `olddefconfig`: Panfrost, Sun4i, RTW88 with the
8821CS, mac80211, SoC audio and MMC are still built in, Bluetooth is still a
module, USB, BTRFS, NTFS3, NFS, SQUASHFS, EXT4, netfilter, `KALLSYMS_ALL`,
`DEBUG_FS` and KASLR are gone, and EROFS with compression, `EXT2`,
`CC_OPTIMIZE_FOR_SIZE` and `TRIM_UNUSED_KSYMS` are in.

### zstd is not available through this U-Boot

The plan called for storing the kernel zstd, which is 5.90 MiB against gzip's
7.02 and decompresses far faster on an A53. The card serves it correctly: the
block capture at the kernel's first sector shows `28b52ffd`, the zstd magic,
with a matching CRC. U-Boot reads it and writes all four of its milestones, and
then `booti` never starts a kernel. There is no `unzstd` command to use
instead, so the kernel is stored gzip. The difference is 0.4 s of reading.

### Distribution, ten cold starts

Measured to the first multi-block write in the raw debug partition, which is
the initramfs writing through `dd`; U-Boot's own milestones are single-block
writes and are excluded.

```text
                            median   min    max   stdev   IQR
quiet console, old kernel     9.82   6.47  10.98   1.24   0.28
trimmed kernel                5.38   2.23   5.75   1.28   1.65
```

The median falls 4.44 s and the slowest trimmed boot is faster than all but one
of the previous ten. Standard deviation is unchanged, so predictability did not
degrade, but the interquartile range grew because of two unusually fast runs.
One of them, 2.23 s, is below the physical floor: the kernel read alone is
2.50 s at the measured card rate. That points at the measurement rather than
the boot, because the trial's zero is when the power-supply command returns
rather than when the target's rail actually rises. The medians are unaffected;
the fast tail is not yet trustworthy.

## 2026-09-19 The spread was the measurement

Every boot-time figure before this entry is wrong, in a way that flattered the
fastest runs. `rg35xx_trial.py` started its clock when the power-supply CLI
returned, and that CLI has to start a Node process and open a serial port
before it switches anything. Measured across twenty runs, it took between 1.03
and 4.29 seconds to do so. A run where it took three seconds had three seconds
of boot already behind it before the first poll, and was reported as three
seconds faster. That is the entire origin of the run-to-run spread this page
has been chasing, and of the outliers that sat below the physical floor set by
the kernel read.

The fix is to launch the power-on without waiting for it, poll immediately, and
re-zero on what the card itself saw. The obvious anchor does not work: with the
target unpowered the card's clock pin floats and the edge counter still
advances, measured here at about fifty edges a second, so anchoring on the
first clock edge puts the zero at the first poll of every run and changes
nothing. The command counters do not move at all while the target is off,
because a floating line does not produce a frame that passes CRC7. The host's
first command follows its first clock edge by microseconds, far below this
poll's resolution, so it is the same instant for this purpose and it is
unambiguous.

A run is only sound if some poll saw the card quiet before that first command.
Runs that fail that test are reported and discarded rather than averaged in.

Re-measured on that basis, with ten sound cold starts each:

```text
                              median   min    max   stdev   IQR
quiet console, shipped kernel   9.93   9.88  11.07   0.36   0.06
trimmed kernel, initramfs       5.75   5.72   5.83   0.03   0.05
trimmed kernel, EROFS root      5.44   5.42   5.49   0.02   0.02
```

The boot is repeatable to within about thirty milliseconds. There was never a
spread to explain.

## 2026-09-19 EROFS root, A/B slots and a data volume

`rg35xx/build_rootfs.py` builds the system image: the same static BusyBox the
initramfs used, so userspace is a known quantity and the only thing under test
is where it is read from, compressed LZ4HC at level 12. LZ4HC is chosen because
its output is ordinary LZ4, so the kernel needs only `CONFIG_EROFS_FS_ZIP` and
its LZ4 decompressor, and the compression effort is spent at build time. The
result is 1,835,008 bytes: 448 blocks of 4 KiB holding 417 inodes.

### Where the new regions go

They sit behind the debug partition, not in front of it:

```text
LBA 16        eGON SPL                  unchanged
LBA 96        FIT                        unchanged
partition 1   FAT16 boot   32768 +81920  unchanged
partition 2   raw debug   114688 +16384  unchanged
partition 3   extended    131072+137216  new
  partition 5 EROFS A     133120 +32768  new
  partition 6 EROFS B     167936 +32768  new
  partition 7 ext2 data   202752 +65536  new
```

The plan put the system slots between the boot and debug partitions, which
would have moved the debug partition and the raw sectors the kernel is read
from, and every one of those addresses is qualified and compiled into a boot
script, a trace capture and the target's own init. Appending instead leaves all
of them byte for byte identical, which is checked by a test. It costs one
primary slot, so the three new regions are logical partitions inside an
extended one; Linux numbers those from five, and that is the numbering the root
argument uses.

The two system slots are exactly the same size, so either is bootable and an
update can be staged into the inactive one without moving anything. The active
slot is compiled into `BOOT.SCR` rather than read from the debug sector at run
time: reading it would need `setexpr`, which this U-Boot has not been shown to
have, and a script that aborts on an unknown command produces neither a boot
nor a milestone to diagnose it with. Switching slots rewrites one file, which
is what an update would do anyway.

### There is no initramfs any more

U-Boot reads the kernel and the device tree and nothing else. `booti` is given
a dash where the ramdisk went, and the kernel mounts the system partition
straight off the card. The 1.53 MB initramfs is neither read nor unpacked.

### What the cluster size actually costs

The physical cluster is the unit the kernel reads and decompresses, so it was
built as an option and measured rather than assumed. With a 64 KiB cluster the
card sees 4 KiB reads for metadata, 64 KiB reads for single clusters, and
128 KiB and 192 KiB reads where readahead merged adjacent ones. The whole mount
and start of init reads about 1.1 MB, against the 1.53 MB the initramfs cost,
and the phase takes 0.5 s of the boot. Since BusyBox is a single 1.1 MB static
binary and starting it faults in most of its text, a smaller cluster has little
left to save here; it would matter for a rootfs whose access pattern is sparse.

### Where the remaining 5.44 seconds go

```text
0.00 - 1.05   SPL, FIT and U-Boot proper
1.10 - 3.89   kernel read, 7.36 MB
3.89 - 4.27   gunzip and device tree
4.27 - 4.93   kernel init to partition scan
4.93 - 5.44   EROFS mount, paging and init to its first milestone
```

Half the boot is one transfer. The payload work is close to done: the kernel is
already trimmed and the rootfs is already demand paged. What is left is the
interface, and that is the step the ladder measurement blocked.

## 2026-09-19 Pinning what the kernel was built from

`build_kernel.py` does not fetch ROCKNIX's patches or configuration; they are
prepared in the work directory out of band, and until now nothing recorded
which commit they came from. A stale re-fetch running in the background
rewrote three of the twenty-six patch files after the measured kernel had been
built, which is what surfaced this. In that instance the branch tip had not
moved and the rewritten files were byte for byte identical, so the measured
kernel was never in doubt, but nothing in the tree could have shown that.

`rocknix-sources.json` now records the commit, a SHA-256 for every patch and
one for the configuration, and the build refuses to run against a tree that
does not match. Missing, extra and altered files are all refused, because all
three change the kernel. Moving to a newer ROCKNIX tree is done deliberately
with `--allow-unpinned` and re-recording the manifest.

## 2026-09-19 The three stages, measured

### The protocol

A standardized cold start is one run of `rg35xx_trial.py`: the target's channel
is switched off synchronously, held off six seconds, then switched on without
waiting for the power CLI while polling is already running. The clock is zeroed
on the first command the card saw, not on the power command, and a run counts
only if some poll saw the card quiet before it. The end is the first
multi-block write in the debug partition: U-Boot writes one sector per
milestone, and every write from Linux goes through the page cache and is at
least a page, so the command itself or a jump of a page in the sector counter
both mark userspace. The image is checked with `--verify-image` before upload
and the upload verifies its own SHA-256 against the file.

### Stage 1, the card interface: blocked, and the rate

The rate is derived from the FPGA's own timestamps: it counts the clock edges
across one 512-byte block and the fabric ticks between the first and the last,
so the figure depends on nothing the host reports and nothing the CSD claims.
Over ten cold starts of the delivered build:

```text
card clock   6.001 MHz   stdev 0.0000
throughput   2.951 MB/s  stdev 0.0000
```

Bit-identical every run. At that rate the 7,363,461-byte kernel takes 2.50 s,
which is 46% of the boot.

The interface could not be raised. The card's advertised `TRAN_SPEED` was made
a build option and swept: at 12, 13 and 20 MHz the host clocks 6.00 MHz, and at
25 MHz it clocks 25.00 MHz. There is no divisor between them to ask for, so
12 MHz is not reachable by advertising it. 25 MHz is reachable and unusable: it
leaves 2.56 fabric cycles per SD period against the 64 MHz SD fabric clock, and
serving it needs roughly 100 MHz, which is the timing work that build exists to
avoid. The step is blocked, and every later stage is measured against the rate
above rather than a hoped-for one.

### Every stage against the same clock

```text
                                  n   median   min    max   stdev   IQR
stage 1  baseline, shipped kernel  10   9.93   9.88  11.07   0.36   0.06
stage 2  trimmed kernel, initramfs 10   5.75   5.72   5.83   0.03   0.05
stage 3  trimmed kernel, EROFS     20   5.44   5.41   6.72   0.29   0.02
```

Each stage improves the median and none widens the interquartile range, so
none is a regression by the standard set for this work. The standard deviations
are carried by a single slow boot in each of stage 1 and stage 3, at 11.07 s
and 6.72 s; both runs have a sound zero, so they are real boots and not
measurement noise. Nineteen of the twenty stage-3 runs fall within 80 ms of
each other.

The target was under four seconds and the result is 5.44. The two payload
stages delivered 4.49 s of the 5.9 s that would have needed; the rest was in
the interface, and the measurement above shows why it could not be taken.

## 2026-09-19 Reading U-Boot's environment, and what zstd really needs

The board has no serial header populated, so a variable U-Boot resolves at run
time could not be read at all. `--export-env` adds two lines to the boot
script: `env export -t` renders the whole environment into memory as text and
`mmc write` carries it back through the debug partition, into sectors 8..15,
between U-Boot's milestones and userspace's.

It came back empty, and that is itself the result. Sector 8 holds exactly what
sector 1 holds, the uninitialized contents of `ramdisk_addr_r`, so the write
happened and the export before it produced nothing. **The boot then continued
and reached userspace anyway.** This U-Boot does not abandon a script when a
command in it fails.

That correction matters twice. It retires the reason given earlier for
compiling the active A/B slot into `BOOT.SCR` rather than reading it at run
time: a missing `setexpr` would not cost the boot, it would fall through to
whatever the script set before it. And it means the zstd failure was never an
aborted script; `booti` was reached, and declined.

### zstd, with both of booti's prerequisites met

`booti` takes a compressed image at `kernel_addr_r`, expands it into
`kernel_comp_addr_r`, and refuses unless `kernel_comp_size` is also set. The
first attempt set neither the load address convention nor that size, which is
enough on its own to explain a silent stop, so it was retried properly: the
6,190,080-byte zstd kernel read into `kernel_addr_r`, `kernel_comp_size` set to
32 MiB, `booti` given the image.

It read all 12,090 sectors, wrote all three of its milestones, and then went
back to rescanning the boot partition's root directory and stopped. No
userspace milestone was written. With both documented prerequisites satisfied
and the image served correctly, what remains is that this U-Boot has no zstd
decompressor built in: its magic sniffing does not recognize the image, so it
is treated as a raw arm64 Image, whose magic check then fails.

The kernel therefore stays gzip, expanded by `unzip`. The cost of that decision
is 1.17 MB of extra reading, 0.40 s at this card's rate. Changing it means
replacing U-Boot, which is a larger change than the saving justifies while the
card interface is the binding constraint.

## 2026-09-19 ThinLTO makes the kernel smaller and the boot slower

The plan asked for the kernel to be built for size with ThinLTO, so
`build_kernel.py` gained `--toolchain clang`, which installs clang, lld and
llvm's binutils, builds with `LLVM=1`, and turns on `LTO_CLANG_THIN`. It
refuses to continue if `olddefconfig` does not keep the option, so a build that
quietly dropped it cannot be mistaken for one that used it. The same run also
took `--trim-network-and-crypto`, which drops every wireless vendor but
Realtek, the wired ethernet drivers, the protocol menus this device never
speaks, and the crypto algorithms outside what WPA selects.

It worked, and it is a regression:

```text
                      built-in   uncompressed      gzip -9
gcc, -Os                  1663     18,659,336    7,363,461
clang, ThinLTO, -Os       1598     18,294,792    7,969,628
```

ThinLTO removed 364,544 bytes of kernel and added 606,167 bytes to what the
card has to read. Cross-module inlining and specialization cut instructions by
replacing repeated call sequences with specialized ones, which is exactly the
repetition gzip was exploiting. On a device where the kernel is read at
2.63 MB/s, the compressed size is the only size that matters, and ThinLTO costs
0.23 s of boot.

The plan asked for it on the reasonable assumption that a smaller kernel is a
faster boot. Measured against the thing that is actually slow, it is not. The
shipped kernel stays gcc.

Every keep survived the run, checked symbol by symbol: Panfrost, Sun4i, RTW88
with the 8821CS, cfg80211, mac80211, SoC audio, the Sunxi MMC controller,
EROFS with compression, EXT2, VFAT, EXFAT, gpio-keys and the AXP717, with
Bluetooth still a module. The crypto trim kept AES and CCM, which mac80211 and
RTW88 select, and dropped Twofish, Serpent, Camellia, the user-space API and
the rest.

## 2026-09-19 Three kernels, and the last of the payload

Building the network and crypto trim twice, once with each toolchain,
separates what the trim does from what ThinLTO does:

```text
                              built-in   uncompressed      gzip -9   read
gcc, -Os                          1663     18,659,336    7,363,461   2.80 s
gcc, -Os, net and crypto trim     1590     18,323,464    7,190,891   2.73 s
clang ThinLTO, same trim          1598     18,294,792    7,969,628   3.03 s
```

The trim is worth 172,570 compressed bytes. ThinLTO, applied on top of the
identical configuration, costs 778,737. It is the toolchain and not the
configuration that made the earlier clang build worse, which is only visible
because both were built.

Every keep survived the trim: Panfrost, Sun4i, RTW88 with the 8821CS,
mac80211, SoC audio, EROFS with compression, EXT2, VFAT, EXFAT, gpio-keys and
the AXP717, Bluetooth a module, and AES and CCM kept by the selects mac80211
and RTW88 carry while Twofish, Serpent, Camellia and the user-space API went.

### The delivered image, twenty cold starts

```text
                        n   median   core span        slow boots
gcc trim, EROFS        20     5.44   5.41-5.49 s      1 at 6.72 s
+ net and crypto trim  20     5.38   5.34-5.43 s      2 at 6.61, 6.68 s
```

The median falls 0.07 s, which is what 172,570 bytes at 2.63 MB/s predicts, and
the core spread is unchanged at about 90 ms against a 50 ms poll. The slow-boot
rate, one and two in twenty, is not distinguishable at this sample size.

### What the slow boots are

They are not the card and not the measurement. Lining a slow run up against a
normal one, every stage matches until the partition scan, and then:

```text
                              normal    slow
partition table scanned         4.93    4.83
first read from system A        5.09    6.31
```

The gap is between Linux finishing the partition scan and the root filesystem
becoming mountable, so it is the root device not yet being there when the
kernel first asks and `rootwait` sleeping before it asks again. It appears in
both EROFS configurations and never appeared with the initramfs, which is what
would be expected: an initramfs root is already in memory, while this root has
to be discovered on a device that is still probing. It costs about 1.4 s when
it happens, in roughly one boot in ten, and it is not diagnosed further here
because the board has no console to watch the retry on.

## 2026-09-19 The gateware toolchain stopped working

Building any bitstream failed, twice, with nextpnr dying on SIGABRT inside the
negative-edge timing probe. It looked like a placement failure on a new
configuration and was not one: nextpnr is linked against Homebrew's Boost by
absolute path, Homebrew has moved to 1.92.0, and the symbol
`boost::program_options::arg` is gone from it. The binary cannot load at all,
so `nextpnr-xilinx --version` aborts just as readily as a real run does.

Homebrew keeps the previous version in the Cellar, so the fix is to point
`DYLD_LIBRARY_PATH` at it:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib ./.venv/bin/python \
  experiments/openxc7-macos/build_ddr.py ...
```

`./.venv/bin/python` rather than `uv run`, because macOS strips
`DYLD_LIBRARY_PATH` when a process is re-executed through a signed launcher,
which is the same reason this file already recommends it.

`check_place_and_route_runs` now runs before anything spawns nextpnr and turns
this into one line naming the Boost mismatch and the Cellar paths to try,
instead of a SIGABRT from whichever subprocess happened to reach it first.

## 2026-09-19 15 MHz closes the advertised-speed ladder

The sweep that found no rung between 6 and 25 MHz skipped 15 MHz on the
grounds that 20 MHz already landed on 6, which left the one untried rung
between the two the plan cared about. A bitstream advertising 15 MHz was
built, seed 7, `fde8dbe0b519…`, with every clock met at the 64 MHz SD fabric
clock: `fclk` 73.44 MHz and `dclk` 85.51 MHz.

One standardized cold start on it, carrying the delivered image
`bd44e08c…`, measured the interface through the FPGA's own block capture:

```text
card clock   6.00 MHz
throughput   2.95 MB/s
```

Identical to every other advertisement below 25, to the fabric tick: 11,103
ticks across 1,041 sampled edges, the same numbers the delivered build
produces. The boot completed normally and reached userspace at 5.27 s.

That finishes the ladder. 12, 13, 15 and 20 MHz all yield 6.00 MHz and 25
yields 25.00 MHz, and those are every representable `TRAN_SPEED` rung between
the two, so no advertised speed reaches the four-second target. Why the host
picks those two divisors and nothing between them is still not established
from outside the board.

## 2026-09-19 The display works, and turning it on breaks the card

### The screen was dark because the kernel build dropped its firmware

Asked to show something on the panel, the first thing the target said was that
it had no framebuffer: the stage-5 milestone of the delivered image reads
`framebuffer-absent`. The display stack in the trimmed configuration is option
for option the same as ROCKNIX's, so the kernel was not missing a driver. It was
missing a file. The panel driver from patch 0110 asks the firmware loader for
`panels/<compatible>.panel`, here `panels/anbernic,rg35xx-plus-panel.panel`, and
gets its init sequence from it. ROCKNIX's shipped kernel has all ten of its
panel files compiled in, which is visible in the binary: the pinned 695-byte
file occurs in it verbatim. `build_kernel.py` cleared `EXTRA_FIRMWARE` to keep
the RTL8821CS blobs out of the image the card has to read, and the panel files
went with them. It now builds the two RG35XX Plus panel files in, verified
against `rocknix-sources.json` like the patches, and with them the kernel logs
`panel-mipi spi0.0: Modeline "640x480" ... added` and binds the mixers, the TCON
top and the LCD controller at 0.438 s.

### A flight recorder, because there is no console

The second page of the userspace range in the debug partition, sectors 24..31,
is now the tail of the kernel log, rewritten ten times a second from the first
milestone on and read back with `image --kernel-log`. On its first outing it
returned the first kernel log anyone has read from this board:

```text
[    0.409899] panel-mipi spi0.0: supply io not found, using dummy regulator
[    0.410152] panel-mipi spi0.0: Direct firmware load for panels/anbernic,rg35xx-plus-panel.panel failed with error -2
[    0.410178] panel-mipi spi0.0: probe with driver panel-mipi failed with error -2
```

### The proof, and what it cost to believe it

The display was proven by a photograph. The image of 2026-09-18 that boots
ROCKNIX's shipped kernel with the old initramfs shows, on the panel, backlit
and sharp: `RG35XX Plus bare Linux bring-up`, `ROCKNIX kernel reference; custom
initramfs; no SYSTEM image`, `Model: Anbernic RG35XX Plus`, `Framebuffer:
/dev/fb0 present`, and a blinking cursor. The panel had been working under the
shipped kernel all along; nobody had looked at it.

Every boot that lights the panel then stops reporting through the card within
about a second, under the shipped kernel and the trimmed one alike. Three
explanations were held for that in turn, and each was wrong:

- *Binding the display after the kernel disables unused clocks hangs the SoC.*
  The first attempt carried the firmware in the rootfs and re-probed the panel
  from init, and reporting stopped at once. But it stops just the same when the
  display binds at 0.438 s from built-in firmware, and under ROCKNIX's kernel.
- *Init blocked on a console held by a wedged display.* The stall first
  appeared at an `echo`, so init was taken off the console. It was blocked in
  the card write beside it; the console was never stuck, and that change was
  reverted.
- *The board browns out when the backlight switches on*, fed from USB-C with no
  battery. The supply sat at 4.997 V, about 0.19 A, in constant-voltage mode
  throughout, the screen stays lit for minutes, and the cursor keeps blinking:
  the kernel is alive.

What is true was on the panel once the kernel was allowed to speak
(`loglevel=7`, the same image otherwise):

```text
[    1.355599] sunxi-mmc 4020000.mmc: data error, sending stop command
[    2.352581] sunxi-mmc 4020000.mmc: send stop command failed
```

A write from Linux to the emulated card fails with a data error shortly after
the panel starts, the stop command that should recover from it times out, and
the MMC layer never tries again. From the card's side the last thing sent is a
CRC-status token on DAT0, partway through a multi-block write, after which the
host never clocks again; the card is idle in `tran`, not holding busy and not
driving the data lines. In hundreds of boots without a working panel the same
writes never failed once.

A control run on the display-less image matters as much as the failure. Its
trace shows `pin_data.serializer_mismatch` with a count of 331,
`pin_response.serializer_mismatch`, and a minimum clock period of zero fabric
cycles, all in a boot that wrote 67 sectors without error. Those monitors do
not distinguish a failed link from a healthy one and must not be read as if
they did.

What is open: why the write fails. The emulator does not drive the data lines
between the blocks of a multi-block write, this host has no working pull-up on
DAT0, and a running panel adds both electrical noise and DMA contention that
stretches the gaps between blocks, so a false start bit on a floating DAT0 is
the leading suspect; and once the host stops clocking, the liveness gate stops
the card's idle-high drive, which would leave DAT0 low and the host waiting for
a busy that never ends. Neither is established. The trace records nothing about
the write path, so the next step is to make it record what the card saw: blocks
received, blocks failing CRC16, the status token sent, and the longest gap
between blocks.

### What the bench taught on the way

The RG35XX's supply module drops off its controller for a minute or two at a
time. While it is gone the CLI either prints a status of all zeroes with the
output shown OFF, or does not know the `psu2` command at all. `deploy` took the
first form as proof the target was off, `trial` switched on a channel that was
not listening, and an `off` sent into a dropout left the target powered for
minutes after a run had ended. Both tools now refuse a module that is not
reporting, and `trial` confirms its power-off by reading the status back and
repeating the command until the supply agrees.

`trial` also anchored its clock on the first command frame of any kind, and
switching the supply glitches the floating lines into a frame that fails its
checksum; it anchors on the first valid command now. Its JSON keeps the FPGA's
whole final trace, because that is the post-mortem.

`build_rootfs.py` staged its payload in the system temporary directory, which
colima does not share with its VM, so the container saw an empty `/payload` and
failed five minutes in; it stages inside the output directory now. That bug
came in with the cleanup and no unit test could have seen it.

`build-kernel --fetch` was the first real use of the pinned fetcher and ran out
of GitHub's anonymous quota, sixty requests an hour, at the twenty-third patch.
It now lists each of ROCKNIX's two patch directories once instead of asking for
every patch in both, and goes through the authenticated `gh` CLI when there is
one; with the anonymous quota at zero it fetched all 27 sources and both
firmware files in twelve seconds.

## 2026-09-19 The card failed at Linux's clock, not at the display

Everything in this entry was measured with nobody at the bench. The picture is
checked by the target: init reads back the 1,228,800 bytes the panel is scanning
out and reports the first half of their MD5 in the stage-5 milestone, and
`display_proof.py --expect` prints what it has to be. `fb-md5-add757487e3a9f6f`
is the picture, whole.

### Pull-ups: one helps, five stop the boot

`build_ddr.py --sd-pullups` turns on the FPGA's weak pull-ups on CMD and
DAT0..3. With them the target reads the SPL, 83 sectors ending at LBA 96, and
then sends nothing more: the host goes on clocking at about 200 kHz and no
command follows. It is the pull-ups and not the placement. A pull-up is one
configuration bit in an I/O block, so the routed design of the qualified
bitstream was patched rather than rebuilt: the FASM of seed 19 with
`PULLTYPE.NONE` changed to `PULLTYPE.PULLUP` on the same five sites differs from
the qualified bitstream in exactly five configuration bits, and stops at the
same place. Which of the five lines does it was not pursued.

With a pull-up on DAT0 alone (F3, `RIOB33_X43Y73.IOB_Y1`) the display image
booted, drew, and reported: stage 5 came back with the right checksum. The link
no longer died at its first error. It died later instead, after 370 writes and
some twenty-five `data error, sending stop command` lines, with 37 command
frames failing their checksum at the card, where a healthy boot has one. So
DAT0 floating was making one error fatal, and was not what made the errors.

### Not the backlight, and not measurable at 12.5 MHz

The first error landed at 1.147 s, just after init raised the backlight, which
made the backlight the suspect for an afternoon. Init was given a host command,
`display-sweep`, to measure it: put the display to sleep, do a fixed piece of
card work in each of a series of display states, count the controller's errors
in each, and write every record with the display asleep. It never got to
measure anything. With the backlight untouched, with it put out before the
second milestone, and with the whole pipeline asleep, the link died within a
fifth of a second of the first error every time, the first error at 1.08 to
1.09 s in each. The command is kept; it works at a clock where the link
survives a state that disturbs it.

### The clock

What the runs had in common was in the trace all along. The card counts clock
edges, and the rate between polls is 6.00 MHz for as long as U-Boot is reading
and 12.5 MHz from the moment Linux takes the card over. It is 12.5 MHz in the
display-less boots of the delivered image too, where it never failed: the card
advertises 13 MHz, U-Boot rounds that down to 6 and Linux to 12.5. The
interface rate quoted everywhere in these notes is U-Boot's, measured on a
sector of the kernel load.

So the device tree was given `max-frequency = <6000000>` on `mmc@4020000`, and
nothing else was changed. The first attempt changed nothing at all, which the
trace also showed, as 12.5 MHz: `--replace-file` had moved `DTB.IMG` to new
clusters and the boot script reads it by sector, so U-Boot loaded the old tree
from where it still lay. `--verify-image` now refuses an image whose script
reads raw sectors that are not where `KERNEL` and `DTB.IMG` lie.

With the cap really in the tree, on the DAT0 pull-up bitstream and then on the
qualified bitstream with no pull-up at all, the same image, backlight at full:

| Linux card clock | bitstream | writes before the link died | controller errors | bad command frames |
| --- | --- | --- | --- | --- |
| 12.5 MHz | qualified | about 20 | 1, fatal | 1 or 2 |
| 12.5 MHz | DAT0 pull-up, five runs | 56 to 370 | 1 to 25 | 4 to 37 |
| 6 MHz | DAT0 pull-up | never; 2855 in 31 s | 0 | 1 |
| 6 MHz | qualified | never; 2855 in 31 s | 0 | 0 |

The card's receive path samples CMD and DAT with the fabric clock, 64 MHz, on
the fabric edge where it first sees SD_CLK high: up to 15.6 ns after the host's
rising edge. A default-speed host changes its lines on the falling edge, which
is 83 ns after the rising one at 6 MHz and 40 ns after it at 12.5 MHz, so at
Linux's rate the sample sits much nearer the moment the line changes. Without the display that margin was enough in every
boot measured. With the display running it is not. That is the mechanism as far
as it has been established: the failure needs both the faster clock and the
display, and removing either removes it. Whether the display costs the margin
through supply noise on the SoC's I/O rail or through something else has not
been measured, and the write-path forensics proposed in the last entry were not
needed to find this and have not been built.

`image --make-erofs-image --card-max-hz 6000000` puts the cap in through the
pipeline, before the boot script is written. The image built that way,
`build/rg35xx-display/rg35xx-plus-display-6mhz.img` (sha256 `f623878c3a23...`),
was then cold-started five times on the qualified bitstream: five pictures with
the right checksum, no controller error in any kernel log, and the recorder
still writing when each 15 s window closed. The cap costs the Linux part of the
boot its faster reads: the userspace milestone was 5.66, 5.69, 5.71, 5.71 and
5.76 s, against about 5.5 s for the same image at 12.5 MHz.

### The sweep, run at last, and why 10 MHz is not a middle way

At 6 MHz the link survives, so `display-sweep` could finally be run to its end.
Its record, from the qualified bitstream:
`display-sweep initial-1250 max-2499 asleep=w0r0/Off lit-0=w0r0/On
lit-100=w0r0/On lit-50=w0r0/On asleep=w0r0/Off done`. No write error and no read
error in any display state, DRM agreeing that the output was off when it was
meant to be and on when it was not, and the kernel's own choice of backlight
half way up, where the PWM switches.

The same sweep with the cap at 10 MHz read the same, clean in every state, with
4321 writes behind it and the userspace milestone back at 5.52 s, which is what
12.5 MHz gives. One run is not a qualification, and this one showed why. Of five
cold starts of the ordinary display image at 10 MHz, four were clean, at 5.49 to
5.55 s, and the fifth died 0.2 s into userspace with the signature of every
12.5 MHz failure: the last command a CMD25, a seven-edge status token on DAT0,
the card idle in `tran`, and no clock after it. It had not seen one bad command
frame first. So the failure thins out between 12.5 and 6 MHz rather than
stopping at a threshold, one boot in six at 10 MHz against every boot at 12.5,
and a rate that looks clean in one run has to be cold-started many times before
it is believed.

Ten more cold starts at 6 MHz followed for that reason: ten pictures with the
right checksum and no controller error. With the five before them, the two long
runs and the sweep, that is eighteen boots at 6 MHz without a failure, against
one in six at 10 MHz and every one at 12.5.

### The slow boots, caught by the recorder

Two of those ten reached userspace at 6.88 and 6.90 s instead of about 5.7, the
slow boot that has been in every batch since the EROFS root and was put down to
`rootwait` retrying. The recorder had the kernel log of both, and it is not the
emulated card at all:

```text
[    1.187723] sunxi-mmc 4022000.mmc: fatal err update clk timeout
[    1.947722] sunxi-mmc 4022000.mmc: fatal err update clk timeout
[    1.961071] sunxi-mmc 4022000.mmc: initialized, max. request size: 2048 KB, uses new timings mode
[    1.964085] VFS: Mounted root (erofs filesystem) readonly on device 179:5.
```

`4022000.mmc` is the second card slot, which holds a real 119 GiB card. In the
eight normal boots its controller logs no timeout, the card is announced as
`mmc1: new high speed SDXC card`, and the root is mounted at 0.73 to 0.74 s. In
the two slow ones the controller times out updating its clock, six times in the
log at 0.75 s apiece, the card is never announced, and the root is mounted at
1.95 and 1.96 s, the moment that controller's probe returns: the kernel waits
for every probe in flight before it mounts the root, so a slot this boot does
not use holds up a root that was ready a second earlier.

## 2026-09-19 The delivered image takes the cap too

The display-less image never failed at 12.5 MHz in twenty cold starts, and the
display image showed how little that says: 10 MHz looked clean for a sweep and
four boots before the fifth died. The emulated card is an instrument for getting
to a real card, not the product, so its margin matters and its speed does not.
The delivered image was rebuilt with `--card-max-hz 6000000` and nothing else
changed. Without the option the recipe still gives `bd44e08c...` byte for byte;
with it, `93e49da1e5a1313f19539018b3354b5c25b4ebe3de4ff432519daa81a3980cb3`,
kept as `build/rg35xx-bare/rg35xx-plus-bare-erofs-6mhz.img`.

Twenty cold starts on the qualified bitstream: median 5.58 s, 5.53 to 5.64,
standard deviation 0.03, interquartile range 0.05, against 5.38 s uncapped. Every
run reported stages 0 to 5 and 7, the card's edge counter put Linux at 6.0 to
6.4 MHz in each, and the only command frames that failed their checksum were at
the power edge and in the SPL's re-initialisation, 0.09 s in, none under Linux.
There was no slow boot among them. The cap is an option and stays one: it is for
the emulated card, and an image for a real card must not carry it.

The three bitstream directories the pull-up experiments left behind,
`microsd-ddr-h700-pullups`, `-seed19-pullups-fasm` and `-s19-pull-dat0`, were
removed with `prune_builds.py`, 413 MiB; their manifests are in
`build/pruned-manifests/`. The DAT0 variant is one FASM feature away from the
qualified routing, `PULLTYPE.PULLUP` in place of `PULLTYPE.NONE` on
`RIOB33_X43Y73.IOB_Y1`, and repacking it takes a minute.


## 2026-09-20 A harness for experiments, and what sleeping costs

The next thing wanted from this target is the smallest current it can be made
to draw in a timed sleep, which is a dozen small experiments rather than one.
Rebuilding a rootfs, an image and a deployment for each of them is eight
minutes; the experiments themselves are seconds. So the boot got a job runner:
a host command like `display-sweep`, but one that loops, reading a shell script
out of the card, running it, and writing back what it printed. The host side is
`rg35xx.py job`, which delivers a script, powers the target through it, samples
the bench supply, and reads the result off.

Four things had to be corrected before any of it worked, each of them something
the bench said rather than something that was designed.

**The gateware only takes a write as part of an ascending run from sector
zero.** A session declares how many sectors it will receive and each write must
land at exactly the next one. The job region had been put in the debug
partition at sector 114688, where a single sector costs 57 MB of rewriting,
about three minutes. It moved into the gap between U-Boot's FIT image, which
ends at sector 1228, and the first partition at 32768: delivering a job is now
a replay of the image's first 2112 sectors with the job substituted, which at
the 707 sectors a second this link writes is three seconds. The target reads it
from `/dev/mmcblk0` by absolute LBA and still writes only inside the debug
partition. The host command moved into the image for the same reason. The
result region can no longer be cleared before a run, so a result is matched to
its job by sequence number.

**A write's LBA does not survive in the trace.** The plan was for the target to
write one sector nothing else uses, so the host could see in the passive trace
that it had reached a point. It cannot: Linux polls the card's status after
every transfer and that poll's argument is the card's address, so by the time
the host looks the write's sector is gone. A read works -- one command with the
sector in it, kept until the next read -- so the target now reads the sector it
just wrote. Two such signals need two pages between them, because the trace
reports a read of a page either at its first sector or at the sector after its
last, and one page of separation made a job's card check indistinguishable from
a suspend.

**BusyBox `dd iflag=direct` reads through the page cache.** The runner polled
the job region once a second and the card saw one read and then nothing for
thirty-two seconds. The flag is accepted and the card saw nine sectors for a
one-sector read, which is readahead, so it was never O_DIRECT at all. The one
read that did reach the card was the one after a card check, which drops the
caches itself. The runner now drops the buffers before every read, with
BLKFLSBUF and `drop_caches` both.

**The supply's serial port takes one speaker at a time.** The sampler and the
power-off ran into each other on the first measured run, the off was lost, and
the target ran on for minutes after the run had reported itself finished. Every
conversation with the supply now goes through one lock and the sampler stops
before the power-off.

Two smaller ones followed from watching real runs. A job is finished when the
runner is steadily polling again, not when the card goes quiet: quiet is
exactly what a suspended target looks like, and cutting its power for being
quiet is the one mistake this harness must not make. And a measured state is
left alone for two seconds after it begins, because entering a suspend the
kernel syncs filesystems and that write, landing a fraction of a second after
the target's own mark, read as the end of the state and cost the whole sleep
window on the first exchange attempt.

What it then measured is in the findings' Sleep section. In short: there is one
sleep state, s2idle, because the device tree has no `cpus/idle-states` and the
kernel has no cpuidle driver bound; `deep` and `shallow` are refused with
EINVAL. Six sleeps and six RTC wakes, none failed, the RTC accounting for 46
seconds of a requested 45 and the card's clock counting exactly zero edges for
the whole of it. Asleep the board draws 121 to 126 mA, awake and idle with the
panel asleep 144 to 151, with the panel lit at the kernel's own level 176 to
183, and at full brightness 246 to 252. The backlight costs four times what the
suspend saves. Two runs of the same state differ by about 7 mA, which is the
figure any later comparison has to beat.

And the exchange works: with the target suspended and issuing no card command
at all, the frontend can be disarmed, the result the job flushed on its way
down read, the next job written and the frontend re-armed, in three seconds of
a seventy-second sleep. The target wakes onto a card that was withdrawn and put
back, re-initialises it without being asked, and runs the next job within a
fifth of a second, with no controller error and no bad command frame. Two jobs
for one boot.

## 2026-09-20 One knob out of a dozen, and a reference point worth more

With the harness built and the baselines taken, the question was how far the
sleeping current could be pushed down. Seventeen experiments later the answer
is eleven milliamps, from one knob, and the interesting part is everything
that turned out not to matter.

**The first three attempts measured the bench, not the knobs.** The plan was
paired: a reference sleep, the knob, another sleep, both in one boot, which
takes the seven milliamps of between-boot noise out. The first job did two
sleeps back to back and the host reported one window. The wake, the mark, the
card check and the next suspend all fit inside a single trace poll, so the end
of the first window and the start of the second were the same event and the
second was never opened; three seconds of deliberate quiet between sleeps
fixed it and every script here has them. Then a ladder of device unbinds
measured 126, 116, 130 and 134 milliamps for four states that should have been
monotonically cheaper, which was the second lesson: the current climbs through
a boot. Six identical sleeps in a row read 121, 125, 125, 128, 126 and 129 --
about a milliamp and a half per cycle, always the same direction. A knob
measured once, after its reference, is three milliamps out before anything
real happens. Everything that decided anything afterwards alternates A B B A
A B, which puts both groups at the same mean position in the run.

That correction changed two answers. Offlining three of the four cores looked
like ten milliamps in the ladder and was nothing at all when alternated: 124
against 127, the wrong way round. Unbinding the two card controllers that are
not the root device looked like ten and was one, even though both of their
regulators -- `vcc-wifi`, for a part with no driver bound, and `vcc3v3-mmc2` --
genuinely went off and came back six times. And the one knob that survived was
one the ladder had underrated: the `powersave` cpufreq governor, which pins
the policy at 480 MHz and takes `vdd-cpu` from 1.1 V to 0.9 V, read 126 mean
against 115 mean over three alternations. Combined with the offlined cores it
read 123 against 112 -- the same eleven milliamps, which is how it became
clear the cores were contributing none of it.

**Two jobs cost a wake.** A screen that applied every knob at once armed its
alarm, wrote its result to the card and suspended, and the board never came
back; so did the device half of it on its own. A ladder found the culprit on
the fourth rung: unbinding `panel-mipi` from spi0.0 while `sun4i-drm` still
holds the panel. With the DRM master unbound first, the same unbind and nine
more underneath it are harmless -- the display pipeline can be taken down
entirely at runtime and the target still wakes -- and it is worth nothing, not
one regulator changes state.

**Nothing else sysfs can reach is worth anything either.** The last screen
unbound twenty-five devices at once on top of the kept governor: the whole
display pipeline, the GPU, three audio codecs, both non-root card
controllers, the backlight PWM, the watchdog, the eFuse, the spare UART, the
PMIC's ADC and its battery and USB power-supply drivers, the SoC's ADC, and
both LEDs off. 112 milliamps before, 109 after, with the drift running the
other way. The rails still standing afterwards are the answer: `vdd-dram`,
`vdd-gpu-sys`, `vcc-pll`, `vcc-io`, `avcc`, `cpusldo`, `vcc-spkr-amp`, and
`aldo3` and `dcdc4`, which have no users at all and cannot be switched off
because the one attempt the kernel makes lands at 32 seconds of uptime, inside
the first suspend, where the PMIC's I2C controller is suspended and answers
`-ETIMEDOUT`. It is never retried.

**And then the reference point, which is not a sleep and is worth more than
all of it.** `poweroff -f` with 5 V still on the USB-C port leaves the board
at 33 milliamps -- the steadiest reading this bench has taken, a 2 mA
interquartile range where a sleeping target gives 7 to 18 -- and the RTC alarm
brings it back. Sixty seconds out, twice in one run, both within a second. The
control says it is really the alarm: with the alarm cleared the board powered
off and the card saw nothing for the remaining 193 seconds. So a timed wake
that can afford to lose its state costs a quarter of what s2idle costs, and
the twelve-second cold boot is the price.

The kept configuration was then run ten times in a row, twice, in one boot
each: twenty sleeps, twenty wakes, RTC elapsed 41 seconds for a requested 40
on all of them, `suspend_stats/success` 0 to 10 and `fail` 0 in both runs, and
twenty-four card checks all good. Sixteen of the twenty current windows are
sound and run from 110 to 119 milliamps; the other four lost two or three
readings each to the supply's link dropping, which is a hole in the
measurement rather than in the sleep.

So: 126 milliamps asleep at the start of the day, 114 at the end, 139 awake
and idle, and 33 powered off. The suspend is worth about 25 milliamps and the
governor about 11, and everything below that is a device-tree and firmware
question -- there is still no `cpus/idle-states`, the DRAM is still not in
self-refresh, and no power domain is collapsed by anything s2idle does.

## 2026-09-20 A bootloader of our own, and a suspend that stops the CPU PLL

The sleep work ended at s2idle because the firmware offered nothing else, and
said so: the next real saving is in the firmware. kailashrs had by then done
that work for the H700 and ROCKNIX merged it the day before -- TF-A hands
control to a program in SRAM A1 which puts the LPDDR4 into self-refresh and
waits -- but nobody had published what it is worth in milliamps. This bench can
answer that, and answering it meant building the firmware here first.

**Stage 0: the bootloader from source, proved equal to the one it replaced.**
ROCKNIX's H700 DDR4 bootloader is mainline U-Boot v2026.01 with one patch to
the H616 DRAM driver and one defconfig, carrying a BL31 from TF-A v2.12.0, and
`rg35xx.py build-firmware` now builds exactly that in the same arm64 container
the kernel uses, where the compiler is native. Two things needed finding out.
TF-A v2.12's toolchain machinery derives the assembler, linker and archiver
from the C compiler, but reads an empty `CROSS_COMPILE` as a request for the
`aarch64-none-elf-` prefix rather than for the native one, so the compiler has
to be named: `CC=gcc`, and with that, ROCKNIX's own patch swapping the
assembler for the compiler is not needed at all. And U-Boot stamps its version
string and its FIT with the moment of the build, so a fixed
`SOURCE_DATE_EPOCH` and a fixed TF-A build banner go in; with those, a second
build into another directory produced both files byte for byte identical.

The result went into the sleep image in place of ROCKNIX's bootloader --
`image --install-bootloader`, which clears the region first so a shorter
bootloader cannot leave the tail of a longer one where the SPL would go on
reading, and refuses one that would grow into the job sector -- and the card
was redeployed. It boots, with the same kernel stage uptimes as before, 1.25 s
at `rootfs-init-entered` and 1.69 s at `job-runner-ready`. Three cold starts
reached the userspace milestone at 5.72, 5.76 and 5.76 s from the first card
command, against 5.66, 5.69, 5.71, 5.71 and 5.76 recorded for the shipped
bootloader at the same 6 MHz cap. The deciding sleep experiment, run again
unchanged, read 131, 124 and 129 mA at `performance` against 115, 114 and 116
at `powersave` -- 128 mean against 115, where the shipped bootloader gave 126
against 115. And `/sys/power/mem_sleep` was still `[s2idle]`, which is the
point: nothing of ours was in that build. One thing the parity run settled for
free: the four RTC general-purpose registers the next stage was going to use
for progress codes all read back `0x00000000` through `devmem`, so `/dev/mem`
works on this kernel for memory-mapped registers and nothing else on the board
is using them.

**Stage 1: the smallest thing that is a real suspend.** On `SYSTEM_SUSPEND`,
EL3 moves the cluster off PLL_CPUX onto the 24 MHz oscillator, stops PLL_CPUX,
waits in WFI, restarts the PLL and re-enters BL31 through
`bl31_warm_entrypoint`. That last part is the whole design problem and it is
kailashrs': an arm64 Linux treats a plain return from the SYSTEM_SUSPEND SMC as
a suspend that did not happen, so the resume has to arrive at the address
`plat_setup_psci_ops` was handed, with the MMU off, and let
`psci_warmboot_entrypoint` unwind the suspend and return to the address Linux
gave. Reading TF-A around it settled the rest: the CPU's power-down cache
maintenance has already run by the time `pwr_domain_pwr_down_wfi` is called, so
the data cache is off and the caches are clean before anything here touches a
register; `reset_handler` on the warm path puts `CPUECTLR.SMP` back; and the
GIC must be left entirely alone, because its distributor and this core's CPU
interface are what turn the RTC's alarm into the event that ends the WFI.
`pwr_domain_pwr_down_wfi` is also the CPU_OFF path, so it only does any of this
when the system level is off.

It worked first time. `/sys/power/mem_sleep` came up `s2idle [deep]` with no
kernel change, and the first `rtc_sleep 40 mem deep` came back: 41 seconds by
the RTC, `success` 0 to 1, card check good, and EL3's own registers reading
stage `0xa5d50008`, one suspend entered, one resume finished, wake interrupt
136 -- which the H616 manual's interrupt table calls `R_Alarm0`. Seventeen deep
suspends across four boots, seventeen resumes, the counters agreeing every
time, and the s2idle sleeps in the same runs leaving those counters untouched,
which is what says `deep` really goes through EL3 and `s2idle` does not.

**And it is worth about four milliamps.** Alternated against s2idle A B B A A
B with the `powersave` governor in both arms: 117 mA mean against 112, and 117
against 114 when the whole thing was run again. Ten consecutive deep cycles
read 110 to 117 mA, ten sound windows, against 110 to 119 for the twenty s2idle
cycles of experiment 17. Four milliamps is half of what this bench calls a
difference, and on reflection it is the right answer: a core in WFI is already
clock-gated, so stopping its PLL can only save the PLL's own bias current. The
milliamps are not in the CPU clock tree. 112 mA asleep against 33 powered off
leaves about 79 in rails a CPU-clock suspend does not reach, and reaching them
means collapsing power domains, which means DRAM in self-refresh, which on this
platform means running from SRAM -- `plat/allwinner/sun50i_h616` links BL31
into DRAM at `0x40000000`, so the stub is not an optimisation of kailashrs'
design, it is the only way to do it at all.

Two things were deliberately not done. The vendor's standby code parks the
cluster on the 32 kHz clock after stopping the PLL; that is built and compiles
(`--suspend wfi32`) and was never put on the card, because on this evidence
there is nothing left for it to find. And the PRCM register at `+0x244` that
the ROCKNIX work writes with a key of `0xa7` to gate the PLL LDO is untouched:
their own comment marks it inferred, it is in the one block of this SoC the
manual does not document, and the review thread on the pull request asks the
same question about a neighbouring write.

## 2026-09-20 The DRAM asleep, from a stub that is not in the DRAM

The suspend above stopped one step short of the DRAM, and said why: BL31 on the
H616 is linked into DRAM at `0x40000000`, so the code that stops the DRAM stops
with it. The only memory left on this SoC is SRAM A1, 32 KiB at `0x20000`,
which U-Boot's SPL ran from at boot and nothing has owned since. This is the
day the inner sequence moved there.

**Assembly, and not reluctantly.** The first sketch was C, following the prior
art, and the list of things it must not do kept growing: no stack, because the
stack is in DRAM; no call, because everything callable is in DRAM; no global,
because BL31's data is in DRAM; and no literal pool, because a blob that runs
from `0x20000` rather than from where it was linked would fetch its own
constants out of a DRAM that is in self-refresh at the time. Each of those is a
thing a compiler may do quietly and correctly and still break. They are all
guaranteed by construction in twenty-odd instructions of assembly: every
constant built with `movz`/`movk`, every label reached with `adr`, which is
PC-relative and therefore gives the address of the running copy. The built
blob was disassembled and read through before it went anywhere near the bench,
which caught nothing and was still the right thing to do.

Two small things the assembler decided. A `.if` on the difference of two labels
in the same section is not a constant as far as GAS is concerned, so the guards
that were going to check the blob's size and the vector table's reach had to
come out -- and that turned out for the better, because replacing the one
arithmetic that needed the guard (`base + (vectors - start)`) with a plain
`adr` made the blob relocatable to any address rather than only to `0x20000`.

**One job before any sleeping, and it earned its boot.** Experiment 22 reads
all sixteen RTC general purpose registers -- all sixteen are zero, so the four
the stub reports through are free and so are the twelve it does not use -- the
DRAM controller's `STAT`, `PWRCTL`, `SWCTL`, `SWSTAT` and the three master
enable registers, which are exactly where and what the stub expects
(`STAT` 1, normal mode; `MAER` `0xffffffff`, `0x7ff`, `0xffff`), and the
watchdog. That last one mattered: the manual calls `WDOG_MODE`'s enable bit
R/W1S, and the stub has to be able to clear it again before a wait that is far
longer than the longest watchdog interval. Configured for interrupt only, so
that a failure to disable could not reset the board, it went `0xb1` armed and
`0x00000000` cleared. It also priced the DRAM probe: 64 MiB of `/dev/urandom`
and its md5 in about a second each, with 1010700 kB of RAM and a 493 MiB tmpfs,
which is what set the probe at 256 MiB.

**It worked first time.** The first `rtc_sleep 40 mem deep` on the self-refresh
firmware came back with 41 seconds by the RTC, `success` 0 to 1, three card
checks good, EL3 stage `0xa5d50008`, one suspend entered and one resume
counted by the stub itself, wake interrupt 136, and the 256 MiB probe's md5
unchanged. 105.5 mA against the 112 to 114 the DRAM-less suspend had been
giving.

**And it is worth eleven and a half milliamps**, which is the first thing in
this whole sleep investigation above the bench's own eight-milliamp threshold
since the cpufreq governor. Alternated against s2idle A B B A A B with
`powersave` in both arms: 119, 114 and 116 mA in s2idle against 103, 107 and
104 in self-refresh, 116.3 mean against 104.7. EL3's counters went 0, 1, 2, 2,
2, 3 across the six sleeps -- up on each deep arm and untouched on each s2idle
one -- which is what makes the s2idle arms a control rather than a comparison.
Ten consecutive cycles in one boot read 103 to 112 mA, ten wakes of ten, ten
md5 checks of ten, `success` 0 to 10 with `fail` 0.

Taking s2idle as the anchor in each boot, the ladder now reads: stopping the
CPU PLL is about 4 mA, and putting the LPDDR4 into self-refresh on top of it is
about 8 mA more. Which is the right shape -- a core in WFI is already
clock-gated, and a DRAM that is being refreshed by its own controller at full
rate is not.

The measurement that actually settles it is the six-minute one: 361 seconds by
the RTC for a requested 360, 105.5 mA median over 112 readings in one unbroken
window, and the 256 MiB probe's md5 unchanged. Forty seconds of unrefreshed
DRAM is within a cell's retention time for pages that were read recently, so a
short sleep coming back intact is consistent with self-refresh and also
consistent with luck. Six minutes is not.

**The middle rung of the ladder works and is not worth anything.**
`--suspend sr-gate` clears the DRAM bus gate and the MBUS clock gate on top of
the self-refresh -- the gates only, never the resets beside them, because a
controller that has been reset cannot be talked out of self-refresh without
re-running the whole of U-Boot's DRAM driver, which is the one thing this stub
is built not to need. It resumes, six wakes of six with the memory probe intact
each time, and both registers read back after the resume exactly as the stub
found them. 101.3 mA mean against an s2idle anchor of 116.0 in its own boot,
where self-refresh alone had read 104.7 against 116.3 in its: about three and a
half milliamps, the right direction and less than half of what this bench
believes.

**The top rung suspends and does not come back**, twice out of twice.
`--suspend sr-pll` stops PLL_DDR0 as well, and the board goes quiet at the
suspend and stays quiet: zero card clock edges a second for the rest of the
run, the read counter frozen at the value it had going in, nothing at the
forty-second alarm, the card still selected five minutes later.

What makes that a finding rather than a dead end is what did not happen. There
was no warm reset -- a reboot is thousands of low-LBA reads in the card's trace
and there are none -- so the watchdog never fired, so the hang is in neither of
the two windows the stub arms it for. Those two windows are the self-refresh
entry and the self-refresh exit, and both are byte-for-byte what `sr-gate`
does, which works. What is left between them is two register writes and their
undo: PLL_DDR0's enable and lock-enable bits going away, the WFI, and the same
two bits coming back with a wait for lock.

And the stage code that would say which of the three it was died with the five
volts. The RTC scratch registers are in the always-on domain, which on a board
with no battery fitted means "while the USB-C port is powering it": a hang the
watchdog turns into a warm reset keeps its evidence, and a hang the watchdog
does not cover ends with the harness cutting the power at `--run-seconds` and
takes the evidence with it. That is the one gap in the blind-debugging scheme
and it is exactly where the failure landed. Closing it means arming the
watchdog across the wait too and waking on its reset rather than on the alarm,
which is a different experiment.

The likeliest answer, on the evidence that everything short of PLL_DDR0 works,
is that the Allwinner PHY does not survive its clock stopping and needs
re-initialising and re-training to come back -- which is the step the prior art
takes, by re-running U-Boot's DRAM driver with the destructive parts removed,
and the step this stub was built to avoid. Whether it is worth taking is now a
priced question rather than an open one: the two clock gates below it were
worth three and a half milliamps, so PLL_DDR0 is unlikely to be worth more than
a handful, against 72 mA still sitting in rails the PMIC controls.

**Where the ladder stopped.** Taking s2idle as the anchor in each boot, and
counting from the state the device ships in:

```text
rung      what it adds                        asleep      against s2idle   kept
wfi       PLL_CPUX stopped                    112.5 mean      -4.5 mA      no
sr        + LPDDR4 in self-refresh            104.7 mean     -11.6 mA      YES
sr-gate   + DRAM bus and MBUS clock gates     101.3 mean     -14.7 mA      no
sr-pll    + PLL_DDR0 stopped                  does not resume              no
```

`sr` is what the card was left carrying. It is the deepest rung that both pays
and is fully proved -- eighteen sleeps, ten of them consecutive and one of them
six minutes, every one with its memory checked -- and it is eleven and a half
milliamps below where the day started. `sr-gate` is three and a half below that
on a fifth of the evidence, which is not a difference this bench believes, and
the rung above it does not come back at all.

Which leaves 72 mA between a sleeping board and one that is off, and none of it
in a clock tree. It is in rails, and rails are the PMIC, and nothing here
writes a PMIC register on purpose.

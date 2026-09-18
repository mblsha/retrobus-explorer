# RG35XX Plus SD boot from the emulator

The Arty A7-35T microSD-Pmod emulator boots an Anbernic RG35XX Plus. The H700
loads its SPL, U-Boot, kernel, initramfs and device tree from FPGA DDR over the
Pmod adapter, and the booted kernel drives the emulated card itself. The target
has no serial output, so the card is also the debug channel: a 64 MiB image
carries the H700 boot chain, a FAT boot partition, and a raw debug partition
the target writes milestones into. ROCKNIX is reference material; the booted
system is a bare kernel and small initramfs.

Sections below are a chronological record. Read the
[boot result](#2026-09-18-the-rg35xx-plus-boots-from-the-emulator) for the
working configuration and its evidence, and
[the R1b busy finding](#2026-09-18-r1b-busy-and-the-missing-data-line-pull-up)
for the two defects that had to be fixed.

## Reproduce the boot

Build the qualified H700 profile. `nextpnr-xilinx` here is linked against Boost
1.90 and macOS strips `DYLD_LIBRARY_PATH` when launching through `uv run`, so
invoke the build with the virtualenv interpreter directly:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib \
  ./.venv/bin/python experiments/openxc7-macos/build_ddr.py \
  --ethernet --slow-mmc --h700-mmc --sd-io-clock-hz 64000000 --seed 8
openFPGALoader -b arty_a7_35t -m build/microsd-ddr-ethernet-h700/design.bit
```

Repair the boot script, verify the image contracts, upload and read it back,
then arm SD access before powering the target:

```sh
uv run python projects/ethernet-diagnostic/scripts/rg35xx_boot_debug.py \
  --repair-boot-script build/rg35xx-bare/rg35xx-plus-bare-64m-uboot-debug.img \
  --output build/rg35xx-bare/rg35xx-plus-bare-64m-bootscr.img
uv run python projects/ethernet-diagnostic/scripts/rg35xx_boot_debug.py \
  --verify-image build/rg35xx-bare/rg35xx-plus-bare-64m-bootscr.img
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json \
  --upload build/rg35xx-bare/rg35xx-plus-bare-64m-bootscr.img \
  --bulk --window 10
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json --arm
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json --trace
```

Power the target only after the readback has verified the image and the card is
armed. Counters are cumulative from FPGA configuration, so take the baseline
trace first and compare deltas. Power the target off and disarm between trials.

`rg35xx_trial.py` performs one standardized cold start: it takes that baseline,
powers the target's PSU channel, polls the trace, and always powers off and
disarms afterwards. It collapses the poll series to the moments card activity
changed and names the sectors each stage touched, which is how a boot is read
without serial output:

```sh
MDP_CLI=/path/to/miniware-mdp-m01/cli \
  ./.venv/bin/python projects/ethernet-diagnostic/scripts/rg35xx_trial.py \
  --state /private/tmp/rg35xx-boot-session.json --observe 25 \
  --image build/rg35xx-bare/rg35xx-plus-bare-64m-bootscr.img
```

```text
t=   0.30s CMD18 arg=16890368 frames= 411 writes= 7 lba=  33138 KERNEL+76288
t=  12.41s CMD18 arg=16808448 frames= 434 writes= 9 lba=  32833 boot partition FAT table
t=  12.49s CMD13 arg=65536    frames= 453 writes=10 lba=  95377 DTB.IMG+49152
t=  15.44s CMD6  arg=2        frames= 474 writes=10 lba=  95377 DTB.IMG+49152
t=  16.15s CMD12 arg=65535    frames= 478 writes=10 lba= 114720 partition 2 sector 32
```

`rg35xx_boot_debug.py --describe <image> --lba N` names a single sector the
same way, following the real FAT chain rather than assuming a file is
contiguous. Its channel default is `psu2`; `psu1` carries the Zaurus on this
bench and must never be switched by a card trial.

The image verifier checks the MBR layout, the H700 eGON SPL at byte 8192 and
its checksum, the FAT16 `BOOT.SCR`, `BOOTMARK`, arm64 kernel, gzip initramfs and
DTB, plus the pristine raw debug command and empty milestone sectors. Run it
before upload; a matching whole-image hash alone does not prove those contracts.

Power the RG35XX Plus, query `--trace` again, and compare counters. The image's
raw debug partition reserves sector 0 for a host command and sectors 1 through
31 for target milestones. `scripts/rg35xx_boot_debug.py` encodes and decodes
those records; U-Boot or Linux must explicitly write them before they can
appear. Power the target off before DISARM, then wait for the output-enable
trace fields to clear before another cold start. ARM only after the source
image has passed complete readback verification. This preserves the verified
DDR image and prevents an independently powered FPGA from driving an unpowered
target.

The raw partition starts at image LBA 114688. Prepare a command before the full
image upload, then retrieve the first 32 debug sectors after disarming:

```sh
uv run python projects/ethernet-diagnostic/scripts/rg35xx_boot_debug.py \
  --make-command continue --output build/rg35xx-bare/debug-command.bin
dd if=build/rg35xx-bare/debug-command.bin \
  of=build/rg35xx-bare/rg35xx-plus-bare-64m-bootscr.img \
  bs=512 seek=114688 conv=notrunc

uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json --disarm
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json \
  --download build/rg35xx-bare/debug-records.bin --start 114688 --blocks 32 --bulk
uv run python projects/ethernet-diagnostic/scripts/rg35xx_boot_debug.py \
  --decode build/rg35xx-bare/debug-records.bin
```

Recompute the source image hash after changing its command sector. A new upload
and complete readback verification are required before ARM.

The repaired boot script writes sector 1 when it starts, sector 2 after
BOOTMARK, and sectors 3, 4 and 5 after the kernel, initramfs and device tree,
so the decoded records and the trace's write counter together locate the stage
a failed boot reached.

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

`rg35xx/build_initramfs.sh` builds a real one. BusyBox is compiled from an
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

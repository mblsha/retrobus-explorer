# RG35XX Plus SD boot debugging

This experiment uses the Arty A7-35T microSD-Pmod emulator as a passive boot
probe for an Anbernic RG35XX Plus without serial output. The target receives a
64 MiB card image containing the first 16 MiB of the ROCKNIX H700 boot chain, a
FAT boot partition, and a raw debug partition intended for later kernel-to-host
milestones. ROCKNIX is reference material; the intended result is a bare kernel
and small initramfs.

## Reproduce the live trace

Connect the Arty Ethernet interface as described in the main README. Upload and
verify the image, arm SD access, then take a trace baseline:

```sh
uv run python experiments/openxc7-macos/build_ddr.py \
  --ethernet --slow-mmc --h700-mmc --seed 5
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json \
  --upload build/rg35xx-bare/rg35xx-plus-bare-64m-uboot-debug.img \
  --bulk --window 10
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json --arm
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/rg35xx-boot-session.json --trace
```

Power the RG35XX Plus, query `--trace` again, and compare counters. The image's
raw debug partition reserves sector 0 for a host command and sectors 1 through
31 for target milestones. `scripts/rg35xx_boot_debug.py` encodes and decodes
those records; U-Boot or Linux must explicitly write them before they can
appear. DISARM and ARM between target power cycles so the SD-loader-to-MMC
fallback state also starts cleanly; this preserves the verified DDR image.

The raw partition starts at image LBA 114688. Prepare a command before the full
image upload, then retrieve the first 32 debug sectors after disarming:

```sh
uv run python projects/ethernet-diagnostic/scripts/rg35xx_boot_debug.py \
  --make-command continue --output build/rg35xx-bare/debug-command.bin
dd if=build/rg35xx-bare/debug-command.bin \
  of=build/rg35xx-bare/rg35xx-plus-bare-64m-uboot-debug.img \
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

## 2026-09-16 MMC bring-up result

The H700 profile now supports legacy MMC initialization, MMC CMD3/CMD6/CMD8,
CMD23-bounded multiblock reads, 256-byte CMD16 reads backed by the two halves
of each 512-byte DDR sector, and deterministic fallback from the first-stage
SD loader to the payload's MMC probe. The SD CSD retains its 13 MHz limit; the
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

The remaining failure occurs even during the low-speed identification phase
and varies across otherwise identical power cycles. Further work should use a
scope at the H700 and FPGA ends, add correctly sized external CMD/DAT pull-ups
if measurements require them, and tune source/load impedance. A successful
bare-kernel boot has not yet been demonstrated.

Raw sampled clock edges and invalid-frame counts can rise while the target is
off because the line is then undriven. Treat those as signal-integrity evidence,
not target progress. During these tests only Miniware P906 channel 02 was
switched; it was confirmed off afterward. Channel 01 was not touched.

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

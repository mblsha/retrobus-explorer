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
256-byte CMD16 reads backed by the two halves of each 512-byte DDR sector, and
deterministic fallback from the first-stage SD loader to the payload's MMC
probe. Both SD and MMC CSD limit the external clock to 13 MHz. CMD uses the
qualified same-edge path; DAT uses opposite-edge final pad registers.

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
With the CMD7 busy-release correction, one clean cold start completed MMC
CMD2/3/9/7, selected 256-byte blocks with CMD16, issued CMD18, and produced
2,548 backend reads through physical LBA 2,560 with zero invalid command
frames. This proves that the implemented MMC path can sustain payload reads.

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

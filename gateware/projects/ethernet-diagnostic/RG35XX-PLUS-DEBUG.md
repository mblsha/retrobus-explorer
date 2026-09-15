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
appear. The current image produced no such milestones because execution did
not reach a block read.

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

## 2026-09-15/16 hardware result

The final source-built bitstream had SHA-256
`c026638806012113d2400627aed4b64f3fae9a1c78c63083daf8fb87e8a29ba7`.
Its seed-3 route passed at 102.35 MHz fabric, 90.46 MHz DDR, 93.71/144.43 MHz
Ethernet against 25 MHz, and 305.34 MHz I/O delay against 200 MHz. The build
also passed 18 bounded CDC paths, five direct SD-output checks, and a 688,890
configuration-bit round-trip. This exact bitstream was programmed and tested.

The uploaded 64 MiB image had SHA-256
`398035d789a742edd05022283465b8846630225ba4cad590cc2319c3defe5b97`.
Upload and complete Ethernet readback verification took 130.57 seconds with
three recovered retries.

The final bounded cold start began at zero command frames. It added 2,817
sampled SD edges and exactly five valid commands, with no invalid frames and no
block reads or writes; the last valid command was CMD1 with argument zero.
Earlier prototype-bitstream runs produced the same five-command/no-read result.
No further valid commands appeared after several seconds.

This establishes that the RG35XX Plus drives the bus and the FPGA recognizes
its commands, but the host switches to the MMC initialization command before
requesting any block. Failure is therefore before U-Boot's filesystem access,
kernel loading, initramfs execution, and the reserved debug-sector protocol.
The next useful investigation is the SD identification response and its
electrical timing, especially the CMD8/ACMD41 response path and whether this
H700 boot ROM requires SDHC behavior rather than the emulator's SDSC card.

Raw sampled clock edges and invalid-frame counts can rise while the target is
off because the line is then undriven. Treat those as signal-integrity evidence,
not target progress. During these tests only Miniware P906 channel 02 was
switched; it was confirmed off afterward. Channel 01 was not touched.

An experimental trace variant added card state and command history, but no
placement seed through 31 passed both the 100 MHz fabric and 80 MHz DDR timing
requirements. It was rejected and never programmed. The retained trace keeps
the smaller, timing-passing observation set above.

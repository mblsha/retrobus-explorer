# RG35XX Plus kernel and rootfs: target state

What the payload should look like when this work is finished. The measurements
behind every number here are in
[the boot record](RG35XX-PLUS-DEBUG.md); this page states the destination, not
the route.

The device is a games handheld. The kernel keeps the GPU, audio and Wi-Fi that
makes it one, and gives up everything that does not serve that. Bluetooth is
wanted but secondary, so it stays a module and costs the boot nothing.

## Boot budget

Boot time is measured from the target's power-on to the first userspace
milestone in the raw debug partition, reported as a distribution over at least
ten standardized cold starts.

```text
stage                      at the start    reached   target
SPL, FIT, U-Boot proper          1.0 s       1.05 s    0.7 s
kernel read and decompress       5.3 s       3.17 s    1.0 s
device tree                      0.7 s       0.38 s    0.1 s
kernel init to userspace         1.3 s       0.66 s    1.0 s
rootfs mount and init                 -      0.51 s    0.3 s
total                            9.9 s       5.44 s   <4 s
```

Each row below is a separate image, uploaded after passing `--verify-image` and
measured on its own. No row blends runs from two configurations. Measured from
the host's first command to the first multi-block write in the debug partition:

```text
                                  n   median   min    max   stdev   IQR
baseline, shipped kernel          10   9.93   9.88  11.07   0.36   0.06
trimmed kernel, initramfs         10   5.75   5.72   5.83   0.03   0.05
trimmed kernel, EROFS root        20   5.44   5.41   6.72   0.29   0.02
+ network and crypto trim         20   5.38   5.34   6.68   0.39   0.05
```

Stage 1 delivered no change to the interface, so its row is the unchanged
interface carrying the shipped kernel. Stage 2's row is the trimmed kernel with
the initramfs it replaced nothing of yet. Stage 3's row is the EROFS root on
that same kernel. The fourth row is stage 2's kernel trimmed further, rebuilt,
re-uploaded and re-measured in full; it is the delivered image. The twenty-run
rows are twenty runs of one image each, not two tens of different ones.

ThinLTO was built and measured and is not in the delivered image: on the identical configuration it costs 778,737 compressed bytes, 0.30 s
of reading, because cross-module specialization removes the repetition gzip was
exploiting. A smaller kernel is not a faster boot here; a smaller *compressed*
kernel is.

Each stage improves the median and none widens the interquartile range. The
standard deviations are carried by a single slow boot in each of the first and
last rows; both have a sound zero and are real boots.

### Why four seconds needs the interface, in numbers

The card moves 2.63 MB/s end to end, measured identically during U-Boot's
kernel read and during Linux's demand paging, so one rate describes the whole
boot. Split the 5.44 s by it:

```text
kernel read, 7.36 MB at 2.63 MB/s        2.80 s
everything else                          2.64 s
```

Four seconds leaves 1.36 s for the read, which at this rate is a compressed
kernel of 3.58 MB. The trimmed kernel is 7.36 MB compressed from 17.8 MB, a
2.42x ratio, so 3.58 MB means an 8.7 MB kernel: half of what is already a
trimmed kernel, while keeping Panfrost, the Sun4i display, RTW88 and SoC audio,
which the plan requires. No payload change reaches it.

Double the clock and the same payload arrives:

```text
 6.0 MHz, 2.63 MB/s    kernel read 2.80 s    total 5.44 s
12.0 MHz, 5.26 MB/s    kernel read 1.40 s    total 4.04 s
```

The 12 MHz target in this plan was the four-second target. The host will not
take 12 MHz, and the measurement above is why the aim is missed rather than
the payload work.

The boot is repeatable to about thirty milliseconds. The spread these figures
once showed was the measurement: the clock started when the power-supply CLI
returned, and that took anywhere from 1.03 to 4.29 seconds. See
RG35XX-PLUS-DEBUG.md.

The target is dominated by two changes that are not payload tuning: the card
interface runs at half the rate it advertises, and the kernel carries roughly
three times the code this device can use.

## Card interface

The FPGA timestamps measure 1,041 sampled edges in 173.5 us, which is a 6.00
MHz card clock and 2.95 MB/s across four bits, while the card's CSD advertises
13 MHz. The host is selecting a divisor one step below what it could use.

Target: the host clocks at 12 MHz, giving 5.9 MB/s. At the qualified 64 MHz SD
fabric clock that is 5.3 fabric cycles per SD period, inside what the frontend
already meets. 25 MHz is explicitly not a target: it would leave 2.5 cycles per
period and reopen the timing work that the 64 MHz build exists to avoid.

This step is blocked, with the measurement that shows it, and one part of it
is unanswered. The plan asked which divisor the host selects. What is
established is the rate it lands on, bit-identically, and that the rate has no
rung between 6 and 25 MHz; the divider and parent clock that produce those two
values are not established, because the board offers no console and each
advertised speed costs a bitstream rebuild to try. 6.001 MHz is consistent with
a 24 MHz oscillator divided by four, which would put 12 MHz on the same ladder
at a divisor of two, but the host does not take it when the card asks for it,
and why it does not is not known from the outside. The card's advertised
`TRAN_SPEED` was made a build option and swept: at 12, 13 and 20 MHz the host
clocks at 6.00 MHz, and at 25 MHz it clocks at 25.00 MHz, which the frontend
cannot serve at a 64 MHz fabric clock because it leaves 2.56 cycles per period.
The host has no divisor between those two, so there is no intermediate step to
ask for. Reaching 25 MHz needs roughly a 100 MHz fabric clock, which is the
timing work this build exists to avoid; the reward would be 11.8 MB/s against
today's 2.95. Until then the kernel read stays at about 2.8 s and no payload
change can reach the four-second target: the remaining 5.44 s is 1.05 s of
loaders, 2.8 s of one transfer and 1.6 s of everything else.

Every byte in the rest of this page is read through this interface, so it is
worth more than the payload changes combined and should land first.

## Image layout

Four regions, sized so the system slots are fixed and interchangeable:

```text
LBA 16        eGON SPL                       raw, loaded by the BootROM
LBA 96        FIT (U-Boot proper)            raw
partition 1   FAT16, boot                    BOOT.SCR, KERNEL, DTB.IMG
partition 2   raw debug                      sector 0 host command,
                                             sectors 1..15 U-Boot milestones,
                                             sectors 16..31 userspace ones
partition 3   extended                       holds the three below
partition 5   EROFS, system A                read-only, demand paged
partition 6   EROFS, system B                read-only, same size as A
partition 7   ext2, data                     rw, noatime
```

Built, and in that order for a reason. Putting the system slots in front of the
debug partition would move it, and with it the raw sectors the kernel is read
from; those addresses are qualified and are compiled into a boot script, a
trace capture and the target's own init. Appending leaves every one of them
byte for byte identical. That costs the last primary slot, so the three new
regions are logical partitions inside an extended one, and Linux numbers those
from five.

The debug partition is not optional. The board has no serial header populated,
so that partition is the only channel the target can report through, and every
boot-time measurement depends on it.

## Kernel

Source is the ROCKNIX tree for this device rather than mainline: Panfrost on
H700 and the RTL8821CS SDIO glue may carry vendor deltas, and the shipped
kernel is `7.2.0` built by `aarch64-rocknix-linux-gnu-gcc`. Its exact
configuration is recoverable from the shipped image, which carries
`CONFIG_IKCONFIG`, and that config is the starting point to trim rather than a
defconfig.

### Keep

- `ARCH_SUNXI` and the H700 platform, MMC, clocks, pinctrl, regulators, thermal
  and cpufreq.
- `DRM_PANFROST`, `DRM_SUN4I` and the panel drivers the device tree names.
- SoC audio.
- `RTW88` with `RTW88_8821CS`, `CFG80211`, `MAC80211`, and the crypto that WPA
  needs rather than the whole crypto menu.
- `gpio-keys`; the device tree describes every control that way.
- `POWER_SUPPLY` and the AXP717 MFD, which is how charging is detected.
- Serial, because Bluetooth is a UART device here.
- `EROFS` with compression, `VFAT` for the boot partition, `EXT2` for data, and
  `EXFAT` for the user's games card on the second SD slot.
- Bluetooth as a module, `realtek,rtl8821cs-bt` over `uart1`.

### Drop

- USB entirely. The device tree enables one port, the physical socket, and
  disables the other three; nothing internal is behind it. Wi-Fi is SDIO on
  `mmc1`, Bluetooth is UART on `uart1`, controls are `gpio-keys`, audio is on
  the SoC. Charging survives, because `x-powers,axp717-usb-power-supply` is a
  power-supply driver and not the USB stack. External gamepads come back as
  modules if they are ever wanted.
- BTRFS, NTFS3, NFS, SQUASHFS with its five decompressors, EXT4, and the F2FS
  compression variants.
- Netfilter, the network schedulers and classifiers, bridging, and the IPv6
  extras beyond a working stack.
- SCSI, ATA, NVMe and MTD. None of them exist on this board.
- Tracing, ftrace, BPF, kexec, crash dump, hibernation, `DEBUG_FS` and
  `KALLSYMS_ALL`.

### Build

Optimize for size, not speed: the bottleneck is a 5.9 MB/s card and the CPU is
a 1.5 GHz quad A53, so `CC_OPTIMIZE_FOR_SIZE`, ThinLTO, and
`TRIM_UNUSED_KSYMS` all convert directly into boot time. KASLR is dropped; its
relocation pass costs time this device has no threat model to justify.

Expected result is roughly 11 to 16 MiB uncompressed against today's 30.4 MiB.

### Format

Stored zstd-compressed, not gzip. Measured on the current kernel, zstd is 13.7
MiB against gzip's 15.7 MiB, and an A53 decompresses zstd several times faster
than it inflates. The FIT's U-Boot carries a zstd decompressor. Because
`unzip` handles gzip only, the kernel is expanded through `booti`'s compressed
image path using `kernel_comp_addr_r` and `kernel_comp_size`, both already in
the environment.

## Rootfs

EROFS, compressed with LZ4HC, mounted read-only straight from the card. The
Zaurus system image is deliberately uncompressed, which is right for a 400 MHz
ARMv5 where the CPU is the scarce resource; here the balance is inverted and
every byte not read saves 0.17 ms at the target clock while LZ4 decompresses at
hundreds of MB/s. LZ4HC costs build time only. The compression cluster size is
a measured choice, not a guess: a larger cluster improves the ratio but reads
more per page fault.

Contents are what a games handheld needs: a static BusyBox base, Mesa with the
Panfrost driver, SDL2, the emulator itself, `wpa_supplicant`, and BlueZ
alongside the Bluetooth module.

Nothing is loaded into RAM up front. There is no initramfs at all; the kernel
mounts the rootfs directly and pages in only what runs. This is what stops boot
time growing with the size of userspace, and it is why a 100 MiB rootfs and a
10 MiB rootfs boot at the same speed.

Two system partitions, A and B, identical in size, each a complete image with a
stable UUID. Data lives on its own `rw,noatime` ext2 partition: ext2 rather
than ext4 because there is no journal to replay after the unclean power-off
that every bench trial causes.

## Boot path

The BootROM loads the SPL, which initializes DRAM and loads the FIT. U-Boot
proper runs a boot script that reads by absolute sector with explicit block
counts, never through the filesystem: U-Boot's filesystem length handling is
what produced the oversized reads that failed six cold starts in ten.

```text
mmc dev 0
mmc read ${kernel_comp_addr_r} <kernel lba> <kernel blocks>
mmc read ${fdt_addr_r} <dtb lba> <dtb blocks>
setenv bootargs 'console=tty0 quiet loglevel=0 ro
    root=/dev/mmcblk0p2 rootfstype=erofs baredebug=/dev/mmcblk0p5'
booti ${kernel_addr_r} - ${fdt_addr_r}
```

`rootfstype` is stated so the kernel does not try each registered filesystem
against the card in turn. The console is `tty0` only: sending the log to an
unattached `ttyS0` at `loglevel=7` cost 2.2 s of kernel init, measured through
the milestones' own uptime field. There is no ramdisk argument to `booti`.

Falcon mode, which would boot the kernel from the SPL and skip U-Boot proper
entirely, is worth about 0.7 s and is not part of this target. The SPL cannot
be removed because the H700 BootROM requires it to initialize DRAM, and the
remaining U-Boot time is small next to the card and kernel terms.

## Tooling and contracts

Every artifact is produced by a committed tool and verified before it reaches
the card:

- The kernel config is extracted from a shipped image, trimmed, and kept in the
  repository.
- `rg35xx_boot_debug.py --verify-image` checks the whole contract before any
  upload: the MBR layout, the eGON SPL and its checksum, the boot script's
  legacy framing and length table, that a compressed kernel is matched by a
  script able to expand it, the EROFS superblocks of both system slots, and a
  pristine debug volume.
- The image is uploaded over Ethernet and read back complete before the card is
  armed.
- `rg35xx_trial.py` runs each standardized cold start and reports the boot as a
  distribution, with the FPGA's own timestamps for stage boundaries.

A change is accepted only if it improves the median without widening the
spread. Predictability is part of the target, not a side effect of it.

## Open questions

- Whether the host selects 12 MHz when the card advertises a higher
  `TRAN_SPEED`, or stays on the divisor below it. One gateware build settles
  it.
- Whether the ROCKNIX kernel tree for this device is publicly obtainable, and
  whether it builds reproducibly in the arm64 container.
- The EROFS compression cluster size, which trades ratio against bytes read per
  page fault and should be measured on this card rather than assumed.
- The remaining run-to-run spread: healthy boots have varied between 6.5 s and
  12 s on identical work, and that variation is not yet explained.

# RG35XX Plus kernel and rootfs: target state

What the payload should look like when this work is finished. This page states
the destination, not the route and not the result. What was actually measured
is in [RG35XX-PLUS-FINDINGS.md](RG35XX-PLUS-FINDINGS.md), the commands that
build and measure it are in [RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md),
and the order it happened in is in
[RG35XX-PLUS-HISTORY.md](RG35XX-PLUS-HISTORY.md).

The device is a games handheld. The kernel keeps the GPU, audio and Wi-Fi that
makes it one, and gives up everything that does not serve that. Bluetooth is
wanted but secondary, so it stays a module and costs the boot nothing.

## Boot budget

Boot time is measured from the target's power-on to the first userspace
milestone in the raw debug partition, reported as a distribution over at least
ten standardized cold starts.

```text
stage                      at the start    target
SPL, FIT, U-Boot proper          1.0 s      0.7 s
kernel read and decompress       5.3 s      1.0 s
device tree                      0.7 s      0.1 s
kernel init to userspace         1.3 s      1.0 s
rootfs mount and init                 -     0.3 s
total                            9.9 s     <4 s
```

A change is accepted only if it improves the median without widening the
spread. Predictability is part of the target, not a side effect of it.

The target is dominated by two changes that are not payload tuning: the card
interface runs at half the rate it advertises, and the kernel carries roughly
three times the code this device can use. What each stage reached against this
budget, and why the total landed where it did, is in the findings.

## Card interface

Target: the host clocks at 12 MHz, giving 5.9 MB/s. At the qualified 64 MHz SD
fabric clock that is 5.3 fabric cycles per SD period, inside what the frontend
already meets. 25 MHz is explicitly not a target: it would leave 2.5 cycles per
period and reopen the timing work that the 64 MHz build exists to avoid.

Every byte in the rest of this page is read through this interface, so it is
worth more than the payload changes combined and should land first.

**This step is blocked.** The host offers 6 MHz or 25 MHz and nothing between,
whatever the card advertises, so 12 MHz is not reachable by asking for it. The
measurement that establishes the whole ladder, and what it would cost to serve
25 MHz instead, is in the findings.

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

Optimize for size, not speed: the bottleneck is the card and the CPU is a
1.5 GHz quad A53, so `CC_OPTIMIZE_FOR_SIZE` and `TRIM_UNUSED_KSYMS` convert
directly into boot time. KASLR is dropped; its relocation pass costs time this
device has no threat model to justify.

ThinLTO was part of this target and is not any more. It was built, measured and
rejected: it makes the kernel smaller and the boot slower, because what matters
here is the compressed size and ThinLTO removes the repetition gzip was
exploiting. The findings carry the three builds side by side. The kernel is
built with gcc.

Expected result is roughly 11 to 16 MiB uncompressed against today's 30.4 MiB.

### Format

Stored gzip, expanded by U-Boot's `unzip` into `kernel_addr_r` from a copy read
into `kernel_comp_addr_r`. zstd would be about 1.17 MB smaller and would
decompress faster on an A53, and it was the plan, but this U-Boot has no zstd
decompressor: `booti`'s compressed-image path was tried with both of its
prerequisites met and the kernel never started. Changing this means replacing
U-Boot.

## Rootfs

EROFS, compressed with LZ4HC, mounted read-only straight from the card. The
Zaurus system image is deliberately uncompressed, which is right for a 400 MHz
ARMv5 where the CPU is the scarce resource; here the balance is inverted and
every byte not read saves 0.17 ms at the target clock while LZ4 decompresses at
hundreds of MB/s. LZ4HC costs build time only. The compression cluster size is
a measured choice, not a guess: a larger cluster improves the ratio but reads
more per page fault. It was measured; 64 KiB is the value, and what it costs is
in the findings.

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
mmc write ${ramdisk_addr_r} <script-running milestone> 1
setenv bootargs 'console=tty0 quiet loglevel=0 root=/dev/mmcblk0p5
    rootfstype=erofs ro rootwait init=/sbin/init baredebug=/dev/mmcblk0p2'
mmc read ${kernel_comp_addr_r} <kernel lba> <kernel blocks>
unzip ${kernel_comp_addr_r} ${kernel_addr_r}
mmc write ${kernel_addr_r} <kernel-loaded milestone> 1
mmc read ${fdt_addr_r} <dtb lba> <dtb blocks>
mmc write ${fdt_addr_r} <device-tree milestone> 1
booti ${kernel_addr_r} - ${fdt_addr_r}
```

Every milestone is addressed from where the debug partition actually starts, so
a card laid out differently still reports into it rather than into whatever
happens to live at a remembered sector.

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
the card. All of them are reached through one entry point,
`projects/ethernet-diagnostic/scripts/rg35xx.py`:

- The kernel config is extracted from a shipped image, trimmed, and kept in the
  repository. `build-kernel` refuses to build against a source tree that does
  not match the recorded ROCKNIX manifest.
- `image --verify-image` checks the whole contract before any upload: the MBR
  layout, the eGON SPL and its checksum, the boot script's legacy framing and
  length table, that a compressed kernel is matched by a script able to expand
  it, the EROFS superblocks of both system slots, and a pristine debug volume.
- `deploy` refuses each of its four steps unless the step before it can be
  shown to have happened, and the image is uploaded over Ethernet and read back
  complete before the card is armed.
- `trial` runs each standardized cold start and `report` reduces a set of them
  to the distribution that compares them, with the FPGA's own timestamps for
  stage boundaries.

## Open questions

- Which divisor the host actually selects, and why it will not take 12 MHz when
  the card advertises it. The rate it lands on is established; the mechanism is
  not, and the board offers no console to observe it from.
- Whether 25 MHz is worth the roughly 100 MHz SD fabric clock it needs. That
  reopens the timing work the 64 MHz build exists to avoid, against a reward of
  about 11.8 MB/s.
- Whether to select the active A/B slot at run time now that a failed script
  command is known not to cost the boot.
- The 1.4 s `rootwait` retry that appears in roughly one boot in ten with an
  EROFS root. Diagnosing it further needs a console the board does not have.

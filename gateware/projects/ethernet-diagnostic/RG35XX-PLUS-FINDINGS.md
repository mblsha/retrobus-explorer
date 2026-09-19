# RG35XX Plus boot: what is known

The current state of the work, by topic. Every figure here is a measurement
that stands today; where the chronological record in
[RG35XX-PLUS-HISTORY.md](RG35XX-PLUS-HISTORY.md) says something different, a
later entry there corrected it and this page carries the correction only. The
commands that produce all of it are in
[RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md), and
[RG35XX-PLUS-TARGET.md](RG35XX-PLUS-TARGET.md) states what the payload was
aiming at.

The board has no serial header populated, so every observation of a boot
arrives through the card: the raw debug partition the boot script and userspace
write milestones into, and the passive SD trace the FPGA keeps.

## The measurement zero

Every boot-time figure recorded before 2026-09-19 is wrong, in a way that
flattered the fastest runs. The trial started its clock when the power-supply
CLI returned, and that CLI has to start a Node process and open a serial port
before it switches anything: measured across twenty runs, it took between 1.03
and 4.29 seconds to do so. A run where it took three seconds had three seconds
of boot already behind it before the first poll, and was reported as three
seconds faster. That is the entire origin of the run-to-run spread the record
chased for two days, and of the outliers that sat below the physical floor set
by the kernel read.

The first clock edge cannot be the anchor either. With the target unpowered the
card's clock pin floats and the edge counter still advances, measured here at
about fifty edges a second, so anchoring on the first edge puts the zero at the
first poll of every run and changes nothing.

The anchor is the host's first command. Command counters do not move at all
while the target is off, because a floating line does not produce a frame that
passes CRC7, and the host's first command follows its first clock edge by
microseconds — far below the 50 ms poll resolution, so it is the same instant
for this purpose and it is unambiguous. A run counts only if some poll saw the
card quiet before that first command; runs that fail that test are reported and
discarded rather than averaged in.

The end of the measurement is the first multi-block write in the raw debug
partition. U-Boot writes one sector per milestone, and every write Linux makes
goes through the page cache and is at least a page, so either the multi-block
write command caught in the act or a jump of a page in the sector counter marks
userspace.

Re-measured on that basis, the boot is repeatable to within about thirty
milliseconds. There was never a spread to explain.

## The card interface

The rate is derived from the FPGA's own timestamps: it counts the clock edges
across one 512-byte block and the fabric ticks between the first and the last,
so the figure depends on nothing the host reports and nothing the CSD claims.
Over ten cold starts of the delivered build:

```text
card clock   6.001 MHz   stdev 0.0000
throughput   2.951 MB/s  stdev 0.0000
```

Bit-identical every run: 11,103 fabric ticks across 1,041 sampled edges, which
is one start bit plus 1024 payload nibbles plus 16 CRC edges. At 64 MHz that
block spans 173.5 us and the response end to the first data bit is 816 ticks,
12.75 us. At that rate the 7,363,461-byte kernel takes 2.50 s.

End to end the card moves 2.63 MB/s, measured identically during U-Boot's
kernel read and during Linux's demand paging, so one rate describes the whole
boot.

### The advertised-speed ladder is fully characterized

The card's advertised `TRAN_SPEED` is a build option, `--sd-tran-speed`, so the
field and the CRC7 sharing its register are computed together rather than
edited by hand. Each value costs a bitstream, and every rung between 6 and 25
MHz has now been built and measured through the block capture:

```text
advertised   measured   block span   fabric cycles   result
   12 MHz     6.00 MHz     11103 t        10.67      boots
   13 MHz     6.00 MHz     11103 t        10.67      boots
   15 MHz     6.00 MHz     11103 t        10.67      boots
   20 MHz     6.00 MHz     11103 t        10.67      boots
   25 MHz    25.00 MHz      2665 t         2.56      fails after ACMD6
```

The span is identical to the tick at 12, 13, 15 and 20 MHz, so this is not a
rounding artefact: the host runs this card at 6.00 MHz for every advertisement
below the SD default and jumps straight to 25.00 MHz when it sees 25, with no
step in between. The 15 MHz point was measured on a seed-7 bitstream,
`fde8dbe0b519…`, whose `fclk` and `dclk` both met timing at the 64 MHz SD
fabric clock; it carried the delivered image, booted normally and reached
userspace at 5.27 s.

25 MHz is reachable and unusable: 2.56 fabric cycles per SD period against the
64 MHz SD fabric clock means the frontend cannot resolve both edges of the
host's clock, and the boot stops at ACMD6, the four-bit width switch, with 83
sectors served. Serving it comfortably needs roughly 4 cycles per period, so
about a 100 MHz SD fabric clock, in a design that already needs a seed search
to meet 80 MHz — the timing work the 64 MHz build exists to avoid. The reward
would be large: 25 MHz across four bits is about 11.8 MB/s against today's
2.95.

What is established is the rate the host lands on, bit-identically, and that
there is no rung between 6 and 25 MHz to ask for. The divider and parent clock
that produce those two values are **not** established: the board offers no
console, so the mechanism cannot be observed from outside. 6.001 MHz is
consistent with a 24 MHz oscillator divided by four, which would put 12 MHz on
the same ladder at a divisor of two, but the host does not take 12 MHz when the
card asks for it, and why it does not is not known.

## The kernel

Source is ROCKNIX's tree for this device: mainline 7.2 with ROCKNIX's H700
patches and its own `linux.aarch64.conf`, trimmed rather than replaced with a
defconfig. The tarball is checked against the SHA-256 ROCKNIX pins, and
`rocknix-sources.json` records the commit, a SHA-256 for every patch and one
for the configuration, so a build cannot silently pick up a newer branch tip.

Two of ROCKNIX's settings are incompatible with the target and are cleared:
`INITRAMFS_SOURCE`, which holds a build-system placeholder and is not wanted
because the rootfs is mounted from the card, and `EXTRA_FIRMWARE`, which builds
the RTL8821CS blobs into the image rather than loading them from
`/lib/firmware`. The rootfs carries them instead, which keeps them out of the
bytes the card must read before anything can run.

Against the shipped kernel:

```text
                      shipped     trimmed
built-in options         1929        1663
uncompressed         30.4 MiB    17.8 MiB
gzip -9              15.0 MiB     7.02 MiB
```

Every intended change survived `olddefconfig`, checked symbol by symbol.
Panfrost, Sun4i, RTW88 with the 8821CS, cfg80211, mac80211, SoC audio and the
Sunxi MMC controller are still built in; EROFS with compression, `EXT2`,
`VFAT`, `EXFAT`, `gpio-keys`, the AXP717, `CC_OPTIMIZE_FOR_SIZE` and
`TRIM_UNUSED_KSYMS` are in; Bluetooth is still a module. USB, BTRFS, NTFS3,
NFS, SQUASHFS, EXT4, netfilter, SCSI, ATA, NVMe, MTD, tracing, BPF, kexec,
crash dump, hibernation, `KALLSYMS_ALL`, `DEBUG_FS` and KASLR are gone. The
crypto trim kept AES and CCM, which mac80211 and RTW88 select, and dropped
Twofish, Serpent, Camellia, the user-space API and the rest.

### Three builds, and why ThinLTO is a regression

Building the network and crypto trim twice, once with each toolchain, separates
what the trim does from what the toolchain does:

```text
                              built-in   uncompressed      gzip -9   read
gcc, -Os                          1663     18,659,336    7,363,461   2.80 s
gcc, -Os, net and crypto trim     1590     18,323,464    7,190,891   2.73 s
clang ThinLTO, same trim          1598     18,294,792    7,969,628   3.03 s
```

The trim is worth 172,570 compressed bytes. ThinLTO, applied on top of the
identical configuration, costs 778,737 — it removed 364,544 bytes of kernel and
added 606,167 bytes to what the card has to read. Cross-module inlining and
specialization cut instructions by replacing repeated call sequences with
specialized ones, which is exactly the repetition gzip was exploiting.

On a device where the kernel is read at 2.63 MB/s, the compressed size is the
only size that matters. A smaller kernel is not a faster boot here; a smaller
*compressed* kernel is. The delivered kernel is the gcc one with the trim.

## zstd, and why the kernel is gzip

The plan called for storing the kernel zstd, which is 5.90 MiB against gzip's
7.02 and which an A53 decompresses several times faster than it inflates gzip.
It does not work through this U-Boot, and the first attempt did not establish
that: it set neither the load-address convention nor `kernel_comp_size`, either
of which is enough on its own to explain a silent stop.

Retried with both of `booti`'s prerequisites met — the 6,190,080-byte zstd
kernel read into `kernel_addr_r`, `kernel_comp_size` set to 32 MiB, `booti`
given the image — U-Boot read all 12,090 sectors, wrote all three of its
milestones, then went back to rescanning the boot partition's root directory
and stopped. No userspace milestone was written. With both documented
prerequisites satisfied and the card serving the image correctly (the block
capture at the kernel's first sector shows `28b52ffd`, the zstd magic, with a
matching CRC), what remains is that this U-Boot has no zstd decompressor built
in: its magic sniffing does not recognize the image, so it is treated as a raw
arm64 Image, whose magic check then fails.

The kernel therefore stays gzip, expanded by `unzip`. The cost of that decision
is 1.17 MB of extra reading, 0.40 s at this card's rate. Changing it means
replacing U-Boot, which is a larger change than the saving justifies while the
card interface is the binding constraint.

## U-Boot does not abandon a script when a command in it fails

`--export-env` adds two lines to the boot script: `env export -t` renders the
whole environment into memory as text and `mmc write` carries it back through
the debug partition, into sectors 8..15, between U-Boot's milestones and
userspace's. It came back empty — sector 8 holds exactly what sector 1 holds,
the uninitialized contents of `ramdisk_addr_r` — so the write happened and the
export before it produced nothing. **The boot then continued and reached
userspace anyway.**

That retires two earlier conclusions. The reason given for compiling the active
A/B slot into `BOOT.SCR` rather than reading it at run time was that a missing
`setexpr` would abort the script and produce neither a boot nor a milestone to
diagnose it with; it would not, it would fall through to whatever the script
set before it, so runtime slot selection is safe to attempt. And the zstd
failure was never an aborted script: `booti` was reached, and declined.

## Image layout

```text
LBA 16        eGON SPL                  raw, loaded by the BootROM
LBA 96        FIT (U-Boot proper)       raw
partition 1   FAT16 boot   32768 +81920  BOOT.SCR, KERNEL, DTB.IMG
partition 2   raw debug   114688 +16384  sector 0 host command,
                                         sectors 1..15 U-Boot milestones,
                                         sectors 16..31 userspace ones
partition 3   extended    131072+137216
  partition 5 EROFS A     133120 +32768  read-only, demand paged
  partition 6 EROFS B     167936 +32768  same size as A
  partition 7 ext2 data   202752 +65536  rw, noatime
```

The three new regions sit behind the debug partition, not in front of it. The
plan put the system slots between the boot and debug partitions, which would
have moved the debug partition and with it the raw sectors the kernel is read
from, and every one of those addresses is qualified and compiled into a boot
script, a trace capture and the target's own init. Appending instead leaves all
of them byte for byte identical, which is checked by a test. It costs one
primary slot, so the three new regions are logical partitions inside an
extended one; Linux numbers those from five, and that is the numbering the root
argument uses.

The debug partition is not optional. It is the only channel the target can
report through, and every boot-time measurement depends on it. It deliberately
has no filesystem, so a host command written into it cannot damage the boot
files.

## The rootfs, and what the EROFS cluster size costs

The system image is the same static BusyBox the initramfs used, so userspace is
a known quantity and the only thing under test is where it is read from,
compressed LZ4HC at level 12. LZ4HC is chosen because its output is ordinary
LZ4, so the kernel needs only `CONFIG_EROFS_FS_ZIP` and its LZ4 decompressor
and the compression effort is spent at build time. The result is 1,835,008
bytes: 448 blocks of 4 KiB holding 417 inodes.

There is no initramfs any more. U-Boot reads the kernel and the device tree and
nothing else, `booti` is given a dash where the ramdisk went, and the kernel
mounts the system partition straight off the card. The 1.53 MB initramfs is
neither read nor unpacked.

The physical cluster is the unit the kernel reads and decompresses, so it was
built as an option and measured rather than assumed. With a 64 KiB cluster the
card sees 4 KiB reads for metadata, 64 KiB reads for single clusters, and
128 KiB and 192 KiB reads where readahead merged adjacent ones. The whole mount
and start of init reads about 1.1 MB, against the 1.53 MB the initramfs cost,
and the phase takes 0.51 s of the boot. Since BusyBox is a single 1.1 MB static
binary and starting it faults in most of its text, a smaller cluster has little
left to save here; it would matter for a rootfs whose access pattern is sparse.

## The A/B slots

Both slots are written with the same image and are exactly the same size, so
either is bootable and an update can be staged into the inactive one without
moving anything. In the delivered image they are byte-identical: sectors
133120 and 167936 both hash to `5fc2959626d5…`.

The active slot is compiled into `BOOT.SCR`. Switching slots rewrites one file,
which is what an update would do anyway. The original reason for not reading
the slot from the debug sector at run time no longer holds — see the
failed-command finding above — so runtime selection is now known to be safe to
attempt, and is simply not needed yet.

## The boot, stage by stage

Each row is a separate image, uploaded after passing `--verify-image` and
measured on its own. No row blends runs from two configurations, and the
twenty-run rows are twenty runs of one image each, not two tens of different
ones. Measured from the host's first command to the first multi-block write in
the debug partition:

```text
                                   n   median   min    max   stdev   IQR
stage 1  baseline, shipped kernel  10   9.93   9.88  11.07   0.36   0.06
stage 2  trimmed kernel, initramfs 10   5.75   5.72   5.83   0.03   0.05
stage 3  trimmed kernel, EROFS     20   5.44   5.41   6.72   0.29   0.02
delivered, + net and crypto trim   20   5.38   5.34   6.68   0.39   0.05
```

Stage 1 delivered no change to the interface, so its row is the unchanged
interface carrying the shipped kernel. Stage 2's row is the trimmed kernel with
the initramfs it had not replaced yet. Stage 3's row is the EROFS root on that
same kernel. The delivered row is stage 2's kernel trimmed further, rebuilt,
re-uploaded and re-measured in full.

A change is accepted only if it improves the median without widening the
spread. **Every stage passes that rule**: each improves the median and none
widens the interquartile range. The standard deviations are carried entirely by
the slow boots below — one in stage 1, one in stage 3, two in the delivered row
— which have sound zeros and are real boots. Nineteen of the twenty stage-3
runs fall within 80 ms of each other; the delivered row's core spread is about
90 ms against a 50 ms poll.

The delivered median falls 0.07 s below stage 3, which is what 172,570 bytes at
2.63 MB/s predicts.

Where the 5.44 s of stage 3 goes:

```text
0.00 - 1.05   SPL, FIT and U-Boot proper
1.10 - 3.89   kernel read, 7.36 MB
3.89 - 4.27   gunzip and device tree
4.27 - 4.93   kernel init to partition scan
4.93 - 5.44   EROFS mount, paging and init to its first milestone
```

Half the boot is one transfer.

## The slow boots

Roughly one boot in ten takes about 1.4 s longer. It is not the card and not
the measurement. Lining a slow run up against a normal one, every stage matches
until the partition scan, and then:

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
to be discovered on a device that is still probing. It is not diagnosed further
because the board has no console to watch the retry on, and the slow-boot rate,
one and two in twenty, is not distinguishable at this sample size.

## Why four seconds needed the interface

The target was under four seconds and the result is 5.44 for stage 3, 5.38
delivered. The two payload stages delivered 4.49 s of the 5.9 s that would have
been needed. The rest was in the interface, and the ladder above is why it
could not be taken.

Split the 5.44 s by the 2.63 MB/s the card moves end to end:

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

The 12 MHz target in the plan was the four-second target, and the host will not
take 12 MHz. The remaining 5.44 s is 1.05 s of loaders, 2.8 s of one transfer
and 1.6 s of everything else; until the interface moves, every further saving
has to come from reading fewer bytes rather than reading them faster.

## The display

The panel works. Under ROCKNIX's shipped kernel it shows a sharp, backlit
640x480 framebuffer console, photographed on 2026-09-19. The trimmed kernel
brings the same pipeline up at 0.438 s once the panel's init sequence is
compiled into it: the driver from patch 0110 loads
`panels/anbernic,rg35xx-plus-panel.panel` through the firmware loader, probes at
0.41 s before any filesystem exists, and nothing retries a probe that fails, so
the file has to be in the kernel, where ROCKNIX also puts it.
`build_kernel.py` builds the two RG35XX Plus panel files in and leaves the
RTL8821CS blobs out; it costs 1,358 bytes of gzip.

**Open: a Linux write to the emulated card fails once the panel is running.**
The kernel reports `sunxi-mmc 4020000.mmc: data error, sending stop command`
and then `send stop command failed`, and never retries; the kernel itself stays
alive. It happens under both kernels and never without a working panel. Until it
is fixed, nothing the target says after the panel starts reaches the debug
partition, including the flight recorder. The pin monitors and the clock-period
monitor in the FPGA trace read the same in a healthy boot as in a failed one and
are not evidence either way. See the 2026-09-19 entry in the history for what
was ruled out and what is suspected.

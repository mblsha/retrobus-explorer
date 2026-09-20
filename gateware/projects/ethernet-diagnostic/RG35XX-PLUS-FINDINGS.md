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
the same, Linux capped at 6 MHz    20   5.58   5.53   5.64   0.03   0.05
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

The last row is the delivered image rebuilt with `--card-max-hz 6000000`
(sha256 `93e49da1...`), and it is the image to use on the emulated card. It is
the one row that is slower than the row above it, by 0.20 s, and it was taken
knowingly: every row above it lets Linux run the card at 12.5 MHz, where the
link fails outright once a display is running and one cold start in six still
fails at 10 (see the display section), so their twenty clean boots measured a
margin that was there on those days and not one that can be relied on. The cap
buys that margin for the part of the boot Linux reads, which is small. All
twenty runs reported every userspace stage, Linux clocked the card at 6 MHz in
each, no command frame failed its checksum after the SPL, and none was a slow
boot. The card is a bench instrument and the destination is a real one, which
must not carry the cap; what is worth making faster from here is whatever
survives that move, and the card's own rate is not.

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

Roughly one boot in ten, two in the last ten, takes about 1.2 s longer. It is
not the emulated card and not the measurement. Lining a slow run up against a
normal one, every stage matches until the partition scan, and then:

```text
                              normal    slow
partition table scanned         4.93    4.83
first read from system A        5.09    6.31
```

The flight recorder caught two of them on 2026-09-19 and the cause is the other
card slot. `sunxi-mmc 4022000.mmc`, the controller of the second slot, which
holds a real card, logs `fatal err update clk timeout` every 0.75 s in a slow
boot and never in a normal one, and in a slow boot that card is never detected.
The kernel does not mount the root until the probes in flight have returned, so
the root, ready at 0.73 s, is mounted at 1.95 s, when that probe gives up its
first attempt. It appears in both EROFS configurations and never appeared with
the initramfs because an initramfs root waits for no device.

Nothing in this boot uses the second slot. Disabling `mmc@4022000` in the
image's device tree would remove the slow boots; it has not been done, because
it also takes the slot away from whatever runs afterwards, and that is a choice
about the product and not about the boot. Why that controller's clock update
times out in one boot in ten is not known.

## Why four seconds needed the interface

The target was under four seconds and the result is 5.44 for stage 3, 5.38
delivered, 5.58 with Linux's card clock capped. The two payload stages delivered 4.49 s of the 5.9 s that would have
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

**The picture is checked without anyone looking at it.** Init draws the test
picture with `fbsplash`, reads back the 1,228,800 bytes the panel is scanning
out, and reports the first sixteen digits of their MD5 in the stage-5 milestone;
`display_proof.py --expect` prints the value the picture has to give. For the
image measured here, whose four lines are `RG35XX PLUS`, `DISPLAY OK`,
`EROFS ROOT - 6 MHZ CARD` and `2026-09-19`, it is `fb-md5-add757487e3a9f6f`, and
every boot of that image that got as far as drawing reported it.

**An image that starts the display has to cap Linux's card clock at 6 MHz.**
The card advertises 13 MHz. U-Boot turns that into 6.00 MHz and Linux into
12.5 MHz; every interface figure in this document is U-Boot's. At 12.5 MHz with
the display running, the card sees command frames fail their checksum (4 to 37
in a boot, against 0 or 1), the controller reports
`sunxi-mmc 4020000.mmc: data error, sending stop command`, and within one to
twenty-five such errors one of them leaves the controller wedged: it stops the
clock and never sends another command, and nothing the target says afterwards
reaches the card. At 12.5 MHz without the display it never failed, and at 6 MHz
with the display, backlight full, it carried 2855 writes in 31 s with no error
and no bad frame, on the qualified bitstream unchanged.
`image --make-erofs-image --card-max-hz 6000000` sets the cap in the image's
device tree, which U-Boot's own clock does not read. Eighteen cold starts at
6 MHz, fifteen of them of the image built that way, all drew the picture and
logged no controller error; leaving out two slow boots, they reached userspace
in 5.64 to 5.78 s, against about 5.5 s at 12.5 MHz. 10 MHz is not a way to have
both: it is as fast as 12.5 MHz and one cold start in six died exactly as they
do at 12.5, after a sweep and four boots had looked clean.

The card samples CMD and DAT up to 15.6 ns after the host's rising edge, one
fabric cycle at 64 MHz, and the distance from there to the host's next change of
the line halves between 6 and 12.5 MHz. That the display is what uses up the
remainder is measured; how it does is not.

A pull-up on DAT0 alone makes a single error survivable rather than fatal and
is otherwise harmless; pull-ups on CMD and all four DAT lines stop the boot
after the SPL is read. Neither is needed at 6 MHz and the qualified bitstream
has none. The pin monitors and the clock-period monitor in the FPGA trace read
the same in a healthy boot as in a failed one and are not evidence either way;
the count of invalid command frames is. See the two 2026-09-19 display entries
in the history.

## Sleep

Measured on 2026-09-20 with the job harness, on the qualified bitstream and an
image built with `--card-max-hz 6000000`. Everything below is from the target's
own records and the bench supply; nothing was read off a screen.

**There is one sleep state and it is s2idle** -- with the firmware the device
ships with. Later the same day the bootloader was rebuilt from source and given
a PSCI `SYSTEM_SUSPEND` of our own; see the end of this section. Everything
between here and there is the shipped firmware.

**There is one sleep state and it is s2idle.** `/sys/power/state` offers
`freeze mem`, and `/sys/power/mem_sleep` offers `[s2idle]` and nothing else, so
`mem` and `freeze` are the same state. Writing `deep` or `shallow` to
`mem_sleep` returns EINVAL. The device tree has a `psci` node with method
`smc` and `cpus/cpu@0` has `enable-method = "psci"`, but there is no
`cpus/idle-states` node, and `/sys/devices/system/cpu/cpuidle/current_driver`
reads `none`: nothing tells the kernel what the idle or suspend states of this
SoC are, so the CPUs only ever WFI and `mem` can only ever be s2idle. Giving
the kernel a deeper state is a device-tree and firmware question, not a
configuration one.

**One sleep and one RTC wake, proved.** `rtc_sleep 45 freeze`: the alarm was
set to RTC 86450 at 86405, the RTC read 86451 on waking, 46 s for a requested
45; `/proc/uptime` went 1.83 to 47.62, so the clock keeps running in s2idle and
uptime is not evidence of anything here; `suspend_stats/success` went 0 to 1
with `fail` 0 and `last_failed_dev` empty; and the card check passed both
before and after. The same with `mem` in place of `freeze`, and the same with a
70 s sleep. Six sleeps, six wakes, no failure.

**The card's clock stops dead.** In the FPGA's passive trace the clock runs at
6.0 MHz through the boot, and from the target's mark to its wake it counts
exactly zero edges a second for the whole 45 or 70 seconds, then resumes. This
is not the floating-pin case a powered-off target shows, which still counts
about fifty edges a second: the H700 gates the clock off and holds the line.

### Baseline currents

Median of the readings taken wholly inside the state, first three seconds
discarded, dwell 45 s, at 5.00 V into the USB-C port with no battery fitted.
Two runs of each, each run a cold boot.

```text
state                                      median      range        IQR   n
supply output off                             1 mA          -          -   -
asleep, s2idle                          121, 126 mA   107-153 mA   7-21 mA  12-17
asleep, s2idle, entered through `mem`       124 mA    116-131 mA     8 mA   10
awake and idle, panel asleep            151, 144 mA   124-168 mA  10-15 mA  15-18
awake and idle, panel lit, kernel level 176, 183 mA   161-200 mA   9-11 mA  12-20
awake and idle, panel lit, full         246, 252 mA   139-267 mA   9-11 mA  15-16
```

The kernel's own backlight level is 1250 of a maximum of 2499, and the panel is
a 640x480 DSI unit on `card1-DSI-1`. "Panel asleep" is `echo 4 >
/sys/class/graphics/fb0/blank`, which is how init leaves the display in
job-runner mode, and which takes `dpms` to `Off`.

**The noise figure is about 7 mA.** Two runs of the same state a few minutes
apart differ by 5.5 to 7.5 mA (121 against 126, 144 against 151, 176 against
183, 246 against 252), which is more than the interquartile range inside a
single run, 7 to 21 mA, would suggest. A difference of less than about 10 mA
between two configurations is not a difference until it has been repeated.

So s2idle saves about 22 mA on an idle target whose panel is already asleep,
roughly 15 percent, and the backlight at full costs about 100 mA more than a
sleeping panel -- four times what the suspend saves. The largest single item on
this supply is the backlight and the second is whatever keeps an idle awake
target at 145 mA.

### What is still holding power up

From the discovery job, with the target awake and idle:

- **`performance` at 1416 MHz.** `cpufreq-dt` is bound with the `performance`
  governor and `scaling_cur_freq` 1416000, the top of a ladder that goes down
  to 480000. `conservative ondemand userspace powersave schedutil` are all
  available. Nothing has measured what a lower governor is worth.
- **No cpuidle driver**, as above. All four CPUs are online.
- **Regulators enabled with the display asleep**: `vcc-pll` 1.8 V,
  `vcc-spkr-amp` 3.3 V, `vcc-io` 3.3 V, `vcc-wifi` 3.3 V, `cpusldo` 0.9 V,
  `vdd-cpu` 1.1 V, `vcc3v3-mmc2` 3.3 V, `vdd-gpu-sys` 0.9 V, `vdd-dram` 1.1 V,
  `dcdc4` 1.0 V, `aldo3` 1.8 V, `avcc` 1.8 V. Disabled: `bldo1`, `bldo3`,
  `bldo4`, `cldo2`, `vdd-lcd`, `boost`, `usb0-vbus`, `aldo1`, `aldo2`.
  `dcdc4` is enabled with zero users. `vcc-wifi` is enabled although there is
  no rfkill device and no wireless driver bound -- the RTW88 firmware is not in
  this kernel. `vcc3v3-mmc2` powers the second card slot, the one whose
  controller causes the slow boots.
- **Bound platform drivers**: `panfrost` on `1800000.gpu`, `sun4i-codec`,
  `sun50i-de2-bus`, `sunxi-de2-clks`, `sun6i-dma`, `sunxi-mmc` on all three
  slots, `axp20x-usb-power-supply`, and the HDMI audio codecs. There are no USB
  devices.
- **Wakeup sources**: `7000000.rtc`, `alarmtimer.0.auto`, `axp20x-pek` (the
  power key), `axp20x-usb`, `battery`, and `mmc0`, `mmc1`, `mmc2`. No IRQ under
  `/sys/kernel/irq` has wakeup enabled.
- **The PMIC's I2C bus is unusable during the suspend.** The kernel log from
  every sleep shows the regulator core trying to disable `aldo3` thirty seconds
  in and getting `mv64xxx: I2C bus locked` and `-ETIMEDOUT`, repeated every two
  seconds until the wake. Whatever a deeper sleep would want to do to the PMIC,
  it cannot be done from there as things stand.

`DEBUG_FS` and `PM_DEBUG` are not set in this kernel, so there is no
`suspend_stats` timing breakdown, no `pm_print_times`, no `wakeup_sources`
debugfs file and no regulator summary. What is above is everything sysfs will
say; the rest needs a kernel rebuild.

### Exchanging a job through the sleep works

Twice, on the qualified bitstream: the target suspends, the host disarms the
card frontend, reads the result the job flushed on its way down, writes the
next job into the card and re-arms, and the target wakes onto a card that was
withdrawn and put back while it was not looking. The exchange took 3.43 s and
3.02 s of a 70 s sleep. After the wake the card re-initialised on its own --
the trace shows the card state going from 0 back to 4 -- the second job ran
within a fifth of a second of the resume, its card check passed, and the
controller logged no error. The count of command frames failing their checksum
stayed at the 5 the power edge and the SPL contribute, with none after.

This makes a two-job cycle cost one boot instead of two. It has not been run
for more than two jobs in a row, and nothing here says how a target that is
disarmed twice in one boot behaves.

### The optimisation experiments

Seventeen experiments on 2026-09-20, all on the qualified bitstream and the
same image built with `--card-max-hz 6000000`, all through `rg35xx.py job`.
One shell script per row, in `projects/ethernet-diagnostic/jobs/sleep/`, so
every row can be run again. The firmware sections below add nine more, 18 to
26, which need their own card images because the bootloader is part of one.

**How a comparison is made here, and why it is not a before and an after.**
Between-boot noise is about 7 mA, so every comparison is inside one boot. Two
identical sleeps in one boot differ by about 3 mA, which is better -- but the
current also climbs through a boot. Six identical sleeps in a row, experiment
7, read 121, 125, 125, 128, 126 and 129 mA: about a milliamp and a half per
cycle, monotonic, the same direction every time. Whatever that is -- the board
warming, the supply settling -- it means a knob measured once, after its own
reference, reads about three milliamps better or worse than it is for that
reason alone, and it is why the first three attempts here disagreed with each
other. The experiments that decide anything therefore alternate in the order
A B B A A B, which puts the two groups at nearly the same mean position in the
run, and a difference below about 8 mA is not believed.

Each cell below is median / interquartile range / readings, in milliamps, over
a 40 s sleep with the first 3 s discarded; `!` marks a window the harness
called UNSOUND because the supply's wireless link dropped inside it. "mean" is
the mean of the three medians in an alternating run. In the last column, "to
N" means the row was a first look that row N then decided properly, and "ref."
means the row is a reference point and not a sleep at all.

```text
 #  knob                                before      after        wake  card kept
 1  nothing: two sleeps in one boot     126/4/11    129/13/12    yes   ok   --
 2  the 32 s reg. cleanup in sleep 1    125/15/6 !  126/4/11     yes   ok   no
 3  every knob at once                  126/12/11   NO WAKE      NO    --   no
 4  the device knobs at once            124/10/9    NO WAKE      NO    --   no
 5  ladder: LEDs, 4021000+4022000.mmc   126/10/7    116/12/9     yes   ok   to 8
    ladder: + panfrost, 1800000.gpu     116/12/9    130/12/10    yes   ok   no
    ladder: + sun4i-codec, 5096000      130/12/10   134/16/11    yes   ok   no
    ladder: + panel-mipi, spi0.0        134/16/11   NO WAKE      NO    --   no
 6  ladder: powersave governor          121/10/13   119/12/9     yes   ok   to 10
    ladder: + cpus 1-3 offline          119/12/9    109/8/15     yes   ok   to 9
    ladder: everything back             109/8/15    126/16/12    yes   ok   --
 7  cpus 1-3 offline, perf., ABBAAB     124 mean    127 mean     yes   ok   no
 8  4021000+4022000.mmc off, ABBAAB     125 mean    126 mean     yes   ok   no
 9  powersave + cpus 1-3 off, ABBAAB    123 mean    112 mean     yes   ok   no
10  powersave governor alone, ABBAAB    126 mean    115 mean     yes   ok   YES
11  PMIC pollers, ADC, thermal, LEDs    112 mean    116 mean     yes   ok   no
12  ladder: DRM master, then the rest   114/15/6    109/11/11 !  yes   ok   no
13  25 devices unbound at once, ABBB    112/7/8     110 mean     yes   ok   no
14  poweroff -f, RTC alarm armed        --          33/2/19      yes   --   ref.
15  poweroff -f, no alarm armed         --          33/2/62      n/a   --   ref.
16  awake and idle, kept configuration  --          139/5/8      --    ok   --
17  ten consecutive cycles, kept cfg.   --          110-119      10/10 ok   --
```

The alternating runs in full, A first:

```text
  7  A 121, 125, 126      B 125, 128, 129 !
  8  A 125, 125 !, 126    B 124 !, 126 !, 129
  9  A 122, 121, 125      B 110, 113 !, 114
 10  A 124, 131, 124      B 114, 116, 116
 11  A 112, 116, 109      B 114 !, 116, 119
 13  A 112                B 109, 113 !, 109
```

Every row's wake was checked the same way: the RTC's own account of the sleep
(41 s for a requested 40, every time), `suspend_stats/success` up by one with
`fail` unchanged and `last_failed_dev` empty, and a `card_check` after the
resume.

### The best configuration, and what it is worth

It is one knob.

```sh
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    echo powersave > "$p/scaling_governor"
done
```

`powersave` pins the one cpufreq policy at the bottom of its ladder, 480 MHz,
and the operating point table takes `vdd-cpu` from 1.100 V to 0.900 V with it.
That rail is where the milliamps come from; the clock is not the point, since
a suspended CPU is not executing anything. It is policy rather than device
state, so it survives a resume and only has to be set once per boot, and it
needs nothing unbound, so it is the same on a real SD card as on the emulated
one.

Asleep it is worth **11 mA**: 126 mA mean against 115 mA mean over three
alternations in experiment 10, and 123 against 112 in experiment 9, where it
was combined with three offlined cores that added nothing. Awake and idle with
the panel asleep it is worth about 8 mA: 139 mA (IQR 5, n=8) against the 144
and 151 mA the same state measured under `performance`.

Experiment 10 was run a third time afterwards by someone who had not written
it, from the committed script and a cold boot: 124 (unsound), 129 and 125 mA
under `performance` against 114, 116 and 115 under `powersave`, a mean of 126
against 115 again, with six wakes of six, six card checks good, and `vdd-cpu`
read back at 1.100 and 0.900 V in the two states.

So in the kept configuration the target draws 139 mA awake and idle and about
114 mA asleep, and the suspend itself is worth about 25 mA of that.

### Ten consecutive cycles

Experiment 17, twice, each in one boot: the governor set once, then ten
`rtc_sleep 40 freeze` in a row with three seconds of quiet between them, each
suspend its own measured window. Both runs: ten sleeps, ten wakes, RTC elapsed
41 s for a requested 40 on all twenty, `suspend_stats/success` 0 to 10 with
`fail` 0 and `last_failed_dev` empty, and twelve card checks each -- one
before, one inside each cycle, one at the end -- all `card-check ok`.

```text
cycle       1    2    3    4    5    6    7    8    9   10
run A     118  114  119  114  118  113!  116  112  114  114!
run B     114  115  114  116!  117!  114  110  116  113  119
```

Sixteen of the twenty windows are sound; the four marked `!` lost two or three
readings each to the supply's link dropping, which is a hole in the
measurement and not in the sleep -- the target's own account of those four
cycles is identical to the other sixteen. The sound sixteen run from 110 to
119 mA. A third run was not attempted: the link drops for a minute or two
about once per eight-minute run, so a clean ten in a row is a matter of luck
rather than of the configuration.

### What is blocked, and the measurement that says so

**Nothing else sysfs can reach is worth anything.** Experiment 13 unbound
twenty-five devices at once on top of the kept governor -- the DRM master, the
panel, both TCONs, both mixers, the HDMI controller and its PHY, the TCON top,
the planes, the DE2 bus, the GPU, the audio codec, the HDMI audio codecs, the
display connector, both card controllers that are not the root device, the
backlight PWM and its PWM controller, the watchdog, the eFuse, the spare UART,
the PMIC's ADC and its battery and USB power-supply drivers, and the SoC's own
ADC -- and turned both LEDs off. 112 mA before, 109, 113 and 109 after. The
drift runs the other way, so if anything that is an over-estimate of the gain.
The rails that were still up afterwards are the answer: `vcc-pll` 1.8 V,
`vcc-spkr-amp` 3.3 V, `vcc-io` 3.3 V, `cpusldo` 0.9 V, `vdd-cpu` 0.9 V,
`vdd-gpu-sys` 0.9 V, `vdd-dram` 1.1 V, `dcdc4` 1.0 V, `aldo3` 1.8 V and `avcc`
1.8 V. Only `vcc-wifi` and `vcc3v3-mmc2` ever went away, and experiment 8
showed that those two together are worth about a milliamp: three sleeps with
them on read 125, 125 and 126 mA and three with them off read 124, 126 and
129. Whatever the remaining 110 mA is, it is on rails no consumer in this
kernel will release.

**Unbinding `panel-mipi` while the DRM master still holds it costs the wake.**
Twice, in experiments 4 and 5: every unbind reported success, the job set its
alarm, wrote its result to the card and suspended, and nothing happened again
for the rest of the run -- no card command, no resume, no counter. Experiment
12 shows it is an ordering problem and not the panel: with `display-engine`
unbound from `sun4i-drm` first, the same `panel-mipi` unbind and nine more
underneath it are harmless, and the target woke three more times with its
card checks passing. It also shows there is nothing to be had by doing it:
114, 118, 113 and 109 mA across the ladder, and not one regulator changed
state.

**`aldo3` and `dcdc4` are enabled with nobody using them, and cannot be
turned off.** The regulator core's delayed cleanup runs at 32 s of uptime and
is the only thing that ever tries. The job harness starts a job at about two
seconds, so the attempt lands inside the first suspend, where the PMIC's I2C
controller is suspended: `aldo3: disabling` at 32.05 s, then `mv64xxx: I2C bus
locked, block: 1, time_left: 0` and `aldo3: couldn't disable: -ETIMEDOUT` at
34.08 s, and the bus timing out again every two seconds until the wake. It is
attempted once and never again -- `aldo3` reads `enabled` with `num_users` 0
for the rest of the boot, and so does `dcdc4`. It costs nothing measurable
either way: experiment 2's sleeps with the cleanup inside and after it read
125 (unsound), 126 and 129 mA. There is no sysfs write that enables or
disables a regulator, so short of being awake at 32 s of uptime -- which the
harness cannot arrange without changing when a job starts -- these two rails
stay up.

**Offlining cores buys nothing on its own.** Experiment 7, three alternations
at `performance`: 124 mA mean with four cores, 127 mean with one. The cores
do go offline through PSCI CPU_OFF, they stay offline across a suspend, and
the wake is unaffected -- `online` still read `0` after the sleep in
experiment 6 -- but an idle core in s2idle is in WFI on a rail shared with the
one that stays, and taking it away does not lower the rail. Experiment 9's
saving is the governor's, which experiment 10 then measured on its own at the
same 11 mA.

**The I2C traffic during a suspend is not where the current goes.**
`mv64xxx_i2c` is the only interrupt that counts up appreciably across a sleep,
about 270 per 40 s cycle. Unbinding the PMIC's ADC, its battery and USB
power-supply drivers and the SoC's ADC takes it to about 128 and changes the
current not at all (experiment 11: 112 mA mean with them, 116 mean without).

**And the state itself is the limit.** There is one sleep state, s2idle, for
the reasons in the first part of this section: no `cpus/idle-states` in the
device tree and no cpuidle driver bound. In s2idle the DRAM is not in
self-refresh, no power domain is collapsed, and the CPUs only WFI. Sysfs
cannot change any of that.

### The reference point: powered off, under USB power

Not a sleep, and worth more than every sleep knob put together.

`poweroff -f` with 5 V still on the USB-C port leaves the board drawing
**33 mA** (33-35 mA, IQR 2, n=19 over 60 s in experiment 14; 33-35, IQR 2,
n=62 over 190 s in experiment 15). That is the steadiest reading this bench
has taken -- a 2 mA interquartile range against the 7 to 18 mA a sleeping
target gives -- and it is 72 mA below the best sleep the firmware sections
below reach, which was 81 before them.

**And the RTC alarm powers it back on.** Experiment 14 armed
`/sys/class/rtc/rtc0/wakealarm` sixty seconds out and powered off. The card
went silent at 8.4 s and the FPGA's trace shows a fresh boot reading the root
filesystem at 69.4 s, 61.0 s later; the runner took the same job up again,
armed the alarm again and powered off again at 74.5 s, and the board came back
at 135.1 s, 60.6 s later. Two for two, both within a second of the alarm.
Experiment 15 is the control: the same job with the alarm explicitly cleared
powered off at 15.7 s and the card saw nothing for the remaining 193 seconds
of the run, at 33 mA throughout. So the board does not simply restart when it
is powered off on USB -- the alarm is what brings it back.

What this costs is state and time: it is a cold boot, not a resume, and the
FPGA's trace puts the first card command about 5 s and userspace about 12 s
after the power comes up. For a timed wake where nothing has to survive, it is
a quarter of the current.

### Deeper than s2idle: a PSCI SYSTEM_SUSPEND of our own

The recommendation that follows -- that the next real saving is in the firmware
-- was acted on the same day. The bootloader is now built here from pinned
sources, mainline U-Boot v2026.01 and TF-A v2.12.0, by
`rg35xx.py build-firmware` (runbook section 12), and one patch to TF-A gives
the H700 a PSCI `SYSTEM_SUSPEND`: at EL3, with the other cores already
offlined by Linux, the boot core moves the cluster off PLL_CPUX onto the 24 MHz
oscillator, stops PLL_CPUX, waits in WFI, restarts the PLL and returns to Linux
through TF-A's warm boot entry point. DRAM is left running, no rail is touched
and no register is written that the H616 manual does not document. The idea and
the shape are kailashrs' work for ROCKNIX,
[ROCKNIX/distribution#3316](https://github.com/ROCKNIX/distribution/pull/3316),
which does the whole job with an SRAM stub and DRAM self-refresh; this is a
minimal version of it, ours, one step short of the DRAM.

- The from-source bootloader is the bootloader it replaced: userspace at 5.72,
  5.76 and 5.76 s against 5.66 to 5.76 recorded before, the same kernel stage
  uptimes, and the same deciding sleep experiment reading 128 mA mean against
  115 where the shipped bootloader gave 126 against 115.
- With the patch, `/sys/power/mem_sleep` reads `s2idle [deep]` and no kernel
  change was needed.
- **Seventeen deep suspends, seventeen resumes**, across four boots: RTC 41 s
  for a requested 40 every time, `success` up by one with `fail` 0, a card
  check after each, and EL3's own counters agreeing. The interrupt EL3 found
  pending when the WFI ended was 136 on all seventeen, which the H616 manual's
  interrupt table calls `R_Alarm0`.
- **It is worth about four milliamps**, which is below the eight this bench
  calls a difference: 117 mA mean asleep in s2idle against 112 in deep, and 117
  against 114 when the alternation was repeated. Ten consecutive deep cycles
  read 110 to 117 mA, against 110 to 119 for the twenty s2idle cycles of
  experiment 17.

A core in WFI is already clock-gated, so what the CPU clock tree had left to
give was PLL_CPUX's own bias, and that is what four milliamps looks like. The
rest is in the rails listed above, which need power domains to collapse, which
needs DRAM in self-refresh, which needs the sequence to run from SRAM because
BL31 on this platform is linked into DRAM. That was then done, and is the next
heading. The full write-up, with what is measured and what is assumed, is the
deep-sleep section of [RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md).

### Deeper still: the LPDDR4 in self-refresh, from a stub in SRAM

The inner sequence moved into SRAM A1: a 4224-byte blob of position-independent
assembly in BL31's read-only data, copied to `0x20000` on the way into every
suspend and called with the MMU off. No stack, no call and no literal pool --
the stack is in DRAM, everything callable is in DRAM, and a literal pool would
be in DRAM. Every constant is `movz`/`movk`, every label is `adr`, and the
built blob was disassembled to confirm it. Its own exception vectors are
installed for the duration, so a fault in it leaves `ESR_EL3` and `ELR_EL3` in
RTC registers and resets through the watchdog instead of wedging.

Three rungs, one `--suspend` mode each, built from one patch with different
`SUNXI_SUSPEND_DRAM_LEVEL`: `sr` is software self-refresh alone, `sr-gate`
also gates the DRAM bus and MBUS clocks, `sr-pll` also stops PLL_DDR0. Gates
only, never the resets beside them. The controller sequences are mainline
U-Boot's, from `mctl_ctrl_init()` and `mctl_phy_init()` in
`arch/arm/mach-sunxi/dram_sun50i_h616.c`, because the H616 manual documents no
DRAM controller registers at all; everything else is cited to the manual.

**A resume that works is not proof.** A DRAM cell holds its charge for a good
fraction of a second unrefreshed, so every sleep from here fills 256 MiB of
tmpfs with random bytes, records its md5 and checks it on the other side, with
one six-minute sleep per kept rung as well as the short ones. In the
alternation the s2idle arms are the control: s2idle does not touch the DRAM,
so if those pass and the deep ones do not, the difference is the self-refresh.

**Self-refresh is worth 11.6 mA**, the first thing above this bench's
eight-milliamp threshold since the cpufreq governor. Alternated against s2idle
A B B A A B with `powersave` in both arms: 119, 114 and 116 mA in s2idle
against 103, 107 and 104 in self-refresh, 116.3 mean against 104.7. All six
windows sound, six wakes of six, six md5 checks unchanged, and EL3's counters
up by one on each deep arm and untouched on each s2idle one. Ten consecutive
cycles in one boot read 103 to 112 mA over ten sound windows, ten wakes, ten
md5 checks, `success` 0 to 10 with `fail` 0, and the card's clock at exactly
zero edges a second throughout every sleep.

**One sleep of six minutes** is what settles whether anything is being
refreshed at all: 361 s by the RTC for a requested 360, 105.5 mA median over
112 readings in one unbroken sound window, and the probe's md5 unchanged.

**The rung above it, `sr-gate`, works and adds nothing measurable.** Gating the
DRAM bus clock and the MBUS clock on top of self-refresh reads 101.3 mean
against an s2idle anchor of 116.0 in its own boot, where self-refresh alone
read 104.7 against 116.3 in its. About 3.4 mA: the right direction, less than
half the threshold, so the kept configuration does not move. Six wakes of six,
six md5 checks, and `MBUS_CFG` and `DRAM_BGR` read back after the resume
exactly as the stub found them.

<!-- FINDINGS-PLL -->

Taking s2idle as the anchor in each boot, the firmware ladder is: stopping the
CPU PLL about 4 mA, and the LPDDR4 in self-refresh about 8 mA more.

### Recommendations

None of these were done here; the first two need a person at the bench.

- **Measure the same states on the battery.** Everything above is the 5 V
  USB-C input with no battery fitted, so it includes the AXP717's own
  conversion losses and whatever the charger path draws with no cell on it.
  The 33 mA powered-off figure in particular is suspiciously large for a board
  that is off, and a good part of it may be the charger looking for a battery.
- **Put a meter in series with the battery terminals**, or read the PMIC's own
  coulomb counter, to separate what the SoC draws from what the PMIC costs.
  The bench supply cannot see inside the PMIC.
- **If the application can afford a cold boot, use poweroff and the RTC
  alarm.** 33 mA against 114, proved above, with the wake proved twice and the
  stay-off proved once.
- **The device tree is where the next real saving is.** `cpus/idle-states`
  with the H700's PSCI states would give the kernel a cpuidle driver and make
  `mem` something other than s2idle; `status = "disabled"` on the nodes
  experiment 13 unbound would stop them being probed at all, which is tidier
  than unbinding but, on this evidence, worth about the same, namely nothing.
  The rails that matter -- `vdd-dram`, `vdd-gpu-sys`, `vcc-pll`, `avcc` --
  need a suspend that collapses power domains, which is firmware.
- **A kernel with `PM_DEBUG` and `DEBUG_FS`** would give `pm_print_times`, the
  `suspend_stats` timing breakdown and a regulator summary, and would say
  which device's suspend callback is holding what. Nothing here needed it, but
  the next question probably will.

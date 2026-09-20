# RG35XX Plus: what timed sleep costs, and how low it goes

The results reference for power and sleep on this board, organised by topic:
every measurement, register fact, dmesg quote and caveat about what the board
draws lives here, newest knowledge first. The `## Sleep` section of
[RG35XX-PLUS-FINDINGS.md](RG35XX-PLUS-FINDINGS.md) is a summary of this page and
points back to it. The suspend firmware itself -- what it is, how it works and
how it got there -- is
[RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md); what the public
documents say, what the prior art did, the outside review and the hypotheses
for the current that is left are
[RG35XX-PLUS-POWER-RESEARCH.md](RG35XX-PLUS-POWER-RESEARCH.md); what still needs
a person at the bench is
[RG35XX-PLUS-BENCH-EXPERIMENTS.md](RG35XX-PLUS-BENCH-EXPERIMENTS.md); the
commands are sections 11 and 12 of
[RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md); and the order things were
discovered in, dead ends included, is the 2026-09-20 and 2026-09-21 entries of
[RG35XX-PLUS-HISTORY.md](RG35XX-PLUS-HISTORY.md).

The question was how little current the board can draw in a timed sleep, one it
enters by itself and leaves on an RTC alarm, and the condition was that nobody
looks at the device: every figure here came from the target's own records on
the emulated card and from the bench supply.

## The answer

| | at the 5 V input |
| --- | --- |
| asleep as the image ships, s2idle | 121 to 126 mA |
| asleep, s2idle, the best sysfs can reach | about 114 mA (110 to 119 over twenty cycles) |
| asleep, our firmware suspend, the CPU PLL off (`wfi`) | about 113 mA (110 to 117 over ten) |
| asleep, our firmware suspend, the LPDDR4 in self-refresh (`sr`) | about 105 mA (103 to 112 over ten) |
| asleep, our firmware suspend, DRAM controller, PHY and clock path off and rebuilt on resume (`sr-phy`) | about 76 mA -- but **one resume in five does not happen**, see below |
| asleep, the same with the DRAM pads held while the PHY is reset (`sr-phy-padhold`) | about 70 mA (67, 67, 75; 72 over a six-minute sleep), and **fifty-two sleeps came back of fifty-two** |
| asleep, that with PLL_VIDEO0, PLL_DE and the DE bus gate stopped too (`sr-phy-padhold-nodisp`) | **about 62 mA** (57, 65, 67; 60 to 67 over ten cycles; 62 over a six-minute sleep), and **fifty sleeps came back of fifty** |
| asleep, ROCKNIX's firmware suspend, built from source, which does the same (`rocknix-deep`) | **about 70 mA** (65 to 75 over ten; 70 over a six-minute sleep), and thirty-five sleeps of it in a row all came back |
| powered off with an RTC alarm armed, which does bring it back | 33 mA |
| supply output off | 1 mA |

**The sr-phy row is not a configuration anybody can keep, and finding that out
is the whole of 2026-09-20's second evening.** Until then that rung had
eighteen deep sleeps and no failure, which is how it came to be the kept one.
Counted properly -- ninety-nine deep sleeps across four firmwares in one
evening, each followed by a 256 MiB md5 check, with the failures counted in a
sector of the card so that the warm reset a failure causes cannot hide it --
**eight of `sr-phy`'s forty-two sleeps did not come back**, every one of them
the same failure: the PHY would not calibrate on the way back and the stub
reset the board. The published implementation, `rocknix-deep`, did the same
thing thirty-five times with no failure at all. So the rebuild is sound as an
idea and ours had a bug.
[How often the rebuild does not come back](#how-often-the-rebuild-does-not-come-back-experiment-34)
is the evidence and names the two writes that separate the two.

**The bug was one register, and the fix is measured: the DRAM pad hold.** On
2026-09-21 the documented one of those two writes was made, and it is what our
rebuild was missing. `sr-phy-padhold` resumed **forty-eight times of
forty-eight** where its control had lost eight of forty-two, and
`sr-phy-padhold-nodisp` -- the same rung with the three display clocks the
stub's own snapshot found still running stopped as well -- **thirty-six of
thirty-six**. The pad hold is also worth a few milliamps by itself, and the
display clocks about seven more, so ours now sleeps at about 62 mA by medians
against the published implementation's 68 on the alternation and 70 to 72 over
six minutes. **That is below theirs by six to ten, which is at the edge of what
this bench believes**: by the *means* of the same readings the two are level,
and
[the per-rung evidence](#the-two-pad-hold-rungs-what-each-was-measured-with)
says so plainly. The kept configuration is ours again, with `rocknix-deep` as
the reference and the fallback.

**The story in one paragraph.** s2idle was the only sleep state this kernel and
firmware offered, and exactly one knob inside it is worth keeping: the
`powersave` cpufreq governor, 11 mA. Nothing else sysfs can reach is worth a
milliamp, because in s2idle the DRAM keeps running, no power domain collapses
and the CPUs only wait for an interrupt. A firmware of our own gives the board
a real `deep` state, and it was built one rung at a time so that each rung
could be priced: stopping the CPU PLL and waiting in WFI is worth about 4 mA,
which is less than this bench calls a difference; putting the LPDDR4 into
self-refresh as well, from a stub in SRAM because BL31 itself lives in the
DRAM, is worth about 9 mA pooled over three boots and lands the board at 105 mA
every time; and **switching the DRAM controller, its PHY and the whole DRAM
clock path off, and building them again on the way back with U-Boot's own DRAM
driver running out of SRAM, is worth another 29** -- 76 mA against an s2idle of
115 in the same boot, ten consecutive cycles between 68.5 and 79, and a
six-minute sleep at 75 mA with a 256 MiB probe's md5 unchanged. That rung did
not always come back, and the one write that makes it come back every time --
holding the DRAM pads while the PHY is reset and unclocked -- is worth about
six milliamps as well, which this bench would not have believed on its own.
Stopping PLL_VIDEO0, PLL_DE and the DE bus gate on top of it, which only became
collectable once something resumed reliably, is worth about seven more. Taken
together that moves a sleeping board from about 124 mA to about 62, half, and
the firmware is about fifty of those milliamps.

**The ledger: what each step saved, and what it cost.**

```text
step                                             asleep      saved       what it cost
s2idle, as the image ships                     121-126 mA      --        --
+ powersave cpufreq governor                     ~115 mA     9-11 mA     one line of shell per boot
+ our PSCI SYSTEM_SUSPEND, CPU PLL stopped       ~113 mA      ~4 mA      a 420-line TF-A patch
+ LPDDR4 in self-refresh, from an SRAM stub      ~105 mA      ~9 mA      4224 bytes of assembly
+ controller, PHY and clock path off and          ~76 mA      ~29 mA     a C stub in SRAM that links
  rebuilt on resume (ours; 8 of 42 resumes                               U-Boot's DRAM driver
  failed, so it is not kept)
+ the DRAM pads held while the PHY is              ~70 mA      ~6 mA      one register write, and the
  reset (ours; 52 of 52 came back)                       (under the noise) rule that forbade it lifted
+ PLL_VIDEO0, PLL_DE and the DE bus gate           ~62 mA      ~7 mA      three clocks the kernel
  stopped as well (ours, KEPT; 50 of 50)                                  leaves running
ROCKNIX's suspend instead (theirs, not ours;      ~70 mA   ~51 vs s2idle  the same idea, theirs
  35 of 35 resumes came back)
powered off, RTC alarm armed (not a sleep)         33 mA       --        a cold boot on waking
supply output off                                   1 mA       --        --
```

If the application can stand a cold boot on waking, powering off with the alarm
armed still draws about half of the best sleep.

All currents are at the USB-C port at 5.00 V with **no battery fitted**, so they
include the PMIC's conversion and charger path and are not battery-life
figures. The supply reads to 1 mA, about once every two and a half seconds, and
every figure here is a median of those readings; the mean of the same readings
runs 5 to 8 mA higher in every sleep window, which the next section explains
and which the differences between arms survive. **The gap widens as the sleep
gets deeper** -- about 5 mA at `sr-phy`, 10 at `sr-phy-padhold`, 11 on theirs
and 16 on the kept rung -- and at the bottom of the ladder it decides a
comparison rather than merely shifting it: see the ladder below.

**The published implementation was 37 mA below ours, then three, and now ours
is six to ten below it -- at the edge of what this bench believes.**
`build-firmware --suspend rocknix-deep` builds kailashrs' TF-A patch and SRAM
stub from source exactly as ROCKNIX pins them, and nothing of ours; measured
first, on the same card, kernel and rootfs, it slept at 70, 67 and 68 mA
against an s2idle of 121, 114 and 124, six wakes of six with six md5 checks
unchanged, and at 72 mA over a six-minute sleep. What it did and our stub did
not was shut down the DFI interface, the DRAM controller's clocks and PLL_DDR0
and rebuild the controller and the PHY on resume -- the step an outside
reviewer said was still unpriced, the rung at which our assembly stub never
resumed, and where most of the clock-level saving turned out to be. **Ours does
it now**, from a C stub of our own compiled against U-Boot's DRAM driver, and
once the pad hold made the rebuild reliable it could also stop three clocks the
prior art leaves running. By medians the six-minute sleeps are 62 mA against
their 70 to 72 and the short sleeps about 62 against 68; the threshold on this
bench is eight milliamps, so the six-minute gap is a difference and the
forty-second one is on the line. By the means of the same readings there is no
gap at all. Ours is kept; theirs stays built, stays measured and is the
fallback.

## How it is measured

- **Bench.** The qualified seed-19 bitstream, unchanged throughout; the card
  image `build/rg35xx-sleep/rg35xx-plus-sleep.img`, built with
  `--card-max-hz 6000000` and the host command `job-runner`; supply channel
  `psu2`, 5.000 V, 1.200 A limit, never altered. `psu1` was never addressed.
  The firmware rungs use images built the same way around a different
  bootloader, and nothing else about the bench changes with them.
- **The rule for a figure.** The median of the supply's readings taken wholly
  inside a state, after discarding the first 3 s, over a dwell of at least
  20 s (40 to 45 s in practice), with the range, the interquartile range and
  the count reported. A window in which the supply's wireless link dropped is
  marked UNSOUND and is not a measurement.
- **A median is not an average, and the difference is not small.** Recomputed
  from the stored readings after the outside review, the mean runs 5 to 8 mA
  above the median in every sleep window, and single readings of 166 to 220 mA
  turn up inside windows whose median is 105. Every figure quoted here is a
  median, so the comparisons between arms survive the recomputation -- the
  first self-refresh alternation is 11.0 mA by means against 11.6 by medians --
  but the absolute sleeping power is nearer 110 to 112 mA than 105. Whether
  those high readings are real bursts or an artefact of the supply's sampling
  needs a shunt and a scope, which needs a person at the bench.
- **Noise.** Two cold boots of the same state differ by about 7 mA. Two
  identical sleeps inside one boot differ by about 3 mA, but the current also
  climbs about 1.5 mA per cycle through a boot (six identical sleeps: 121,
  125, 125, 128, 126, 129 mA). So every deciding comparison alternates the two
  configurations inside one boot in the order A B B A A B, and a difference
  below about 8 mA is not believed.
- **What counts as a wake.** The RTC's own account of the sleep against the
  requested duration, `suspend_stats/success` up by one with `fail` unchanged,
  and a card check after the resume: a unique pattern written to a scratch
  sector, the caches dropped, the sector read back and compared.
- **What counts as proof that the DRAM kept anything.** A resume that works is
  not proof. A DRAM cell holds its charge for a good fraction of a second with
  nobody refreshing it, so a controller that quietly never entered self-refresh
  would still come back looking healthy from a forty-second sleep. Every deep
  sleep from the self-refresh rung onwards therefore fills 256 MiB of tmpfs with
  random bytes, records its md5 and checks it on the other side, and each kept
  rung gets one sleep of six minutes as well as the short ones. The s2idle arms
  of each alternation are the control: s2idle does not touch the DRAM at all, so
  if those checks pass and the deep ones do not, the difference is the
  self-refresh and not the probe.

## What the target offers

- `/sys/power/state` is `freeze mem`; `/sys/power/mem_sleep` is `[s2idle]` and
  nothing else, and writing `deep` or `shallow` to it returns EINVAL. `mem` and
  `freeze` are the same state. That is the firmware the device ships with; with
  our own bootloader on the card `mem_sleep` reads `s2idle [deep]` and `mem`
  resolves to `deep`, with no kernel change, because Linux probes
  `PSCI_1_0_FN64_SYSTEM_SUSPEND` and installs its suspend ops when the firmware
  answers.
- There is no cpuidle driver (`current_driver` reads `none`) and no
  `cpus/idle-states` in the device tree, though there is a `psci` node with
  method `smc` and `cpus/cpu@0` has `enable-method = "psci"`; the device tree
  says `arm,psci-0.2`. Nothing tells the kernel what the idle or suspend states
  of this SoC are, so in s2idle a sleeping CPU only waits for an interrupt, the
  DRAM is not in self-refresh and no power domain collapses. The device-tree
  half of that is still true; the firmware half is not.
- The RTC is `7000000.rtc` with a working `wakealarm`; BusyBox has `rtcwake`.
  The kernel has `CONFIG_SUSPEND` and `CONFIG_RTC_DRV_SUN6I`; it does not have
  `DEBUG_FS` or `PM_DEBUG`, so there is no regulator summary, no
  `pm_print_times`, no `wakeup_sources` debugfs file and no suspend timing
  breakdown. What sysfs will say is all there is; the rest needs a kernel
  rebuild.
- **`/dev/mem` works and the RTC scratch registers are free.** `CONFIG_DEVMEM`
  is on, `CONFIG_IO_STRICT_DEVMEM` is off, and the RTC's general-purpose
  registers 12 to 15 read `0x00000000` on a board that has never suspended, so
  nothing else uses them. That is the whole of the firmware's voice on a board
  with no serial console, and a job reads them with `devmem`.
- One sleep and one RTC wake, proved. `rtc_sleep 45 freeze`: the alarm was set
  to RTC 86450 at 86405, the RTC read 86451 on waking, 46 s for a requested 45;
  `/proc/uptime` went 1.83 to 47.62, so the clock keeps running in s2idle and
  uptime is not evidence of anything here; `suspend_stats/success` went 0 to 1
  with `fail` 0 and `last_failed_dev` empty; and the card check passed both
  before and after. The same with `mem` in place of `freeze`, and the same with
  a 70 s sleep. Six sleeps, six wakes, no failure in Phase 0, and none in any
  s2idle sleep since.
- While the target sleeps the card's clock stops dead. In the FPGA's passive
  trace it runs at 6.0 MHz through the boot, and from the target's mark to its
  wake it counts exactly zero edges a second for the whole 45 or 70 seconds,
  then resumes. That is not the floating-pin case a powered-off target shows,
  which still counts about fifty edges a second: the H700 gates the clock off
  and holds the line.

## Baselines

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

**The noise figure is about 7 mA**, and this is where it comes from. Two runs
of the same state a few minutes apart differ by 5.5 to 7.5 mA (121 against 126,
144 against 151, 176 against 183, 246 against 252), which is more than the
interquartile range inside a single run, 7 to 21 mA, would suggest. That is
why nothing below is decided between boots, and why the threshold above is
about 8 mA.

So the shipped suspend is worth about 22 mA on a target whose panel is already
asleep, roughly 15 percent, and the backlight at full costs about 100 mA more
than a sleeping panel -- four times what that suspend saves. The largest single
item on this supply is the backlight and the second is whatever keeps an idle
awake target at 145 mA.

## The kept configuration, and how to apply it

Two things pay, and together they are a sleep of about 62 mA: the `powersave`
cpufreq governor, and a firmware that shuts the DRAM controller and its PHY
down and rebuilds them on resume. They are independent -- the governor is
policy, the firmware is what the SoC does while the core waits -- and the
governor is worth its eleven milliamps under every firmware rung below.

**The firmware that is kept is `sr-phy-padhold-nodisp`, which is ours again.**
It is `sr-phy` with two things added: the DRAM pads held while the PHY is reset
and unclocked, which is what makes our rebuild come back, and PLL_VIDEO0,
PLL_DE and the DE bus gate stopped for the sleep, which is worth about seven
milliamps and could not be collected on any rung that failed one resume in
five. Fifty deep sleeps on 2026-09-21, no failure, every md5 unchanged:
[the per-rung evidence](#the-two-pad-hold-rungs-what-each-was-measured-with) is
below.

**`rocknix-deep` remains the reference and the fallback.** It is the
implementation this design came from, it is the only firmware on this bench
that was reliable before ours was, and it stays built and stays measured at
about 68 to 70 mA -- so a doubt about our rebuild is settled by deploying
theirs and running the same jobs, not by argument. Ours is now the lower of the
two by six to ten milliamps, which is at the edge of the eight this bench
believes. If what is wanted is ours with no DRAM driver in the way at all, that
is `--suspend sr`: 105 mA, sixteen proved sleeps, and a way back that never
touches the PHY. What must **not** be used is any rung that rebuilds the PHY
without the pad hold -- `sr-phy`, `sr-phy-nodisp`, `sr-phy-nodisp-late` and the
two ablations -- because those fail about one resume in five to eight; they are
measured rungs and they stay in the tree as measurements.

```sh
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    echo powersave > "$p/scaling_governor"
done
```

It pins the CPUs at 480 MHz, and the operating-point table takes `vdd-cpu` from
1.100 V to 0.900 V with it; the rail is where the milliamps come from, since a
suspended CPU executes nothing. It is policy, not device state, so it is set
once per boot, survives every resume, needs nothing unbound, and is the same on
a real SD card as on the emulated one. It is
[`jobs/sleep/apply-best.sh`](jobs/sleep/apply-best.sh).

- Asleep: **11 mA**. 126 mA mean against 115 over three alternations
  (experiment 10), 123 against 112 with three cores also offline, which added
  nothing (experiment 9). Run a third time from the committed script by someone
  who had not written it: 124 (unsound), 129, 125 against 114, 116, 115, the
  same means to the milliamp, six wakes of six, `vdd-cpu` read back at both
  voltages.
- Awake and idle, panel asleep: about 8 mA, 139 mA (IQR 5, n=8) against the 144
  and 151 mA the same state measured under `performance`.

The firmware is built and installed by runbook section 12:
`build-firmware --suspend sr-phy-padhold-nodisp`, then `image
--install-bootloader`, then a `deploy`. The card was left carrying
`build/rg35xx-firmware-src/sr-phy-padhold-nodisp/rg35xx-plus-sleep-sr-phy-padhold-nodisp.img`,
image sha256 `4389c576...`. The fallback is the same three commands with
`--suspend rocknix-deep --fetch` and its own image. What our own stub does, and
why it is two programs under two licences, is
[RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md).

**Both halves are qualified the same way: ten consecutive cycles in one boot,
and a long sleep.**

Under the governor alone, in s2idle (experiment 17, run twice): the governor
set once, then ten `rtc_sleep 40 freeze` in a row with three seconds of quiet
between them, each suspend its own measured window. Both runs: ten wakes of
ten, 41 s by the RTC for a requested 40 on all twenty,
`suspend_stats/success` 0 to 10 with `fail` 0 and `last_failed_dev` empty, and
twelve card checks each -- one before, one inside each cycle, one at the end --
all `card-check ok`.

```text
cycle       1    2    3    4    5    6    7    8    9   10
run A     118  114  119  114  118  113!  116  112  114  114!
run B     114  115  114  116!  117!  114  110  116  113  119
```

Sixteen of the twenty windows are sound, 110 to 119 mA. The four marked `!`
lost two or three readings each to the supply's link dropping, which is a hole
in the measurement and not in the sleep -- the target's own account of those
four cycles is identical to the other sixteen. A third run was not attempted:
the link drops for a minute or two about once per eight-minute run, so a clean
ten in a row is a matter of luck rather than of the configuration.

Under `sr-phy-padhold-nodisp`, the kept firmware: ten consecutive forty-second
cycles read 66, 65, 60, 67, 60, 64, 62, 60, 60 and 67 mA -- median of medians
63.0, all ten windows sound, which is the first ten-cycle run on this bench
that lost nothing to the supply's link -- ten wakes of ten,
`suspend_stats/success` 0 to 10 with `fail` 0, twelve card checks and ten md5
checks unchanged. The means of the same ten windows are 88.7, 77.8, 74.2, 76.0,
69.7, 73.5, 78.6, 68.9, 81.0 and 84.2, which average about 77: the gap between
median and mean is wider on this rung than on any below it, and that is
[B9](RG35XX-PLUS-BENCH-EXPERIMENTS.md)'s question and not an answer. One
six-minute sleep read **62 mA** (mean 64.5, n=98) in one sound window with the
256 MiB probe's md5 unchanged after 361 s by the RTC.

Under `rocknix-deep`, the reference, on the evening its reliability was
counted: ten consecutive cycles read 65, 75, 72, 68, 74, 70, 71, 70, 75 and
74 mA -- median of medians 71.5, mean 71.4, eight of the ten windows sound and
two short of readings to a link dropout -- ten wakes of ten, ten card checks
and ten md5 checks unchanged; and one six-minute sleep read **70 mA** (50 to
92, IQR 10, n=116) with the 256 MiB probe's md5 unchanged after 361 s by the
RTC. Those eleven are the tail of thirty-five in a row that evening with no
failure.

`--suspend sr` is the fallback if the whole rebuild is in doubt and the
firmware has to be ours: 105 mA, sixteen proved sleeps, and a way back that
needs no DRAM driver at all. Not `sr-gate` or `sr-pll`, which the rebuild
supersedes, not the ablations, which exist to be measured rather than shipped,
and not any rung that rebuilds the PHY without the pad hold.

## What each step is worth

### The sysfs experiments, 1 to 17

Thirty-four experiments in all, one script each in [`jobs/sleep/`](jobs/sleep)
so every row can be run again, plus `apply-best.sh`: the first seventeen are
below, 18 to 26 and 29 to 34 are the firmware ladder in the next section, and
27 and 28 are the two checks that came out of the outside review, after that.
The firmware rows need their own card images, because the bootloader is part of
one. Cells are median / IQR / readings in mA over a 40 s sleep; `!` is an
UNSOUND window; "mean" is the mean of three medians in an A B B A A B run; "to
N" means row N decided it properly; "ref." is a reference point and not a
sleep.

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

The ladders of rows 5 and 6 measured each knob once, after its own reference,
and the drift through a boot made them disagree with each other; the
alternations of rows 7 to 10 supersede them. The sysfs experiments stopped where
the goal said they should: rows 11, 12 and 13 are three in a row with no gain
above the noise. What each of those dead ends measured is "What does not work"
below.

### The firmware ladder

Every rung is a separate bootloader build, a separate card image and its own
eight-minute deploy, and each was run through one sleep on its own before
anything was measured with it, because a rung that cannot come out of
self-refresh looks exactly like a target that stopped answering.

**The zero rung is parity.** Before anything of ours went on the card, the
unmodified build of the same two upstream trees replaced ROCKNIX's bootloader
in the sleep image and was measured against it.

```text
                                      ROCKNIX's build     ours, --suspend none
userspace milestone, cold start    5.66-5.76 s (five)    5.72, 5.76, 5.76 s
kernel stages 0 to 6                  1.25 to 1.69 s       1.25 to 1.69 s
asleep, s2idle, performance              126 mA mean          128 mA mean
asleep, s2idle, powersave                115 mA mean          115 mA mean
/sys/power/mem_sleep                       [s2idle]             [s2idle]
```

The sleep figures are the three-alternation means of
[`jobs/sleep/10-powersave-only-abba.sh`](jobs/sleep/10-powersave-only-abba.sh),
the experiment that decided the kept governor, run again unchanged: 131, 124
and 129 mA against 115, 114 and 116, six sound windows. Two builds of the same
sources are byte-identical, because U-Boot and TF-A are given a fixed build
date rather than the clock.

Taking s2idle as the anchor in each boot, and counting from the state the
device ships in:

```text
rung             what it adds                             asleep,      vs s2idle  kept
                                                        medians/means
wfi              PLL_CPUX stopped, DRAM running          112.5 mean     -4.5 mA    no
wfi32            + the cluster on 32 kHz                 113.3 mean     -6.3 mA    no
sr               + LPDDR4 in self-refresh (assembly)     104.7 mean    -11.6 mA    no
sr-gate          + DRAM bus and MBUS clock gates         101.3 mean    -14.7 mA    no
sr-pll           + PLL_DDR0 stopped, nothing rebuilt     does not resume           no
sr-c             sr again, from the C stub               104.5 mean    -13.8 mA    no
sr-phy           + DFI off, CLKEN 0, the DRAM clock       76.0 / 81.1  -39.3 mA    no
                   path in reset, PLL_DDR0 off, 32 kHz                  8 of 42 resumes failed
                   APBs, controller and PHY rebuilt
sr-phy-pllon     ablation: PLL_DDR0 left running          74.8 mean    -40.0 mA    no
sr-phy-fastapb   ablation: CPU and APBs on OSC24M         73.0 mean    -39.7 mA    no
sr-phy-nodisp    + PLL_VIDEO0, PLL_DE, DE gate off        66-71        not priced  no
sr-phy-nodisp-late  the same three, put back after the    66.0 median  not priced  no
                   rebuild instead of before it                        4 of 30 resumes failed
sr-phy-padhold   + the DRAM pads held while the PHY       69.7 / 79.4  -44.0 mA    no
                   is reset (the prior art's write)                     0 of 52 resumes failed
sr-phy-padhold-nodisp  + PLL_VIDEO0, PLL_DE, DE gate off  63.0 / 79.3  -55.7 mA   YES
                   on top of the pad hold                               0 of 50 resumes failed
rocknix-deep     theirs, the same idea, their code        68.3 / 79.7  -51.3 mA    reference
                                                                        0 of 35 resumes failed
```

Each "vs s2idle" is that rung's own boot, and the s2idle arms move between
boots by more than some of the differences, which is why the ablations are read
against each other and not against the table's left-hand column. `sr`'s saving
was measured three times in all -- 11.6, 4.7 and 10.3 mA, about 9 mA pooled --
and the steady number in it is the state the board ends up in, about 105 mA
every time, rather than the saving.

**The bottom three rows are the ones to read carefully.** Each figure is the
mean of that arm's three window medians, and beside it the mean of the same
arms' means. By medians ours ends up below theirs, 63.0 against 68.3; by means
the three are level, 79.4, 79.3 and 79.7, because the readings inside a
sleep window on these rungs are burstier than on any rung above. Both numbers
are real and the report quotes medians throughout, so the comparison between
ours and theirs is the one claim in this note that the choice of statistic
decides. What would settle it is a scope across a shunt, which is
[B9](RG35XX-PLUS-BENCH-EXPERIMENTS.md).

The experiment numbers are 18 to 21 for `wfi`, 22 to 26 for the self-refresh
rungs, 29 to 33 for the PHY rebuild and 34 for how often that rebuild comes
back; 25, 26 and 34 are generic and were run again at each kept rung.

```text
 #  what was run                                        s2idle      the rung    wake  card  DRAM
19  wfi, one deep sleep, first of its kind                --       109/16/11     yes   ok    --
20  wfi against s2idle, ABBAAB                         117 mean    112 mean      6/6   ok    --
20  the same again                                     117 mean    114 mean      6/6   ok    --
21  ten consecutive deep cycles                           --        110-117     10/10  ok    --
23  sr, one sleep, first of its kind                      --       106/5/14      yes   ok    ok
24  sr against s2idle, ABBAAB                          116 mean    105 mean      6/6   ok   6/6
25  ten consecutive self-refresh cycles                   --        103-112     10/10  ok  10/10
26  one six-minute self-refresh sleep                     --      106/13/112     yes   ok    ok
23  sr-gate, one sleep, first of its kind                 --        99/10/11     yes   ok    ok
24  sr-gate against s2idle, ABBAAB                     116 mean    101 mean      6/6   ok   6/6
30  sr-phy, one sleep, first of its kind                  --       73.5/9/10     yes   ok    ok
31  sr-phy, three watchdog-covered short sleeps           --         3/3          3/3  ok   3/3
32  sr-phy against s2idle, ABBAAB                     115.3 mean    76.0 mean    6/6   ok   6/6
25  sr-phy, ten consecutive cycles                        --        68.5-79     10/10  ok  10/10
26  sr-phy, one six-minute sleep                          --        75/9/114     yes   ok    ok
34  sr-phy, how often it comes back                       --           --       34/42  ok  34/34
34  sr-phy-nodisp, the same                               --           --       12/12  ok  12/12
34  sr-phy-nodisp-late, the same                          --        66.0 median 26/30  ok  26/26
34  rocknix-deep, the same                                --           --       24/24  ok  24/24
25  rocknix-deep, ten consecutive cycles                  --         65-75      10/10  ok  10/10
26  rocknix-deep, one six-minute sleep                    --        70/10/116    yes   ok    ok
34  sr-phy-padhold, how often it comes back               --           --       48/48  ok  48/48
24  sr-phy-padhold against s2idle, ABBAAB              113.7 mean   69.7 mean     6/6   ok   6/6
26  sr-phy-padhold, one six-minute sleep                  --      72/-/105 (u)    yes   ok    ok
34  sr-phy-padhold-nodisp, how often it comes back        --           --       36/36  ok  36/36
24  sr-phy-padhold-nodisp against s2idle, ABBAAB       118.7 mean   63.0 mean     6/6   ok   6/6
25  sr-phy-padhold-nodisp, ten consecutive cycles         --         60-67      10/10  ok  10/10
26  sr-phy-padhold-nodisp, one six-minute sleep           --        62/-/98      yes   ok    ok
```

Cells are median / IQR / readings in mA over a 40 s sleep, `(u)` marking a
window the supply's link made unsound; "mean" is the mean
of three medians in an A B B A A B run, A being `mem` resolved to s2idle and B
`mem` resolved to `deep`, with the `powersave` governor set once at the top and
in force in both arms. The harness opens an extra short window over the md5
check between sleeps, 9 to 10 s long and reading 166 to 181 mA; that is the
target awake, not a sleep, and `--min-window-seconds 30` drops them before the
labels are handed out.

**`wfi`: the CPU PLL alone is worth about four milliamps, which is not a
difference.** Seventeen deep suspends were entered across four boots and
seventeen resumed. Every one of them: the RTC read 41 s for a requested 40,
`suspend_stats/success` went up by one with `fail` unchanged and
`last_failed_dev` empty, the card check passed after the resume, and EL3's own
counters agreed -- one more suspend entered, one more resume finished, stage
`0xa5d50008`, which is written from the PSCI resume hook and therefore only
after the warm boot has handed control back. The s2idle sleeps in the same runs
left those counters untouched, which is what says `deep` is really going
through EL3 and `s2idle` is not. The interrupt EL3 found pending when the WFI
ended was 136 on all seventeen; the H616 manual's interrupt table calls 136
`R_Alarm0`, so the RTC alarm is ending the wait, at EL3, exactly as intended.
The three alternations read 119, 116, 116 mA in s2idle against 113, 110 and 114
in deep (4.5 mA); 113, 119, 119 against 114, 112, 116 (3.0 mA); and, re-run
independently, 116 mean against 113. Ten consecutive deep cycles in one boot:
112, 110, 114, 113, 112, 110, 112, 115, 114 and 116 mA, ten sound windows
between 110 and 117. The difference is in the same direction every time and is
about four milliamps, against a threshold of eight. That is not a surprise on
reflection: a core in WFI is already clock-gated, so the 24 MHz step costs
nothing by itself, and what remains is PLL_CPUX's own bias current on a 1.8 V
rail.

**`wfi32`: the vendor's 32 kHz cluster step is worth six or seven.** Built
early and left unrun on the grounds that a core waiting for an interrupt is
clock-gated anyway, it was run later: 121, 119 and 119 mA in s2idle against
114, 112 and 114, two of the s2idle windows unsound. Worth slightly more than
stopping the PLL alone and nowhere near forty. The APB half of the same step is
priced by `sr-phy-fastapb` below, at nothing.

**`sr`: the LPDDR4 in self-refresh is worth about nine milliamps pooled, and it
is the first thing above the noise since the governor.** The first alternation
read 119, 114 and 116 mA in s2idle against 103, 107 and 104 in self-refresh:
116.3 mean against 104.7, **11.6 mA**, all six windows sound, all six wakes, all
six card checks, all six md5 checks unchanged. EL3's suspend and resume counters
went 0, 1, 2, 2, 2, 3 across the six sleeps -- up by one on each of the three
deep arms and untouched on each of the three s2idle ones -- with the stage
reading `0xa5d50008` and the wake interrupt 136 every time. **The alternation
was then run twice more by someone who had not written it**, from the committed
script and image, a cold boot each, windows read by their dwell because the md5
check shifts the labels: 112, 108 and 109 mA in s2idle against 104 (unsound,
seven readings), 104 and 107, 109.7 mean against 105.0; then 114, 112 and 119
against 104, 108 and 102, 115.0 against 104.7. Twelve wakes of twelve, twelve
card checks, twelve md5 checks unchanged, EL3's counters up on the deep arms
only. The self-refresh arm is the steady one, 104.7, 105.0 and 104.7 mean in
the three runs; the s2idle arm moves between boots, 116.3, 109.7 and 115.0, and
the saving moves with it: 11.6, 4.7 and 10.3 mA, **about 9 mA pooled**. Ten
consecutive cycles in one boot: 103, 104, 107, 104, 104, 106, 112, 109, 106 and
107 mA, ten sound windows, ten wakes of ten, 41 s by the RTC for a requested 40
on all ten, `success` 0 to 10 with `fail` 0, twelve card checks of twelve, ten
md5 checks unchanged, EL3's counters reaching 10 and 10. **One sleep of six
minutes**, which is the measurement that settles whether anything is being
refreshed: 361 s by the RTC for a requested 360, 105.5 mA median over 112
readings in one unbroken sound window, IQR 13, and the 256 MiB probe's md5
unchanged. A DRAM that nobody was refreshing would not survive six minutes; a
forty-second sleep cannot tell the difference. Against the rung below, taking
s2idle as the anchor in each boot, self-refresh is worth about 8 mA more than
stopping the CPU PLL alone. Put back on the card after the two rungs above it
had been tried and taken off again, `sr` slept once more at 104 mA with its
probe unchanged, which is the sixteenth self-refresh sleep.

**`sr-gate`: the two DRAM-side clock gates are worth about three and a half,
which is less than half of a difference.** Its s2idle arms read 116, 116 and
116 mA and its gated arms 102, 104 and 98, a mean of 101.3 against 116.0.
Against `sr`'s 104.7 with an s2idle anchor of 116.3 in its own boot, that is
about 3.4 mA better -- the right direction, and not believed. Six wakes of six,
six md5 checks unchanged, `success` 0 to 6 with `fail` 0, EL3's counters at 3
and 3, and every CCU register the stub touched read back afterwards exactly as
it was found: `MBUS_CFG` `0xc1000002`, `DRAM_BGR` `0x00010001`. The first
s2idle window lost one reading to the supply's link dropping and is marked
unsound, though its median is the same 116 as the other two. It is built, it
works, and it is not the recommendation: it has four self-refresh sleeps behind
it rather than `sr`'s sixteen, and `sr-phy` supersedes it by 25 mA.

**`sr-c`: the same registers as `sr`, from the C stub, reads the same.** 104.5
mean against `sr`'s 104.7. It is the rung that made `sr-phy` safe to try: the
same register sequence as the assembly stub -- which had sixteen proved sleeps
behind it -- written in C and run from the new SRAM environment. So when
`sr-phy` worked, nothing about it was the environment; and had it not, the
environment would not have been the suspect. Its snapshot, taken at the
instruction before WFI, shows `PLL_DDR0` and the whole DRAM clock path still
running, which is what that rung is.

**`sr-phy`: the controller, the PHY and the DRAM clock path off, and built
again on the way back, is worth 29 mA more than everything above it.**

- **Three watchdog-covered short sleeps first.** Before anything was measured:
  three ten-second sleeps with the stub asked, through an RTC register, to keep
  the watchdog armed across the wait as well as around it, so that a hang
  anywhere would become a warm reset with its stage code readable on the next
  boot. Three resumes, three md5 checks unchanged, stage `0xa5d50042` and
  status 1 each time.
- **The alternation:** 112, 117.5 and 116.5 mA in s2idle against 76, 77 and
  75 in `sr-phy`. 115.3 mean against 76.0, **39.3 mA**, against a threshold of
  about eight. All six windows sound, all six wakes, all six md5 checks
  unchanged. By means of the same readings, 117.3 against 81.1.
- **The alternation again, by someone who had not written it**, from the
  committed script and the image left on the card, a cold boot, labels assigned
  with `--min-window-seconds 30`: 115, 119 and 122 mA in s2idle against 77, 78
  and 75 in `sr-phy`, 118.7 mean against 76.7, **42 mA**; by means 123.0
  against 86.1, one deep window's mean pulled up to 95 by a single high
  reading. Six windows sound, six wakes of six, six md5 checks unchanged.
- **Ten consecutive cycles in one boot**: ten wakes of ten, 42 s by the RTC for
  a requested 40 on all ten, `success` 0 to 10 with `fail` 0, twelve card
  checks, ten md5 checks unchanged. The harness opened eleven forty-second
  windows for the ten sleeps and two short ones for the gaps; every one of the
  eleven is between 68.5 and 79 mA.
- **One sleep of six minutes**, the cleanest single figure this rung produces:
  361 s by the RTC for a requested 360, **75 mA over 114 readings** in one
  unbroken sound window, IQR 9, and the 256 MiB probe's md5 unchanged. A
  controller and a PHY were switched off, built again from a driver running out
  of SRAM, and a gigabyte of DRAM came through six minutes of holding itself.

**Which sub-step carries the 29 mA.** Each ablation is the whole of `sr-phy`
with one sub-step left out, built as its own bootloader, put on the card by its
own eight-minute deploy, and alternated against s2idle in its own boot; six
sleeps each, six md5 checks each.

- **Stopping PLL_DDR0 is worth nothing.** `sr-phy-pllon` reads 74.8 against
  76.0, in two boots whose s2idle arms agree to half a milliamp, which makes
  this an unusually clean comparison and the answer an unusually confident one:
  the DDR PLL's own bias current is not where the saving is. It is left in
  because it costs nothing, is what the prior art does, and is the honest end of
  the clock tree -- but the 29 mA is not in it.
- **Nor is the 32 kHz clock step.** `sr-phy-fastapb`, with the cluster and both
  APBs left on the 24 MHz oscillator, reads 73.0 against 76.0, and 39.7 mA of
  saving against 39.3 -- the wrong side of `sr-phy`, by less than the noise.
  That agrees with `wfi32`, which priced the cluster half of it at six or seven
  milliamps at a rung where the DRAM was still running, and says the APB half is
  not worth anything either. It too is kept because it costs nothing and is what
  the vendor's standby code does.
- **So the 29 mA is the DFI shutdown, the controller's own clock enables and
  the reset**, by elimination. `sr-gate` had already gated `MBUS_CFG` bit 31 and
  `DRAM_BGR` bit 0 for 3.4 mA; what `sr-phy` adds on top of the two ablated
  steps is shutting the DFI interface down, clearing `CLKEN`, and holding the
  clock path and MBUS in *reset* rather than merely gated. Nothing here
  separates those three from each other; separating them would be three more
  rungs and three more deploys.

**`sr-phy-nodisp` reads about eight milliamps lower and is not kept**, because
one of its first three sleeps failed its PHY rebuild; it is in "What does not
work" below with the evidence it left. The eight milliamps are real and are
collected by `sr-phy-padhold-nodisp`, which is the same three clocks on a rung
that comes back.

**`rocknix-deep`: theirs, on the same card, the same kernel, the same harness
and the same day.**

```text
                                 theirs (rocknix-deep)   ours (sr-phy)
s2idle arms, medians                121, 114, 124        112, 117.5, 116.5
the deep arms, medians                70, 67, 68            76, 77, 75
   the same windows, means         127, 131, 129 /       117.3 / 81.1
                                      81, 79, 79
saving against its own s2idle          51.3 mA              39.3 mA
one six-minute sleep                72 mA, n=115          75 mA, n=114
one sleep, first of its kind           65 mA                73.5 mA
```

Six wakes of six each, the 256 MiB probe's md5 unchanged every time, 361 s by
the RTC for a requested 360 in each long sleep, on a 1 GiB LPDDR4 board their
authors had not run. **On the six-minute sleep the two are three milliamps
apart, which this bench does not call a difference.** On the forty-second
alternation ours reads about eight milliamps higher and saves about twelve
less, and the two runs' s2idle arms differ by four, so some of that is the boot
and not the firmware. Two things theirs does that ours did not were the DRAM
pad hold and the PRCM register at `+0x244` with a key of `0xa7`, which takes a
PLL LDO down. The first has since been made and is the next subsection; the
second is a supply and not a clock, this work writes no supply of any kind, and
it is the only write left that separates the two sequences.

### The two pad-hold rungs: what each was measured with

**2026-09-21, one card, one bitstream, one harness, `powersave` set once in
every boot, `--card-max-hz 6000000`, every current at the 5 V USB-C input.**
These are the two rungs that hold the DRAM pads while the PHY is reset and
unclocked. The write itself, the polarity question and who authorised it are
[RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md)'s; this is what they
measured.

**`sr-phy-padhold`** -- `sr-phy` with `STUB_PAD_HOLD=1` and nothing else
changed. Image sha256 `0845a457...`.

- **Reliability (experiment 34, job 34): 48 of 48 came back, no failure.** Four
  batches of twelve ten-second watchdog-covered sleeps, each sleep followed by
  the 256 MiB md5 check, counted in the card's own sector so a reset cannot
  hide one. Its control, `sr-phy`, lost eight of forty-two in exactly the same
  shape.
- **The alternation (job 24, A B B A A B, `--min-window-seconds 30`):** 115,
  119 and 107 mA in s2idle against 67, 67 and 75 in the deep arms. 113.7 mean
  against 69.7, **44.0 mA**, all six windows sound, six wakes of six, six md5
  checks unchanged. By the means of the same readings, 124.3, 121.3 and 111.6
  against 76.3, 76.3 and 85.6.
- **One sleep of six minutes (job 26):** 361 s by the RTC for a requested 360,
  **72 mA** median, mean 72.5, n=105, the probe's md5 unchanged. **The window
  is UNSOUND**: the supply's wireless link dropped inside it, so by this note's
  own rule it is not a measurement, and it is recorded because the sleep and
  the md5 are evidence even when the current is not.
- Fifty-two deep sleeps in all -- 48 plus the alternation's three deep arms
  plus the long one -- with no failure and every md5 unchanged.

**`sr-phy-padhold-nodisp`** -- that rung with PLL_VIDEO0, PLL_DE and the DE bus
gate stopped as well, restored in the ordinary place, before the rebuild,
because the late restore had already measured no different. Built by commit
`aeb9380`, `-DSTUB_LEVEL=2 -DSTUB_PAD_HOLD=1 -DSTUB_DISPLAY_OFF=1`. Image
sha256 `4389c576...`.

- **Reliability: 36 of 36 came back, no failure.** Three batches of twelve, the
  same shape as above.
- **The alternation:** 113, 119 and 124 mA in s2idle against 57, 65 and 67 in
  the deep arms. 118.7 mean against 63.0, **55.7 mA**. Six md5 checks
  unchanged. **Two of the six windows are unsound** -- the second s2idle arm
  and the last deep arm -- and the link was flapping throughout, so the deep
  windows hold only five to seven readings each, which is thin for a median.
  By means: 120.0, 123.4 and 129.7 against 79.0, 77.2 and 81.6.
- **Ten consecutive forty-second cycles (job 25):** ten wakes of ten,
  `suspend_stats/success` 0 to 10 with `fail` 0, ten md5 checks and twelve card
  checks, **all ten windows sound** -- medians 66, 65, 60, 67, 60, 64, 62, 60,
  60 and 67, means 88.7, 77.8, 74.2, 76.0, 69.7, 73.5, 78.6, 68.9, 81.0 and
  84.2. This is the cleanest evidence the rung has: ten sound windows in one
  boot, nothing lost to the link.
- **One sleep of six minutes:** 361 s by the RTC, **62 mA** median, mean 64.5,
  n=98, one sound window, the probe's md5 unchanged.
- Fifty deep sleeps in all: 36 plus three alternation arms plus the long one
  plus the ten cycles, no failure, every md5 unchanged.

**What the pair says.**

- **The pad hold is what makes our rebuild reliable.** 0 of 48 and 0 of 36
  against 8 of 42, on the same card, the same harness and the same batch shape
  one day apart. It is the only change between `sr-phy` and `sr-phy-padhold`.
- **It is also worth a few milliamps by itself**, which nobody expected: 69.7
  against `sr-phy`'s 76.0, and 44.0 mA of saving against 39.3 in each rung's
  own boot. That is under this bench's eight-milliamp threshold and is recorded
  as suggestive, not as a difference.
- **The display clocks are worth about seven to twelve, and this is the first
  rung that could collect them.** Deep arms 63.0 against 69.7 is 6.7; savings
  against each boot's own s2idle anchor, 55.7 against 44.0, is 11.7; the
  six-minute sleeps, 62 against 72, is 10, and the 72 is from an unsound
  window. All three are separate boots with no alternation between the two
  rungs themselves, so the spread is the boot as much as the clocks. The
  earlier unreliable reading of the same three clocks was about eight to nine
  milliamps, and these agree with it.
- **Against the published implementation, by medians, ours is now lower:**
  63.0 against 68.3 on the alternations and 62 against 70 to 72 on the
  six-minute sleeps. Six to ten milliamps, against a threshold of eight -- the
  long sleeps clear it and the short ones do not. **By the means of the same
  readings the three rungs are level**, 79.3 for ours against 79.7 for theirs,
  and the gap between median and mean is wider on this rung than on any other
  in this note. Whether that is real bursts or the supply's sampling is exactly
  [B9](RG35XX-PLUS-BENCH-EXPERIMENTS.md).

### How often the rebuild does not come back (experiment 34)

**Ours failed about one resume in five and theirs did not fail at all, and one
register write is the whole difference.** That is the evening of 2026-09-20,
ninety-nine deep sleeps across four firmwares, which overturned the rung the
ladder above had kept, and then 2026-09-21, eighty-four more across two, which
fixed it.

The question was meant to be narrower. `sr-phy` had eighteen sleeps and no
failure, `sr-phy-nodisp` had three and one, and the obvious reading was that
restarting two display PLLs immediately before the PHY is re-trained had broken
the rebuild. Three sleeps cannot say that -- a rung that fails one in five
comes out clean in three sleeps half the time -- so the rate was measured
first, on the control as well as on the variant.
[`jobs/sleep/34-reliability-short-sleeps.sh`](jobs/sleep/34-reliability-short-sleeps.sh)
is how: a batch of short deep sleeps, each followed by the 256 MiB md5 check,
with the running count kept in a sector of the debug partition and tagged with
the job's sequence number, so that the warm reset a failed rebuild causes --
which restarts the job, empties tmpfs and rewrites the result region -- cannot
hide a failure or a sleep. The host allows the run to survive those resets with
`--expect-reboots`.

```text
firmware                   sleeps  did not come back   the shapes it was run in
sr-phy (ours)                 42          8 (19%)     24x10 s watchdog, 12x10 s none, 6x40 s
sr-phy-nodisp (ours)          12          0           12x10 s watchdog
sr-phy-nodisp-late            30          4 (13%)     24x10 s watchdog, 6x40 s
rocknix-deep (theirs)         35          0           24x10 s, 10x40 s, 1x360 s
sr-phy-padhold (ours)         48          0           48x10 s watchdog, four batches of twelve
sr-phy-padhold-nodisp (ours)  36          0           36x10 s watchdog, three batches of twelve
```

The last two rows are 2026-09-21 and the rest are 2026-09-20; the batches are
the same script, the same shape and the same card. **The pad hold is the only
difference between row 1 and row 5, and between rows 3 and 6.** Against
`sr-phy`'s eight failures in forty-two, forty-eight clean sleeps is p = 0.0015
by Fisher, one-sided, and thirty-six is p = 0.005 -- the same test, and a
slightly stronger result, than the one that says theirs is better than ours.

Every single failure left the same four words behind, on every firmware of ours
that failed:

```text
el3 stage=0xA5D500E5   stub fail_reg=0x047FB004 fail_info=0x00350007 await=0x107FB010
```

Stage `0xe5` is the stub giving up and resetting; `fail_info` is stage `0x35`
with reason 7, the marker immediately before read calibration and
`mctl_phy_init()` returning false, so read calibration failed all five of its
tries; and the await counter is unchanged from the sixteen bounded waits before
it, so nothing hung and no poll timed out. **The PHY simply would not
calibrate, and it is the same failure every time.** Every resume that did
happen passed its md5 check: the failure mode is a board that resets, not
memory that comes back wrong.

What that rules out, each by a batch of its own:

- **Not the display clocks.** The control fails at the same rate with the same
  signature. 8 of 42 for `sr-phy` against 4 of 30 for the late-restore variant
  is nothing (Fisher, one-sided, p = 0.38), and the premise that
  `sr-phy-nodisp`'s one failure in three was caused by two PLLs relocking does
  not survive its own control. `sr-phy-nodisp` itself, re-run as it stands,
  went twelve for twelve -- which says nothing on its own, since twelve clean
  sleeps happen one time in twelve at this rate, but it is not the behaviour of
  a rung that is broken and its control is not.
- **Not the change that was made to test it.** `sr-phy-nodisp-late` restores
  `PLL_VIDEO0`, `PLL_DE` and the DE bus gate only after the controller and the
  PHY have been rebuilt and a deliberate read of the restored memory has
  matched. It fails as often as everything else of ours.
- **Not the debug watchdog.** Twelve sleeps with it armed across the wait and
  twelve without, in the same shape: 4 of 24 against 3 of 12. It could not have
  been: a rebuild that gives up calls `stub_reset()`, which arms a half-second
  watchdog of its own, so the failure resets the board and leaves its evidence
  whether or not the debug request was made.
- **Not the length of the sleep.** Six forty-second sleeps of `sr-phy` -- the
  same length as every measurement in this note -- failed one. The eighteen
  clean forty-second sleeps the rung was kept on were luck: at one in five,
  eighteen in a row come out clean about twice in a hundred tries.

**What it leaves is the one write our stub does not make.** `rocknix-deep` is
kailashrs' TF-A patch and SRAM stub built from source at the commits ROCKNIX
pins, with none of ours; it shuts the same blocks down in the same order and
rebuilds them with the same U-Boot driver, and 35 of 35 came back (against ours,
Fisher, one-sided, p = 0.006). Their stub's suspend sequence differs from ours
in exactly two writes, and both are writes this work deliberately does not
make:

- **RTC + 0x1F4 bit 0, the DRAM pad hold**, which they clear immediately after
  self-refresh is confirmed and before the DFI is shut down, with the comment
  "Hold the DRAM pads (CKE low) while the PHY is reset and unclocked", and set
  again in their resume path before the controller is told to leave
  self-refresh. Ours does neither. That is a mechanism for exactly this
  failure: if CKE is not held while the PHY is unclocked and in reset, what the
  memory sees during the rebuild depends on what the pads do, which is not the
  same on every cycle -- an intermittent failure of the first step that reads
  the array is what it would look like. **That is what it was.** The write was
  authorised and made on 2026-09-21, and `sr-phy-padhold` resumed 48 of 48 and
  `sr-phy-padhold-nodisp` 36 of 36:
  [the per-rung evidence](#the-two-pad-hold-rungs-what-each-was-measured-with)
  is above.
- **PRCM + 0x244 with a key of `0xa7`**, a PLL LDO, which is a supply and not a
  clock and is not written here either. It is now the only write that
  separates the two suspend sequences, and there is no longer a reliability
  difference for it to explain.

Their `udelay(1000)` after the APBs are restored, against our `udelay(100)`, is
the only other difference in the resume path and is not obviously enough to
matter; it has not been tried, and the failure it might have explained is
gone.

**The eight milliamps the display clocks are worth are still there, and they
were not priced properly.** The forty-second batches of experiment 34 hold six
sound sleep windows each, same evening, same governor, same harness, and they
read: `sr-phy` 73.5, 71, 75, 75, 77, 77 -- median of medians 75.0, mean 74.8;
`sr-phy-nodisp-late` 67, 70, 65, 60, 73.5, 65 -- median 66.0, mean 66.8. Nine
milliamps apart, in the same direction as the earlier reading of about eight,
and above this bench's eight-milliamp threshold. It is **not** an A-B-B-A-A-B
figure: the two arms are separate boots half an hour apart with no s2idle
anchor inside either, which is exactly the comparison this note does not
normally believe, and each arm contains a reset. It is recorded as what it is.
**The rung that could carry it arrived the next day**, and on the pad-hold pair
the same three clocks read seven milliamps apart by deep arms and ten on the
six-minute sleeps, which is the same answer from better evidence.

So the ladder's 76 mA is a real current and `sr-phy` is not a configuration
anybody can keep; nor is any other rung that rebuilds the PHY without holding
the pads. The card was left carrying `rocknix-deep` that evening and carries
`sr-phy-padhold-nodisp` now.

### Two checks that came out of the outside review

Experiments 27 and 28 are the points of the outside review that could be
answered the same day with nobody at the bench. The review itself, point by
point, is
[RG35XX-PLUS-POWER-RESEARCH.md](RG35XX-PLUS-POWER-RESEARCH.md); the results are
here.

```text
 #  what was run                            awake before  awake after   asleep
27  stay awake past the 32 s reg. cleanup      141 mA        142 mA    107, 104
28  six awake windows, no suspend at all    142, 140, 139, 144, 134, 145 mA
```

- **The regulator-cleanup race is closed, and it was worth nothing.**
  Experiment 27 stays awake past the kernel's one cleanup instead of sleeping
  through it: `aldo3: disabling` at 32.05 s, and `aldo3` reads `disabled`
  afterwards rather than `enabled` with no users. The same awake idle state
  read 141 mA before it and 142 mA after, and two self-refresh sleeps taken
  with `aldo3` off read 107 and 104 mA against the 105 every self-refresh sleep
  has read with it on. The upstream board file calls ALDO3 unused, and an
  output with nothing on it saves nothing. Every earlier figure in this report
  was taken with the cleanup still pending, and this is the measurement that
  says that does not matter.
- **`dcdc4` is not a rail to chase.** It stays `enabled` with no users right
  through the cleanup. On an AXP717 configured as a charger DCDC4 is not an
  independent output at all; the regulator framework's 1.0 V entry is a
  descriptor and not evidence of a supply. It is left alone.
- **Charging cannot be switched off through the driver in this kernel.** The
  same job lists the power-supply class: the battery reports `present=0` and
  `Not charging`, and there is no charge-enable attribute anywhere under
  `/sys/class/power_supply`, so that experiment needs a driver change or a
  person with a battery.
- **The drift goes with the transitions, which is suggestive and not
  established.** Inside the one six-minute self-refresh sleep the current does
  not climb: 104, 102 and 107 mA taken by thirds of the window. Experiment 28
  is the other half of the control -- the alternations' awake work, a 256 MiB
  md5, at the same dwell, six times in one boot with no suspend at all: 142,
  140, 139, 144, 134 and 145 mA while the SoC warmed from 36.0 to 37.9 C, which
  is no climb that a 10 mA spread can show. So the 1.5 mA per cycle is not time
  asleep and not the awake work between cycles; what is left is the suspend and
  resume transitions themselves, and nothing here has measured that directly.

### What is measured here, and what is assumed

- **Measured:** every current above; every wake, with the RTC's own account of
  each sleep, `suspend_stats`, a card check either side, and from the
  self-refresh rung onwards a 256 MiB md5; EL3's stage and counter registers
  and the stub's status, stage, wake interrupt and DRAM geometry, read out of
  SRAM after each sleep; the wake interrupt, 136 on every one; the CCU
  snapshot; the card's clock, which the FPGA counts at exactly zero edges a
  second for the whole sleep; and the parity of the from-source bootloader
  against the one it replaced.
- **Measured, and worth saying separately:** that the controller comes back in
  normal operating mode with `CLKEN` back to `0x8100`, `MSTR`, `STAT`,
  `DFIMISC`, `SWCTL` and `SWSTAT` as they were, and its three master-enable
  registers back to `0xffffffff`, `0x7ff` and `0xffff`, all read through
  `/dev/mem` after the resume; that the watchdog is back to `CFG=1 MODE=0`,
  which is how the stub found it; and that the rebuild takes seventeen bounded
  waits, the last on `SWSTAT`, which the stub records in an RTC register as it
  goes, so a rebuild that hung would say which wait it hung on.
- **Assumed, because nothing here can look:** that the memory is in
  self-refresh *for the whole* of the wait rather than only when `STAT` was
  read, and that PLL_CPUX is genuinely off during the WFI. Nothing can read a
  register while the core is in WFI and there is no debug port. The six-minute
  sleep is the argument, and it is a stronger one at `sr-phy` than at `sr`: the
  controller that would have been refreshing the memory has been in reset for
  the whole six minutes and was built again from scratch afterwards.
- **Assumed:** that 160 words -- eighty at the base of the memory and eighty at
  its half-way point -- are all the PHY's training writes over. That figure is
  the prior art's, arrived at empirically; nothing documents it. What is
  measured is that a 256 MiB probe's md5 survives -- eighteen times at `sr-phy`,
  and every one of the fifty deep sleeps of the kept rung.
- **Written, and no longer on this list:** RTC + 0x1F4 bit 0, the DRAM pad
  hold. It is documented (H616 User Manual 3.13.6.17), it is in the RTC block
  and not the PMIC, it involves no rail and no voltage, the worst case is a
  resume that does not happen -- and it is what makes our rebuild reliable. The
  rule it broke was this work's own, the owner lifted it for this write, and
  the whole story is
  [RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md)'s "what is
  deliberately not written".
- **Not touched, deliberately:** the PRCM register at `+0x244` that the prior
  art writes with a key of `0xa7`, because it is a supply and because their own
  comment marks it inferred and the manual does not document that block; and
  the PMIC, over any bus.

## What is still running, and where the rest of the current is

**Awake and idle, from the discovery job:**

- **`performance` at 1416 MHz** as the image ships. `cpufreq-dt` is bound with
  the `performance` governor and `scaling_cur_freq` 1416000, the top of a ladder
  that goes down to 480000; `conservative ondemand userspace powersave
  schedutil` are all available.
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
- **Eleven PLL control registers, read through `/dev/mem`** (experiment 22).
  Awake and idle with the panel asleep, five have their enable bit set:

```text
enabled   PLL_CPUX  PLL_DDR0  PLL_PERI0  PLL_VIDEO0  PLL_DE
disabled  PLL_DDR1  PLL_PERI1  PLL_GPU0  PLL_VIDEO1  PLL_VIDEO2  PLL_VE
```

**Asleep, which nothing could see before.** Twenty-four CCU registers are read
by the stub itself at the last instruction before WFI and left in the parameter
block in SRAM, which keeps its contents through the sleep; a job reads them out
of `/dev/mem` afterwards. A register cannot be read while the core is in WFI,
and by the time Linux is back its drivers have turned their clocks on again,
which is why experiment 22's inventory is an awake-idle one and this is not. At
the instruction before WFI, with `sr-phy`:

```text
enabled    PLL_PERI0   PLL_VIDEO0   PLL_DE
disabled   PLL_CPUX*  PLL_DDR0*  PLL_DDR1  PLL_PERI1  PLL_GPU0
           PLL_VIDEO1  PLL_VIDEO2  PLL_VE  PLL_AUDIO
clocks     CPUX_AXI, APB1, APB2 all on the 32 kHz source*
           MBUS gated and in reset*, DRAM_CLK and DRAM_BGR cleared*
gates      DE bus clock ON; GPU, SMHC and USB bus clocks off;
           VE in reset with its gate clear
```

`*` is the stub's own work; everything else is the state Linux and its clock
framework left behind. So the kernel does take most of the pipeline down --
`PLL_VIDEO1`, `PLL_VIDEO2`, `PLL_VE`, `PLL_GPU0` and `PLL_AUDIO` are all off,
and so are the card and USB bus clocks -- but **`PLL_VIDEO0`, `PLL_DE` and the
DE bus clock are still running with the panel long asleep.** `PLL_PERI0` is
also on and stays: it feeds the card controller among much else.

**Where the remaining 30 mA probably is.** A sleeping board now draws about 62
to 63 mA and a powered-off one 33. Almost none of the difference can be a
clock: every PLL that can be stopped has been *except one*, the CPU and both
APBs are on 32 kHz, the whole DRAM clock path is in reset, the one PLL whose
stopping was expected to matter, PLL_DDR0, measured nothing, and the three
display clocks the snapshot found have since been stopped for about seven
milliamps -- which is most of what was left to take at this level. What is left
is `vdd-dram` holding a gigabyte that is refreshing itself -- which is the
floor for any sleep that keeps its memory -- the other core rails at full
voltage (`vdd-gpu-sys`, `vcc-pll`, `vcc-io`, `avcc`, `cpusldo`,
`vcc-spkr-amp`), and the AXP717's own conversion and charger path with no cell
on it. That last is worth suspecting first: 33 mA for a board that is off is a
lot, and it may be mostly that. Reaching the rails is a PMIC question, and
nothing here writes a PMIC register. The hypotheses, and what evidence each
would need, are
[RG35XX-PLUS-POWER-RESEARCH.md](RG35XX-PLUS-POWER-RESEARCH.md).

**The one clock-level item left is `PLL_PERI0`.** The snapshot has it running
in every sleep this work has taken, ours and theirs, and neither the prior art
nor the vendor's standby code stops it. It feeds the card controller among much
else, which is why it has been left alone and why stopping it is not a one-line
rung: whatever it clocks has to be quiesced first and put back on the way out,
and on this bench the card is also the only way the target can say anything.
Nothing should be written for it until a mainline source says what depends on
it and how the vendor parks those consumers -- the same rule that kept the pad
hold out until the manual was found to document it.

## What does not work, or is blocked, and the measurement that says so

- **Nothing else sysfs reaches is worth anything.** Experiment 13 unbound
  twenty-five devices at once on top of the kept governor -- the DRM master, the
  panel, both TCONs, both mixers, the HDMI controller and its PHY, the TCON top,
  the planes, the DE2 bus, the GPU, the audio codec, the HDMI audio codecs, the
  display connector, both card controllers that are not the root device, the
  backlight PWM and its PWM controller, the watchdog, the eFuse, the spare
  UART, the PMIC's ADC and its battery and USB power-supply drivers, and the
  SoC's own ADC -- and turned both LEDs off: 112 mA before, 109, 113 and 109
  after. The drift runs the other way, so if anything that is an over-estimate
  of the gain. The rails that were still up afterwards are the answer:
  `vcc-pll` 1.8 V, `vcc-spkr-amp` 3.3 V, `vcc-io` 3.3 V, `cpusldo` 0.9 V,
  `vdd-cpu` 0.9 V, `vdd-gpu-sys` 0.9 V, `vdd-dram` 1.1 V, `dcdc4` 1.0 V,
  `aldo3` 1.8 V and `avcc` 1.8 V. Only `vcc-wifi` and `vcc3v3-mmc2` ever went
  away, and experiment 8 prices those two together at about a milliamp: three
  sleeps with them on read 125, 125 and 126 mA and three with them off read 124,
  126 and 129. Whatever the remaining current is, it is on rails no consumer in
  this kernel will release. Setting `status = "disabled"` on the same nodes in
  the device tree would stop them being probed at all, which is tidier than
  unbinding and, on this evidence, worth about the same, namely nothing.
- **Offlining cores buys nothing on its own** (experiment 7, three alternations
  at `performance`: 124 mA mean with four cores, 127 mean with one). The cores
  do go offline through PSCI CPU_OFF, they stay offline across a suspend and the
  wake is unaffected -- `online` still read `0` after the sleep in experiment 6
  -- but an idle core in s2idle is in WFI on a rail shared with the one that
  stays, and taking it away does not lower the rail. Experiment 9's saving is
  the governor's, which experiment 10 then measured on its own at the same
  11 mA.
- **Unbinding `panel-mipi` while the DRM master holds it costs the wake**,
  twice (experiments 4 and 5): every unbind reported success, the job set its
  alarm, wrote its result to the card and suspended, and nothing happened again
  for the rest of the run -- no card command, no resume, no counter. It is
  ordering and not the panel: with `display-engine` unbound from `sun4i-drm`
  first, the same `panel-mipi` unbind and nine more underneath it are harmless
  and the target woke three more times with its card checks passing (experiment
  12). That row also shows there is nothing to be had by doing it: 114, 118, 113
  and 109 mA across the ladder, and not one regulator changed state.
- **`aldo3` and `dcdc4` are enabled with nobody using them, and the race that
  kept them that way is now closed and cost nothing.** The regulator core's
  delayed cleanup runs at 32 s of uptime and is the only thing that ever tries
  to take them down. The job harness starts a job at about two seconds, so the
  attempt lands inside the first suspend, where the PMIC's I2C controller is
  suspended: `aldo3: disabling` at 32.05 s, then `mv64xxx: I2C bus locked,
  block: 1, time_left: 0` and `aldo3: couldn't disable: -ETIMEDOUT` at 34.08 s,
  and the bus timing out again every two seconds until the wake. It is attempted
  once and never again -- `aldo3` reads `enabled` with `num_users` 0 for the
  rest of the boot, and so does `dcdc4`. It costs nothing measurable either way:
  experiment 2's sleeps with the cleanup inside and after it read 125 (unsound),
  126 and 129 mA, and experiment 27 arranged to be awake for it and measured
  nothing. There is no sysfs write that enables or disables a regulator, so
  short of being awake at 32 s of uptime these two rails stay up.
- **The I2C traffic during a suspend is not where the current goes.**
  `mv64xxx_i2c` is the only interrupt that counts up appreciably across a
  sleep, about 270 per 40 s cycle. Unbinding the PMIC's ADC, its battery and
  USB power-supply drivers and the SoC's ADC takes it to about 128 and changes
  the current not at all (experiment 11: 112 mA mean with them, 116 mean
  without). The "I2C bus locked" message above is a transfer timeout in
  `mv64xxx` against a suspended controller, an ordering matter, and not a
  measured stuck bus.
- **s2idle is the limit for anything sysfs can reach.** There is one sleep
  state, for the reasons in "What the target offers": no `cpus/idle-states` in
  the device tree and no cpuidle driver bound. In s2idle the DRAM is not in
  self-refresh, no power domain is collapsed, and the CPUs only WFI. Sysfs
  cannot change any of that; only a firmware can, which is the ladder above.
- **`sr-pll` suspends and does not come back**, twice. The board goes quiet at
  the suspend and stays quiet: in the FPGA's trace the card's clock is at zero
  edges a second from the moment the job marks the sleep until the harness gives
  up five minutes later, with the read counter frozen at the value it had going
  in and the card left selected. The RTC alarm was forty seconds out and nothing
  happened at forty seconds. What makes it a useful failure is what did **not**
  happen: there was no warm reset -- a reboot would have shown thousands of
  low-LBA reads in the trace and there are none -- so the watchdog never fired,
  so the hang is not in either of the two windows the assembly stub arms it for.
  Those two windows are the self-refresh entry and exit, and both are
  byte-for-byte what `sr-gate` does, which works. The hang is therefore in
  stopping PLL_DDR0, the WFI itself, or relocking PLL_DDR0 before the watchdog
  is armed again. **The evidence for which of the three died with the 5 V**: the
  stage codes live in RTC registers in the always-on domain, and on a board with
  no battery fitted "always on" means "while the USB-C port is powering it", so
  the harness cutting the power at `--run-seconds` took them with it. The
  likeliest answer, on the evidence that everything up to PLL_DDR0 works, is
  that the Allwinner PHY does not survive its clock stopping -- which `sr-phy`
  then confirmed by rebuilding it, and which is why `sr-pll` is superseded
  rather than debugged.
- **A DRAM rebuild without the pad hold fails about one resume in five to
  eight, and those rungs must not be used.** That is `sr-phy`,
  `sr-phy-nodisp`, `sr-phy-nodisp-late` and the two ablations `sr-phy-pllon`
  and `sr-phy-fastapb`, all of which rebuild the PHY and none of which holds
  the pads while it is reset. They stay in the tree, stay built and stay
  measured, because each of them prices a sub-step and the ladder is only
  readable if every rung goes on building what it was measured as; none of them
  is a configuration anybody should deploy. The rate, what it rules out and
  what fixed it are in
  [How often the rebuild does not come back](#how-often-the-rebuild-does-not-come-back-experiment-34).
- **The pad-hold write used to be forbidden, and lifting that rule is what
  fixed the rebuild.** `sr-phy` never touches RTC + 0x1F4 and reads it back as
  1 before and after every sleep. The prior art clears bit 0 as soon as
  self-refresh is confirmed, saying that is what holds CKE low while the PHY is
  reset and unclocked, and sets it again before the controller leaves
  self-refresh; the H616 manual's 3.13.6.17 calls the bit `DRAM_CH_PAD_HOLD`,
  says 1 holds the pads, and frames the whole thing around VDD_SYS being
  powered off, which never happens here. The manual and the working code
  therefore disagree about the polarity, and ours follows the working code.
  With the owner's leave the write was made on 2026-09-21 and it is what the
  rebuild was missing: 0 of 48 and 0 of 36 against 8 of 42. **The polarity
  disagreement is not resolved by this**, only worked around -- what is
  measured is that the prior art's sense resumes and its absence does not.
- **The PRCM register at `+0x244` is not written.** The prior art writes it with
  a key of `0xa7` to take a PLL LDO down. Their own comment marks it inferred,
  it is in the one block of this SoC the manual does not document, and it is a
  supply rather than a clock. Nothing here writes a register it cannot cite, and
  nothing here writes a supply of any kind.
- **Whether the FPGA card interface is electrically neutral is not testable
  hands-off.** The gateware releases its lines when the host clock stops and the
  qualified bitstream has no pull-ups, but a powered FPGA on a target's pulled-up
  lines is exactly the back-powering the ROCKNIX work found on its second card
  slot, and only a physical disconnect settles it (bench experiment B5).

## Powered off with the RTC alarm armed

`poweroff -f` with 5 V still on the USB-C port draws **33 mA** (33 to 35,
IQR 2, n=19 over 60 s in experiment 14; 33 to 35, IQR 2, n=62 over 190 s in
experiment 15), the steadiest reading this bench has taken -- a 2 mA
interquartile range against the 7 to 18 mA a sleeping target gives.

**And the RTC alarm powers it back on.** Experiment 14 armed
`/sys/class/rtc/rtc0/wakealarm` sixty seconds out and powered off. The card
went silent at 8.4 s and the FPGA's trace shows a fresh boot reading the root
filesystem at 69.4 s, 61.0 s later; the runner took the same job up again,
armed the alarm again and powered off again at 74.5 s, and the board came back
at 135.1 s, 60.6 s later. Two for two, both within a second of the alarm.
Experiment 15 is the control: the same job with the alarm explicitly cleared
powered off at 15.7 s and the card saw nothing for the remaining 193 seconds of
the run, at 33 mA throughout. So the board does not simply restart when it is
powered off on USB -- the alarm is what brings it back.

The price is a cold boot, about 5 s to the first card command and about 12 s to
userspace after power comes up, and nothing survives it. **The gap between the
best sleep and a board that is off is now about 30 mA**: 33 against the 63 mA
of the kept rung's alternation and ten cycles, 29 against its 62 mA six-minute
sleep. It was 43 before the pad hold and the display clocks. Where that 30 mA
is, on the evidence, is the previous section. For a long enough timed sleep
powering off is still the answer today, by a smaller margin than it was; the
break-even sleep length is the extra
energy of a shutdown and a cold boot over a suspend and a resume, divided by the
difference in sleeping power, and nobody has integrated either.

## The harness

`rg35xx.py job` runs one experiment per command. A job is a shell script; the
host writes it into the card, init's job runner reads it, runs it and writes
back what it printed, and the host samples the supply meanwhile and reports
what each state the job marked off drew. Changing an experiment costs a file on
the host, not a rootfs, an image, or an FPGA load. The commands are runbook
section 11.

- One job is about 90 s for a 45 s dwell. A deploy, eight minutes, is needed
  only when the rootfs or the bootloader changes.
- Jobs may call `rtc_sleep SECONDS [STATE [MEM_SLEEP]]`, `card_check`,
  `mark_sector LABEL` and `rtc_now`. Each `rtc_sleep` is its own measured
  window, so one boot can hold several.
- **The target's sleep can be the exchange window.** While it is suspended --
  issuing no card command at all -- the host disarms the card frontend, reads
  the result the job flushed on its way down, writes the next job into the card
  and re-arms, and the target wakes onto a card that was withdrawn and put back
  while it was not looking. Done twice on the qualified bitstream: the exchange
  took 3.43 s and 3.02 s of a 70 s sleep. After the wake the card
  re-initialised on its own -- the trace shows the card state going from 0 back
  to 4 -- the second job ran within a fifth of a second of the resume, its card
  check passed, and the controller logged no error. The count of command frames
  failing their checksum stayed at the 5 the power edge and the SPL contribute,
  with none after. This makes a two-job cycle cost one boot instead of two. It
  has not been run for more than two jobs in a row, and nothing here says how a
  target that is disarmed twice in one boot behaves.
- Four things the bench taught it: the gateware takes writes only as an
  ascending run from sector zero, so a job is delivered by replaying the
  image's first 2112 sectors (3 s) and lives at LBA 2048; a write's LBA does
  not survive in the FPGA's trace, so the target signals by reading; BusyBox
  `dd iflag=direct` reads through the page cache, so the runner drops the
  buffers before every read; and the supply's CLI takes one speaker at a time,
  so every conversation with it goes through one lock.
- One bug found by its first outside user and fixed: a second sight of the
  opening mark closed a 45 s window after 0.23 s. Nothing ends a window now
  until it has settled for 2 s.

## Open questions

- **Whether ours really is below theirs.** By medians it is, by six to ten
  milliamps against a threshold of eight; by the means of the same readings the
  two are level. The two rungs have never been alternated against each other in
  one boot, only each against its own s2idle, and the readings on these rungs
  are the burstiest this bench has seen. An A-B-B-A-A-B between
  `sr-phy-padhold-nodisp` and `rocknix-deep` cannot be run -- they are
  different bootloaders and a rung is a boot -- so what would settle it is B9,
  a scope across a shunt, and until then the claim is "at the edge".
- **Whether the pad hold's own few milliamps are real**, 69.7 against 76.0 in
  separate boots and 44.0 of saving against 39.3. It is under the threshold and
  nothing predicted it; an ablation on the reliable rung would price it
  properly and costs one deploy.
- **What `PLL_PERI0` costs and what it would take to stop it.** It is the last
  PLL running in any sleep here, ours or theirs, and neither the prior art nor
  the vendor's standby code stops it. It needs grounding in mainline sources
  before anything is written.
- Where the 30 mA between the best sleep and a powered-off board actually sits,
  and whether the 33 mA "off" is the board or the AXP717's power path with no
  cell on it. That needs rail voltages, a battery with a shunt and the card
  interface unplugged: bench experiments B5, B6 and B7.
- Whether the 166 to 220 mA readings inside sleep windows are real bursts
  (B9), and where the 1.5 mA per cycle drift comes from now that time asleep and
  the awake work are both excluded. This matters more than it did: the kept
  rung's median and mean are sixteen milliamps apart.
- Whether the PRCM PLL LDO and a PMIC-assisted rail-off are worth doing, and
  what would have to be true first. Both are in
  [RG35XX-PLUS-POWER-RESEARCH.md](RG35XX-PLUS-POWER-RESEARCH.md) with the
  evidence each would need.
- **Whether the manual's polarity or the working code's is right.** The manual
  says 1 holds the pads and the prior art's sequence clears the bit on the way
  down; ours mirrors the prior art and resumes. Only a rail-off standby, where
  VDD_SYS actually goes away, can tell the two readings apart.

## Running it again

Deploy the image once (runbook section 11), then any row of the table is one
command, for example the deciding one:

```sh
MDP_CLI=/path/to/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py job \
  --state /private/tmp/rg35xx-sleep-session.json \
  --image build/rg35xx-sleep/rg35xx-plus-sleep.img \
  --script projects/ethernet-diagnostic/jobs/sleep/10-powersave-only-abba.sh \
  --name powersave --run-seconds 360 \
  --label A1 --label B1 --label B2 --label A2 --label A3 --label B3 \
  --output /tmp/powersave.json
```

Rows 1 to 17 run on any of the images, and so does row 28, which never
suspends. Rows 18 to 21 need the card image built with the `--suspend wfi`
bootloader, `build/rg35xx-firmware-src/wfi/rg35xx-plus-sleep-wfi.img`; rows 22
to 26 and row 27 need one of the self-refresh ones,
`…/sr/rg35xx-plus-sleep-sr.img` and its `sr-gate` and `sr-pll` siblings; rows
29 to 33 need one of the PHY-rebuild ones, `…/sr-phy/rg35xx-plus-sleep-sr-phy.img`
and its six `sr-phy-*` siblings -- the kept one being
`…/sr-phy-padhold-nodisp/rg35xx-plus-sleep-sr-phy-padhold-nodisp.img`, sha256
`4389c576...`; row 34 runs on any firmware that offers
`deep`, ours or theirs, and rows 24, 25, 26 and 34 are what the kept one was
qualified with. Runbook section 12 builds all of them, and each needs its
own eight-minute `deploy` because the bootloader is part of the card image.
Runbook section 11 has the `--label` lists and run lengths for every row,
including 27 and 28, whose windows are read by their dwell.

Any row with more than one sleep in it should be given
`--min-window-seconds 30`, which drops the windows the harness opens over the
md5 check between sleeps before the labels are handed out; they are still
reported, as `short-1` and so on.

Every run ends with the supply's output read back OFF and the card disarmed.
`psu2` is the RG35XX; `psu1` carries another machine on this bench and must
never be switched.

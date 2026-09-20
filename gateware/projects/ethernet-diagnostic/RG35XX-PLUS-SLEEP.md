# RG35XX Plus: what timed sleep costs, and how low it goes

A report of the sleep-current work of 2026-09-20, and the one long-form home for
everything about power and sleep on this board: every measurement, register
fact, dmesg quote and caveat lives here. The `## Sleep` section of
[RG35XX-PLUS-FINDINGS.md](RG35XX-PLUS-FINDINGS.md) is a summary of this page and
points back to it. The commands are sections 11 and 12 of
[RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md); the verdict of the firmware
experiment, and the outside review of it, are
[RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md); what still needs a
person at the bench, and what each of those experiments would answer, is
[RG35XX-PLUS-BENCH-EXPERIMENTS.md](RG35XX-PLUS-BENCH-EXPERIMENTS.md); and the
story, dead ends included, is the 2026-09-20 entries of
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
| asleep, our firmware suspend, the CPU PLL off | about 113 mA (110 to 117 over ten) |
| asleep, our firmware suspend, the LPDDR4 in self-refresh | about 105 mA (103 to 112 over ten) |
| powered off with an RTC alarm armed, which does bring it back | 33 mA |
| supply output off | 1 mA |

s2idle was the only sleep state this kernel and firmware offered, and one knob
is worth keeping in it: the `powersave` cpufreq governor, 11 mA. Nothing else
that sysfs can reach is worth a milliamp.

A firmware of our own gives the board a real `deep` state. Two things were
built into it and each was priced on its own. Stopping the CPU PLL and waiting
in WFI works -- seventeen suspends, seventeen resumes -- and is worth about
4 mA, less than this bench calls a difference. Putting the LPDDR4 into
self-refresh as well, from a stub in SRAM because BL31 itself lives in the
DRAM, is the first thing above the noise since the governor: 11.6, 4.7 and
10.3 mA against s2idle in three boots, **about 9 mA pooled**, with the sleeping
board at 105 mA every time.

Taken together, everything in this report moves a sleeping board from about
124 mA to about 105, fifteen percent, and the firmware is about nine of those
milliamps. [RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md) is the short
account of that experiment and of whether it was worth doing.

If the application can stand a cold boot on waking, powering off with the alarm
armed still draws a third of the best sleep.

All currents are at the USB-C port at 5.00 V with **no battery fitted**, so they
include the PMIC's conversion and charger path and are not battery-life
figures. The supply reads to 1 mA, about once every two and a half seconds, and
every figure here is a median of those readings; the mean of the same readings
runs 5 to 8 mA higher in every sleep window, which the next section explains
and which the differences between arms survive.

## How it was measured

- **Bench.** The qualified seed-19 bitstream, unchanged throughout; the card
  image `build/rg35xx-sleep/rg35xx-plus-sleep.img`, built with
  `--card-max-hz 6000000` and the host command `job-runner`; supply channel
  `psu2`, 5.000 V, 1.200 A limit, never altered. `psu1` was never addressed.
  The firmware sections at the end use images built the same way around a
  different bootloader, and nothing else about the bench changes with them.
- **The rule for a figure.** The median of the supply's readings taken wholly
  inside a state, after discarding the first 3 s, over a dwell of at least
  20 s (40 to 45 s in practice), with the range, the interquartile range and
  the count reported. A window in which the supply's wireless link dropped is
  marked UNSOUND and is not a measurement.
- **A median is not an average, and the difference is not small.** Recomputed
  from the stored readings after the outside review, the mean runs 5 to 8 mA
  above the median in every sleep window, and single readings of 166 to 220 mA
  turn up inside windows whose median is 105. Every figure quoted in this
  report is a median, so the comparisons between arms survive the recomputation
  -- the first self-refresh alternation is 11.0 mA by means against 11.6 by
  medians -- but the absolute sleeping power is nearer 110 to 112 mA than 105.
  Whether those high readings are real bursts or an artefact of the supply's
  sampling needs a shunt and a scope, which needs a person at the bench.
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

## What the target offers

- `/sys/power/state` is `freeze mem`; `/sys/power/mem_sleep` is `[s2idle]` and
  nothing else, and writing `deep` or `shallow` to it returns EINVAL. `mem` and
  `freeze` are the same state. That is the firmware the device ships with; the
  last section of this report replaces it and `deep` appears.
- There is no cpuidle driver (`current_driver` reads `none`) and no
  `cpus/idle-states` in the device tree, though there is a `psci` node with
  method `smc` and `cpus/cpu@0` has `enable-method = "psci"`; the device tree
  says `arm,psci-0.2`. Nothing tells the kernel what the idle or suspend states
  of this SoC are, so a sleeping CPU only waits for an interrupt, the DRAM is
  not in self-refresh and no power domain collapses. Giving the kernel a deeper
  state is a device-tree and firmware question, not a configuration one. The
  device-tree half of that is still true at the end of this report; the
  firmware half is not.
- The RTC is `7000000.rtc` with a working `wakealarm`; BusyBox has `rtcwake`.
  The kernel has `CONFIG_SUSPEND` and `CONFIG_RTC_DRV_SUN6I`; it does not have
  `DEBUG_FS` or `PM_DEBUG`, so there is no regulator summary and no suspend
  timing breakdown.
- One sleep and one RTC wake, proved. `rtc_sleep 45 freeze`: the alarm was set
  to RTC 86450 at 86405, the RTC read 86451 on waking, 46 s for a requested 45;
  `/proc/uptime` went 1.83 to 47.62, so the clock keeps running in s2idle and
  uptime is not evidence of anything here; `suspend_stats/success` went 0 to 1
  with `fail` 0 and `last_failed_dev` empty; and the card check passed both
  before and after. The same with `mem` in place of `freeze`, and the same with
  a 70 s sleep. Six sleeps, six wakes, no failure in Phase 0, and none in any
  sleep since.
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

So the suspend is worth about 22 mA on a target whose panel is already asleep,
roughly 15 percent, and the backlight at full costs about 100 mA more than a
sleeping panel -- four times what the suspend saves. The largest single item on
this supply is the backlight and the second is whatever keeps an idle awake
target at 145 mA.

## What is still holding power up

From the discovery job, with the target awake and idle:

- **`performance` at 1416 MHz.** `cpufreq-dt` is bound with the `performance`
  governor and `scaling_cur_freq` 1416000, the top of a ladder that goes down
  to 480000. `conservative ondemand userspace powersave schedutil` are all
  available. What a lower governor is worth is measured further down.
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

## The harness

`rg35xx.py job` runs one experiment per command. A job is a shell script; the
host writes it into the card, init's job runner reads it, runs it and writes
back what it printed, and the host samples the supply meanwhile and reports
what each state the job marked off drew. Changing an experiment costs a file on
the host, not a rootfs, an image, or an FPGA load.

- One job is about 90 s for a 45 s dwell. A deploy, eight minutes, is needed
  only when the rootfs changes.
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

## The experiments

Twenty-eight experiments, one script each in [`jobs/sleep/`](jobs/sleep), so
every row can be run again: the first seventeen are below, 18 to 21 are in the
deep-sleep section, 22 to 26 in the self-refresh section after it, and 27 and
28 in "After an outside review" at the end. The firmware rows need their own
card images, because the bootloader is part of one. Cells are median / IQR /
readings in mA over a 40 s sleep; `!` is an UNSOUND window; "mean" is the mean
of three medians in an A B B A A B run; "to N" means row N decided it properly;
"ref." is a reference point and not a sleep.

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
alternations of rows 7 to 10 supersede them. The experiments stopped where the
goal said they should: rows 11, 12 and 13 are three in a row with no gain above
the noise.

## The best configuration sysfs can reach

It is still worth its eleven milliamps under the firmware suspends below, which
change what the SoC does and not what the governor does.

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

- Asleep: **11 mA**. 126 mA mean against 115 over three alternations (row 10),
  123 against 112 with three cores also offline, which added nothing (row 9).
  Run a third time from the committed script by someone who had not written it:
  124 (unsound), 129, 125 against 114, 116, 115, the same means to the
  milliamp, six wakes of six, `vdd-cpu` read back at both voltages.
- Awake and idle, panel asleep: about 8 mA, 139 mA (IQR 5, n=8) against the 144
  and 151 mA the same state measured under `performance`.

So in the kept configuration the target draws 139 mA awake and idle and about
114 mA asleep, and the suspend itself is worth about 25 mA of that.

**Ten consecutive cycles, twice.** Experiment 17, each run in one boot: the
governor set once, then ten `rtc_sleep 40 freeze` in a row with three seconds
of quiet between them, each suspend its own measured window. Both runs: ten
wakes of ten, 41 s by the RTC for a requested 40 on all twenty,
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

## What is blocked, and the measurement that says so

- **Nothing else sysfs reaches is worth anything.** Row 13 unbound twenty-five
  devices at once on top of the kept governor -- the DRM master, the panel,
  both TCONs, both mixers, the HDMI controller and its PHY, the TCON top, the
  planes, the DE2 bus, the GPU, the audio codec, the HDMI audio codecs, the
  display connector, both card controllers that are not the root device, the
  backlight PWM and its PWM controller, the watchdog, the eFuse, the spare
  UART, the PMIC's ADC and its battery and USB power-supply drivers, and the
  SoC's own ADC -- and turned both LEDs off: 112 mA before, 109, 113 and 109
  after. The drift runs the other way, so if anything that is an over-estimate
  of the gain. The rails that were still up afterwards are the answer:
  `vcc-pll` 1.8 V, `vcc-spkr-amp` 3.3 V, `vcc-io` 3.3 V, `cpusldo` 0.9 V,
  `vdd-cpu` 0.9 V, `vdd-gpu-sys` 0.9 V, `vdd-dram` 1.1 V, `dcdc4` 1.0 V,
  `aldo3` 1.8 V and `avcc` 1.8 V. Only `vcc-wifi` and `vcc3v3-mmc2` ever went
  away, and row 8 prices those two together at about a milliamp: three sleeps
  with them on read 125, 125 and 126 mA and three with them off read 124, 126
  and 129. Whatever the remaining 110 mA is, it is on rails no consumer in this
  kernel will release. Setting `status = "disabled"` on the same nodes in the
  device tree would stop them being probed at all, which is tidier than
  unbinding and, on this evidence, worth about the same, namely nothing.
- **Offlining cores buys nothing on its own** (row 7, three alternations at
  `performance`: 124 mA mean with four cores, 127 mean with one). The cores do
  go offline through PSCI CPU_OFF, they stay offline across a suspend and the
  wake is unaffected -- `online` still read `0` after the sleep in row 6 -- but
  an idle core in s2idle is in WFI on a rail shared with the one that stays,
  and taking it away does not lower the rail. Row 9's saving is the governor's,
  which row 10 then measured on its own at the same 11 mA.
- **Unbinding `panel-mipi` while the DRM master holds it costs the wake**,
  twice (rows 4 and 5): every unbind reported success, the job set its alarm,
  wrote its result to the card and suspended, and nothing happened again for
  the rest of the run -- no card command, no resume, no counter. It is ordering
  and not the panel: with `display-engine` unbound from `sun4i-drm` first, the
  same `panel-mipi` unbind and nine more underneath it are harmless and the
  target woke three more times with its card checks passing (row 12). That row
  also shows there is nothing to be had by doing it: 114, 118, 113 and 109 mA
  across the ladder, and not one regulator changed state.
- **`aldo3` and `dcdc4` are enabled with nobody using them.** The regulator
  core's delayed cleanup runs at 32 s of uptime and is the only thing that ever
  tries to take them down. The job harness starts a job at about two seconds,
  so the attempt lands inside the first suspend, where the PMIC's I2C
  controller is suspended: `aldo3: disabling` at 32.05 s, then `mv64xxx: I2C
  bus locked, block: 1, time_left: 0` and `aldo3: couldn't disable:
  -ETIMEDOUT` at 34.08 s, and the bus timing out again every two seconds until
  the wake. It is attempted once and never again -- `aldo3` reads `enabled`
  with `num_users` 0 for the rest of the boot, and so does `dcdc4`. It costs
  nothing measurable either way: row 2's sleeps with the cleanup inside and
  after it read 125 (unsound), 126 and 129 mA. There is no sysfs write that
  enables or disables a regulator, so short of being awake at 32 s of uptime
  these two rails stay up -- which is what row 27 later arranged, and it was
  worth nothing either.
- **The I2C traffic during a suspend is not where the current goes.**
  `mv64xxx_i2c` is the only interrupt that counts up appreciably across a
  sleep, about 270 per 40 s cycle. Unbinding the PMIC's ADC, its battery and
  USB power-supply drivers and the SoC's ADC takes it to about 128 and changes
  the current not at all (row 11: 112 mA mean with them, 116 mean without).
- **The state itself is the limit,** for anything sysfs can reach. There is one
  sleep state, s2idle, for the reasons above: no `cpus/idle-states` in the
  device tree and no cpuidle driver bound. In s2idle the DRAM is not in
  self-refresh, no power domain is collapsed, and the CPUs only WFI. Sysfs
  cannot change any of that. Something deeper needs a firmware that implements
  it, which is the rest of this report: it was implemented, it works, and the
  CPU-clock half of it is worth four milliamps.

## Deep sleep: our own PSCI SYSTEM_SUSPEND

The recommendation above -- that the next real saving is in the firmware -- was
acted on the same day, and this section is what that turned out to be worth.

Someone had already done the work. kailashrs' H700 suspend for ROCKNIX, merged
on 2026-09-19 as
[ROCKNIX/distribution#3316](https://github.com/ROCKNIX/distribution/pull/3316)
from [H700_rocknix_enhancement](https://github.com/kailashrs/H700_rocknix_enhancement),
gives the H700 a PSCI `SYSTEM_SUSPEND` in which TF-A hands control to a program
in SRAM A1 that puts the LPDDR4 into self-refresh and waits. It publishes drain
figures in percent per hour and no currents. What follows is a minimal
implementation of the same idea, built here so it can be put on this bench's
supply: the design, the choice of PSCI hooks and the return through TF-A's warm
boot entry are theirs, the code is ours, and it deliberately stops one step
short of the DRAM.

### What was built

`rg35xx.py build-firmware` builds the bootloader ROCKNIX ships for this device
-- mainline U-Boot v2026.01, ROCKNIX's one patch to the H616 DRAM driver, their
`anbernic_rg35xx_h700_lpddr4_defconfig`, and a BL31 from TF-A v2.12.0 -- from
sources pinned by hash, in the arm64 container the kernel build already used.
`--suspend none` is that and nothing else. `--suspend wfi` adds one patch,
[`rg35xx/firmware/0001-allwinner-h616-minimal-psci-system-suspend.patch`](rg35xx/firmware),
which is the whole of the deep sleep. Runbook section 12 has the commands.

On `SYSTEM_SUSPEND`, with the other cores already offlined by Linux, EL3 moves
the CPU cluster off PLL_CPUX onto the 24 MHz oscillator, stops PLL_CPUX, routes
interrupts to EL3 and waits in WFI. On waking it restarts PLL_CPUX, waits up to
2 ms for lock, puts the cluster back on it and re-enters BL31 through
`bl31_warm_entrypoint` -- which is how an arm64 Linux has to be given control
back, since a plain return from the SMC is a suspend that did not happen.
Nothing else is touched: no rail, nothing over I2C or RSB, no DRAM, no GIC.
Four of the RTC's general-purpose scratch registers carry a stage code, the
number of suspends entered, the number of resumes finished and the interrupt
that ended the wait; on a board with no serial console that is the only thing
EL3 can say, and a job reads them with `devmem`.

### The bootloader from source is the bootloader it replaced

Before anything of ours went on the card, the unmodified build replaced
ROCKNIX's bootloader in the sleep image and was measured against it.

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
the experiment that decided the kept configuration, run again unchanged: 131,
124 and 129 mA against 115, 114 and 116, six sound windows. Two builds of the
same sources are byte-identical, because U-Boot and TF-A are given a fixed
build date rather than the clock.

### `deep` arrives, and it comes back

With `--suspend wfi` on the card, `/sys/power/mem_sleep` reads `s2idle [deep]`
and `mem` resolves to `deep`. No kernel change was needed: Linux probes
`PSCI_1_0_FN64_SYSTEM_SUSPEND` and installs its suspend ops when the firmware
answers.

Seventeen deep suspends were entered across four boots and seventeen resumed.
Every one of them: the RTC read 41 s for a requested 40,
`suspend_stats/success` went up by one with `fail` unchanged and
`last_failed_dev` empty, the card check passed after the resume, and EL3's own
counters agreed -- one more suspend entered, one more resume finished, stage
`0xa5d50008`, which is written from the PSCI resume hook and therefore only
after the warm boot has handed control back. The s2idle sleeps in the same runs
left those counters untouched, which is what says `deep` is really going
through EL3 and `s2idle` is not.

The interrupt EL3 found pending when the WFI ended was 136 on all seventeen.
The H616 manual's interrupt table calls 136 `R_Alarm0`: the RTC alarm is
ending the wait, at EL3, exactly as intended.

### What it is worth: about four milliamps, which is not a difference

```text
 #  knob                                   before       after      wake  card
19  one deep sleep, first of its kind         --      109/16/11    yes   ok
20  deep against s2idle, ABBAAB            117 mean    112 mean    6/6   ok
20  the same again                         117 mean    114 mean    6/6   ok
21  ten consecutive deep cycles               --       110-117    10/10  ok
```

Cells are median / IQR / readings in mA over a 40 s sleep; "mean" is the mean
of three medians in an A B B A A B run, A being `mem` resolved to s2idle and B
`mem` resolved to `deep`, with the `powersave` governor set once at the top and
in both arms. All twenty-three windows in the four runs are sound.

- **First run:** 119, 116, 116 mA asleep in s2idle against 113, 110 and 114 in
  deep. 4.5 mA.
- **Second run:** 113, 119, 119 against 114, 112, 116. 3.0 mA.
- **Ten consecutive deep cycles in one boot:** 112, 110, 114, 113, 112, 110,
  112, 115, 114 and 116 mA, ten sound windows between 110 and 117, against 110
  to 119 over the twenty s2idle cycles of experiment 17.

The difference is in the same direction both times and is about four
milliamps, and the rule this report has used throughout is that a difference
below about eight is not believed. So: the suspend is real, it resumes
reliably, and with DRAM left running it saves nothing this bench can measure.

That is not a surprise on reflection. A core in WFI is already clock-gated, so
the 24 MHz step costs nothing by itself, and what remains is PLL_CPUX's own
bias current on a 1.8 V rail -- a few milliamps, which is what was seen. The
milliamps are not in the CPU clock tree at all: the rails still standing
during a suspend are `vdd-dram`, `vdd-gpu-sys`, `vcc-pll`, `vcc-io`, `avcc`,
`cpusldo`, `vcc-spkr-amp`, `aldo3` and `dcdc4`, and the board powered off with
its alarm armed draws 33 mA, so about 79 mA of a 112 mA sleep is in rails that
a CPU-clock suspend does not reach.

### What is measured here and what is assumed

- **Measured:** every current above, the seventeen wakes, the RTC's own account
  of each sleep, the suspend counters, the card checks, EL3's stage and counter
  registers, the wake interrupt number, and the parity of the from-source
  bootloader against the one it replaced.
- **Assumed, because nothing here looked:** that PLL_CPUX is genuinely off
  during the WFI. EL3 writes the disable and reads the lock bit back on the way
  up, and the resume works, but no register was read back while the board was
  asleep -- there is no way to, with the CPU in WFI and no debug port. The
  four milliamps are consistent with the PLL being off and are the only
  evidence for it.
- **Not attempted:** the 32 kHz step the vendor's standby code takes after
  stopping the PLL is built (`--suspend wfi32`, it compiles) and was never put
  on the card. On this evidence there is nothing for it to find.
- **Not touched, deliberately:** the PRCM register at `+0x244` that the ROCKNIX
  work writes with a key of `0xa7` to gate the PLL LDO. Their own comment marks
  it inferred, it is in the one block of this SoC the manual does not document,
  and the review thread on the pull request asks the same question about a
  neighbouring write. Nothing here writes a register it cannot cite.

### What the next step -- DRAM self-refresh from SRAM -- needed from this

- **The warm-boot return works.** Turning the MMU off and branching to
  `bl31_warm_entrypoint` brings Linux back through PSCI's resume path,
  seventeen times out of seventeen. That is the part of kailashrs' design this
  confirms independently, and an SRAM stub only has to do the same jump.
- **BL31 lives in DRAM on this platform.** `plat/allwinner/sun50i_h616` sets
  `SUNXI_BL31_IN_DRAM := 1`, so BL31 is at `0x40000000`. Self-refresh therefore
  cannot be done by BL31 itself at all -- the stub is not an optimisation, it
  is the only way. The inner sequence here is already written to be lifted: it
  calls nothing in BL31, using only memory-mapped registers, the architected
  counter and WFI, and it takes its delays from `CNTPCT_EL0` rather than
  `udelay()` for exactly that reason.
- **SRAM A1 is `0x20000`, 32 KiB**, and TF-A maps the whole SRAM region
  `MT_DEVICE | MT_EXECUTE_NEVER`, so a stub must be entered with the MMU off --
  which the existing jump already does -- or the mapping has to change.
- **`/dev/mem` works and the RTC scratch registers are free.** `CONFIG_DEVMEM`
  is on, `CONFIG_IO_STRICT_DEVMEM` is off, and registers 12 to 15 read
  `0x00000000` on a board that has never suspended, so nothing else uses them.
  A stub can report the same way. They do not survive the 5 V going away on
  this battery-less board, so a stub that hangs takes its evidence with it
  unless a watchdog is armed to turn the hang into a warm reset -- which is why
  kailashrs arms one around the DRAM recovery and not around the wait.
- **The budget.** 112 mA asleep, 33 mA powered off. Self-refresh has to find
  its saving in `vdd-dram` and in whatever the DRAM controller and PHY draw
  idle; everything the CPU clock tree had to give has now been given, and it
  was four milliamps.

All five of those held, and the next section is what was built on them.

## Deeper still: the DRAM asleep, from a stub that is not in the DRAM

The section above ends by saying what the next step needs. This is that step
taken, and unlike the one before it, it is worth something.

### The shape of it, and why it is assembly

BL31 on this platform is linked into DRAM, so the moment the LPDDR4 stops
answering, the code that stopped it has stopped too. The only memory left is
SRAM A1: 32 KiB at `0x00020000`, which U-Boot's SPL ran from at boot and
nothing has owned since.

So the inner sequence moved there. A blob of position-independent instructions
lives in BL31's read-only data, is copied into SRAM A1 on the way into every
suspend, and is called with the MMU off -- off because TF-A maps the whole
SRAM region execute-never, and because BL31's page tables are themselves in
the DRAM that is about to go away. The jump with the MMU off was already
proved by the rung below; this only adds a destination.

It is written in assembly, and the reason is the whole design:

- **No stack.** The stack is in DRAM. Everything the stub remembers across the
  sleep -- the saved `PWRCTL`, the three MBUS master-enable words, `CPUX_AXI`,
  `SCR_EL3`, `VBAR_EL3` and the watchdog's two registers -- lives in a save
  area inside the copy, in SRAM.
- **No call.** Everything callable is in DRAM.
- **No literal pool.** A compiler puts one where it likes, and a
  `ldr x0, =label` in a blob that runs from `0x20000` rather than from where
  it was linked would fetch from DRAM in self-refresh. Every constant is built
  with `movz`/`movk` and every label is reached with `adr`, which is
  PC-relative and so gives the address of the running copy. The built blob was
  disassembled to confirm it: 4224 bytes, no literal loads, two `adr`s.

Its own exception vectors are installed for the duration, because BL31's are
in DRAM: a fault inside the stub records `ESR_EL3` and `ELR_EL3` in RTC
scratch registers and resets through the watchdog, which on a board with no
console is the difference between a clue and a power cycle.

### What it does, in order

```text
save the watchdog and stop it              it must not fire during the wait
zero MAER0/1/2                             no more MBUS masters
arm a 2 s watchdog
set PWRCTL bit 5, wait for STAT mode 3     software self-refresh
disarm the watchdog                        the wait outlasts any interval
cluster onto OSC24M, stop PLL_CPUX         as the rung below already did
[sr-gate]  clear MBUS_CFG bit 31 and DRAM_BGR bit 0
[sr-pll]   clear PLL_DDR0 bits 31 and 29
WFI
[sr-pll]   PLL_DDR0 back, wait for lock
[sr-gate]  DRAM_BGR bit 0 and MBUS_CFG bit 31 back
PLL_CPUX back, wait for lock, cluster back on it
arm a 2 s watchdog
SWCTL=0, restore PWRCTL, SWCTL=1, wait SWSTAT, wait for STAT mode 1
restore MAER0/1/2 and the watchdog, return to BL31 in DRAM
```

The two controller sequences are mainline U-Boot's own, from
`arch/arm/mach-sunxi/dram_sun50i_h616.c`: `mctl_ctrl_init()` zeroes the master
enables and writes `PWRCTL` `0x20` to go in, and `mctl_phy_init()` clears the
same bit inside a `SWCTL` commit and waits for `STAT & 3 == 1` to come out.
The H616 manual documents no DRAM controller registers at all, so there was no
other honest source. Everything in the CCU, the watchdog and the RTC is from
the manual and cited where it is used.

Gates only, never the resets beside them: `MBUS_CFG` bit 30 and `DRAM_BGR`
bit 16 are resets, and a controller that has been reset cannot be talked out
of self-refresh without re-running a whole DRAM driver -- which is what the
prior art does, and what this is built not to need.

### Proving the DRAM kept anything

A resume that works is not proof. A DRAM cell holds its charge for a good
fraction of a second with nobody refreshing it, so a controller that quietly
never entered self-refresh would still come back looking healthy from a
forty-second sleep. Every sleep from here on therefore fills 256 MiB of tmpfs
with random bytes, records its md5 and checks it on the other side, and each
kept rung gets one sleep of six minutes as well as the short ones.

The s2idle arms of the alternation are the control: s2idle does not touch the
DRAM at all, so if those checks pass and the deep ones do not, the difference
is the self-refresh and not the probe.

### What it is worth: nine to twelve milliamps, which is a difference

```text
 #  what was run                          s2idle      self-refr.  wake  card  DRAM
22  the firmware's own account, no sleep     --          --        --    ok    --
23  one self-refresh sleep, first of kind    --      106/5/14      yes   ok    ok
24  self-refresh against s2idle, ABBAAB   116 mean    105 mean     6/6   ok    6/6
25  ten consecutive self-refresh cycles      --       103-112     10/10  ok  10/10
26  one six-minute self-refresh sleep        --      106/13/112    yes   ok    ok
```

Cells are median / IQR / readings in mA over a 40 s sleep; "mean" is the mean
of three medians in an A B B A A B run, A being `mem` resolved to s2idle and B
`mem` resolved to `deep`, with the `powersave` governor set once at the top and
in force in both arms.

- **The alternation:** 119, 114 and 116 mA in s2idle against 103, 107 and 104
  in self-refresh. 116.3 mean against 104.7, **11.6 mA**, against a threshold
  of about eight. All six windows sound, all six wakes, all six card checks,
  all six md5 checks unchanged.
- **The counters say which arm was which.** EL3's suspend and resume counters
  went 0, 1, 2, 2, 2, 3 across the six sleeps -- up by one on each of the three
  deep arms and untouched on each of the three s2idle ones -- with the stage
  reading `0xa5d50008` and the wake interrupt 136 every time. The s2idle arms
  are running the same kernel through the same `rtc_sleep` and are not going
  through EL3 at all, which is what makes them a control rather than a
  comparison.
- **The alternation again, twice, by someone who had not written it.** From
  the committed script and image, a cold boot each, windows read by their
  dwell because the md5 check shifts the labels: 112, 108 and 109 mA in s2idle
  against 104 (unsound, seven readings), 104 and 107 in self-refresh, 109.7
  mean against 105.0; then 114, 112 and 119 against 104, 108 and 102, 115.0
  against 104.7. Twelve wakes of twelve, twelve card checks, twelve md5 checks
  unchanged, EL3's counters up on the deep arms only. The self-refresh arm is
  the steady one, 104.7, 105.0 and 104.7 mean in the three runs; the s2idle arm
  moves between boots, 116.3, 109.7 and 115.0, and the saving moves with it:
  11.6, 4.7 and 10.3 mA, **about 9 mA pooled**. What the three runs agree on is
  the state the board ends up in, about 105 mA, more than what it is compared
  with.
- **Against the rung below.** The DRAM-less suspend measured 112.5 and 113.8
  mean in the same experiment against s2idle means of 117.0 both times; this
  one measures 104.7 against 116.3. Taking s2idle as the anchor in each boot,
  self-refresh is worth about 8 mA more than stopping the CPU PLL alone, and
  about 11.6 mA against doing nothing.
- **Ten consecutive cycles in one boot:** 103, 104, 107, 104, 104, 106, 112,
  109, 106 and 107 mA, ten sound windows between 103 and 112. Ten wakes of ten,
  41 s by the RTC for a requested 40 on all ten, `success` 0 to 10 with `fail`
  0, twelve card checks of twelve, ten md5 checks unchanged, and EL3's counters
  reaching 10 and 10. The harness opened an eleventh window over the awake gap
  between cycles 3 and 4 and marked it unsound, which is what a 9.7 s window
  reading 181 mA is: the target awake, not a sleep.
- **One sleep of six minutes**, which is the measurement that actually settles
  whether anything is being refreshed: 361 s by the RTC for a requested 360,
  105.5 mA median over 112 readings in one unbroken sound window, IQR 13, and
  the 256 MiB probe's md5 unchanged. A DRAM that nobody was refreshing would
  not survive six minutes; a forty-second sleep cannot tell the difference. It
  is also the cleanest single current this rung produces, because the harness's
  own overheads are a rounding error against a dwell that long.

### What is measured here and what is assumed

- **Measured:** every current above; every wake, with the RTC's own account of
  each sleep, `suspend_stats`, a card check either side and the 256 MiB md5;
  EL3's stage and counter registers, where the counters are incremented by the
  stub itself after it has DRAM back, so they cannot read high on a sleep that
  did not complete; the wake interrupt, 136 on every one; and the card's clock,
  which the FPGA counts at exactly zero edges a second for the whole sleep.
- **Measured, and worth saying separately:** that the controller is back in
  normal operating mode and its three master-enable registers are back to
  `0xffffffff`, `0x7ff` and `0xffff` after the resume, read through `/dev/mem`;
  and that the watchdog is back to `CFG=1 MODE=0`, which is how the stub found
  it.
- **Assumed, because nothing here can look:** that the DRAM is in self-refresh
  *for the whole* of the wait rather than only at the moment `STAT` was read.
  The stub reads `STAT` back as mode 3 before it stops waiting, and reads it
  back as mode 1 after, but nothing can read a register while the core is in
  WFI. The six-minute sleep is the argument: a DRAM that was not being
  refreshed would not survive it, and a controller that had fallen out of
  self-refresh would not be drawing eleven milliamps less.
- **Not touched, still:** the PRCM register at `+0x244` that the ROCKNIX work
  writes with a key of `0xa7`. Same reason as before -- their own comment marks
  it inferred and the manual does not document that block.

### What else is still running, and where the rest of the current is

Experiment 22 reads the CCU's eleven PLL control registers through `/dev/mem`.
Awake and idle with the panel asleep, five of them have their enable bit set:

```text
enabled   PLL_CPUX  PLL_DDR0  PLL_PERI0  PLL_VIDEO0  PLL_DE
disabled  PLL_DDR1  PLL_PERI1  PLL_GPU0  PLL_VIDEO1  PLL_VIDEO2  PLL_VE
```

This is the awake state, not the sleeping one: nothing here can read a CCU
register while the core is in WFI, and the kernel's own clock framework may
take some of them down on the way into a suspend. Two of the five,
`PLL_VIDEO0` and `PLL_DE`, are the display pipeline, and experiment 13 already
priced the whole of that pipeline at nothing measurable, so they are unlikely
to be where the milliamps are. `PLL_PERI0` feeds the card controller among
much else and stays. That leaves PLL_CPUX, which the firmware already stops,
and PLL_DDR0, which the last rung below stops.

So the account of a sleep is: about 105 mA with the CPU PLL stopped and the
LPDDR4 in self-refresh, 33 mA powered off with the alarm armed, and therefore
about 72 mA in rails that are still up -- `vdd-dram`, `vdd-gpu-sys`,
`vcc-pll`, `vcc-io`, `avcc`, `cpusldo`, `vcc-spkr-amp`, `aldo3` and `dcdc4`,
plus whatever the AXP717's own conversion and charger path costs with no
battery fitted. `vdd-dram` is still powering an array that is refreshing
itself, which is the floor for a sleep that keeps its memory; reaching the rest
is a PMIC question, and nothing here writes a PMIC register.

At this rung the DRAM controller, its PHY and PLL_DDR0 are all still clocked,
which is the next thing to try.

### Two more rungs: the DRAM clocks, and PLL_DDR0

`--suspend sr-gate` adds the two clock gates on the DRAM side -- `MBUS_CFG`
bit 31 and `DRAM_BGR` bit 0 -- and `--suspend sr-pll` also stops PLL_DDR0 and
relocks it before anything downstream is ungated. Both are built from the same
patch and differ from `sr` only in `SUNXI_SUSPEND_DRAM_LEVEL`. Each needs its
own card image and its own eight-minute deploy, and each was run through
experiment 23 first -- one sleep on its own -- before anything was measured
with it, because a rung that cannot come out of self-refresh looks exactly like
a target that stopped answering.

```text
 #  rung                                  s2idle    the rung    wake  card  DRAM
23  sr-gate, one sleep, first of its kind    --      99/10/11    yes   ok    ok
24  sr-gate against s2idle, ABBAAB        116 mean  101 mean     6/6   ok    6/6
```

**`sr-gate` works and is not worth anything on top of `sr`.** Its s2idle arms
read 116, 116 and 116 mA and its gated arms 102, 104 and 98, a mean of 101.3
against 116.0. Against `sr`'s 104.7 with an s2idle anchor of 116.3 in its own
boot, that is about 3.4 mA better -- the right direction, and less than half of
what this bench calls a difference. Six wakes of six, six md5 checks unchanged,
`success` 0 to 6 with `fail` 0, EL3's counters at 3 and 3, and every CCU
register the stub touched read back afterwards exactly as it was found:
`MBUS_CFG` `0xc1000002`, `DRAM_BGR` `0x00010001`.

Two things to know about reading that table. The first s2idle window lost one
reading to the supply's link dropping and is marked unsound, though its median
is the same 116 as the other two. And the harness opened eight windows for six
sleeps: the two extra are 9.7 s long and read 166 and 176 mA, which is the
target awake between cycles, not a sleep -- the DRAM probe's md5 is checked
after each wake and that check takes long enough to look like a state.

**`sr-pll` suspends and does not come back.** The board goes quiet at the
suspend and stays quiet: in the FPGA's trace the card's clock is at zero edges
a second from the moment the job marks the sleep until the harness gives up
five minutes later, with the read counter frozen at the value it had going in
and the card left selected. The RTC alarm was forty seconds out and nothing
happened at forty seconds.

What makes that a useful failure rather than just a dead end is what did
**not** happen. There was no warm reset -- a reboot would have shown thousands
of low-LBA reads in the trace and there are none -- so the watchdog never
fired, so the hang is not in either of the two windows the stub arms it for.
Those two windows are the self-refresh entry and the self-refresh exit, and
both of them are byte-for-byte what `sr-gate` does, which works. The hang is
therefore in the part in between: stopping PLL_DDR0, the WFI itself, or
relocking PLL_DDR0 before the watchdog is armed again.

The difference between the rung that works and the rung that does not is two
register writes and their undo:

```text
going down   PLL_DDR0_CTRL_REG &= ~(PLL_ENABLE | PLL_LOCK_ENABLE)
coming up    PLL_DDR0_CTRL_REG |=  (PLL_ENABLE | PLL_LOCK_ENABLE), wait for LOCK
```

**And the evidence for which of the three it is died with the 5 V.** The stub
writes a stage code into an RTC scratch register at every step, and those
registers are in the always-on domain -- but this board has no battery fitted,
so "always on" means "while the USB-C port is powering it". A hang that the
watchdog turns into a warm reset keeps them; a hang the watchdog does not cover
ends in the harness cutting the power at `--run-seconds`, and takes them with
it. Reproduced twice, identically.

What would settle it is arming the watchdog across the WFI as well, which means
waking on its reset rather than on the RTC alarm and reading the stage code on
the next boot -- a different experiment, and one this note did not run. The
likeliest answer, on the evidence that everything up to PLL_DDR0 works, is that
the Allwinner PHY does not survive its clock stopping: coming back would need
re-initialisation and re-training, which is exactly the step the prior art
takes and this stub is built to avoid.

### Where the ladder stopped, and what is kept

Taking s2idle as the anchor in each boot, and counting from the state the
device ships in:

```text
rung      what it adds                        asleep      against s2idle   kept
wfi       PLL_CPUX stopped                    112.5 mean      -4.5 mA      no
sr        + LPDDR4 in self-refresh            104.7 mean     -11.6 mA      YES
sr-gate   + DRAM bus and MBUS clock gates     101.3 mean     -14.7 mA      no
sr-pll    + PLL_DDR0 stopped                  does not resume              no
```

Each "against s2idle" is that rung's own boot. `sr`'s was measured three times
in all -- 11.6, 4.7 and 10.3 mA, about 9 mA pooled -- and the steady number in
it is the state the board ends up in, about 105 mA every time, rather than the
saving.

`sr` is the kept configuration, and it is what the card was left carrying. It
is the deepest rung that both pays and is fully proved: about nine milliamps
against s2idle pooled over three boots, ten consecutive cycles, and a
six-minute sleep with its memory intact. Put back on the card after the two
rungs above it had been tried and taken off again, it slept once more at
104 mA with its probe unchanged, which is the sixteenth self-refresh sleep and
the state the bench was left in.

`sr-gate` is three and a half milliamps below it, which is less than half of
what this bench calls a difference, and it has four self-refresh sleeps behind
it rather than sixteen. It is built, it works, and it is not the recommendation. The
ladder's own rule -- stop climbing when a rung stops paying -- stops here, and
the rung above it stops harder.

## Powered off is a third of the best sleep

`poweroff -f` with 5 V still on the USB-C port draws **33 mA** (33 to 35,
IQR 2, n=19 over 60 s in row 14; 33 to 35, IQR 2, n=62 over 190 s in row 15),
the steadiest reading this bench has taken -- a 2 mA interquartile range
against the 7 to 18 mA a sleeping target gives.

**And the RTC alarm powers it back on.** Row 14 armed
`/sys/class/rtc/rtc0/wakealarm` sixty seconds out and powered off. The card
went silent at 8.4 s and the FPGA's trace shows a fresh boot reading the root
filesystem at 69.4 s, 61.0 s later; the runner took the same job up again,
armed the alarm again and powered off again at 74.5 s, and the board came back
at 135.1 s, 60.6 s later. Two for two, both within a second of the alarm. Row
15 is the control: the same job with the alarm explicitly cleared powered off
at 15.7 s and the card saw nothing for the remaining 193 seconds of the run, at
33 mA throughout. So the board does not simply restart when it is powered off
on USB -- the alarm is what brings it back.

The price is a cold boot, about 5 s to the first card command and about 12 s to
userspace after power comes up, and nothing survives it. Against the 105 mA the
self-refresh firmware now sleeps at, that is a third rather than the quarter it
was before this section's neighbours were written; the gap has closed by eight
milliamps, and the remaining 72 are not in any of the clocks this work was able
to stop.

## After an outside review

The brief that went to a power expert is
[RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md](RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md), as it
was sent; their assessment and what it changed is the "After an outside review"
section of [RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md). Their main
correction is to the conclusion and not to the measurements, and it is applied
throughout this report: **what these experiments show is that the particular
CPU-clock, core-offline, peripheral-unbind and DRAM-clock-gating changes tried
do not explain most of the input power** -- not that the floor has been reached,
and not that none of the current is in a clock. The controller and PHY shutdown
the prior art performs (DFI shutdown, controller clocks off, pad retention,
reconstruction on resume) is more than this stub's `sr` rung does and is the one
clock-level step still unpriced. Every rail is up at full voltage, the DRAM
controller and its PHY are powered and mostly clocked, and the PMIC was
deliberately never written.

What of their points could be checked the same day with nobody at the bench was
checked, and that is experiments 27 and 28.

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
- **The drift goes with the transitions, which is suggestive and not
  established.** Inside the one six-minute self-refresh sleep the current does
  not climb: 104, 102 and 107 mA taken by thirds of the window. Experiment 28
  is the other half of the control -- the alternations' awake work, a 256 MiB
  md5, at the same dwell, six times in one boot with no suspend at all: 142,
  140, 139, 144, 134 and 145 mA while the SoC warmed from 36.0 to 37.9 C, which
  is no climb that a 10 mA spread can show. So the 1.5 mA per cycle is not time
  asleep and not the awake work between cycles; what is left is the suspend and
  resume transitions themselves, and nothing here has measured that directly.
- **Charging cannot be switched off through the driver in this kernel.** The
  battery supply reports `present=0` and `Not charging`, and there is no
  charge-enable attribute anywhere under `/sys/class/power_supply`, so that
  experiment needs a driver change or a person with a battery.
- **A median is not an average**, and the recomputation that says so -- means 5
  to 8 mA above medians in every sleep window, differences between arms
  unchanged -- is in "How it was measured" at the top of this report, because it
  applies to every figure in it and not only to these two rows.
- **Not testable hands-off:** whether the FPGA card interface is electrically
  neutral when the target is off or asleep. The gateware releases its lines
  when the host clock stops and the qualified bitstream has no pull-ups, but a
  powered FPGA on a target's pulled-up lines is exactly the back-powering the
  ROCKNIX work found on its second card slot, and only a physical disconnect
  settles it.

## Recommendations

Keep both of the things that paid: the `powersave` cpufreq governor, one line
of shell per boot, and the `--suspend sr` firmware, runbook section 12. Between
them they are the 105 mA sleep, they need no kernel or device-tree change, and
they resume reliably -- not `sr-gate`, which is three milliamps lower on a
quarter of the evidence, and not `sr-pll`, which does not come back. If the
application can stand a cold boot on waking, `poweroff -f` with the RTC alarm
armed is 33 mA instead of 105.

Everything else that would move the number needs a person at the bench, a
kernel rebuilt with `PM_DEBUG` and `DEBUG_FS`, or a decision about writing the
PMIC -- and the list of those, in the order the outside review put them and
with what each one would answer, is
[RG35XX-PLUS-BENCH-EXPERIMENTS.md](RG35XX-PLUS-BENCH-EXPERIMENTS.md).

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
`…/sr/rg35xx-plus-sleep-sr.img` and its `sr-gate` and `sr-pll` siblings.
Runbook section 12 builds all of them, and each needs its own eight-minute
`deploy` because the bootloader is part of the card image. Runbook section 11
has the `--label` lists and run lengths for every row, including 27 and 28,
whose windows are read by their dwell rather than by their labels.

Every run ends with the supply's output read back OFF and the card disarmed.
`psu2` is the RG35XX; `psu1` carries another machine on this bench and must
never be switched.

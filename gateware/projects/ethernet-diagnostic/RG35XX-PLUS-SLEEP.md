# RG35XX Plus: what timed sleep costs, and how low it goes

A report of the sleep-current work of 2026-09-20. It stands on its own; the
long-form evidence for every figure is the "Sleep" section of
[RG35XX-PLUS-FINDINGS.md](RG35XX-PLUS-FINDINGS.md), the commands are section 11
of [RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md), and the story, dead ends
included, is the 2026-09-20 entries of
[RG35XX-PLUS-HISTORY.md](RG35XX-PLUS-HISTORY.md).

The question was how little current the board can draw in a timed sleep, one it
enters by itself and leaves on an RTC alarm, and the condition was that nobody
looks at the device: every figure here came from the target's own records on
the emulated card and from the bench supply.

## The answer

| | at the 5 V input |
| --- | --- |
| asleep as the image ships, s2idle | 121 to 126 mA |
| asleep in the best configuration found | about 114 mA (110 to 119 over twenty cycles) |
| powered off with an RTC alarm armed, which does bring it back | 33 mA |
| supply output off | 1 mA |

s2idle is the only sleep state this kernel and firmware offer, and one knob is
worth keeping in it: the `powersave` cpufreq governor, 11 mA. Nothing else that
sysfs can reach is worth a milliamp. If the application can stand a cold boot
on waking, powering off with the alarm armed draws a quarter of the best sleep.

All currents are at the USB-C port at 5.00 V with **no battery fitted**, so they
include the PMIC's conversion and charger path and are not battery-life
figures. The supply reads to 1 mA, about once every two and a half seconds.

## How it was measured

- **Bench.** The qualified seed-19 bitstream, unchanged; the card image
  `build/rg35xx-sleep/rg35xx-plus-sleep.img`, built with
  `--card-max-hz 6000000` and the host command `job-runner`; supply channel
  `psu2`, 5.000 V, 1.200 A limit, never altered. `psu1` was never addressed.
- **The rule for a figure.** The median of the supply's readings taken wholly
  inside a state, after discarding the first 3 s, over a dwell of at least
  20 s (40 to 45 s in practice), with the range, the interquartile range and
  the count reported. A window in which the supply's wireless link dropped is
  marked UNSOUND and is not a measurement.
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
  nothing else, and writing `deep` to it returns EINVAL. `mem` and `freeze`
  are the same state.
- There is no cpuidle driver (`current_driver` reads `none`) and no
  `cpus/idle-states` in the device tree; PSCI is 0.2. A sleeping CPU only
  waits for an interrupt, the DRAM is not in self-refresh and no power domain
  collapses.
- The RTC is `7000000.rtc` with a working `wakealarm`; BusyBox has `rtcwake`.
  The kernel has `CONFIG_SUSPEND` and `CONFIG_RTC_DRV_SUN6I`; it does not have
  `DEBUG_FS` or `PM_DEBUG`, so there is no regulator summary and no suspend
  timing breakdown.
- One sleep and one RTC wake, proved: 46 s by the RTC for a requested 45,
  `success` 0 to 1, card check good before and after. Six of six in Phase 0,
  and every sleep since.
- While the target sleeps the card's clock stops dead: the FPGA counts exactly
  zero edges a second, where a powered-off target's floating pin still gives
  about fifty.

## Baselines

Two cold boots of each state, 45 s dwell.

```text
state                                       median       IQR
supply output off                              1 mA        -
asleep, s2idle                           121, 126 mA   7-21 mA
awake and idle, panel asleep             151, 144 mA  10-15 mA
awake and idle, panel lit, kernel level  176, 183 mA   9-11 mA
awake and idle, panel lit, full          246, 252 mA   9-11 mA
```

The suspend is worth about 22 mA on a target whose panel is already asleep. The
backlight at full costs about 100 mA more than a sleeping panel, four times
what the suspend saves.

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
- **The target's sleep can be the exchange window.** While it is suspended the
  host disarms the card, reads the result the job flushed on its way down,
  writes the next job and re-arms, in about 3 s; on waking Linux
  re-initialises the card by itself and the next job runs within a fifth of a
  second. Proved for two jobs in one boot, not for more.
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

Seventeen, one script each in
[`jobs/sleep/`](jobs/sleep). Cells are median / IQR / readings in mA over a
40 s sleep; `!` is an UNSOUND window; "mean" is the mean of three medians in an
A B B A A B run; "to N" means row N decided it properly; "ref." is a reference
point and not a sleep.

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

The ladders of rows 5 and 6 measured each knob once, after its own reference,
and the drift through a boot made them disagree with each other; the
alternations of rows 7 to 10 supersede them. The experiments stopped where the
goal said they should: rows 11, 12 and 13 are three in a row with no gain above
the noise.

## The best configuration

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
- Awake and idle, panel asleep: about 8 mA, 139 mA against 144 to 151.

**Ten consecutive cycles, twice.** The governor set once, then ten
`rtc_sleep 40 freeze` in one boot: ten wakes of ten and twelve card checks of
twelve in both runs, 41 s by the RTC for a requested 40 on all twenty,
`success` 0 to 10, `fail` 0.

```text
cycle       1    2    3    4    5    6    7    8    9   10
run A     118  114  119  114  118  113!  116  112  114  114!
run B     114  115  114  116!  117!  114  110  116  113  119
```

Sixteen of the twenty windows are sound, 110 to 119 mA. The four marked `!`
lost two or three readings to the supply's link dropping, a hole in the
measurement and not in the sleep.

## What is blocked, and the measurement that says so

- **Nothing else sysfs reaches is worth anything.** Row 13 unbound twenty-five
  devices at once, the whole display pipeline, the GPU, three audio codecs,
  both card controllers that are not the root, the backlight PWM, the watchdog,
  the PMIC's ADC, battery and USB drivers and the SoC's ADC, and put the LEDs
  out: 112 mA before, 109, 113 and 109 after. Still up afterwards: `vcc-pll`,
  `vcc-spkr-amp`, `vcc-io`, `cpusldo`, `vdd-cpu`, `vdd-gpu-sys`, `vdd-dram`,
  `dcdc4`, `aldo3`, `avcc`. Only `vcc-wifi` and `vcc3v3-mmc2` ever go away,
  and row 8 prices the two together at about a milliamp.
- **Offlining cores buys nothing** (row 7, 124 against 127). PSCI CPU_OFF works
  and survives a suspend; the rail the cores share does not drop.
- **Unbinding `panel-mipi` while the DRM master holds it costs the wake**,
  twice (rows 4 and 5). It is ordering and not the panel: with
  `display-engine` unbound first the same unbind is harmless (row 12), and
  worth nothing.
- **`aldo3` and `dcdc4` have no users and cannot be turned off.** The regulator
  core tries once, at 32 s of uptime, which lands inside the first suspend
  where the PMIC's I2C bus is down: `mv64xxx: I2C bus locked`, `aldo3:
  couldn't disable: -ETIMEDOUT`. It is never retried, and it costs nothing
  measurable either way (row 2).
- **The I2C traffic during a suspend is not the cost.** About 270 interrupts
  per 40 s cycle, about 128 with the pollers unbound, the current unchanged
  (row 11).
- **The state itself is the limit.** Anything deeper than s2idle needs idle
  states in the device tree and a firmware that implements them.

## Powered off is a quarter of the best sleep

`poweroff -f` with 5 V still on the port draws **33 mA** (33 to 35, IQR 2,
n=19 over 60 s and n=62 over 190 s), the steadiest reading this bench has
taken. An RTC alarm armed beforehand powers the board back on: twice of twice,
61.0 s and 60.6 s after a 60 s alarm. With the alarm cleared it stayed dark for
the remaining 193 s of the run, so the board does not simply restart on USB
power; the alarm is what brings it back. The price is a cold boot, about 5 s
to the first card command and about 12 s to userspace after power comes up, and
nothing survives it.

## Recommendations

None of these was done; the first two need a person at the bench.

1. Measure the same states on the battery. Everything here includes the
   AXP717's conversion and charger path with no cell fitted, and 33 mA is
   suspiciously large for a board that is off.
2. Put a meter in series with the battery terminals, or read the PMIC's
   coulomb counter, to separate what the SoC draws from what the PMIC costs.
3. If a cold boot on waking is acceptable, use poweroff and the RTC alarm:
   33 mA against 114, the wake proved twice and the stay-off once.
4. The next real saving is in the device tree and the firmware:
   `cpus/idle-states` for a cpuidle driver and a `mem` that is not s2idle, and
   a suspend that collapses the domains behind `vdd-dram`, `vdd-gpu-sys`,
   `vcc-pll` and `avcc`.
5. A kernel with `PM_DEBUG` and `DEBUG_FS` for `pm_print_times`, the suspend
   timing breakdown and the regulator summary. Nothing here needed it; the
   next question probably will.

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

Every run ends with the supply's output read back OFF and the card disarmed.
`psu2` is the RG35XX; `psu1` carries another machine on this bench and must
never be switched.

# RG35XX Plus: the deep-sleep firmware experiment

A lab report of one experiment, run on 2026-09-20: give the Anbernic RG35XX
Plus (Allwinner H700) a real suspend-to-RAM with a firmware of our own, built
from source, and measure what it is worth at the wall. The measurements, all
thirty-three job scripts and the long-form evidence are in
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md); the commands are section 12 of
[RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md). This is the short version:
why it was tried, what was built, what it measured, and whether it was worth
doing.

## Verdict

**Ours works and saves about forty milliamps, which is within three of the
published implementation it was modelled on.** It took three attempts to get
there: the first two saved almost nothing, and the third -- switching the DRAM
controller, its PHY and PLL_DDR0 off and building them again on the way back --
is where all of it was.

```text
step                                          asleep, 5 V input   saved    cost
s2idle as the image ships                         ~124 mA            --     --
+ powersave cpufreq governor                      ~115 mA         9-11 mA   one line of shell
+ our PSCI SYSTEM_SUSPEND, CPU PLL stopped        ~113 mA          ~3 mA    a 420-line TF-A patch
+ LPDDR4 in self-refresh, from an SRAM stub       ~105 mA          ~9 mA    4224 bytes of assembly
+ controller, PHY and PLL_DDR0 off, rebuilt        ~75 mA          ~29 mA   a C stub in SRAM that
  on resume from U-Boot's DRAM driver                                       links U-Boot's driver
ROCKNIX's suspend instead (`rocknix-deep`)         ~68 mA      ~51 vs s2idle  the same idea, theirs
powered off, RTC alarm armed (not a sleep)          33 mA            --     a cold boot on waking
```

All of it together takes a sleeping board from about 124 mA to about 75, forty
percent, and the firmware is about forty of those milliamps. About 42 mA
separates the best sleep from a board that is powered off, and that is rails:
every one is still up at full voltage and the PMIC was deliberately never
written.

The experiment's shape is worth keeping as well as its number. Two rungs in a
row measured nothing and the report said so; the third, which an outside
reviewer named as the one clock-level step still unpriced, was worth three
times everything before it. A clock-level change that has not been tried is not
a clock-level change that is worth nothing.

Currents are at the USB-C port at 5.00 V with no battery fitted, so they
include the AXP717's conversion and charger path and are not battery-life
figures.

## Why it was tried

The sysfs experiments (SLEEP.md, experiments 1 to 17) ended with one kept knob
and a wall: `/sys/power/mem_sleep` offered `[s2idle]` alone, there is no
cpuidle driver, and in s2idle the cores only wait for an interrupt while the
DRAM, its controller and every PLL keep running. The question that followed was
whether the kernel could be patched to switch more of the CPU off while asleep.

**What the public documents say.** There is no public H700 register manual;
the H700 is the H616 die in a package that brings out the LCD pins, so the
H616 datasheet and user manual (linux-sunxi.org) were read instead.

- The datasheet's power-consumption section is one sentence, "contact
  Allwinner FAE". There is no sleep current to compare with.
- Its power-sequence figure (5-42) has Power-on, Sleep and Wakeup columns, and
  **in it every rail stays up through Sleep** -- VCC_DRAM, the 1.8 V group,
  VCC_IO, and VDD_SYS/CPU/GPU/HDMI at 0.9 V -- and so does the 24 MHz clock.
  The datasheet's own picture of sleep is a clock-level one. (An earlier
  reading of this figure from extracted text, as showing the core rails
  dropping, was wrong; the rendered page settles it.)
- The user manual documents per-core power switches and an L2 idle mode in
  the CPUX configuration block, and Super Standby flag and software-entry
  registers in the RTC (`0x070001F8`, `0x070001FC`) that a boot ROM path uses
  to resume a retained session. The PRCM is in the memory map at `0x07010000`
  and its registers are not documented.

**Why not the kernel.** The kernel runs from the DRAM, so it cannot put the
DRAM into self-refresh; that needs code running from on-chip SRAM, entered
through the firmware. Offlining cores, which goes through PSCI CPU_OFF, had
already measured nothing (124 against 127 mA). The one CPU lever the kernel
has is the operating point, and that is the governor knob already kept.

**Prior art.** kailashrs implemented PSCI `SYSTEM_SUSPEND` for the H616/H700
([H700_rocknix_enhancement](https://github.com/kailashrs/H700_rocknix_enhancement)):
TF-A hands control to a program in SRAM that puts the LPDDR4 into
self-refresh, stops the DRAM controller, PHY and CPU PLL, and waits. ROCKNIX
merged it as [PR #3316](https://github.com/ROCKNIX/distribution/pull/3316) on
2026-09-19, packaged from
[h700-suspend-stub](https://github.com/Jacob-Matthew-Cook/h700-suspend-stub).
They report dozens of cycles, RTC and power-key wake, and **about 3 %/h of
battery in deep sleep**, with three further peripheral-gating kernel patches
measuring no change at that level (2.7 and 3.3 %/h against 3.05). They publish
no current and no s2idle drain to compare with. Their own notes say the port
"does not change PMIC rail voltages" and is not the stock firmware's deeper
standby, which by their static analysis of the OEM BL31 writes a CPU/SYS/IO
rail mask to the PMIC and resumes through boot0.

So the experiment: build our own minimal version of the same idea from source,
one rung at a time, and put a number on each rung.

## What was built

Our own code, their design credited. The TF-A patches are BSD-3-Clause like
the TF-A they patch; the C stub added later is GPL-2.0-or-later because it
links U-Boot's DRAM driver, and lives apart from them for that reason. No PMIC
register, rail, or I2C/RSB access anywhere in any of it.

- **`rg35xx.py build-firmware --suspend {none,wfi,wfi32,sr,sr-gate,sr-pll}`**
  builds the bootloader ROCKNIX ships for this board from pinned sources in a
  container: mainline U-Boot v2026.01, ROCKNIX's one DRAM patch and
  `anbernic_rg35xx_h700_lpddr4_defconfig` at a pinned commit, and TF-A v2.12.0.
  A second build into another directory is byte-identical.
  `image --install-bootloader` puts the result at byte 8192 of a base image and
  refuses one that would reach the job region or the first partition.
- **`firmware/0001-...-minimal-psci-system-suspend.patch`** advertises
  `SYSTEM_SUSPEND` and implements it: CPU clock from PLL_CPUX to the 24 MHz
  oscillator, PLL_CPUX stopped, wait for an interrupt at EL3, PLL relocked with
  a bounded wait, MMU off, branch to `bl31_warm_entrypoint`. Every register is
  cited to the manual; the PRCM PLL-LDO write the prior art marks "inferred" is
  not made. Counters and a stage code go to RTC general-purpose registers
  12 to 15, which a job reads back with `devmem`.
- **`firmware/0002-...-dram-self-refresh-from-an-sram-stub.patch`** adds the
  stub: 4224 bytes of hand-written assembly copied to SRAM A1 (`0x20000`),
  because BL31 itself lives in the DRAM on this platform. It is assembly and
  not C because there is no stack, nothing callable and no literal pool once
  the DRAM is asleep. It requests software self-refresh from the controller,
  waits for the controller to report it, stops the CPU PLL, waits, and undoes
  it in reverse, with the watchdog armed around each step that touches the
  DRAM so that a hang becomes a warm reset.
- **`firmware/stub/` and `firmware/0003-...-suspend-from-a-stub-built-outside-the-tree.patch`**
  are the third stage, added after the published implementation was measured:
  a C stub for the same SRAM, compiled in the container against U-Boot's H616
  DRAM driver so that it can shut the controller and the PHY down completely
  and build them again on the way back. 0003 is an alternative to 0002, never
  applied beside it. Modes `sr-c`, `sr-phy` and three `sr-phy-*` ablations.

No kernel or device-tree change was needed: with the firmware advertising the
call, `/sys/power/mem_sleep` reads `s2idle [deep]`.

## Method

The job harness and the measurement rule of SLEEP.md, unchanged. Each
comparison alternates the two states inside one boot in the order
A B B A A B (A is `mem` resolved to s2idle, B is `mem` resolved to `deep`),
with the `powersave` governor in both arms, 40 s sleeps, the median of the
supply's readings inside each window after discarding 3 s. A difference under
about 8 mA is not believed. A wake counts only if the RTC says the sleep lasted
what was asked, `suspend_stats/success` rose by one with `fail` unchanged, and
a card write and read-back passes. From stage 2 on, every deep sleep also
carries a 256 MiB random file in tmpfs whose md5 is checked after the resume.
The firmware's own counters in the RTC registers say which sleeps went through
EL3, which makes the s2idle arm a control and not only a comparison.

There is no serial console. Debugging was the FPGA's passive trace of the card
(the clock stops and resumes; a reboot shows as boot reads), the supply
current, and the RTC progress codes read back after a watchdog reset.

## Results

**Stage 0, parity.** The from-source bootloader with no suspend patch is the
bootloader it replaced: userspace at 5.72, 5.76 and 5.76 s against 5.66 to
5.76, the same kernel stage times, s2idle at 128 mA under `performance` and
115 under `powersave` against 126 and 115, and `mem_sleep` still `[s2idle]`.

**Stage 1, the CPU PLL stopped, DRAM running.** Seventeen deep suspends over
four boots, seventeen resumes, ten of them consecutive (110 to 117 mA); wake
interrupt 136, the RTC alarm, every time. Against s2idle: 117 mean against
112, and 117 against 114. Re-run independently: 116 against 113. **About
3 to 4 mA, which is not a difference here.** A core waiting for an interrupt
is already clock-gated; all the CPU clock tree had left to give was the PLL's
bias current.

**Stage 2, the LPDDR4 in self-refresh.**

```text
rung      what it adds                        asleep       against s2idle   resumes
sr        LPDDR4 in self-refresh              ~105 mA       about -9 mA     yes, kept
sr-gate   + DRAM bus and MBUS clock gates     ~101 mA       about -15 mA    yes
sr-pll    + PLL_DDR0 stopped                  --            --              never, 2 of 2
```

- `sr`: sixteen self-refresh sleeps, sixteen resumes, every md5 unchanged: ten
  consecutive cycles at 103 to 112 mA, and **one sleep of six minutes**, 361 s
  by the RTC at 105.5 mA over 112 readings with the probe intact. The
  six-minute sleep is the one that proves the memory is being refreshed; a
  cell holds its charge for longer than forty seconds unaided.
- The saving was measured three times, once by the agent that built it and
  twice from the committed script by the session that orchestrated the work:
  116.3 against 104.7, 109.7 against 105.0, 115.0 against 104.7. **The
  self-refresh arm reads 105 mA every time; the s2idle arm moves between
  boots, and the saving with it: 11.6, 4.7 and 10.3 mA, about 9 pooled.**
  Twelve more wakes of twelve and twelve more md5 checks in those re-runs.
- `sr-gate` is about 3 mA below `sr`, under half of what this bench believes,
  with four sleeps behind it. Built, working, not kept.
- `sr-pll` suspends and never returns. There was no warm reset, so the
  watchdog did not fire, so the hang is in the wait or the relock, which the
  watchdog does not cover; the progress code that would say which died with
  the 5 V. The likeliest cause is that the Allwinner DRAM PHY needs
  re-initialising once its clock has stopped, which is the step the prior art
  borrows U-Boot's DRAM driver for and this stub exists to avoid.

## What it means

- **The accessible clock-level changes are nearly spent.** Stopping the CPU
  PLL, gating the DRAM bus clocks and putting the memory to sleep together move
  a 115 mA sleep by about ten. The datasheet's own sleep figure keeps every
  rail up, the prior art keeps every rail up, and the prior art's peripheral
  gating measured nothing on a battery either. What has *not* been done is the
  controller and PHY shutdown the prior art performs (DFI shutdown, controller
  clocks off, pad retention, reconstruction on resume), which is more than this
  stub's `sr` rung and is the one clock-level step still unpriced.
- **The remaining 72 mA is rails**: `vdd-dram`, `vdd-gpu-sys`, `vcc-pll`,
  `vcc-io`, `avcc`, `cpusldo`, `vcc-spkr-amp`, and `aldo3` and `dcdc4` with no
  users, plus whatever the AXP717 and its charger path cost with no cell on
  them. 33 mA for a board that is off is itself suspicious, and may be mostly
  that.
- **What it did produce**: current figures nobody had published for this
  design; a reproducible from-source bootloader; a `deep` state that resumes
  with its memory proved intact, which is the entry and exit any deeper scheme
  needs; and the knowledge of where not to look.

## Their firmware on the same card

The reviewer's main objection was that the DRAM controller and PHY shutdown the
published implementation performs had never been priced. The bench-experiment
list had it as B4, needing a real card and a person to press the power key. It
did not: `build-firmware --suspend rocknix-deep` builds kailashrs' TF-A patch
and SRAM stub from source at the commits ROCKNIX pins (patch sha256
`6928fc3e...`, stub `712653d1...`), with none of our patches, beside the same
U-Boot and TF-A trees, and the result goes on the emulated card under the same
kernel, rootfs and job harness as everything else here. Only the firmware
differs, which a whole ROCKNIX image on a real card would not have given.

```text
what was run (powersave in both arms, 40 s sleeps)   s2idle            deep             wake  card  DRAM
one deep sleep, first of its kind                       --             65 mA             yes   ok    ok
theirs against s2idle, ABBAAB, medians            121, 114, 124     70, 67, 68          6/6   ok   6/6
   the same windows, means                        127, 131, 129     81, 79, 79
one six-minute sleep                                    --        72 mA, n=115           yes   ok    ok
ours with the 32 kHz CPU clock (wfi32), ABBAAB    121, 119, 119    114, 112, 114        6/6   ok    --
```

- **Theirs sleeps at about 68 mA by medians, 80 by means: about 50 mA below
  s2idle in the same boot and about 37 below our `sr` firmware's 105.** 361 s
  by the RTC for a requested 360 in the long sleep, the 256 MiB probe's md5
  unchanged every time, on a 1 GiB LPDDR4 board their authors had not run.
- **What theirs does that ours does not**: stops the MBUS masters, shuts down
  the DFI interface, clears the controller's clock enables, gates and resets
  the DRAM clock path, stops PLL_DDR0, moves APB1 and APB2 as well as the CPU
  to the 32 kHz clock, and on resume rebuilds the controller and PHY with
  U-Boot's own DRAM driver, cold initialisation skipped and the words training
  overwrites saved and restored. Ours requests self-refresh and leaves the
  controller, PHY and PLL_DDR0 running; our `sr-gate` rung gated two clocks for
  3 mA, and our `sr-pll` rung stopped the PLL without rebuilding the PHY and
  never came back. The prize was on the far side of the rung that hung.
- **It is not the 32 kHz CPU clock.** `wfi32`, built earlier and never run on
  the grounds that a core waiting for an interrupt is clock-gated anyway, was
  run: 120 mA mean against 113, six or seven milliamps, two of the s2idle
  windows unsound. Worth slightly more than stopping the PLL alone and nowhere
  near forty.
- **What this does to the verdict.** "Clock-level suspend is a dead end on this
  SoC" was wrong, and was already softened on the reviewer's advice before
  this was measured. The DDR PHY and its PLL are a large consumer, and
  switching them off while the memory refreshes itself is worth more than
  everything else in this report together. The gap to a powered-off board is
  now about 35 mA, not 72.

## Ours does it too now

The rung that hung is the rung that pays, and `--suspend sr-phy` is it: a C
stub of ours in SRAM A1, compiled inside the build container against U-Boot's
own H616 DRAM driver from the same pinned tree the bootloader is built from,
which shuts the DFI interface down, clears the controller's clock enables,
gates and resets the DRAM clock path, stops PLL_DDR0, parks the CPU and both
APBs on 32 kHz -- and then builds the controller and the PHY again on the way
back, with the cold SDRAM initialisation skipped and the words the training
writes over saved and restored.

```text
what was run (powersave both arms, 40 s sleeps)   s2idle              sr-phy
three short sleeps, watchdog across the wait        --            3/3, md5 ok
sr-phy against s2idle, ABBAAB, medians        112, 117.5, 116.5   76, 77, 75
ten consecutive cycles                              --          68.5-79, 10/10
one six-minute sleep                                --          75 mA, n=114
   theirs, the same job, the same day               --          72 mA, n=115
```

**On the six-minute sleep, which is the cleanest figure either firmware
produces, ours is 75 mA against their 72 -- three apart, which this bench does
not call a difference.** On the forty-second alternation ours reads about eight
higher and saves about twelve less, and the two runs' s2idle arms differ by
four, so some of that is the boot. The one thing theirs does that ours
deliberately does not is write the PRCM register at `+0x244` with a key of
`0xa7`, which takes a PLL LDO down; their own comment marks it inferred, it is
a supply and not a clock, and this work writes no supply of any kind. That is
the likeliest place for the rest of the difference.

It is GPL-2.0-or-later and lives in `rg35xx/firmware/stub/` with its own
licence note, because it is a derived work of U-Boot's driver; the TF-A patch
that loads it (`0003-...`) is BSD-3-Clause like the rest of our TF-A work, and
is an alternative to the assembly stub's patch rather than an addition. Nothing
of U-Boot is copied into this repository.

Two ablations say where the 29 mA is *not*. **Stopping PLL_DDR0 is worth
nothing**: 74.8 mA with it left running against 76.0 with it stopped, in two
boots whose s2idle arms agree to half a milliamp. **Nor is the 32 kHz clock
step**: 73.0 mA with the cluster and both APBs left on the 24 MHz oscillator.
Both are the wrong side of `sr-phy` by less than the noise, so by elimination
the saving is the DFI shutdown, the controller's own clock enables, and holding
the DRAM clock path in reset rather than merely gated -- `sr-gate` had already
priced the gates alone at 3.4 mA. The long-form account, and the first look
anyone has had at which PLLs are running while this board is asleep -- read by
the stub itself at the instruction before WFI and left in SRAM for a job -- are
in [RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md).

That snapshot says `PLL_VIDEO0`, `PLL_DE` and the DE bus clock are still on
with the panel long asleep, and `--suspend sr-phy-nodisp` stops all three. Its
sleeps read about eight milliamps lower, which would close the gap to theirs
entirely -- **and it is not kept, because one of its first three sleeps failed
its PHY rebuild** and the watchdog reset the board. The marker channel caught
it exactly: stage `0xa5d500e5`, `fail_info` `0x00350007`, which is read
calibration failing all five of its tries with no poll timing out. Restarting
two PLLs and waiting for them to lock immediately before the PHY is re-trained
is the likeliest cause and moving that restore after the rebuild is one line,
but a rung that cannot be trusted to resume is not a rung whatever it draws.

The card was left carrying
`build/rg35xx-firmware-src/sr-phy/rg35xx-plus-sleep-sr-phy.img`.

## After an outside review

The brief in [RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md](RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md)
went to a power expert. Their assessment: the measurements are credible, the
conclusion was stated too strongly (corrected above), and the next evidence
worth having is battery-only power, the physical rail voltages in each state,
and the current in DCDC2, the shared system and GPU supply. What could be
checked without anyone at the bench was checked the same day:

- **The regulator-cleanup race is closed, and it was worth nothing.**
  Experiment 27 stays awake past the kernel's one cleanup at 32 s: `aldo3:
  disabling` at 32.05 s, `aldo3` reads `disabled` afterwards. The same awake
  idle state read 141 mA before it and 142 after, and two self-refresh sleeps
  with it off read 107 and 104 mA against the 105 every sleep read with it on.
  The upstream board file calls ALDO3 unused, and an output with nothing on it
  saves nothing.
- **DCDC4 is not a rail to chase.** It stays `enabled` with no users through
  the cleanup. On an AXP717 configured as a charger DCDC4 is not an
  independent output at all; the regulator framework's 1.0 V entry is a
  descriptor, not evidence of a supply. It is left alone.
- **Charging cannot be switched off through the driver here.** The battery
  supply reports `present=0`, `Not charging`, and this kernel exposes no
  charge-enable attribute, so that experiment needs a driver change or a
  person with a battery.
- **The drift is not time asleep and not the awake work.** Inside the one
  six-minute sleep the current does not climb: 104, 102 and 107 mA by thirds.
  Experiment 28 repeats the alternations' awake work, a 256 MiB md5 and the
  same dwell, six times with no suspend: 142, 140, 139, 144, 134 and 145 mA
  while the SoC warmed from 36.0 to 37.9 C, no climb a 10 mA spread can show.
  That leaves the transitions themselves, which is suggestive and not
  established.
- **A median is not an average.** Recomputed from the stored readings, the
  mean runs 5 to 8 mA above the median in every sleep window, with single
  readings of 166 to 220 mA inside windows whose median is 105. The
  differences between arms survive (11.0 mA by means against 11.6 by medians
  in the first self-refresh alternation), but the absolute sleeping power is
  nearer 110 to 112 mA than 105, and only a shunt and a scope will say whether
  those readings are bursts or edges.
- **Not yet testable hands-off:** whether the FPGA card interface is
  electrically neutral when the target is off or asleep. The gateware releases
  its lines when the host clock stops and the qualified bitstream has no
  pull-ups, but a powered FPGA on a target's pulled-up lines is exactly the
  back-powering the ROCKNIX work found on the second card slot, and only a
  physical disconnect settles it.

**For the next visit to the bench**, in the expert's order: the battery with a
shunt, the rail voltages in each state, the card interface unplugged for the
off measurement, then DCDC2. The list itself, with what each experiment would
answer and what it needs,
is [RG35XX-PLUS-BENCH-EXPERIMENTS.md](RG35XX-PLUS-BENCH-EXPERIMENTS.md), so
that it lives in one place.

## What would move the number

0. **Done since this list was written**: the DRAM controller and PHY shutdown,
   item 4 below, which turned out to be 29 mA rather than "a few milliamps at
   most". See "Ours does it too now" above.
1. **Power off with the RTC alarm armed**: 33 mA, the wake proved twice. It is
   a cold boot, about 5 s to the first card command. For long timed sleeps this
   is the answer today, though the gap is now 42 mA and not 72.
2. **Cut the core rails through the PMIC during the suspend**, as the stock
   firmware's deepest standby does by the prior art's analysis, with a resume
   path in the first-stage loader that rebuilds the DRAM controller without
   wiping memory (the manual's Super Standby registers are what that path
   keys on). That is where the 72 mA is. It means I2C writes to the AXP717
   from firmware and SPL work, on a board that at present has no battery
   fitted; it was not attempted and should not be without a battery and a
   decision.
3. **Measure on a battery**, or with a meter in series with the cell. Both the
   105 and the 33 include a USB-fed PMIC with nothing to charge, and the ratio
   on a cell may be quite different.
4. ~~If `sr-pll` is wanted anyway: arm the watchdog across the wait so the hang
   leaves evidence, then re-initialise the PHY on resume. On the evidence of
   `sr-gate` it is worth a few milliamps at most.~~ **Done, and the estimate
   was wrong by an order of magnitude: 29 mA.** Both halves of the suggestion
   were needed and both worked -- job 31 arms the watchdog across a ten-second
   wait so a hang leaves its stage code behind, and `sr-phy` re-initialises the
   PHY with U-Boot's driver running out of SRAM.

## Running it again

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-firmware --suspend sr          # then runbook section 12: install, image, deploy

MDP_CLI=/path/to/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py job \
  --state /private/tmp/rg35xx-sleep-session.json \
  --image build/rg35xx-firmware-src/sr/rg35xx-plus-sleep-sr.img \
  --script projects/ethernet-diagnostic/jobs/sleep/24-selfrefresh-vs-s2idle-abba.sh \
  --name sr-abba --run-seconds 480 \
  --label A1 --label B1 --label B2 --label A2 --label A3 --label B3 \
  --output /tmp/sr-abba.json --print-output
```

The md5 check between sleeps opens an extra short window at about 170 mA, so
read the windows by their dwell (a sleep is 40 s) and not by their labels.
Of the thirty-three job scripts, 1 to 17 are the sysfs experiments, 18 to 21
stage 1, 22 to 26 stage 2, 27 and 28 the checks that followed this review, and
29 to 33 stage 3, the PHY rebuild -- 29 its facts, 30 one sleep, 31 the
watchdog-covered short sleeps that make a hang leave evidence, 32 the
alternation and 33 a register dump that can be diffed against theirs.
`psu2` is the RG35XX; `psu1` carries another machine on this bench and must
never be switched.

## Sources

- H616 Datasheet V1.0 and H616 User Manual V1.0, linux-sunxi.org
- <https://github.com/ROCKNIX/distribution/pull/3316>
- <https://github.com/kailashrs/H700_rocknix_enhancement> (`docs/DESIGN.md`,
  `docs/OEM_STANDBY.md`)
- <https://github.com/Jacob-Matthew-Cook/h700-suspend-stub>

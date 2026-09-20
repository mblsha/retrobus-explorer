# RG35XX Plus: the deep-sleep firmware experiment

A lab report of one experiment, run on 2026-09-20: give the Anbernic RG35XX
Plus (Allwinner H700) a real suspend-to-RAM with a firmware of our own, built
from source, and measure what it is worth at the wall. The measurements, all
twenty-six job scripts and the long-form evidence are in
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md); the commands are section 12 of
[RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md). This is the short version:
why it was tried, what was built, what it measured, and whether it was worth
doing.

## Verdict

**It works, and it saves less than ten milliamps.**

```text
step                                          asleep, 5 V input   saved    cost
s2idle as the image ships                         ~124 mA            --     --
+ powersave cpufreq governor                      ~115 mA         9-11 mA   one line of shell
+ our PSCI SYSTEM_SUSPEND, CPU PLL stopped        ~113 mA          ~3 mA    a 420-line TF-A patch
+ LPDDR4 in self-refresh, from an SRAM stub       ~105 mA          ~9 mA    4224 bytes of assembly
powered off, RTC alarm armed (not a sleep)          33 mA            --     a cold boot on waking
```

All of it together takes a sleeping board from about 124 mA to about 105 mA,
fifteen percent. The firmware, which is nearly all of the work, is about 9 mA
of that, and only the self-refresh half of it is above what this bench can
tell from noise. About 72 mA separates the best sleep from a board that is
powered off, and none of it is in a clock, a PLL, an idle core or the DRAM's
own activity: it is rails that stay up, and rails belong to the PMIC, which
this experiment deliberately never wrote.

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

Our own code, their design credited; BSD-3-Clause like the TF-A it patches.
No PMIC register, rail, or I2C/RSB access anywhere in it.

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

- **Clock-level suspend is a dead end for power on this SoC.** Stopping the
  CPU PLL, gating the DRAM clocks and putting the memory to sleep together move
  a 115 mA sleep by about ten. The datasheet's own sleep figure keeps every
  rail up, the prior art keeps every rail up, and the prior art's peripheral
  gating measured nothing on a battery either. The three agree.
- **The remaining 72 mA is rails**: `vdd-dram`, `vdd-gpu-sys`, `vcc-pll`,
  `vcc-io`, `avcc`, `cpusldo`, `vcc-spkr-amp`, and `aldo3` and `dcdc4` with no
  users, plus whatever the AXP717 and its charger path cost with no cell on
  them. 33 mA for a board that is off is itself suspicious, and may be mostly
  that.
- **What it did produce**: current figures nobody had published for this
  design; a reproducible from-source bootloader; a `deep` state that resumes
  with its memory proved intact, which is the entry and exit any deeper scheme
  needs; and the knowledge of where not to look.

## What would move the number

1. **Power off with the RTC alarm armed**: 33 mA, the wake proved twice. It is
   a cold boot, about 5 s to the first card command. For long timed sleeps this
   is the answer today.
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
4. If `sr-pll` is wanted anyway: arm the watchdog across the wait so the hang
   leaves evidence, then re-initialise the PHY on resume. On the evidence of
   `sr-gate` it is worth a few milliamps at most.

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
Jobs 18 to 21 are stage 1, 22 to 26 stage 2. `psu2` is the RG35XX; `psu1`
carries another machine on this bench and must never be switched.

## Sources

- H616 Datasheet V1.0 and H616 User Manual V1.0, linux-sunxi.org
- <https://github.com/ROCKNIX/distribution/pull/3316>
- <https://github.com/kailashrs/H700_rocknix_enhancement> (`docs/DESIGN.md`,
  `docs/OEM_STANDBY.md`)
- <https://github.com/Jacob-Matthew-Cook/h700-suspend-stub>

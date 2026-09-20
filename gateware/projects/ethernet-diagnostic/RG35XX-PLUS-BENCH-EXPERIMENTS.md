# RG35XX Plus: experiments that need a person at the bench

Everything measured so far was measured with nobody there: the target reports
through the emulated card, the FPGA traces it, and the bench supply reads the
current at the USB-C port. That has run out of questions it can answer. The
ones left are about what is *physically* happening on the board, and each
needs hands, a meter, a battery or a second card. This is the list: what each
experiment is, **the question it is supposed to answer, and what we would do
differently depending on the answer.**

Where we stand, in one paragraph: suspended with our own firmware (LPDDR4 in
self-refresh, CPU PLL stopped, `powersave` governor) the board draws about
105 mA at 5.00 V by the median of the supply's readings, 110 to 112 by their
mean; with the published ROCKNIX firmware built from source, which also shuts
the DRAM controller, PHY and PLL down, about 68 mA (80 by the mean); powered
off with USB attached it draws 33 mA. There is no battery fitted, so all of
these include the AXP717's power path with nothing to charge. About 35 mA lies
between the best sleep and off, every rail is still up at full voltage, and no
PMIC register has been written. The background is in
[RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md) (the verdict and the
outside review) and [RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md) (every
measurement).

## At a glance

Ordered by value for effort. "Then hands-off" means one manual action after
which the existing harness does the measuring.

| # | experiment | the question | needs | effort | risk |
| --- | --- | --- | --- | --- | --- |
| B1 | pull the card from slot 2 | does that card cost sleep/off current, and is it the slow boots? | fingers | 5 min, then hands-off | none |
| B2 | photograph the board, read the chips | which DRAM, which PMIC wiring, where are the probe points and UART pads? | phone, magnifier | 20 min | none |
| B3 | stock firmware on the same supply | what can this hardware actually reach in standby? | the stock SD card | 1 h | none |
| B4 | ~~ROCKNIX's deep sleep on the same supply~~ **done, with nobody there** | is the controller/PHY shutdown we have not built worth anything? **Yes: 68 mA against our 105** | -- | -- | -- |
| B5 | unplug the FPGA card interface while off / asleep | is the rig itself feeding or loading the target? | fingers, a watch | 30 min | low |
| B6 | rail voltages in awake / sleep / off | which rails are physically up, and is anything back-powered? | DMM, board open | 1 h | low |
| B7 | battery with a shunt, USB disconnected | what is the real battery-side power, and how much of our figures is USB power-path? | the cell, shunt, DMM | half a day | low–medium |
| B8 | RTC wake on battery alone | is power-off-with-alarm a product strategy or a bench artefact? | B7's setup | with B7 | low |
| B9 | scope across the shunt during sleep | are the 170–220 mA readings real bursts? what is the true mean? | B7 + scope/diff probe | 1 h | low |
| B10 | real SD card in slot 1 | what does a real card add, and must its supply be held or cut in suspend? | a real SD card | 1 h | none |
| B11 | shunt in DCDC2's load side, then DCDC3 | which rail carries the remaining current? | rework, shunt, DMM | a day | medium |
| B12 | fit a UART | (not a power question) can the risky firmware work stop being blind? | UART adapter, soldering | 2 h | low–medium |
| B13 | charger on/off with a battery fitted | what does the charger path cost at the USB input? | B7's setup | 30 min | low |
| B14 | sleep current cold against warm | how much of the sleeping current is leakage? | a way to warm/cool the board | 1 h | low |

## Rules that apply to every one of them

- `psu2` is the RG35XX; **`psu1` carries another machine and must never be
  switched.** Do not change `psu2`'s 5.000 V or its 1.200 A limit.
- An armed FPGA must not be left driving an unpowered target: disarm the card
  (`images.py --disarm`) before unplugging or powering anything by hand, unless
  the experiment is about exactly that (B5).
- Nothing here writes a PMIC register. B7 onward handles a lithium cell: the
  correct protected cell, correct polarity, no bench supply across its
  terminals while the charger can drive it, no earth-referenced scope ground on
  battery positive.
- Write down the state, the time and the reading. A number without its state is
  not a measurement.

## The experiments

### B1. Pull the card from slot 2

**Question.** Does the real 119 GiB card in the second slot cost anything while
the board sleeps or is off, and is it the cause of the one-boot-in-ten slow
boot?
**Why it matters.** Its controller (`4022000.mmc`) is what times out in every
slow boot. Its supply `vcc3v3-mmc2` is cut in some states while its signal
lines stay pulled up from the always-on `vcc-io`, which is exactly the
back-powering the ROCKNIX work found on this slot and fixed by keeping the
supply on. Unbinding the controller measured about 1 mA, but unbinding does
not remove the card.
**Do.** Power off, disarm, pull the card. Say so. The harness then re-runs the
`sr` alternation, the power-off reference and twenty cold starts unattended.
**Read it as.** A step in the off or sleep current is that card's standby plus
back-power, and the fix is a device-tree decision about its supply. No slow
boot in twenty would (weakly) tie the slow boots to the card rather than the
controller.

### B2. Photograph the board and read the chips

**Question.** Which LPDDR4 part is fitted, how is the AXP717 wired (is DCDC4's
inductor populated or is that converter the charger, is ALDO3 routed
anywhere), which board revision is this, and where are the probe points for
B6/B11 and the UART pads for B12?
**Why it matters.** The DRAM's datasheet gives its self-refresh current
(IDD6), which is the honest floor for any sleep that keeps its memory; without
the part number that floor is a guess. The expert's point about DCDC4 (on a
charger-configured AXP717 it is not an independent rail) is settled by looking.
Every later experiment needs to know where to put a probe.
**Do.** Open the case, photograph both sides in good light, read the markings
on the DRAM, the PMIC and the inductors around it.
**Read it as.** Feeds a retention-power budget: DRAM supplies × IDD6 +
always-on + conversion. If that budget is tens of milliwatts and we are at
500, the remaining projects are worth doing; if it is already hundreds, they
are not.

### B3. The stock firmware on the same supply

**Question.** What does this exact hardware draw in the vendor's Normal
standby, its Super standby, and off, measured the way we measure ours?
**Why it matters.** It is the only evidence available of what the hardware can
reach. By the prior art's static analysis the stock Super standby writes a
CPU/SYS/IO rail mask to the PMIC and resumes through boot0 with the DRAM
retained. If it measures 20 mA, the rail-off project has a known prize; if it
measures 90, nobody should spend a week on it.
**Do.** Boot the stock Anbernic card in slot 1 (FPGA interface unplugged) from
`psu2` with no battery, exactly as now. In its menu choose Normal standby,
press the power key, read the supply for two minutes; wake; repeat with Super
standby; then shut down and read the off current. Repeat later on battery
(B7).
**Read it as.** Stock off ≈ 33 mA confirms our off figure is the board and not
our shutdown path. Stock Super ≪ 105 mA makes PMIC-assisted rail-off the
project to do; stock Normal ≈ 105 mA says our `sr` suspend is already at the
vendor's clock-level floor.

### B4. ROCKNIX's deep sleep on the same supply -- done, 2026-09-20

**Answer.** It did not need a person. Their TF-A patch and SRAM stub were built
from source (`build-firmware --suspend rocknix-deep`) and put on the emulated
card under our own kernel and harness, so only the firmware differed: s2idle
121, 114, 124 mA against **70, 67, 68** in their deep sleep, six wakes of six
with the memory's md5 unchanged, and a six-minute sleep at 72 mA. About 37 mA
below our own self-refresh firmware. The controller, PHY and PLL_DDR0 shutdown
is where most of the clock-level saving is, the next firmware rung is worth
building (or theirs worth adopting), and the gap to powered off is about
35 mA rather than 72. See "Their firmware on the same card" in
[RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md). What follows is the
experiment as it was planned.


**Question.** Does the DRAM controller and PHY shutdown that the published
implementation performs, and ours does not, lower the sleeping current?
**Why it matters.** It is the one clock-level step still unpriced, and the
expert's main objection to our conclusion. Building it ourselves means porting
U-Boot's DRAM initialisation into the SRAM stub. Measuring theirs first prices
it for the cost of flashing a card.
**Do.** Write a ROCKNIX H700 DDR4 nightly from 2026-09-20 or later to a real
card, boot it in slot 1 from `psu2`, set suspend mode to `mem`/deep, let it
idle to the same state each time, press the power key, read the supply for two
minutes. Same with its s2idle mode if it offers one.
**Read it as.** Theirs ≈ 105 mA: the controller/PHY shutdown is worth nothing
here and we stop climbing that ladder. Theirs clearly lower (say ≤ 90 mA): the
next firmware rung is worth building, and `sr-pll` is worth debugging.
Caveat: their image runs a full userspace and different drivers, so compare
suspended currents only, and note what was running.

### B5. Unplug the FPGA card interface while off, and while asleep

**Question.** Is the emulated-card interface electrically neutral, or does a
powered FPGA on the target's pulled-up SD lines feed or load it?
**Why it matters.** It underlies every number we have. The gateware releases
its lines when the host clock stops and the qualified bitstream has no
pull-ups, but that is a design statement, not a measurement.
**Do.** Off first: the harness runs the power-off job with a ten-minute window
and logs the supply; at a noted time unplug the interface at the Pmod, at a
later noted time plug it back. Then the same inside one long `sr` sleep
(`rtc_sleep 300`), replugging at least a minute before the alarm.
**Read it as.** A step at the unplug time is the rig's contribution, and every
figure in the reports shifts by it. No step: the rig is neutral and the
question is closed.

### B6. Rail voltages in awake, sleep and off

**Question.** Which supply outputs are physically present in each state:
DCDC1 (`vdd-cpu`), DCDC2 (`vdd-gpu-sys`), DCDC3 (`vdd-dram`), the LDO outputs,
VSYS, RTCLDO? Does anything that should be off sit at an intermediate voltage?
**Why it matters.** Regulator enable bits are not voltages. This separates
four cases for the 33 mA "off" state: the SoC rails really disappear; a
switched rail stays up; a rail is back-powered through a signal pin; or the
rails are gone and the current is upstream, in the PMIC or something on VSYS.
**Do.** With B2's map, a DMM on each output while the harness holds each state
for five minutes (awake idle, `sr` sleep, off).
**Read it as.** Rails up when "off" → a shutdown-path bug, fixable in software.
Intermediate voltages → back-powering; find the pin. All rails gone and still
33 mA → it is the PMIC/charger path, and only B7 can say what it is on a
battery.

### B7. A battery with a shunt, USB disconnected

**Question.** What does the board draw from its cell, awake, in s2idle, in the
`sr` sleep, and off? How much of the 105 and of the 33 is the USB power path
with no cell attached?
**Why it matters.** It is the number the product cares about, and the expert's
first priority. Our figures cannot be converted: the same 0.525 W would be
about 142 mA at 3.7 V before any change in losses, and removing USB may remove
a load entirely.
**Do.** The correct protected cell through an interposer with a Kelvin shunt
(50 to 100 mΩ; size it for boot peaks, not for sleep), a floating DMM across
it, USB unplugged. Power on by the key. The harness still delivers jobs through
the FPGA card but cannot switch power, so it needs a mode that does not talk to
the supply (software to prepare beforehand, see below). Read voltage and
current in each state. Do not use the PMIC's own `current_now`: upstream marks
it uncalibrated.
**Read it as.** Off on battery in the microamps to low milliamps → the 33 mA is
a USB artefact and power-off-with-alarm is excellent. Sleep on battery far
below 140 mA-equivalent → much of our sleeping figure was the power path too.
Sleep on battery ≈ 140 mA → it is all real and the rail projects are the only
way down.

### B8. RTC wake on battery alone

**Question.** Does the RTC alarm still power the board on, and wake it from the
`sr` sleep, with no USB attached?
**Why it matters.** Power-off with the alarm armed is the best timed sleep we
have (33 mA on USB, maybe far less on battery). On the bench it was proved
with USB present, where the PMIC is never really unpowered.
**Do.** With B7's setup: arm a 120 s alarm, power off, watch for the boot.
Repeat for an `sr` sleep.
**Read it as.** Works → it is a product strategy; measure its break-even
against the `sr` sleep. Fails → the alarm path depends on VBUS and the strategy
is a bench artefact.

### B9. A scope across the shunt during sleep

**Question.** Are the single readings of 166 to 220 mA inside sleep windows
real current bursts, and if so at what period; what is the true mean power?
**Why it matters.** Our medians under-report the mean by 5 to 8 mA and we do
not know why. Periodic bursts would point at something waking (the 2 s I2C
retry, a PMIC mode hop, a refresh burst); no bursts would say the supply's
sampling straddles window edges.
**Do.** Differential probe or floating scope across B7's shunt, a few 40 s
sleeps, then one awake-idle window for scale.
**Read it as.** A period identifies the culprit by its period. A flat trace
means quote means from now on and ignore the outliers.

### B10. A real SD card in slot 1

**Question.** What does a real card add to the sleeping and off currents, and
does cutting its supply in suspend back-power it as slot 2's does?
**Why it matters.** The product boots from a real card; the emulated one draws
nothing from the target, so every figure we have is missing a consumer.
**Do.** Write the `sr` image to a real card (needs the fixed-schedule image
below, because the job harness lives in the FPGA), boot from `psu2`, read the
supply in the scheduled states.
**Read it as.** The difference from the emulated-card figures is the card. If
it is milliamps, the card's supply in suspend becomes a device-tree question
with ROCKNIX's back-powering finding as the warning.

### B11. A shunt in DCDC2's load side, then DCDC3

**Question.** Which rail carries the remaining current: the shared system/GPU
supply, the DRAM supply, or the analog/IO group?
**Why it matters.** It chooses the next project. Current in DCDC2 says the
prize is rail-off standby (PMIC sleep mask, SPL resume). Current in DCDC3 says
it is the DDR PHY and pads. Neither says look upstream.
**Do.** Only after B6 and B7. Break an existing load-side link or lift an
inductor's output leg; never add resistance in a converter's switching node or
feedback path. Compute power per rail from its own voltage.
**Read it as.** The rail with the milliwatts is the project.

### B12. Fit a UART

**Question.** None about power. It answers "where did it hang".
**Why it matters.** The `sr-pll` rung never resumes and its progress code died
with the 5 V. PMIC writes from firmware and an SPL resume path are not
responsible to attempt blind on a board with a cell attached.
**Do.** Find UART0's pads (B2), solder three wires, 115200 8N1 to a 3.3 V
adapter.
**Read it as.** A prerequisite, not a result.

### B13. Charger on and off, battery fitted

**Question.** With a cell fitted and USB attached, what does the charger path
cost at the USB input when it is not charging?
**Why it matters.** Separates "the power path is inefficient" from "the power
path is hunting for a battery that is not there", which is one reading of the
33 mA.
**Do.** B7's cell fitted, USB back on, a full battery; read the USB-side
current awake, asleep and off, and compare with today's battery-less figures.

### B14. Sleep current cold against warm

**Question.** How much of the sleeping current moves with temperature?
**Why it matters.** Leakage rises steeply with temperature and clock power does
not. If a 15 C swing moves the sleeping current by tens of milliamps, the
remaining 72 mA is mostly leakage in powered domains, and only removing rails
will touch it.
**Do.** The harness runs repeated `sr` sleeps while the board is first at room
temperature and then warmed (a closed box over a warm surface, not a heat
gun); the SoC's sensors are logged between sleeps.

## What can be prepared with nobody there

These make the visits above shorter, and are software only.

- **State-holder jobs**: hold awake-idle, `sr` sleep and off for a chosen
  number of minutes with a timestamped supply log, for B5 and B6.
- **A harness mode that does not drive the supply**, for battery operation
  (B7–B9): deliver jobs and read results, leave power to the person.
- **A fixed-schedule image** for a real card (B3's comparison runs, B10): init
  cycles awake, s2idle, `sr`, off on a fixed timetable, signals the state on
  the power LED, and logs to the card for reading back on the Mac.
- **Energy to ready**: integrate the supply over a cold boot and over a resume,
  to turn "33 mA against 105" into a break-even sleep length.

## Firmware questions that need no hands

Listed so they are not mistaken for bench work.

**Answered on 2026-09-20, after B4 priced the rung at 37 mA:**

- ~~The DRAM controller and PHY shutdown as its own rung.~~ Done, ours:
  `--suspend sr-phy`, a C stub in SRAM A1 compiled against U-Boot's H616 DRAM
  driver, which rebuilds the controller and the PHY on resume. **29 mA below
  `sr`, and within three of theirs on a six-minute sleep.**
- ~~Progress markers and a watchdog armed across the wait, to find where
  `sr-pll` dies.~~ Done: job 31 asks the stub, through an RTC register, to keep
  the watchdog armed across a ten-second wait, so a hang becomes a warm reset
  and the next boot reads the stage code. It was not needed -- the rung worked
  first time -- but it is the thing that would have been needed if it had not.
- ~~The vendor's 32 kHz CPU/APB step (`--suspend wfi32`, built, never run).~~
  Run: 6 to 7 mA for the CPU alone, and the APB half of it is priced by
  `sr-phy-fastapb`.
- **Which PLLs are running while the board is asleep.** Answered by the stub's
  own snapshot, taken at the instruction before WFI: `PLL_PERI0`, `PLL_VIDEO0`,
  `PLL_DE` and the DE bus clock, and nothing else. `--suspend sr-phy-nodisp`
  stops the last three, reads about eight milliamps lower, and is not kept --
  one of its first three sleeps failed its PHY rebuild at read calibration and
  warm-reset the board. **Retrying it with the display PLLs restarted *after*
  the DRAM rebuild rather than before it is one line, needs no hands, and is
  the single highest-value thing left on this list**: if it holds, it closes
  the whole remaining gap to the published implementation without writing a
  supply.

**Still open, and none of them needs hands:**

- The PRCM register at `+0x244`, written by the prior art with a key of `0xa7`
  to take a PLL LDO down. It is the likeliest remaining difference between
  their 68 mA and our 75, and it is a supply rather than a clock, so it is
  outside what this work writes. It needs a decision, not a bench visit.
- The DRAM pad hold at RTC + 0x1F4. `--suspend sr-phy-padhold` is built and
  unrun; not making the write costs nothing in correctness, and whether it
  costs current is unmeasured. The manual's polarity and the prior art's
  disagree and VDD_SYS never goes off here, so the experiment answers less than
  it looks like it does.
- `opp-suspend` in the device tree in place of the userspace governor.
- A read-only PMIC transaction from the SRAM stub at suspend entry and exit,
  all rails kept: the first proof that firmware can talk to the AXP717 before
  anything asks it to change a rail. Gated on B7 and on a decision.
- A retention qualification: full-memory integrity rather than a 256 MiB
  probe, sleeps of an hour, and temperature.

**Where the remaining gap probably is.** A sleeping board now draws about
75 mA and a powered-off one 33, so 42 mA is unaccounted for. Almost none of it
can be a clock: every PLL that can be stopped has been, the CPU and both APBs
are on 32 kHz, and the whole DRAM clock path is in reset -- and the one PLL
whose stopping was expected to matter, PLL_DDR0, measured nothing. What is left
is `vdd-dram` holding a gigabyte in self-refresh, the other core rails at full
voltage, and the AXP717's own conversion and charger path with no cell on it.
That last is the one worth suspecting first: 33 mA for a board that is off is a
lot, and B1, B2 and B5 are the experiments that would say.

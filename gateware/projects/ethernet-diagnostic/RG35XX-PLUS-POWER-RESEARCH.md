# RG35XX Plus: the research behind the sleep work

What is known about power on this SoC that did not come off our own bench: what
the public documents say, what the prior art built and measured, why a kernel
patch cannot do this job, what an outside expert made of the work, and where
the current that is left probably is. It is the background to
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md), which holds every measurement,
and to [RG35XX-PLUS-DEEP-SLEEP.md](RG35XX-PLUS-DEEP-SLEEP.md), which is the
suspend firmware. What needs a person at the bench is
[RG35XX-PLUS-BENCH-EXPERIMENTS.md](RG35XX-PLUS-BENCH-EXPERIMENTS.md).

Nothing here is a measurement of ours. Where a document or another project is
being reported, it is named; where something is inferred from it, that is said.

## What the public documents say

There is no public H700 register manual. The H700 is the H616 die in a package
that brings out the LCD pins, so the H616 datasheet and user manual
(linux-sunxi.org) were read instead.

- **The datasheet has no power figures at all.** Its power-consumption section
  is one sentence: contact Allwinner FAE. There is no sleep current to compare
  anything with, which is why this work had to measure its own.
- **The datasheet's own picture of sleep keeps every rail up.** Its
  power-sequence figure (5-42) has Power-on, Sleep and Wakeup columns, and in it
  VCC_DRAM, the 1.8 V group, VCC_IO and VDD_SYS/CPU/GPU/HDMI at 0.9 V all stay
  up through Sleep, and so does the 24 MHz clock. So the sleep the datasheet
  describes is a clock-level one. (An earlier reading of this figure from
  extracted text, as showing the core rails dropping, was wrong; the rendered
  page settles it.)
- **The user manual documents per-core power switches and an L2 idle mode** in
  the CPUX configuration block -- levers a firmware could use, and which this
  work did not need once offlining cores had measured nothing.
- **It documents a Super Standby the boot ROM knows about.** There are Super
  Standby flag and software-entry registers in the RTC at `0x070001F8` and
  `0x070001FC` that a boot ROM path uses to resume a retained session. Those are
  flags, not evidence of electrical retention.
- **It documents the DRAM pad hold.** 3.13.6.17, `VDDOFF_GATING_SOF_REG` at
  RTC + 0x1F4, bit 0 `DRAM_CH_PAD_HOLD`, "1: hold dram pad", to be set before
  VDD_SYS is powered off and cleared after it comes back. That is the opposite
  sense to the write the prior art makes, which is why our firmware leaves the
  register alone.
- **The PRCM is undocumented.** It is in the memory map at `0x07010000` and its
  registers are not described anywhere public. The PLL LDO gate the prior art
  writes at `+0x244` with a key of `0xa7` is in that block, which is why our
  firmware does not write it.

## Prior art: kailashrs' H700 suspend for ROCKNIX

kailashrs implemented PSCI `SYSTEM_SUSPEND` for the H616/H700
([H700_rocknix_enhancement](https://github.com/kailashrs/H700_rocknix_enhancement)):
TF-A hands control to a program in SRAM that puts the LPDDR4 into self-refresh,
stops the DRAM controller, its PHY and the CPU PLL, and waits. ROCKNIX merged it
as [PR #3316](https://github.com/ROCKNIX/distribution/pull/3316) on 2026-09-19,
packaged from
[h700-suspend-stub](https://github.com/Jacob-Matthew-Cook/h700-suspend-stub).
The design, the choice of PSCI hooks and the return through TF-A's warm boot
entry are theirs, and our firmware credits them throughout.

- **What they report**: dozens of cycles, RTC and power-key wake, and **about
  3 %/h of battery in deep sleep**. They publish no current and no s2idle drain,
  so the figure cannot be compared with anything measured at a USB-C input, and
  it does not say what the same board draws awake or in the state it replaces.
  That is why the only useful comparison was to build their firmware from source
  and measure it on this bench, which is `--suspend rocknix-deep` and
  [RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md)'s 68 mA.
- **Three further peripheral-gating kernel patches measured no change** at that
  level on their own bench: 2.7 and 3.3 %/h against 3.05. Our experiment 13,
  which unbound twenty-five devices at once for nothing, is the same result by
  another road.
- **They say what their port does not do.** Their own notes say it "does not
  change PMIC rail voltages" and that it is not the stock firmware's deeper
  standby.
- **Their static analysis of the OEM firmware** (`docs/OEM_STANDBY.md`)
  distinguishes the stock Normal standby from its Super standby: by their
  reading the deeper one writes a CPU/SYS/IO rail mask to the PMIC and resumes
  through boot0 with the DRAM retained. That is the shape of the project nobody
  has built openly, and it is why the AXP717's sleep/wake machinery appears in
  the candidate projects below.
- **Their back-powering finding** is a warning for our bench as much as for
  their product: on the second card slot they found the target fed through
  signal pull-ups from the always-on `vcc-io` when the slot's supply was cut,
  and fixed it by keeping the supply on. That is why bench experiment B5 exists.

## Why a kernel patch cannot do it

The kernel runs from the DRAM, so it cannot put the DRAM into self-refresh:
that needs code running from on-chip SRAM, entered through the firmware. The
kernel's other levers were tried and measured: offlining cores goes through
PSCI CPU_OFF and measured nothing (124 against 127 mA), unbinding drivers
measured nothing, and the one CPU lever that does pay is the operating point,
which is the `powersave` governor already kept. Nothing in `/sys/power` can
reach a state the firmware does not implement, and with the shipped firmware
`/sys/power/mem_sleep` offers `[s2idle]` alone.

There is one kernel-side item still worth doing and it is a device-tree change
rather than a patch: `opp-suspend`, which encodes the suspend operating point in
the device tree instead of relying on a userspace governor to have been set, as
ROCKNIX did.

## The outside review, point by point

The brief in [RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md](RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md)
went to a power expert on 2026-09-20, when the best sleep was 105 mA. This is
their assessment condensed to its technical content, with where each point
stands now. "Done" means measured on this bench; "open" means nobody has.

**Their summary.** The measurements are credible but do not show the retention
floor has been reached; they show that the accessible clock and driver changes
offer little in the present power configuration. Next: a battery-only
electrical baseline, find which physical rails carry the remaining power, and
treat controller/PHY shutdown and CPU/system rail shutdown as two separate
projects.

| # | their point | status |
| --- | --- | --- |
| 1 | 0.5 W with every rail up is plausible; "clocks, PLLs, idle cores and DRAM activity are not where the current is" claims too much. Self-refresh is not the same as powering down the controller and PHY, which the published implementation does and ours did not. | **Done, and they were right.** Their firmware on our card: 68 mA. Ours with the controller and PHY shut down and rebuilt (`sr-phy`): 76 mA. The step was worth about 29 mA. |
| 2 | The `powersave` result changes voltage and frequency together, so it does not partition the saving into leakage, switching and conversion loss. | Open. The OPP table ties the two; separating them needs a device-tree OPP at 480 MHz and 1.1 V. |
| 3 | First rail to measure: DCDC2, `vdd-gpu-sys`, shared by the system and the GPU and always on, so unbinding panfrost does not power that domain down. Then the DRAM supply group, then analog and I/O. A prioritisation, not a diagnosis. | Open; needs hands (bench list B6, B11). |
| 4 | No numerical floor can be promised. For a genuinely CPU/system-off design the target is tens of milliwatts. The honest budget is the DRAM's self-refresh current on each of its supplies, plus always-on, plus pad retention, plus conversion, which needs the actual memory part. | Open; needs the DRAM part number (B2). |
| 5 | 33 mA "off" is credible for this setup and not the board's intrinsic off current. The AXP717 datasheet gives 35 uA typical with VBUS absent, BATFET off and RTCLDO on, which is not our condition. Measure the supply outputs with a meter in awake, sleep and off before any shunt; test whether the FPGA card interface back-powers the target (the ROCKNIX work found exactly that on the second card slot, from pull-ups on the always-on `vcc-io`); then a battery interposer with a shunt, USB disconnected. | Open; needs hands (B5, B6, B7). Deferred by the owner: keep measuring at USB-C for now. |
| 6 | Do not use the PMIC's `current_now`: upstream marks its offset unknown. Battery percentage is a weak proxy. USB and battery milliamps are not comparable: 525 mW is about 142 mA at 3.7 V before losses change. | Noted; nothing here uses either. |
| 7 | Try disabling charging through the battery driver (upstream clears `AXP717_CHRG_ENABLE` in `MODULE_EN_CONTROL_2`), not by unbinding it. | **Checked:** this kernel's battery supply reports `present=0`, `Not charging`, and exposes no charge-enable attribute. Needs a driver change or a fitted cell. |
| 8 | ALDO3 is labelled unused upstream and is a fair candidate once the cleanup race is removed. DCDC4 is different: on an AXP717 configured as a charger it is not an independent output, and the regulator framework's 1.0 V entry is a descriptor, not a rail. | **Done:** experiment 27, ALDO3 really off, worth nothing. DCDC4 left alone. |
| 9 | With the SRAM/WFI architecture the executing CPU's supply and the shared system supply cannot be removed. Keep DCDC1 at the low OPP, DCDC2, DCDC3, BLDO2 `vcc-pll`, ALDO4 `avcc` (it also feeds GPIO bank G and the Wi-Fi I/O, so it is not audio-only) and CPUSLDO (the board file says its function is uncertain and that disabling it made GPIO reads inconsistent in the bootloader). Dedicated peripheral supplies are fair game if their pins are put in a safe state first. | Stands. Nothing here removes a rail. |
| 10 | Real rail-off standby is reset-based: quiesce and enter confirmed self-refresh with valid pad retention; arm a hardware wake and run the PMIC sequence; on wake detect a retention marker in early SPL before any destructive DRAM initialisation; rebuild the memory interface without resetting the memory, restore what training overwrote, re-enter TF-A's warm path. The hazards are SPL's memory tests, sizing probes, training writes, and loading images over retained state, with BL31 at `0x40000000`. No proprietary boot0 is required. | Open; the largest remaining project. The stub's PHY rebuild is the hard half of step 4, already working from SRAM. |
| 11 | Pad hold: the published stub writes RTC+0x1F4 bit 0 and its own pull request lists the write as ungrounded; the standby flag registers at 0x1F8/0x1FC are not proof of electrical retention; resumes with all rails up do not prove the hold survives rail removal. Repeat the RTC wake on battery, and establish the RTC's clock source before stopping the 24 MHz oscillator. | Partly done: the H616 manual documents the register (`DRAM_CH_PAD_HOLD`, 1 = hold, "set before VDD_SYS power off"), which is the opposite sense to the published write. `sr-phy` never touches it and resumes. Untestable while VDD_SYS stays up. |
| 12 | "I2C bus locked" is a transfer timeout in `mv64xxx`, not a measured stuck bus: an ordering bug. For PMIC access from firmware: Linux prepares policy while its adapter works; the stub does only the final transaction with a private polled R-I2C, explicit ownership handoff, bounded polling, everything it needs out of DRAM. First test a read-only transaction with all rails kept. | Open, and gated on a decision: nothing here writes the PMIC. |
| 13 | The AXP717 has the feature: sleep/wake control at `0x25`, auto-sleep masks at `0x28` to `0x2a`; sleep captures the output enables and wake restores them. The OEM mask bytes `03 40 00` select DCDC1, DCDC2 and CLDO3, consistent with CPU, system/GPU and main I/O. Do not copy the OEM's `0x2d`/`0x6d` writes to `0x25`: they set bit 3, which the public register table marks reserved. Power-key and RTC wake must be shown to restore switched-off supplies. Green mode (keeps CPUSLDO, DCDC3, BLDO2, RTCLDO at 10, 10, 5, 5 mA limits) is not the next experiment. | Open; this is the map for the rail-off project. |
| 14 | The failed PLL-off rung: add persistent progress markers at each step, bound every poll, record the failing register, make sure the watchdog really covers the interval; a missing reset does not distinguish "never woke" from "watchdog unavailable". The published stub preserves 320 bytes at the DRAM base and 320 at half the memory, because training may overwrite them. | **Done** in the `sr-phy` work: markers, a watchdog across short debug sleeps, and the one failure since (`sr-phy-nodisp`) named its own failing stage. |
| 15 | A 256 MiB checksum does not cover the memory map; qualify retention across the whole memory, long sleeps and temperature. Six minutes is a milestone, not a qualification. | Open; hands-off. |
| 16 | No cpuidle driver does not mean busy-spinning: arm64's default idle is WFI. Offlining cores measuring nothing makes per-core idle states unlikely to pay; last-core and cluster idle is a separate firmware project. Encode the suspend OPP in the device tree (`opp-suspend`, as ROCKNIX did) instead of relying on a userspace governor. | Open; `opp-suspend` is a small device-tree change. |
| 17 | The per-cycle drift: separate elapsed time from the number of transitions; add a run with the same awake work and no suspend; use balanced ABBA and BAAB groups; treat whole cycles or boots as the experimental unit. | **Done:** no climb inside the six-minute sleep (104, 102, 107 by thirds), none in experiment 28's awake control; it goes with the transitions. Balanced BAAB groups not yet used. |
| 18 | A median of sparse readings is not average current; use mean power for energy comparisons and a scope across a shunt to see whether there are bursts. | Half done: means run 5 to 8 mA above medians and are now reported beside them. The scope needs hands (B9). |
| 19 | Power-off with the alarm stays useful. The break-even sleep length is the extra energy of a shutdown and cold boot over a suspend and resume, divided by the difference in sleeping power, measured to the actual ready state. | Open; hands-off. The difference was 0.36 W against the 105 mA sleep and is about 0.22 W against `sr-phy`. |

**Their order of work**, and where it stands: remove the known confounders
(done); one productive bench visit for battery power, rail voltages and the
FPGA interface (deferred by the owner); instrument DCDC2 (needs hands);
controller and PHY shutdown as its own rung (**done**); PMIC-assisted rail-off
with early-SPL recovery, only with a mapped retention supply set and a proven
wake path (open, and the route most likely to change the power class).

### What the review changed, and what it did not

Their main correction was to the conclusion and not to the measurements, and it
is applied throughout the reports: **what the experiments show is that the
particular CPU-clock, core-offline, peripheral-unbind and DRAM-clock-gating
changes tried do not explain most of the input power** -- not that a floor has
been reached, and not that none of the current is in a clock. The reports were
softened to say that before the objection was tested. Then it was tested, and
the step they named as the one clock-level change still unpriced turned out to
be worth 29 mA, which is more than everything else in the work except the
governor. The shape of the correction is the lasting part: a clock-level change
that has not been tried is not a clock-level change that is worth nothing.

**Four of their points could be answered the same day with nobody at the
bench**, and that is where experiments 27 and 28 came from; the readings are in
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md) and only the conclusions are here.
Every figure this work had quoted was taken with `aldo3` still enabled, because
the kernel's one attempt to disable unused regulators happens at 32 s of uptime
and the harness had always been asleep at that moment; experiment 27 simply
stays awake for it, the rail really does go off, and it is worth nothing --
which is the good outcome, because it means none of the earlier figures needs
an asterisk. The same job settles DCDC4 (left alone: on a charger-configured
AXP717 it is not an independent output) and charging (no charge-enable
attribute in this kernel). Experiment 28 removes the last innocent explanation
for the 1.5 mA per cycle drift by running the alternations' awake work six times
in one boot with no suspend at all: the drift is not time asleep and not the
awake work, so what is left is the suspend and resume transitions themselves,
and nothing has measured a transition. And the recomputation of means beside
medians is now part of how every figure is reported. The one hands-off question
that stayed open is whether the FPGA card interface is electrically neutral,
which only a physical disconnect settles (B5).

## Where the remaining current probably is

A sleeping board draws about 76 mA and a powered-off one 33, so about 43 mA is
unaccounted for, and about 35 mA if the published implementation's 68 is taken
as the target. The hypotheses, in the order the evidence supports them:

1. **The AXP717's own conversion and charger path, with no cell on it.** 33 mA
   for a board that is off is a lot, the expert's reading is that it is not the
   board's intrinsic off current, and a battery-less charger path hunting for a
   cell would show up in exactly this way. Evidence needed: B5 (the FPGA
   interface unplugged), B6 (rail voltages in each state), B7 (a battery with a
   shunt, USB disconnected), B13 (the charger with a cell fitted).
2. **`vdd-dram`, holding a gigabyte that is refreshing itself.** This is the
   floor for any sleep that keeps its memory, and it cannot be removed by
   anything short of not keeping the memory. Evidence needed: the DRAM part
   number and its IDD6 (B2), then a shunt in DCDC3 (B11).
3. **The other core rails at full voltage** -- `vdd-gpu-sys`, `vcc-pll`,
   `vcc-io`, `avcc`, `cpusldo`, `vcc-spkr-amp`. DCDC2, shared by the system and
   the GPU, is the expert's first candidate and the one the sysfs experiments
   could never touch, because unbinding panfrost does not power that domain
   down. Evidence needed: B11.
4. **Leakage rather than any of the above.** Leakage rises steeply with
   temperature and clock power does not, so a cold-against-warm sleep (B14)
   would separate them, and experiment 28 has already shown that a 2 C warming
   over six windows does not move the awake current measurably.
5. **Three clocks, and only three.** The stub's snapshot says `PLL_VIDEO0`,
   `PLL_DE` and the DE bus clock are still running while the board sleeps.
   Stopping them is worth about eight milliamps and currently costs the
   reliability of the DRAM rebuild, which is the first candidate project below.

## Two candidate projects

Both are firmware. They are independent, and the expert's advice was to treat
them as separate projects rather than as two more rungs of one ladder.

### Finish the clock-level work

**What.** Restart `PLL_VIDEO0` and `PLL_DE` and re-enable the DE bus gate
**after** the DRAM rebuild rather than before it, which is one line in the
stub's resume path, and then re-run the `sr-phy-nodisp` alternation. If the
rebuild is reliable with the display PLLs left off across the wait, this is
about eight milliamps and closes most of the remaining gap to the published
implementation without writing a supply. After that, the PRCM PLL LDO at
`+0x244`: theirs writes it, ours does not, and it is the likeliest remaining
difference between their 68 and our 76.

**Evidence it would need.** For the display half: ten consecutive cycles and a
six-minute sleep with no rebuild failure, plus the marker channel clean, before
any current is believed -- one failure in three is what disqualified it the
first time. For the PRCM half: a ground for the write. It is in the one block
the manual does not document and the prior art's own comment marks it inferred;
either a document, or a datasheet for the LDO it gates, or a decision to accept
an inferred supply write. Nothing in this work has written a supply, and that
rule is worth breaking only deliberately.

**Risk.** Low for the reordering (the worst case is another reset that leaves
its stage code), open for the PRCM write (a supply that does not come back is a
board that does not come back, and the only recovery on this bench is a power
cycle and another deploy).

### PMIC-assisted rail-off with an SPL resume

**What.** The project the expert describes in point 10 and maps in point 13,
and the one the stock firmware's Super standby appears to implement by the prior
art's analysis: quiesce and enter confirmed self-refresh with valid pad
retention; arm a hardware wake; run the AXP717's sleep sequence so that the
CPU, system and I/O rails go off; on wake, detect a retention marker in early
SPL before any destructive DRAM initialisation; rebuild the memory interface
without resetting the memory; restore what training overwrote; re-enter TF-A's
warm path. This is the only route that changes the power class rather than the
number.

**What is already in hand.** The hard half of the rebuild works and works from
SRAM: `sr-phy` shuts the controller and PHY down and builds them again with
U-Boot's driver, saves and restores what training writes over, and has eighteen
proved sleeps behind it. The AXP717's registers are mapped in the review's point
13. The wake path exists in one form already: the RTC alarm powers a
fully-powered-off board back on, twice out of twice.

**Evidence it would need, before anything is written.** A mapped retention
supply set, which means B2 (read the chips) and B6 (rail voltages in each
state). A proven wake path on the actual retention configuration, which means
B7 and B8 on a battery. A demonstration that the pad hold does what it is
supposed to when VDD_SYS actually goes away, which cannot be shown while it
stays up. A read-only PMIC transaction from the stub first, with every rail
kept, to prove that firmware can talk to the AXP717 at all at that point in the
suspend. And a UART (B12), because a board that does not come back from a rail
that did not come back leaves nothing at all.

**Risk.** The highest in this work, and it should not be attempted without a
battery fitted, a serial console, and a decision taken deliberately. Do not copy
the OEM's `0x2d`/`0x6d` writes to `0x25`: they set bit 3, which the public
register table marks reserved.

## Sources

- H616 Datasheet V1.0 and H616 User Manual V1.0, linux-sunxi.org
- <https://github.com/ROCKNIX/distribution/pull/3316> (merged 2026-09-19)
- <https://github.com/kailashrs/H700_rocknix_enhancement> (`docs/DESIGN.md`,
  `docs/OEM_STANDBY.md`)
- <https://github.com/Jacob-Matthew-Cook/h700-suspend-stub>
- The AXP717 register descriptions and the upstream `axp20x` regulator and
  battery drivers, as cited by the outside review above
- [RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md](RG35XX-PLUS-SLEEP-EXPERT-BRIEF.md), the
  brief as it was sent on 2026-09-20

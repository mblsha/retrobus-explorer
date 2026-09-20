# Request for advice: sleep current of an Allwinner H700 handheld (Anbernic RG35XX Plus)

> **This is the brief as it was sent, on 2026-09-20, and it is not updated.**
> It is kept as a dated snapshot of what was known and claimed at that moment.
> The expert's assessment, point by point, and what was checked after it are in
> [RG35XX-PLUS-POWER-RESEARCH.md](RG35XX-PLUS-POWER-RESEARCH.md); the current
> results are [RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md), where the best sleep
> is now 76 mA rather than the 105 quoted below. Two statements here were
> corrected there: the conclusion in section 6 that "clocks, PLLs, idle cores
> and DRAM activity are not where the current is" claims more than the
> experiments show -- shutting the DRAM controller and PHY down was later worth
> 29 mA -- and `dcdc4` is treated here as a rail when on a charger-configured
> AXP717 it is not an independent output.

Self-contained brief, 2026-09-20. We are trying to get the suspend current of
this board down, have run out of things that software at the clock level can
do, and would like an expert's view on where the remaining current is and what
is safe to try next.

## 1. Goal

A **timed sleep**: the device suspends by itself and wakes on an RTC alarm (and
ideally the power key), keeping its session in RAM, drawing as little as
possible. Secondary goal: lower awake-idle power. The eventual product boots
from a real SD card; boot-time and correctness work is done, power is what is
left.

Where we are: **about 105 mA at the 5 V input while suspended** (≈0.52 W),
down from about 124 mA. The same board **powered off draws 33 mA** on the same
input. We would like to understand the ~72 mA in between and the 33 mA itself.

## 2. Hardware and software

- **Board:** Anbernic RG35XX Plus. **SoC:** Allwinner H700 (the H616 die in a
  package with LCD pins): 4× Cortex-A53, Mali-G31. No management core (no
  AR100/SCP) as far as we know.
- **DRAM:** 1 GiB LPDDR4, DesignWare-uMCTL2-style controller with Allwinner's
  PHY, PLL_DDR0 = 1344 MHz (672 MHz clock), as initialised by mainline U-Boot's
  `dram_sun50i_h616.c`.
- **PMIC:** X-Powers AXP717 on I2C. **No battery is fitted**; the board is
  powered through its USB-C port from a bench supply at 5.00 V.
- Wi-Fi/BT RTL8821CS on SDIO (no firmware loaded, no driver bound), a second
  SD slot holding a real card, 640×480 LCD with PWM backlight, audio codec +
  speaker amp, HDMI, USB (musb + EHCI/OHCI), gpio LEDs, ADC joypad.
- **Firmware:** built by us from source: mainline U-Boot v2026.01 (ROCKNIX's
  H700 LPDDR4 defconfig + one DRAM-driver patch) and TF-A v2.12.0
  `sun50i_h616` (native PSCI, BL31 runs from DRAM at 0x40000000), plus our two
  TF-A patches described below.
- **Kernel:** mainline Linux 7.2 with ROCKNIX's H700 patch set, trimmed config.
  `CONFIG_SUSPEND`, sun6i RTC, cpufreq-dt present; **no cpuidle driver and no
  `idle-states` in the device tree**; `DEBUG_FS`/`PM_DEBUG` off. Device tree
  says `arm,psci-0.2`.
- **Userspace:** a BusyBox init of our own, nothing else running. Root
  filesystem is EROFS on the SD card in slot 1.
- **Test rig:** slot 1's "SD card" is an FPGA emulating a card (6 MHz clock).
  It draws nothing from the target, so a real card's standby current is not in
  our figures. There is **no serial console**; the target reports through a raw
  partition on the emulated card and the FPGA traces card activity.

## 3. How we measure (and its limits)

- Current is read from the bench supply at the USB-C input: 1 mA resolution,
  one reading every ~2.5 s, so averages only, no transients.
- A figure is the median of readings wholly inside a state, first 3 s
  discarded, 40–45 s dwell (one 6-minute run), with range/IQR/count.
- Noise: two cold boots of the same state differ by ~7 mA; within one boot two
  identical sleeps differ by ~3 mA, and **the sleeping current climbs ~1.5 mA
  per sleep cycle through a boot** (six identical sleeps: 121, 125, 125, 128,
  126, 129 mA) for a reason we have not identified. So comparisons alternate
  the two configurations inside one boot (A B B A A B) and we do not believe a
  difference under ~8 mA.
- A wake only counts if the RTC says the sleep lasted what was asked,
  `suspend_stats/success` rose with `fail` unchanged, and a card write +
  read-back passes; for firmware suspends also an md5 of a 256 MiB random file
  in tmpfs checked across the suspend.
- **Big caveat:** everything includes the AXP717's conversion losses and its
  charger path with no cell attached. These are not battery-side numbers.

## 4. Baselines (5.00 V input, no battery)

| state | current |
| --- | --- |
| supply output off | 1 mA |
| powered off (`poweroff -f`), USB still attached | **33 mA** (33–35, very steady) |
| suspended, s2idle, as shipped (`performance` governor, 1416 MHz) | 121–126 mA |
| awake idle, panel asleep | 144–151 mA (139 with `powersave`) |
| awake idle, panel lit at kernel default backlight | 176–183 mA |
| awake idle, backlight full | 246–252 mA |

Powered off, an RTC alarm **does** power the board back on (2 of 2, within 1 s
of a 60 s alarm); with no alarm it stays off. Cold boot is ~5 s to first SD
command.

## 5. What we tried

### 5.1 From Linux userspace/sysfs (17 experiments, s2idle)

**Worked**
- `powersave` cpufreq governor before suspending (480 MHz; the OPP table takes
  `vdd-cpu` 1.10 → 0.90 V): **−9 to −11 mA**, reproduced three times
  (126 → 115 mA). Also ~−8 mA awake.

**Did not work (no change above noise)**
- Offlining CPUs 1–3 (PSCI CPU_OFF works and survives suspend): 124 vs 127 mA.
- Unbinding the Wi-Fi SDIO controller and the second SD slot's controller
  (their regulators `vcc-wifi` and `vcc3v3-mmc2` do switch off): ~1 mA.
- Unbinding GPU (panfrost), audio codec, HDMI audio.
- Unbinding the PMIC's ADC/battery/USB-power drivers and the SoC ADC, LEDs off
  (I2C interrupts during a 40 s suspend fall from ~270 to ~128; current
  unchanged).
- Unbinding the whole display pipeline (DRM master first, then panel, TCONs,
  mixers, HDMI + PHY, DE2 bus, backlight PWM).
- **Unbinding 25 devices at once** on top of `powersave`: 112 → ~110 mA.
- `freeze` vs `mem`: same state.

**Broke things**
- Unbinding the panel driver while the DRM master still holds it: the target
  never wakes (ordering problem; harmless if the DRM master goes first).

**Observed but not fixable from sysfs**
- Regulators still enabled while suspended: `vcc-pll` 1.8 V, `avcc` 1.8 V,
  `vcc-io` 3.3 V, `vcc-spkr-amp` 3.3 V, `cpusldo` 0.9 V, `vdd-cpu` 0.9 V,
  `vdd-gpu-sys` 0.9 V, `vdd-dram` 1.1 V, and **`aldo3` 1.8 V and `dcdc4` 1.0 V
  enabled with zero users**.
- The kernel's one attempt to disable unused regulators (at 32 s uptime) fails
  if the board is suspended then: `mv64xxx: I2C bus locked`, `aldo3: couldn't
  disable: -ETIMEDOUT`, repeated every 2 s until wake, never retried. The
  PMIC's I2C bus appears unusable for the whole of a suspend.
- PLLs enabled while awake-idle: PLL_CPUX, PLL_DDR0, PLL_PERI0, PLL_VIDEO0,
  PLL_DE (others off). We cannot read them while suspended.

### 5.2 Our own firmware suspend (PSCI SYSTEM_SUSPEND), built from source

Mainline TF-A has no SYSTEM_SUSPEND for the H616, so `mem` could only be
s2idle. Following the design of kailashrs' H700 work (merged into ROCKNIX as
PR #3316 on 2026-09-19; they report ~3 %/h battery drain in deep sleep and
publish no current figures), we wrote a minimal implementation of our own. No
PMIC, I2C or rail access anywhere in it.

| rung | what it does at EL3 | suspended current | vs s2idle (same boot) | resumes |
| --- | --- | --- | --- | --- |
| `wfi` | CPU clock PLL_CPUX → 24 MHz osc, PLL_CPUX stopped, WFI, relock, warm-entry resume. DRAM untouched. | ~113 mA | −3 to −4 mA (noise) | 17/17 + 3/3 |
| `sr` | the above from a 4 KiB assembly stub in SRAM A1, plus LPDDR4 software self-refresh via the controller (`PWRCTL.selfref_sw`, wait on `STAT`) | **~105 mA** | **−11.6, −4.7, −10.3 mA (≈ −9 pooled)** | 16/16 + 6/6, md5 intact every time, incl. one 6-minute sleep |
| `sr-gate` | + gate DRAM bus clock and MBUS (CCU gates; PLL_DDR0 still locked) | ~101 mA | ≈ −3 more (below noise) | 4/4 |
| `sr-pll` | + stop PLL_DDR0, relock on wake | — | — | **never resumes (2/2)**; no watchdog reset, so it hangs in the wait or the relock; we suspect the Allwinner DDR PHY needs re-initialising once its clock stops |

`/sys/power/mem_sleep` becomes `s2idle [deep]` with no kernel change; wake IRQ
is 136 (R_Alarm0) every time. 24 MHz oscillator and PLL_PERI0 stay on. We did
not try the vendor step of moving CPU/APB to the 32 kHz clock, nor the PRCM
"PLL LDO" write at PRCM+0x244 that the prior art marks as inferred.

### 5.3 Reading the public documents

No public H700 manual; we used the H616 datasheet and user manual. The
datasheet gives no power figures ("contact Allwinner FAE"); its power-sequence
figure shows **every rail and the 24 MHz clock staying up through "Sleep"**.
The manual documents per-core power switches, an L2 idle mode, and Super
Standby flag / software-entry registers in the RTC (0x070001F8/0x070001FC);
the PRCM (0x07010000) is undocumented. By the prior art's static analysis, the
stock (BSP) firmware's deepest standby writes a CPU/SYS/IO rail mask to the
PMIC and resumes through boot0 with DRAM retained; nobody has done that in open
source and we have not attempted it.

## 6. Summary

- Total gain: ~124 → ~105 mA suspended (−15 %). Half from one cpufreq knob,
  half from DRAM self-refresh in our firmware. Stopping the CPU PLL, gating
  DRAM clocks, offlining cores and unbinding essentially every peripheral are
  each worth ≤ 3–4 mA.
- Conclusion so far: clocks, PLLs, idle cores and DRAM activity are not where
  the current is. ~72 mA remains between suspended and powered off, all rails
  are still up at full voltage, and we have deliberately **not written the
  PMIC** from firmware on a battery-less board.
- For long sleeps, power-off + RTC alarm (33 mA, cold boot) beats every suspend
  we have.

## 7. Questions for you

1. **Is ~0.5 W plausible** for an H616-class SoC with all rails up, CPU PLL
   off, LPDDR4 in self-refresh — or does it point to something specific
   leaking (DDR PHY pads/ODT/VREF, HDMI PHY, USB PHY, audio analog on `avcc`,
   GPU domain, floating IO pads, the 24 MHz DCXO, PLL_PERI0)? What floor would
   you expect with rails up, and with core rails off?
2. **Is 33 mA "off" credible**, or is it mostly the AXP717's charger/power-path
   with no battery attached? How would you expect battery-side numbers to
   relate to our USB-side ones, and what is the cheapest trustworthy way to
   measure (series shunt at the cell, per-rail shunts, the PMIC's gauge)?
3. **Which rails can be dropped in suspend on an H616 + AXP717 design** with
   DRAM retained (`vdd-cpu`, `vdd-gpu-sys`/`vdd-sys`, `vcc-pll`, `avcc`…), in
   what sequence, and what holds the DDR pads (CKE/reset) and wake logic while
   they are off? Is there a pad-hold / RTC-domain mechanism on this die beyond
   the documented Super Standby flag registers? Can it be done without the BSP
   boot0, e.g. resuming through mainline SPL?
4. **Doing PMIC writes from EL3**: with the kernel's I2C controller suspended
   and the bus apparently locked during suspend, what is the sane way to talk
   to the AXP717 at suspend entry/exit (own polled I2C in the SRAM stub? AXP717
   sleep/wake-sequenced register sets so that one write arms a hardware
   sequence)? Any AXP717 features meant for exactly this?
5. **DDR PHY low-power states**: with LPDDR4 in self-refresh, what should be
   done to the H616 PHY (DLL off, pad power-down, ODT/VREF off, IO retention)
   and is any of it possible without full re-initialisation/re-training on
   resume? Is that the likely reason stopping PLL_DDR0 never resumes?
6. `aldo3` (1.8 V) and `dcdc4` (1.0 V) are on with no consumers in the device
   tree. Any idea what they feed on this family of boards, and whether they are
   safe to turn off?
7. **Awake idle is 139–151 mA with no cpuidle.** Would PSCI CPU_SUSPEND idle
   states (core power-gating via the CPUX power switches) be worth implementing
   on the H616 given that offlining three cores measured nothing?
8. The **+1.5 mA per suspend cycle drift** within a boot — thermal, leakage, a
   regulator mode, or a measurement artefact of the supply?
9. Anything in the approach that looks wrong, or a cheaper experiment that
   would localise the 72 mA (e.g. which rail to put a shunt on first)?

## 8. Constraints

- We can rebuild firmware (U-Boot SPL, TF-A, our SRAM stub), kernel and device
  tree freely and test unattended; a bad firmware cannot brick the device (it
  lives on the emulated card).
- No serial console at present; debugging is by RTC scratch registers read
  after a watchdog reset, the FPGA's trace of SD activity, and supply current.
- Hardware changes (fitting a battery, shunts, a UART) are possible but need a
  person at the bench, so advice on which one is worth doing first is welcome.

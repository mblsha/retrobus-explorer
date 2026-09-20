# RG35XX Plus: the suspend firmware

What it is, how it works, and how it got there. The Anbernic RG35XX Plus
(Allwinner H700) ships with a firmware that offers Linux no sleep state deeper
than s2idle; this is the firmware we built to give it one, from source, in
three stages, each priced on the bench -- a fourth that counted how often the
deepest of them actually comes back, and a fifth that made it come back every
time.

Every current is in [RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md), which is the
results reference and the one home for measurements; this page is the design
and the story. What the public documents say, what the prior art did, the
outside review and the hypotheses for the current that is left are
[RG35XX-PLUS-POWER-RESEARCH.md](RG35XX-PLUS-POWER-RESEARCH.md). The commands
are section 12 of [RG35XX-PLUS-RUNBOOK.md](RG35XX-PLUS-RUNBOOK.md).

## Verdict

**Ours saves about fifty-three milliamps, comes back every time, and by
medians now sleeps below the published implementation it was modelled on.** It
took three attempts to get to the current: the first two saved almost nothing,
and the third -- switching the DRAM controller, its PHY and the DRAM clock path
off and building them again on the way back -- is where all of it was. Then the
resumes were counted rather than assumed, and eight of forty-two were not
there: the PHY would not calibrate, always at the same step. The same
experiment ran the published implementation thirty-seven times with no failure,
so the design was sound and this implementation of it had a bug. **The bug was
one register.** Their suspend sequence held the DRAM pads while the PHY was
reset and unclocked and ours did not, because this work had a standing rule
against writing a register it could not ground and that rule had been applied
too widely. The owner lifted it for this one write; with the pads held, ours
resumed 48 of 48, and with the three display clocks stopped as well, 36 of 36
and about seven milliamps lower again. The card carries ours,
`--suspend sr-phy-padhold-nodisp`, with theirs as the reference and the
fallback. Every current and every count is in
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md).

```text
step                                          asleep, 5 V input   saved    cost
s2idle as the image ships                         ~124 mA            --     --
+ powersave cpufreq governor                      ~115 mA         9-11 mA   one line of shell
+ our PSCI SYSTEM_SUSPEND, CPU PLL stopped        ~113 mA          ~4 mA    a 420-line TF-A patch
+ LPDDR4 in self-refresh, from an SRAM stub       ~105 mA          ~9 mA    4224 bytes of assembly
+ controller, PHY and clock path off, rebuilt      ~76 mA          ~29 mA   a C stub in SRAM that
  on resume from U-Boot's DRAM driver                                       links U-Boot's driver,
  (8 of 42 resumes did not happen)                                          and a bug
+ the DRAM pads held while the PHY is              ~70 mA          ~6 mA    one register write, and
  reset (52 of 52 resumes happened)                              (in doubt) a rule lifted to make it
+ PLL_VIDEO0, PLL_DE and the DE bus gate           ~62 mA          ~7 mA    three clocks the kernel
  stopped too (KEPT; 50 of 50 happened)                                     leaves running
ROCKNIX's suspend instead (`rocknix-deep`)         ~70 mA      ~51 vs s2idle  the same idea, theirs,
  (0 of 37 resumes did not happen)                                          and it worked first
powered off, RTC alarm armed (not a sleep)          33 mA            --     a cold boot on waking
```

All of it together takes a sleeping board from about 124 mA to about 62, half,
and the firmware is about fifty of those milliamps. About 30 mA separates the
best sleep from a board that is powered off, and that is rails: every one is
still up at full voltage and the PMIC was deliberately never written. The one
clock still running in any sleep here, ours or theirs, is `PLL_PERI0`.

The experiment's shape is worth keeping as well as its number. Two rungs in a
row measured nothing and the report said so; the third, which an outside
reviewer named as the one clock-level step still unpriced, was worth three
times everything before it. A clock-level change that has not been tried is not
a clock-level change that is worth nothing.

The second lesson cost a rung. Eighteen resumes with no failure is not a
reliability measurement, it is eighteen tries at something that fails one time
in five; the only reason the rate was ever counted is that a *different* rung
failed once in three and the obvious explanation had to be checked against its
own control. It was not the explanation, and the control was as broken as the
variant. Anything a note calls proven should say how many times it was tried
and what would have shown a failure.

The third lesson is about the rule that caused the bug. "Never write a register
that cannot be grounded" is a good rule and it was applied to a register that
*is* grounded: the H616 manual documents it, it is in the RTC block and not the
PMIC, no rail and no voltage is involved, and the worst case is a resume that
does not happen -- which is the failure the rule's absence was already causing.
The forbidding was written down in one place and read as settled everywhere
else, so nobody re-examined it for a day. A standing prohibition should carry
its own reason next to it, so that the reason can be checked when the evidence
changes.

What it produced, besides the number: current figures nobody had published for
this design; a reproducible from-source bootloader; a `deep` state whose
resumes are counted and whose memory is proved intact, which is the entry and
exit any deeper scheme needs; and the knowledge of where not to look.

Currents are at the USB-C port at 5.00 V with no battery fitted, so they
include the AXP717's conversion and charger path and are not battery-life
figures.

# The design

## What is built, and what each mode is

`rg35xx.py build-firmware` builds the bootloader ROCKNIX ships for this device
-- mainline U-Boot v2026.01, ROCKNIX's one patch to the H616 DRAM driver, their
`anbernic_rg35xx_h700_lpddr4_defconfig` at a pinned commit, and a BL31 from
TF-A v2.12.0 -- from sources pinned by hash, in the arm64 container the kernel
build already used. A second build into another directory is byte-identical,
because U-Boot and TF-A are given a fixed build date rather than the clock.
`image --install-bootloader` puts the result at byte 8192 of a base image and
refuses one that would reach the job region at LBA 2048 or the first partition.

No kernel or device-tree change is needed anywhere in this: with the firmware
advertising the call, `/sys/power/mem_sleep` reads `s2idle [deep]`, because
Linux probes `PSCI_1_0_FN64_SYSTEM_SUSPEND` and installs its suspend ops when
the firmware answers.

Three TF-A patches, and a mode picks which of them apply and what they are
built with. `0002` and `0003` are two answers to the same question and a build
takes one or the other, never both.

```text
mode            our patches   build options                   what runs while the core waits
none            --            --                              nothing: the parity build
wfi             0001          SUNXI_SYSTEM_SUSPEND=1          in-tree, from DRAM: CPU PLL off
wfi32           0001          + SUNXI_SUSPEND_CPU_32K=1       the same, cluster on 32 kHz too
sr              0001 0002     SUNXI_SUSPEND_DRAM_LEVEL=1      assembly stub: self-refresh
sr-gate         0001 0002     SUNXI_SUSPEND_DRAM_LEVEL=2      + DRAM bus and MBUS gates
sr-pll          0001 0002     SUNXI_SUSPEND_DRAM_LEVEL=3      + PLL_DDR0 stopped
sr-c            0001 0003     SUNXI_SUSPEND_BLOB, STUB_LEVEL=1   C stub: self-refresh only
sr-phy          0001 0003     SUNXI_SUSPEND_BLOB, STUB_LEVEL=2   C stub: the whole DRAM side
sr-phy-pllon    0001 0003     + STUB_DDR_PLL_OFF=0            ablation: PLL_DDR0 left running
sr-phy-fastapb  0001 0003     + STUB_APB_32K=0 STUB_CPU_32K=0 ablation: everything on OSC24M
sr-phy-padhold  0001 0003     + STUB_PAD_HOLD=1               + the DRAM pads held while the PHY
                                                              is reset: what makes ours reliable
sr-phy-padhold-nodisp 0001 0003 + STUB_PAD_HOLD=1             + the two display PLLs and DE gate
                                + STUB_DISPLAY_OFF=1          as well. THE KEPT CONFIGURATION
sr-phy-nodisp   0001 0003     + STUB_DISPLAY_OFF=1            + the two display PLLs and DE gate
sr-phy-nodisp-late 0001 0003  + STUB_DISPLAY_LATE=1           the same three, put back after the
                                                              rebuild instead of before it
rocknix-deep    none of ours  their TF-A patches, their stub  theirs, at the commit ROCKNIX pins
```

**Five of these rungs rebuild the PHY without holding the pads** -- `sr-phy`,
its two ablations, `sr-phy-nodisp` and `sr-phy-nodisp-late` -- and each of them
fails about one resume in five to eight. They are kept, built and measured
because each prices a sub-step and a ladder is only readable if every rung goes
on building what it was measured as; none of them is a configuration anybody
should deploy.

Every switch is off by default, so a build that does not ask for one is
byte-for-byte the build that came before: `none` and `sr` were both rebuilt
after `0003` was written and are byte for byte what they were measured as.
`rocknix-deep` builds kailashrs' TF-A patch and SRAM stub from source at the
commits ROCKNIX pins (patch sha256 `6928fc3e...`, stub `712653d1...`) beside
the same two upstream trees, with none of our patches, so that theirs and ours
differ only in the firmware.

## 0001: the TF-A side

`firmware/0001-allwinner-h616-minimal-psci-system-suspend.patch`,
BSD-3-Clause, `SUNXI_SYSTEM_SUSPEND=1`. The H616/H700 has no management
processor, so mainline TF-A leaves system suspend unimplemented; this adds the
smallest thing that is a real suspend entry and a real warm resume, and every
later mode is built on it.

It fills in four `plat_psci_ops_t` hooks. `pwr_domain_suspend` is deliberately
empty -- the GIC distributor and this core's CPU interface have to stay
enabled or the interrupt Linux left unmasked as its wake source would never end
the WFI, and nothing in the suspend takes their state away, but PSCI will not
advertise `SYSTEM_SUSPEND` unless both hooks exist, so they exist.
`pwr_domain_pwr_down_wfi` calls the suspend only when the whole machine is
going off (`is_local_state_off(target_state->pwr_domain_state[PLAT_MAX_PWR_LVL])`),
because the CPU_OFF path comes through the same hook and wants the generic
wait. `get_sys_suspend_power_state` asks for the deepest state at every level.
`pwr_domain_suspend_finish` logs what came back.

The in-tree sequence, which runs from DRAM and therefore leaves DRAM running:

```text
read CCU_CPUX_AXI_CFG_REG and CCU_PLL_CPUX_CTRL_REG, and SCR_EL3
cluster onto OSC24M            CCU + 0x0500 bits 26:24 = 000 (3.3.5.45)
[wfi32] cluster onto RTC_32K   the same field = 001
stop PLL_CPUX                  CCU + 0x0000, clear bits 31 and 29 (3.3.5.1)
route IRQ and FIQ to EL3       SCR_EL3 | SCR_IRQ_BIT | SCR_FIQ_BIT
WFI
restore SCR_EL3, name the wake interrupt from the GIC distributor
restart PLL_CPUX, wait up to 2 ms for bit 28, LOCK
put the cluster back on PLL_CPUX
disable_mmu_el3(), branch to bl31_warm_entrypoint
```

Two things about it are load-bearing for everything after. The first is the
return: an arm64 Linux treats a plain return from the `SYSTEM_SUSPEND` SMC as a
suspend that did not happen, so the resume has to arrive through
`bl31_warm_entrypoint`, the address `plat_setup_psci_ops()` programs into every
core's reset vector; `psci_warmboot_entrypoint()` then unwinds the suspend and
returns to the address Linux passed in. BL31 is identity mapped, so turning the
MMU off and branching there carries on at the same address. The second is that
`suspend_sequence()` calls nothing in BL31: memory-mapped I/O, the architected
counter (which runs from OSC24M and so keeps time whatever the CPU is clocked
from) and WFI, and its delays come from `CNTPCT_EL0` rather than `udelay()`,
which reaches a function pointer in BL31's data. That is what made it liftable
into SRAM.

Every register is cited to the H616 User Manual rev 1.0: `CCU + 0x0000`
PLL_CPUX control (3.3.5.1, bit 31 enable, bit 29 lock-enable, bit 28 lock
status), `CCU + 0x0500` CPUX_AXI configuration (3.3.5.45, bits 26:24 select
000 OSC24M, 001 RTC_32K, 010 RC16M, 011 PLL_CPUX, 100 PLL_PERI0(1X)), 3.3.2 for
the 1.5 ms settling time behind the 2 ms timeout, 3.3.3.1 for the rule that the
cluster moves off a PLL before the PLL is touched, and 3.13.6.12 for the RTC
general-purpose registers. The GIC reads are the v2 architecture
specification's 4.3.

## The two SRAM stubs, and why there are two

BL31 is linked into DRAM on this platform -- `plat/allwinner/sun50i_h616` sets
`SUNXI_BL31_IN_DRAM := 1`, so BL31 is at `0x40000000` -- so the moment the
LPDDR4 stops answering, the code that stopped it has stopped too. Self-refresh
cannot be done by BL31 itself at all: the stub is not an optimisation, it is
the only way. The only memory left is **SRAM A1, 32 KiB at `0x00020000`**,
which U-Boot's SPL ran from at boot and nothing has owned since. TF-A maps the
whole SRAM region `MT_DEVICE | MT_EXECUTE_NEVER`, so a stub has to be entered
with the MMU off -- which the warm-boot jump already does -- and the page
tables are themselves in the DRAM that is about to go away, which is the second
reason.

Which stub a build carries is a licensing question as much as a technical one.

- **`firmware/0002-...-dram-self-refresh-from-an-sram-stub.patch`**: 4224 bytes
  of hand-written assembly in BL31's read-only data, BSD-3-Clause like the TF-A
  it patches. It asks the controller for self-refresh and asks it to come out
  again, and re-initialises nothing, so it needs no DRAM driver and no code
  from one. It is assembly on purpose: **no stack** (the stack is in DRAM, so
  everything it remembers across the sleep -- the saved `PWRCTL`, the three MBUS
  master-enable words, `CPUX_AXI`, `SCR_EL3`, `VBAR_EL3` and the watchdog's two
  registers -- lives in a save area inside the copy, in SRAM), **no call**
  (everything callable is in DRAM), and **no literal pool** (a compiler puts one
  where it likes, and a `ldr x0, =label` in a blob running from `0x20000` rather
  than from where it was linked would fetch from DRAM in self-refresh, so every
  constant is built with `movz`/`movk` and every label reached with `adr`, which
  is PC-relative and so gives the address of the running copy). The built blob
  was disassembled to confirm it: 4224 bytes, no literal loads, two `adr`s. Its
  `SUNXI_SUSPEND_DRAM_LEVEL` is 1 for self-refresh, 2 for the DRAM bus and MBUS
  **gates** and 3 for PLL_DDR0 as well -- gates only, never the resets beside
  them (`MBUS_CFG` bit 30 and `DRAM_BGR` bit 16), because a controller that has
  been reset cannot be talked out of self-refresh without re-running a whole
  DRAM driver, which is exactly what this stub is built not to need.
- **`firmware/stub/` plus
  `firmware/0003-...-suspend-from-a-stub-built-outside-the-tree.patch`**: a
  separate C program, GPL-2.0-or-later, linked to run from SRAM A1 and compiled
  **inside the build container** against the same pinned U-Boot tree the
  bootloader is built from. It puts the controller, its PHY and PLL_DDR0 away
  completely, and there is no way back from that except to run a DRAM
  initialisation; the only open one for this PHY is U-Boot's
  `arch/arm/mach-sunxi/dram_sun50i_h616.c`, which is GPL-2.0-or-later -- so the
  program that links it is too, and it cannot be a file inside the BSD-3-Clause
  TF-A tree. 0003 is the TF-A side of it and an alternative to 0002.

Being C rather than assembly costs nothing at this level, because the stack,
the variables and the driver all live in SRAM A1 with the code. `sr-phy` is
18,544 bytes of the 32 KiB; `sr-c`, where the linker drops the driver because
nothing calls it, is 8,776.

## SRAM A1: the layout, the stack and the link-time assert

`stub.lds` owns the whole of SRAM A1 and is the reason a build that does not
fit fails on the host instead of on a board with no console:

```text
MEMORY   sram (rwx) : ORIGIN = 0x00020000, LENGTH = 0x8000
STACK_SIZE = 0x1000        U-Boot's PHY training functions are the deepest
                           frames here and nothing is recursive; 4 KiB is
                           what the prior art reserves for the same code
.text    __stub_start, KEEP(.head), . = 0x10, KEEP(.params),
         .text* .rodata* .data*, __stub_end
.bss     (NOLOAD) __bss_start .. __bss_end
         __stack_top = ORIGIN + LENGTH
         __stub_size = __stub_end - __stub_start
ASSERT(__bss_end <= __stack_top - STACK_SIZE,
       "the suspend stub does not fit into SRAM A1 with room for its stack")
```

The first sixteen bytes are a header -- `b _start`, `.word __stub_size`, eight
reserved -- and the parameter block sits at offset `0x10`, placed by the linker
script, reached by `start.S` through the same constant, and checked by a
`_Static_assert` in `main.c` that `offsetof(..., resume_entry) == 16`.

## Entry with the MMU off, and the return through BL31

`sunxi_suspend_blob_jump()` (assembly, in 0003) masks every exception, clears
`SCTLR_M_BIT | SCTLR_C_BIT` in `SCTLR_EL3` and branches: the MMU and the data
cache go off and stay off, and because BL31 is identity mapped the instructions
carry on at the same addresses with translation off. It does not return.

`start.S` is entered at SRAM A1's base at EL3 with the MMU and data cache off
and every exception masked. It sets `daifset #0xf`, installs the stub's own
vectors in `VBAR_EL3` -- BL31's are in DRAM -- unmasks SErrors alone so that a
bus fault is recorded rather than left hanging, sets `sp` to `__stack_top`,
zeroes `.bss`, and calls `stub_main()`. When that returns it loads
`resume_entry` out of the parameter block and branches to it: BL31's warm boot
entry point, in DRAM, and therefore only reachable because `stub_main()` has
brought the DRAM back.

BL31's half of the handshake, in 0003:

- at boot, `blob_is_sound()` reads the parameter block out of the image it
  carries in `.rodata` and refuses a stub whose size is impossible or whose
  magic (`0x4d415253`, "SRAM") or version is wrong. Refusing there is the point:
  the alternative is branching into SRAM and finding out with the MMU off and
  nothing able to report it. A stub that fails the check is not run and the
  suspend does nothing at all rather than half of something -- the OS gets a
  resume that took no time and a stage code (`0x0a`, NO_BLOB) saying why.
- on the way into **every** suspend, `place_suspend_blob()` copies the image to
  `0x00020000`, writes `resume_entry`, `flags` and `status` into the copy, and
  does `dsb; ic iallu; dsb; isb` because SRAM is mapped as device memory and the
  instruction side may still hold the previous suspend's copy. Copying every
  time rather than once at boot is deliberate: nothing owns that SRAM, and the
  stub's own variables are in the copy. It costs microseconds.
- after the resume, `sunxi_system_suspend_finish()` reads the "out" half back
  out of SRAM, which keeps its contents through the sleep, and logs the wake
  IRQ, the memory size and the config word, or the status, stage and failure
  words if it did not come back clean.

The parameter block, `sunxi_suspend_blob.h`, is the whole of the interface and
is the one file both sides include; it is BSD-3-Clause and lives in the TF-A
tree with the firmware it belongs to.

```text
0x00 magic       build  0x4d415253 "SRAM"     0x24 wake_irq   out first pending IRQ
0x04 version     build  1                     0x28 fail_reg   out register a wait gave up on
0x08 dram_clk    build  the DRAM clock        0x2c fail_info  out stage << 16 | why
0x0c level       build  which rung it is      0x30 dram_cfg   out cols|rows|ranks|width
0x10 resume_entry  in   BL31's warm entry     0x34 dram_mb    out memory found, MiB
0x18 flags         in   reserved, zero        0x38 snapshot_n out CCU words that follow
0x1c status       out   NONE/OK/BAD_CONFIG/   0x40 snapshot[] out the CCU snapshot
                        NO_SELFREF/FAILED            (room for 32 words; 24 used)
```

## The suspend sequence, step by step

This is `sr-phy-padhold-nodisp`, the kept rung, which is `STUB_LEVEL=2` with
both `STUB_PAD_HOLD` and `STUB_DISPLAY_OFF`; the steps those two add are marked
`[padhold]` and `[nodisp]`, and `sr-phy` is the same sequence with neither.
`sr-c` is the same code with `STUB_LEVEL=1`, which stops after self-refresh and
comes back by clearing the request.

```text
clear the debug registers, stage ENTER
read and consume the debug-watchdog request   RTC GP11; see the markers below
save the watchdog and stop it                 it must not fire during the wait
read the geometry back out of the controller  MSTR device type against the build,
  and check it                                PLL5 N = 2 * CONFIG_DRAM_CLK / 24,
                                              STAT mode 1; then ranks from MSTR
                                              bits 25:24, bus width from MSTR,
                                              cols from ADDRMAP1 & 0x1f + 2 (+1 at
                                              half width), rows 12 + the non-0x0f
                                              bytes of ADDRMAP6 and ADDRMAP7.
                                              Refuses cols outside 7..12 or rows
                                              outside 13..18: this board reads
                                              10 cols, 15 rows, 1 rank, 1024 MiB
save 80 words at the base and 80 at the       0x50 words each; the PHY's training
  half-way point                              writes over them
arm a 16 s watchdog
zero MAER0/1/2                                no more MBUS masters -- a master
                                              blocked on a stopped controller is
                                              a deadlock, a stopped master is not
set PWRCTL bits 5 and 0, wait STAT mode 3     software self-refresh, and the
                                              automatic-self-refresh enable
                                              because the controller is about to
                                              lose its clock. A controller that
                                              refuses rolls back to mode 1 and the
                                              suspend does not happen
[padhold] clear RTC + 0x1F4 bit 0,            the DRAM pad hold. It happens here
  stage PAD_HELD                              and nowhere else: after the memory
                                              is confirmed holding itself and
                                              before the DFI goes, so the pads
                                              are held for the whole of the
                                              window in which the PHY is reset
                                              and unclocked. Without it the
                                              rebuild fails one time in five
SWCTL=0, DFIMISC = (x & ~1) | 0x1f20,         shut the DFI interface down; bit 0
  SWCTL=1, wait DFISTAT bit 0 clear           is the DFI init-complete enable
CLKEN = 0                                     the controller's own clock enables
clear PLL5 enable                             PLL_DDR0 stopped
clear DRAM_CLK_CFG bit 30                     mctl_sys_init() run backwards: that
clear DRAM_BGR gate and reset                 function begins by putting exactly
clear MBUS_CFG enable and reset               these blocks into reset, which is
                                              also the proof a rebuild can start
                                              from where this leaves them
cluster onto OSC24M, then APB1, APB2 and      the vendor's standby clock tree;
  the cluster onto 32 kHz, PLL_CPUX stopped   CCU 0x500 bits 26:24, 0x520 and
                                              0x524 bits 25:24
[nodisp] DE bus gate, then PLL_DE, then       gate first so nothing downstream of
  PLL_VIDEO0                                  a PLL is clocked while it is off
read 24 CCU registers into SRAM               the snapshot: every PLL, CPUX_AXI,
                                              PSI/AHB, APB1/2, MBUS, DE, GPU, VE,
                                              DRAM_CLK, DRAM_BGR, SMHC and USB
disarm the watchdog                           unless a job asked otherwise
WFI                                           interrupts routed to EL3 for the
                                              wait, SCR_EL3 put back after
```

Two writes in the descent are in neither the manual nor U-Boot and are the
prior art's reading of the vendor's standby code: the `0x1f20` into `DFIMISC`
and the `PWRCTL` bit 0 beside bit 5. The pad-hold register *is* in the manual;
what is the prior art's and not the manual's is the *sense* in which it is
written, which is the next section. The H616 manual documents no DRAM
controller registers at all, so U-Boot's own driver -- `mctl_ctrl_init()` to go
in, `mctl_phy_init()` to come out -- is the only honest source for the rest;
everything in the CCU, the watchdog and the RTC is from the manual and cited
where it is used.

## The resume sequence

```text
stage WOKE, arm a 16 s watchdog
name the wake interrupt                       lowest enabled-and-pending in the
                                              GIC distributor; 136, R_Alarm0
cluster onto OSC24M, PLL_CPUX back and        the cluster stays on OSC24M: a
  locked (2 ms), APB2 and APB1 restored       rebuild at 24 MHz is slow and
                                              correct, one on a PLL that did not
                                              relock is neither
[nodisp] PLL_VIDEO0, PLL_DE, then the DE gate as whole words, so the kernel's
                                              clock framework finds what it wrote
U-Boot's DRAM driver, resume path             17 bounded waits, the last on
  [padhold] and, from inside it, RTC +        SWSTAT; see below. The release is
  0x1F4 bit 0 set again -- the release --     made from inside the driver rather
  immediately before the controller is        than from the stub because only the
  told to leave self-refresh                  driver knows when the controller is
                                              about to be let out, and everything
                                              before that moment still needs the
                                              pads held
put the 160 saved words back
[nodisp-late] read those 160 words back and   the display restore moved to here
  then PLL_VIDEO0, PLL_DE, the DE gate        instead, so that nothing restarts
                                              a PLL until the PHY has finished
                                              training and the memory has
                                              answered; a readback that does not
                                              match is recorded and not acted on
cluster back on PLL_CPUX (CPUX_AXI restored)
watchdog restored exactly as it was found
RTC resume counter + 1, status OK, stage STUB_DONE
return through BL31's warm boot entry
```

The rebuild is `sunxi_dram_resume_init()`, added to our copy of U-Boot's driver
by `stub/uboot-dram-resume.patch`: the two PRCM writes `sunxi_dram_init()`
makes before anything else (the 240 ohm resistor calibration --
`CCU_PRCM_RES_CAL_CTRL` bit 8, then clear the bottom six bits of
`CCU_PRCM_OHMS240`), then `mctl_core_init()` with the geometry the stub read
back, then `mctl_set_master_priority()`. Four changes make a cold-boot driver
into a resume path:

- **the cold SDRAM initialisation is skipped**, or the contents are lost:
  `INIT0` bits 31:30 are uMCTL2's `skip_dram_init` field;
- **the two polls in `mctl_phy_read_calibration()`** that are written as a
  `while` with no way out get a deadline, because in a stub with no console a
  hang leaves nothing behind. Every other wait in the driver goes through
  `mctl_await_completion()`, which the stub supplies and bounds itself;
- **an entry point that takes the geometry** the stub read out of the controller
  instead of detecting it, because detection writes patterns over the memory the
  suspend exists to keep;
- **the DRAM pad hold is released** before the controller is told to leave
  self-refresh, on the builds that take it on the way down.

The rest of the patch is markers, `0x30` to `0x3a` in the order they are
reached, which is how a rebuild that fails says where.

## What is deliberately not written

- **The PMIC, over any bus.** No rail, no I2C, no RSB, anywhere in any of this.
  Real rail-off standby is a separate project, and it is
  [RG35XX-PLUS-POWER-RESEARCH.md](RG35XX-PLUS-POWER-RESEARCH.md)'s.
- **PRCM + 0x244, the PLL LDO**, which the prior art writes with a key of
  `0xa7`. Their own comment marks it inferred, it is in the one block of this
  SoC the manual does not document, and it is a supply and not a clock. Nothing
  here writes a register it cannot cite. It is now the **only** write that
  separates their suspend sequence from ours, and there is no longer a
  reliability difference for it to explain.
- **PLL_PERI0 and the 24 MHz oscillator** are left running on purpose: the
  first feeds the card controller among much else, and the second clocks the
  architected counter and the watchdog, which are the only two ways this code
  can tell the time. PLL_PERI0 is the last clock-level item on the list, and
  stopping it needs a mainline source for what depends on it and how those
  consumers are parked -- not an inference from the fact that theirs leaves it
  running too.

### RTC + 0x1F4, the DRAM pad hold: the one that moved off this list

It used to be the second item here and it is now in the suspend sequence, on
the kept rung. The whole story, because the shape of the mistake is worth more
than the register:

- **What the manual says.** H616 User Manual 3.13.6.17 calls the register
  `VDDOFF_GATING_SOF_REG` and bit 0 `DRAM_CH_PAD_HOLD`, "1: hold dram pad", to
  be set before VDD_SYS is powered off and cleared after it comes back.
- **What the working code does.** kailashrs' stub *clears* bit 0 on the way
  down, as soon as self-refresh is confirmed and before the DFI is shut down,
  with a comment saying that is what holds CKE low while the PHY is reset and
  unclocked, and *sets* it again in its resume path before the controller is
  told to leave self-refresh. That is the opposite sense to the manual's, and
  it is the sense that resumes thirty-seven times of thirty-seven.
- **What this board does at rest.** The register reads 1 before and after every
  sleep, on a board that has never suspended and on one that has.
- **What mainline does.** U-Boot's H616 DRAM driver never touches this
  register -- checked in the pinned v2026.01 tarball -- so there is no third
  opinion to break the tie.
- **Why it was forbidden.** This work's own rule was never to write a register
  it could not ground, and the pad hold was filed under it along with the PRCM
  PLL LDO and the PMIC. That was too wide. The register is documented, it is in
  the RTC block and not the PMIC, no rail and no voltage is involved, and the
  worst case of a wrong write is a resume that does not happen -- which is the
  failure that *not* writing it was already causing, one time in five. The rule
  was right and its application was not, and it had been written down in one
  place and read as settled everywhere else.
- **How it came to be written.** When the orchestrator tried to lift its own
  rule, the session's permission system refused the run as a weakening of a
  safety guard, which is the correct behaviour: an agent does not get to widen
  its own authority. **The owner was asked and said yes**, and that is the only
  reason the write exists.
- **What it bought.** `sr-phy-padhold` resumed 48 of 48 against its control's
  8 failures in 42, `sr-phy-padhold-nodisp` 36 of 36, and both are a few
  milliamps lower as well. The counts and currents are
  [RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md)'s.
- **What is still not known.** Which polarity is *correct*. Ours mirrors the
  prior art because the prior art works; nothing here distinguishes "the hold
  is doing what the comment says" from "writing this register at this moment
  perturbs something else helpfully". Only a standby in which VDD_SYS actually
  goes away can tell them apart, and that is the rail-off project.
- `STUB_PAD_HOLD` stays **0 by default**, so every rung measured without it
  goes on building exactly what it was measured as; the two rungs that want it
  ask for it by name.

## Debugging it blind: the markers and the watchdog

There is no serial console on this board, so the firmware's whole voice is
sixteen RTC general-purpose registers at `RTC + 0x100 + 4N` (manual 3.13.6.12),
whose only documented behaviour is to hold what was written to them. They are
in the always-on domain, so they survive a suspend and a warm reset -- but not
the 5 V going away on a board with no battery fitted, which is how `sr-pll`'s
failure took its own evidence with it. The high registers are used so as to stay
clear of the low ones the boot ROM and the vendor firmware use for boot-mode and
standby flags.

```text
GP8   the register a bounded wait gave up on      GP12  stage, tagged 0xa5d50000
GP9   stage << 16 | why                           GP13  suspends entered (TF-A)
GP10  await count << 24 | last awaited register   GP14  resumes finished
GP11  in: 0x57440001, the debug-watchdog request  GP15  the wake interrupt
```

Stage codes share one tag so that one register tells the whole story: `0x01` to
`0x0a` are TF-A's, `0x20` to `0x2f` the stub's own steps, `0x30` to `0x3f` the
markers inside the patched U-Boot driver, `0x40` to `0x42` the way out, and
`0xe1` to `0xee` the failures -- self-refresh refused, self-refresh stuck, DFI
stuck, CPU PLL stuck, rebuild failed, exception. Each failure names the register
its wait was watching, and only the first is kept, because the ones after it are
its consequences. `mctl_await_completion()` writes its own count and register as
it goes, so a rebuild that hangs says which of the seventeen waits it hung on.

The watchdog turns a hang into evidence. It is clocked from OSC24M/750, which
nothing here stops, so it counts through WFI; `WDOG_CFG` 01 resets the whole
system, `WDOG_MODE` bits 7:4 are the interval (0xb is the longest, about
sixteen seconds) and bit 0 the enable, and `WDOG_CTRL` takes the key `0xa57`
(manual 3.6.6.11 to 3.6.6.13). The OS may have it running for its own reasons,
so the stub saves it, takes it, and gives it back exactly as it was found. It is
armed from entry to the wait and again from the wake to the end of the resume;
across the wait it is normally off, because the longest interval it has cannot
cover a forty-second or six-minute sleep. A job that wants it anyway writes
`0x57440001` into GP11 before a short sleep, and the stub **clears the register
as it reads it** -- a request that outlived its own sleep would reset the board
in the middle of the next measurement.

The stub's own exception vectors are installed for the duration, because BL31's
are in DRAM. The handler cannot use the stack -- the fault may be the stack --
so it rebuilds the two addresses it needs, records `ESR_EL3` and `ELR_EL3` in
GP8 and GP9 beside stage `0xa5d500ee`, and arms a half-second watchdog. On a
board with no console that is the difference between a clue and a power cycle.

## Licensing, and where each file lives

- **BSD-3-Clause, in the TF-A tree**: patches `0001`, `0002` and `0003`, and
  `sunxi_suspend_blob.h`, which is an interface description used by both sides
  and stays with the firmware it belongs to.
- **GPL-2.0-or-later, in `rg35xx/firmware/stub/`**: the C stub, because it is a
  derived work of U-Boot's H616 DRAM driver. `src/start.S`, `src/main.c`,
  `src/dram.c`, `src/clock.c`, `src/lib.c`, `src/stub.h`, `compat/` (the
  freestanding environment the driver compiles in), `stub.lds`, a `Makefile`
  that builds it out of tree from `$(UBOOT_DIR)` and `$(ATF_DIR)`, and
  `uboot-dram-resume.patch`.
- **Nothing of U-Boot is in this repository.** `uboot-dram-resume.patch` is
  applied inside the build container to a *copy* of
  `arch/arm/mach-sunxi/dram_sun50i_h616.c` taken from the pinned tree, never to
  the bootloader's own copy. The stub is built first, then TF-A is built with
  `SUNXI_SUSPEND_BLOB=` pointing at the result, which it `.incbin`s into its
  read-only data.

## Credits

The idea -- a PSCI `SYSTEM_SUSPEND` whose inner sequence runs from SRAM A1 so
that the LPDDR4 can be put into self-refresh, with U-Boot's DRAM driver used to
rebuild the controller and the PHY on the way back -- the choice of PSCI hooks,
and the return through TF-A's warm boot entry are **kailashrs' work for
ROCKNIX**:

- <https://github.com/kailashrs/H700_rocknix_enhancement>
- <https://github.com/ROCKNIX/distribution/pull/3316>, merged 2026-09-19
- packaged as <https://github.com/Jacob-Matthew-Cook/h700-suspend-stub>

The code here is ours, and where a register write is theirs and not in any
public document, the comment beside it says so.

# How it got there

Five acts, in two days. The numbers are all
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md)'s; this is the shape.

**Act one: the minimal version, and it was worth nothing.** The sysfs
experiments had ended at a wall -- one sleep state, no cpuidle driver, and in
s2idle the cores only wait for an interrupt while the DRAM, its controller and
every PLL keep running -- so the firmware was the next place to look. 0001 gave
Linux a real `deep` state, seventeen suspends and seventeen resumes over four
boots, and about four milliamps, which this bench does not call a difference. A
core in WFI is already clock-gated; all the CPU clock tree had left to give was
PLL_CPUX's bias current. 0002 added the SRAM stub and the LPDDR4 in
self-refresh: about nine milliamps pooled over three boots, the first thing
above the noise since the governor, and the board at 105 mA every time. Two
rungs above that -- the DRAM-side clock gates, worth 3.4 mA, and PLL_DDR0,
which suspended and never came back -- said the ladder had stopped paying. The
report said so.

**Act two: theirs, measured, at 68.** An outside reviewer's main objection was
that the controller and PHY shutdown the published implementation performs had
never been priced. The bench-experiment list had it as B4, needing a real card
and a person to press the power key; it did not. `--suspend rocknix-deep`
builds kailashrs' TF-A patch and SRAM stub from source at the commits ROCKNIX
pins, with none of our patches, and the result goes on the emulated card under
the same kernel, rootfs and harness as everything else, so only the firmware
differs -- which a whole ROCKNIX image on a real card would not have given.
Theirs slept at about 68 mA against our 105, on a 1 GiB LPDDR4 board their
authors had not run. The ladder had not stopped paying; it had stopped working,
one rung below the prize.

**Act three: ours, with the rebuild, at 76.** The rung that hung is the rung
that pays. `firmware/stub/` and 0003 are the answer: a C stub of ours in SRAM
A1, compiled against U-Boot's own H616 DRAM driver, which shuts the DFI
interface down, clears the controller's clock enables, gates and resets the
DRAM clock path, stops PLL_DDR0, parks the CPU and both APBs on 32 kHz -- and
then builds the controller and the PHY again on the way back. 39.3 mA against
s2idle in its own boot, eighteen deep sleeps with a 256 MiB probe's md5
unchanged after every one, ten consecutive cycles and a six-minute sleep at
75 mA against their 72. Two ablations say where the 29 mA is *not* -- stopping
PLL_DDR0 is worth nothing and the 32 kHz step is worth nothing -- so by
elimination it is the DFI shutdown, `CLKEN`, and holding the clock path in reset
rather than merely gated.

The stub also took the first look anyone has had at what is running while this
board sleeps, by reading 24 CCU registers at the instruction before WFI and
leaving them in SRAM: `PLL_VIDEO0`, `PLL_DE` and the DE bus clock are still on
with the panel long asleep. `sr-phy-nodisp` stops all three and reads about
eight milliamps lower, and one of its first three sleeps failed its PHY rebuild
-- caught exactly by the marker channel, stage `0xa5d500e5`, `fail_info`
`0x00350007`, read calibration failing all five of its tries with no poll
timing out.

**Act four: counting the resumes, which took the rung away.** Restarting two
PLLs immediately before the PHY is re-trained was the obvious cause, and moving
that restore to after the rebuild is one line -- `STUB_DISPLAY_LATE`, and
`sr-phy-nodisp-late` is the build. Before making it, the rate was measured, on
the variant and on the control both, because one failure in three sleeps cannot
tell a broken rung from a lucky one. **`sr-phy`, the control, failed eight of
forty-two**, with `sr-phy-nodisp-late` at four of thirty and `sr-phy-nodisp`
itself at none of twelve: the arms are indistinguishable, the late restore
fixes nothing, and every failure of every build is the same one, read
calibration giving up at marker `0x35`. It is not the display clocks, not the
length of the sleep and not the debug watchdog, each ruled out by a batch of
its own. The published implementation, run through the same batch, resumed
thirty-seven times out of thirty-seven. What separates the two suspend
sequences is two writes, the DRAM pad hold and the PLL LDO, and this work made
neither.

**Act five: the write that was not allowed, and the rung that came back.** Of
those two writes only one could plausibly cause an intermittent failure of the
first step that reads the array, and it was the documented one. Lifting the
prohibition took the owner, because the session's permission system correctly
refused to let the orchestrator weaken its own safety rule; the owner said yes,
and `sr-phy-padhold` -- built the day before and never run -- resumed
**forty-eight times of forty-eight**, with the memory's md5 unchanged after
every one. The pad hold is what our rebuild was missing. It is also worth a few
milliamps, 69.7 against 76.0, which nobody predicted and which is under this
bench's threshold. And with a rung that resumes every time, the eight
milliamps of display clocks that had been sitting unreachable since act three
could finally be collected: `sr-phy-padhold-nodisp`, **thirty-six of
thirty-six**, ten consecutive cycles with all ten windows sound, and 62 mA over
six minutes -- below the published implementation's 70 to 72 by medians,
level with it by means. The card carries it. Theirs is the reference and the
fallback, and the rungs without the pad hold are measurements that must not be
deployed. The whole of it is in
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md).

## Running it again

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-firmware --suspend sr-phy-padhold-nodisp  # the kept one; runbook 12
  build-firmware --suspend rocknix-deep --fetch   # theirs, the fallback
  build-firmware --suspend sr-phy                 # ours without the pad hold:
                                                  # a rung, and not deployable

MDP_CLI=/path/to/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py job \
  --state /private/tmp/rg35xx-sleep-session.json \
  --image build/rg35xx-firmware-src/sr-phy/rg35xx-plus-sleep-sr-phy.img \
  --script projects/ethernet-diagnostic/jobs/sleep/32-phy-vs-s2idle-abba.sh \
  --name phy-abba --run-seconds 480 \
  --label A1 --label B1 --label B2 --label A2 --label A3 --label B3 \
  --output /tmp/phy-abba.json --print-output
```

The md5 check between sleeps opens an extra short window at about 170 mA, so
give any multi-sleep job `--min-window-seconds 30` and read the windows by
their dwell. Of the thirty-four job scripts in `jobs/sleep/`, 1 to 17 are the
sysfs experiments, 18 to 21 act one, 22 to 26 the self-refresh rungs, 27 and 28
the checks that followed the outside review, and 29 to 34 the PHY rebuild --
29 its facts, 30 one sleep, 31 the watchdog-covered short sleeps that make a
hang leave evidence, 32 the alternation, 33 a register dump that can be
diffed against theirs, and 34 how often the rebuild comes back at all, which is
acts four and five and the one that decided what the card carries -- twice.
Each firmware rung needs its own card image and its own
eight-minute `deploy`, because the bootloader is part of the image. `psu2` is
the RG35XX; `psu1` carries another machine on this bench and must never be
switched.

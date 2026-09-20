/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * The H616/H700 SRAM suspend stub: what every file in it can see.
 *
 * GPL because this stub is linked against U-Boot's H616 DRAM driver, which is
 * the only open initialisation for this PHY. See ../README.md.
 */

#ifndef STUB_H
#define STUB_H

#include <asm/arch/cpu.h>
#include <asm/arch/dram.h>
#include <sunxi_suspend_blob.h>

/*
 * How far down this build goes. Set from the build script, one value per rung
 * of the measurement ladder, so that each step can be put on a card on its own
 * and priced in milliamps.
 *
 *  1  self-refresh only: the controller, its PHY and PLL_DDR0 stay clocked and
 *     the way back is to clear the self-refresh request. This is what our
 *     assembly stub does, in C, and exists to prove this environment before
 *     the PHY is involved.
 *  2  the DRAM side is shut down completely -- DFI off, controller clock
 *     enables cleared, the DRAM clock path gated and reset, PLL_DDR0 stopped
 *     -- and the way back is to run U-Boot's DRAM driver.
 */
#ifndef STUB_LEVEL
#define STUB_LEVEL		1
#endif

/* Stop PLL_DDR0 as well. Nothing downstream of it is running by then. */
#ifndef STUB_DDR_PLL_OFF
#define STUB_DDR_PLL_OFF	(STUB_LEVEL >= 2)
#endif

/* Move APB1 and APB2 to the 32 kHz clock, as the vendor's standby code does. */
#ifndef STUB_APB_32K
#define STUB_APB_32K		(STUB_LEVEL >= 2)
#endif

/* Park the cluster on the 32 kHz clock too, rather than leave it on OSC24M. */
#ifndef STUB_CPU_32K
#define STUB_CPU_32K		(STUB_LEVEL >= 2)
#endif

/*
 * Touch RTC + 0x1F4 bit 0 around the sleep. Off by default and deliberately:
 * the H616 manual (3.13.6.17, VDDOFF_GATING_SOF_REG) calls bit 0
 * DRAM_CH_PAD_HOLD and says to set it before VDD_SYS is powered off and clear
 * it after VDD_SYS comes back, while the prior art clears it on the way down
 * with a comment saying that is what holds the pads. VDD_SYS never goes off in
 * this work, so neither reading applies and the register is left alone. When
 * this is 1 the prior art's polarity is used, so that its cost can be measured
 * as a rung of its own.
 */
#ifndef STUB_PAD_HOLD
#define STUB_PAD_HOLD		0
#endif

/*
 * Progress codes. They share the tag of the codes our TF-A patch writes, so
 * one register tells the whole story of a suspend, and every one of them is
 * readable after a watchdog reset.
 */
#define STAGE_TAG		0xa5d50000U
#define STAGE_ENTER		0x20U
#define STAGE_BAD_CONFIG	0x21U
#define STAGE_SAVED		0x22U
#define STAGE_SELFREF		0x23U
#define STAGE_PAD_HELD		0x24U
#define STAGE_DFI_OFF		0x25U
#define STAGE_CTL_CLK_OFF	0x26U
#define STAGE_DRAM_CLK_OFF	0x27U
#define STAGE_DDR_PLL_OFF	0x28U
#define STAGE_CPU_CLK_DOWN	0x29U
#define STAGE_SNAPSHOT		0x2aU
#define STAGE_WFI		0x2bU
#define STAGE_WOKE		0x2cU
#define STAGE_CPU_CLK_UP	0x2dU
#define STAGE_DRAM_REBUILD	0x2eU
/* 0x30..0x3f: markers inside the patched U-Boot driver, see the patch. */
#define STAGE_DRAM_BACK		0x40U
#define STAGE_MEM_RESTORED	0x41U
#define STAGE_STUB_DONE		0x42U
/* Failures. Each says which wait ran out, so a warm reset is still evidence. */
#define STAGE_SELFREF_REFUSED	0xe1U
#define STAGE_SELFREF_STUCK	0xe2U
#define STAGE_DFI_STUCK		0xe3U
#define STAGE_CPU_PLL_STUCK	0xe4U
#define STAGE_REBUILD_FAILED	0xe5U
#define STAGE_EXCEPTION		0xeeU

/* Why a bounded wait gave up, recorded beside the register it was waiting on. */
#define FAIL_SELFREF_ENTER	1U
#define FAIL_SELFREF_ROLLBACK	2U
#define FAIL_DFI_OFF		3U
#define FAIL_CPU_PLL_LOCK	4U
#define FAIL_AWAIT		5U
#define FAIL_PHY_POLL		6U
#define FAIL_REBUILD_FALSE	7U

/*
 * H616 User Manual rev 1.0, 3.13.6.12: sixteen general purpose registers at
 * RTC + 0x100 + 4N whose only documented behaviour is to hold what was written
 * to them, in the always-on domain, so they survive a suspend and a warm
 * reset. There is no serial console on this bench; these are the whole of what
 * the stub can say. 12 to 15 are the ones our TF-A patch already uses and a
 * job already reads; 8 to 11 are added here, high enough to stay out of the
 * way of the low ones the boot ROM and the vendor firmware use for boot-mode
 * and standby flags.
 */
#define RTC_GP(n)		(SUNXI_RTC_BASE + 0x100U + ((n) * 4U))
#define STUB_RTC_FAIL_REG	RTC_GP(8)	/* the register a wait gave up on */
#define STUB_RTC_FAIL_INFO_REG	RTC_GP(9)	/* stage << 16 | why */
#define STUB_RTC_AWAIT_REG	RTC_GP(10)	/* count << 24 | last awaited reg */
#define STUB_RTC_DEBUG_REG	RTC_GP(11)	/* in: STUB_DEBUG_WATCHDOG; cleared here */
#define STUB_RTC_STAGE_REG	RTC_GP(12)
#define STUB_RTC_RESUMES_REG	RTC_GP(14)
#define STUB_RTC_WAKE_REG	RTC_GP(15)

/*
 * A job writes this word into RTC general purpose register 11 before a short
 * sleep to ask for the watchdog to stay armed across the wait as well as
 * around it, so that a hang anywhere becomes a warm reset and the next boot
 * reads the stage code. The stub clears the register as it reads it: a marker
 * left behind would reset the board in the middle of the next forty-second
 * measurement.
 */
#define STUB_DEBUG_WATCHDOG	0x57440001U

#ifndef __ASSEMBLY__

extern struct sunxi_suspend_blob_params stub_params;

/* start.S */
u64 read_cntpct(void);
u64 read_scr_el3(void);
void write_scr_el3(u64 value);
void cpu_wfi(void);

/* lib.c */
void stage(u32 code);
void fail(unsigned long reg, u32 why);
__attribute__((noreturn)) void stub_reset(u32 code);
void udelay(unsigned long us);
bool wait_reg(unsigned long reg, u32 mask, u32 value, unsigned long us);
void wdog_save(void);
void wdog_arm(void);
void wdog_off(void);
void wdog_restore(void);

/* clock.c */
void clocks_down(void);
void clocks_up(void);
void cpu_clock_restore(void);
void snapshot_clocks(void);

/* dram.c */
bool dram_read_config(struct dram_config *config);
u32 dram_config_word(const struct dram_config *config);
void dram_save_contents(const struct dram_config *config);
bool dram_enter_selfrefresh(void);
void dram_shutdown(void);
bool dram_leave_selfrefresh(void);
bool dram_rebuild(const struct dram_config *config);

/* U-Boot's driver, with uboot-dram-resume.patch applied to our copy. */
extern bool sunxi_dram_resume;
extern bool sunxi_dram_pad_hold;
extern bool sunxi_dram_poll_failed;
bool sunxi_dram_resume_init(const struct dram_config *config);
unsigned long mctl_calc_size(const struct dram_config *config);

#endif /* __ASSEMBLY__ */

#endif /* STUB_H */

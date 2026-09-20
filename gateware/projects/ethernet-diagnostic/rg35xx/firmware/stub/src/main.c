// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * The suspend, in order.
 *
 * Entered from start.S, which was entered from BL31 with the MMU off. BL31 is
 * linked into DRAM on this platform, so from the moment the memory stops
 * answering until the moment it answers again, this file and what it calls are
 * the only code in the machine. Everything it needs -- its stack, its
 * variables, the DRAM driver it rebuilds the controller with -- is in SRAM A1,
 * and stub.lds refuses to link a build that does not fit there with room for
 * the stack.
 *
 * Debugging this blind is the reason for the progress codes. Each one goes
 * into an RTC general purpose register, which is in the always-on domain and
 * survives a watchdog reset; a job on the next boot reads it with devmem. A
 * job can also ask, by writing STUB_DEBUG_WATCHDOG into another of those
 * registers, for the watchdog to stay armed across the wait itself, which
 * turns a hang anywhere at all into a warm reset that leaves its evidence
 * behind. That only works for a sleep shorter than the watchdog's longest
 * interval of about sixteen seconds, so measured forty-second and six-minute
 * sleeps run without it and a hang in those costs the evidence.
 */

#include <asm/io.h>
#include "stub.h"

/* GICv2 distributor, Arm GIC Architecture Specification v2 section 4.3. */
#define GICD(offset)			(SUNXI_GICD_BASE + (offset))
#define GICD_TYPER			0x004
#define GICD_ISENABLER(n)		(0x100 + 4 * (n))
#define GICD_ISPENDR(n)			(0x200 + 4 * (n))
#define GICD_TYPER_ITLINES_MASK		0x1fU
#define GIC_SPURIOUS_INTERRUPT		1023U

/* SCR_EL3.IRQ and SCR_EL3.FIQ, Arm ARM D13.2.114. */
#define SCR_ROUTE_TO_EL3		0x6ULL

/*
 * The block BL31 fills in before it jumps here and reads back afterwards. It
 * is at a fixed offset inside the image so that BL31 can check the build-time
 * half of it before it copies anything into SRAM; stub.lds puts it there and
 * start.S reaches resume_entry by the same constant.
 */
struct sunxi_suspend_blob_params stub_params
	__attribute__((section(".params"), used)) = {
	.magic		= SUNXI_SUSPEND_BLOB_MAGIC,
	.version	= SUNXI_SUSPEND_BLOB_VERSION,
	.dram_clk	= CONFIG_DRAM_CLK,
	.level		= STUB_LEVEL,
};

_Static_assert(offsetof(struct sunxi_suspend_blob_params, resume_entry) == 16,
	       "start.S reaches resume_entry at offset 16");

static u32 first_pending_interrupt(void)
{
	unsigned int words = (readl(GICD(GICD_TYPER)) &
			      GICD_TYPER_ITLINES_MASK) + 1U;
	unsigned int word;

	for (word = 0; word < words; word++) {
		u32 active = readl(GICD(GICD_ISPENDR(word))) &
			     readl(GICD(GICD_ISENABLER(word)));

		if (active != 0U)
			return 32U * word + (u32)__builtin_ctz(active);
	}

	return GIC_SPURIOUS_INTERRUPT;
}

/*
 * Interrupts are masked in PSTATE, which does not stop one ending a WFI, but
 * route them to EL3 for the wait so that the core is certain to see the one
 * the OS left unmasked at the GIC.
 */
static void wait_for_wakeup(void)
{
	u64 scr = read_scr_el3();

	write_scr_el3(scr | SCR_ROUTE_TO_EL3);
	cpu_wfi();
	write_scr_el3(scr);
}

/*
 * A job asks for the watchdog across the wait by writing a word into an RTC
 * register. It is consumed here rather than left standing: a marker that
 * outlived its own sleep would reset the board in the middle of the next
 * forty-second measurement.
 */
static bool debug_watchdog_requested(void)
{
	bool asked = readl(STUB_RTC_DEBUG_REG) == STUB_DEBUG_WATCHDOG;

	if (asked)
		writel(0, STUB_RTC_DEBUG_REG);

	return asked;
}

static void clear_debug_registers(void)
{
	writel(0, STUB_RTC_FAIL_REG);
	writel(0, STUB_RTC_FAIL_INFO_REG);
	writel(0, STUB_RTC_AWAIT_REG);
}

void stub_main(void)
{
	struct dram_config config;
	bool watchdog_through_the_wait;

	stub_params.status = SUNXI_SUSPEND_BLOB_STATUS_NONE;
	stub_params.fail_reg = 0;
	stub_params.fail_info = 0;
	clear_debug_registers();
	stage(STAGE_ENTER);

	watchdog_through_the_wait = debug_watchdog_requested();
	wdog_save();

	/*
	 * Nothing has been taken away yet, so a controller that is not the one
	 * this stub was built for costs only a suspend that lasted no time:
	 * start.S still returns through BL31's warm boot entry and the OS gets
	 * its resume, with a stage code saying why it never slept.
	 */
	if (!dram_read_config(&config)) {
		stub_params.status = SUNXI_SUSPEND_BLOB_STATUS_BAD_CONFIG;
		stage(STAGE_BAD_CONFIG);
		wdog_restore();
		return;
	}
	stub_params.dram_cfg = dram_config_word(&config);
	stub_params.dram_mb = (u32)(mctl_calc_size(&config) >> 20);

#if STUB_LEVEL >= 2
	dram_save_contents(&config);
#endif

	/* From here to the wait, a hang should be a warm reset and not a wedge. */
	wdog_arm();

	if (!dram_enter_selfrefresh()) {
		stub_params.status = SUNXI_SUSPEND_BLOB_STATUS_NO_SELFREF;
		stage(STAGE_SELFREF_REFUSED);
		wdog_restore();
		return;
	}

	dram_shutdown();
	clocks_down();
	snapshot_clocks();

	stage(STAGE_WFI);
	/*
	 * The wait is forty seconds or six minutes and the watchdog's longest
	 * interval is about sixteen, so it cannot cover a measured sleep. A
	 * debug run asks for a sleep short enough that it can.
	 */
	if (!watchdog_through_the_wait)
		wdog_off();

	wait_for_wakeup();

	stage(STAGE_WOKE);
	wdog_arm();

	stub_params.wake_irq = first_pending_interrupt();
	writel(stub_params.wake_irq, STUB_RTC_WAKE_REG);

	clocks_up();

#if STUB_LEVEL >= 2
	if (!dram_rebuild(&config))
		stub_reset(STAGE_REBUILD_FAILED);
#else
	if (!dram_leave_selfrefresh())
		stub_reset(STAGE_SELFREF_STUCK);
#endif

	/* DRAM is readable again from here, and so is the rest of BL31. */
	cpu_clock_restore();
	wdog_restore();

	writel(readl(STUB_RTC_RESUMES_REG) + 1U, STUB_RTC_RESUMES_REG);
	stub_params.status = SUNXI_SUSPEND_BLOB_STATUS_OK;
	stage(STAGE_STUB_DONE);
}

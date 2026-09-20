// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * The clock tree around the wait: what is stopped on the way down, what is put
 * back on the way up, and the one look at the CCU nobody has taken before --
 * a snapshot of every PLL and of the gates that matter, read at the last
 * instruction before WFI and left in SRAM for a job to read afterwards.
 *
 * Every register here is H616 User Manual rev 1.0 section 3.3.5, named in
 * compat/asm/arch/clock.h with the manual's own numbering. PLL_PERI0 and the
 * 24 MHz oscillator are left alone: the first feeds the card controller and
 * much else, and the second clocks the architected counter and the watchdog,
 * which are the only two ways this code can tell the time.
 *
 * What is deliberately *not* here is the PRCM register at +0x244 that the
 * prior art writes with a key of 0xa7 to take the PLL LDO down. Their own
 * comment marks it inferred, the manual does not document that block at all,
 * and it is a supply and not a clock.
 */

#include <asm/io.h>
#include <asm/arch/clock.h>
#include "stub.h"

#define CCU(offset)			(SUNXI_CCM_BASE + (offset))

/*
 * 3.3.5.45: bits 26:24 select the cluster clock -- 000 OSC24M, 001 RTC_32K,
 * 010 RC16M, 011 PLL_CPUX, 100 PLL_PERI0(1X). APB1 and APB2 (3.3.5.48 and
 * 3.3.5.49) use bits 25:24 with the same first two sources.
 */
#define CLK_SRC_MASK			(0x7U << 24)
#define CLK_SRC_OSC24M			(0x0U << 24)
#define CLK_SRC_RTC32K			(0x1U << 24)

/* 3.3.5.2: PLL_CPUX settles within 1.5 ms; two of patience, then give up. */
#define PLL_LOCK_TIMEOUT_US		2000UL

/*
 * 3.3.5.8 and 3.3.5.12: PLL_VIDEO0 and PLL_DE, and 3.3.5.53 the DE bus gating
 * register, whose bit 0 is the gate and bit 16 the reset. Only the gate is
 * touched; a block that has been reset is a block a driver does not expect.
 */
#define CCU_PLL_VIDEO0_CFG		0x040
#define CCU_PLL_DE_CFG			0x060
#define CCU_DE_BGR			0x60c
#define DE_BUS_GATING			BIT(0)

static struct {
	u32 pll_cpux;
	u32 cpux_axi;
	u32 apb1;
	u32 apb2;
	u32 pll_video0;
	u32 pll_de;
	u32 de_bgr;
} saved;

/*
 * The display pipeline, stopped and put back exactly. The panel has been
 * asleep since long before the suspend and the whole pipeline measured nothing
 * through sysfs, but the snapshot below says both its PLLs and its bus clock
 * are still running at the instruction before WFI, which is a different
 * statement and is the one this rung is here to price.
 *
 * The gate goes first and comes back last, so that nothing downstream of a
 * PLL is clocked while that PLL is off; the registers are written back as
 * whole words, so whatever the kernel's clock framework had set is what it
 * finds when it runs again.
 *
 * When the restore happens is STUB_DISPLAY_LATE's question and not this
 * function's: either at the end of clocks_up(), which is where it began, or
 * through display_late_up() once the memory is back.
 */
static void display_down(void)
{
#if STUB_DISPLAY_OFF
	saved.pll_video0 = readl(CCU(CCU_PLL_VIDEO0_CFG));
	saved.pll_de = readl(CCU(CCU_PLL_DE_CFG));
	saved.de_bgr = readl(CCU(CCU_DE_BGR));

	clrbits_le32(CCU(CCU_DE_BGR), DE_BUS_GATING);
	clrbits_le32(CCU(CCU_PLL_DE_CFG), CCM_PLL_CTRL_EN | CCM_PLL_LOCK_EN);
	clrbits_le32(CCU(CCU_PLL_VIDEO0_CFG), CCM_PLL_CTRL_EN | CCM_PLL_LOCK_EN);
	stage(STAGE_DISPLAY_OFF);
#endif
}

static void display_up(void)
{
#if STUB_DISPLAY_OFF
	writel(saved.pll_video0, CCU(CCU_PLL_VIDEO0_CFG));
	writel(saved.pll_de, CCU(CCU_PLL_DE_CFG));

	/*
	 * Not fatal if either is slow: the kernel's clock framework will find
	 * the register it wrote, and the failure is recorded for the job to
	 * read. Nothing between here and Linux touches the display.
	 */
	if (saved.pll_video0 & CCM_PLL_CTRL_EN) {
		if (!wait_reg(CCU(CCU_PLL_VIDEO0_CFG), CCM_PLL_LOCK,
			      CCM_PLL_LOCK, PLL_LOCK_TIMEOUT_US))
			fail(CCU(CCU_PLL_VIDEO0_CFG), FAIL_DISPLAY_PLL_LOCK);
	}
	if (saved.pll_de & CCM_PLL_CTRL_EN) {
		if (!wait_reg(CCU(CCU_PLL_DE_CFG), CCM_PLL_LOCK,
			      CCM_PLL_LOCK, PLL_LOCK_TIMEOUT_US))
			fail(CCU(CCU_PLL_DE_CFG), FAIL_DISPLAY_PLL_LOCK);
	}

	writel(saved.de_bgr, CCU(CCU_DE_BGR));
#endif
}

#if STUB_DISPLAY_LATE
/*
 * The same restore, held back until main() has the memory answering again.
 * Two PLLs relocking while the PHY is being re-trained is the one difference
 * between the rung that has never failed to resume and the rung that failed
 * read calibration once in three sleeps, and this is the cheapest way to find
 * out whether that is what it was.
 */
void display_late_up(void)
{
	display_up();
}
#endif

void clocks_down(void)
{
	saved.pll_cpux = readl(CCU(CCU_H6_PLL1_CFG));
	saved.cpux_axi = readl(CCU(CCU_H6_CPU_AXI_CFG));
	saved.apb1 = readl(CCU(CCU_H6_APB1_CFG));
	saved.apb2 = readl(CCU(CCU_H6_APB2_CFG));

	/*
	 * The manual's own order for touching PLL_CPUX (3.3.3.1) is to move
	 * the cluster onto another source first, and OSC24M is the one source
	 * that is certainly running and is not about to be stopped.
	 */
	clrsetbits_le32(CCU(CCU_H6_CPU_AXI_CFG), CLK_SRC_MASK, CLK_SRC_OSC24M);
	udelay(100);

#if STUB_APB_32K
	clrsetbits_le32(CCU(CCU_H6_APB1_CFG), CLK_SRC_MASK, CLK_SRC_RTC32K);
	clrsetbits_le32(CCU(CCU_H6_APB2_CFG), CLK_SRC_MASK, CLK_SRC_RTC32K);
#endif
#if STUB_CPU_32K
	clrsetbits_le32(CCU(CCU_H6_CPU_AXI_CFG), CLK_SRC_MASK, CLK_SRC_RTC32K);
#endif

	clrbits_le32(CCU(CCU_H6_PLL1_CFG), CCM_PLL_CTRL_EN | CCM_PLL_LOCK_EN);
	stage(STAGE_CPU_CLK_DOWN);

	display_down();
}

/*
 * Everything back except the cluster itself, which stays on OSC24M until the
 * DRAM is usable again: a rebuild that runs at 24 MHz is slow and correct, and
 * one that runs on a PLL that did not relock is neither.
 */
void clocks_up(void)
{
	clrsetbits_le32(CCU(CCU_H6_CPU_AXI_CFG), CLK_SRC_MASK, CLK_SRC_OSC24M);

	writel(saved.pll_cpux | CCM_PLL_CTRL_EN | CCM_PLL_LOCK_EN,
	       CCU(CCU_H6_PLL1_CFG));
	if (!wait_reg(CCU(CCU_H6_PLL1_CFG), CCM_PLL_LOCK, CCM_PLL_LOCK,
		      PLL_LOCK_TIMEOUT_US)) {
		/*
		 * Not fatal: a cluster left on the oscillator is slow but
		 * alive, and the memory still has to come back. It is recorded
		 * so that a resume which takes an implausibly long time can be
		 * explained afterwards.
		 */
		fail(CCU(CCU_H6_PLL1_CFG), FAIL_CPU_PLL_LOCK);
		stage(STAGE_CPU_PLL_STUCK);
	}

	writel(saved.apb2, CCU(CCU_H6_APB2_CFG));
	writel(saved.apb1, CCU(CCU_H6_APB1_CFG));
	udelay(100);

#if !STUB_DISPLAY_LATE
	display_up();
#endif
	stage(STAGE_CPU_CLK_UP);
}

void cpu_clock_restore(void)
{
	writel(saved.cpux_axi, CCU(CCU_H6_CPU_AXI_CFG));
	udelay(100);
}

/*
 * The last thing read before WFI, and the first evidence anyone will have had
 * of what is still running while this board sleeps. Awake and idle, five PLLs
 * read as enabled; whether the kernel's clock framework takes any of them down
 * on its way into a suspend has never been visible, because nothing can read a
 * register while the core is in WFI and by the time Linux is back its drivers
 * have turned their clocks on again.
 *
 * SRAM A1 keeps its contents across the sleep and nothing else runs from it,
 * so the answer is still here on the other side, and a job reads it out of
 * /dev/mem at the parameter block's own address.
 */
static const u16 snapshot_offsets[] = {
	0x000,	/* PLL_CPUX   3.3.5.1  */
	0x010,	/* PLL_DDR0   3.3.5.2  */
	0x018,	/* PLL_DDR1   3.3.5.3  */
	0x020,	/* PLL_PERI0  3.3.5.4  */
	0x028,	/* PLL_PERI1  3.3.5.5  */
	0x030,	/* PLL_GPU0   3.3.5.6  */
	0x040,	/* PLL_VIDEO0 3.3.5.8  */
	0x048,	/* PLL_VIDEO1 3.3.5.9  */
	0x050,	/* PLL_VIDEO2 3.3.5.10 */
	0x058,	/* PLL_VE     3.3.5.11 */
	0x060,	/* PLL_DE     3.3.5.12 */
	0x078,	/* PLL_AUDIO  3.3.5.14 */
	0x500,	/* CPUX_AXI   3.3.5.45 */
	0x510,	/* PSI/AHB    3.3.5.46 */
	0x520,	/* APB1       3.3.5.48 */
	0x524,	/* APB2       3.3.5.49 */
	0x540,	/* MBUS_CFG   3.3.5.50 */
	0x60c,	/* DE_BGR     3.3.5.53 */
	0x67c,	/* GPU_BGR    3.3.5.58 */
	0x69c,	/* VE_BGR     3.3.5.60 */
	0x800,	/* DRAM_CLK   3.3.5.71 */
	0x80c,	/* DRAM_BGR   3.3.5.73 */
	0x84c,	/* SMHC_BGR   3.3.5.77 */
	0xa8c,	/* USB_BGR    3.3.5.99 */
};

void snapshot_clocks(void)
{
	unsigned int i;

	_Static_assert(ARRAY_SIZE(snapshot_offsets) <=
		       ARRAY_SIZE(stub_params.snapshot),
		       "the parameter block has no room for this snapshot");

	for (i = 0; i < ARRAY_SIZE(snapshot_offsets); i++)
		stub_params.snapshot[i] = readl(CCU(snapshot_offsets[i]));

	stub_params.snapshot_n = ARRAY_SIZE(snapshot_offsets);
	stage(STAGE_SNAPSHOT);
}

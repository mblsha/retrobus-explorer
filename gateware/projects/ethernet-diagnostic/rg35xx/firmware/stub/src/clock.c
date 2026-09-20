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

static struct {
	u32 pll_cpux;
	u32 cpux_axi;
	u32 apb1;
	u32 apb2;
} saved;

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

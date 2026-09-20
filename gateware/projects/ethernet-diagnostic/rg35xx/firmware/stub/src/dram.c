// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Putting the LPDDR4 away and getting it back.
 *
 * The H616 User Manual's DRAMC chapter has no register descriptions at all, so
 * nothing in this file can be cited to it. The controller is a Synopsys uMCTL2
 * with an Allwinner PHY, and the two sources used here are named at each step:
 * U-Boot's own driver for this exact part
 * (arch/arm/mach-sunxi/dram_sun50i_h616.c, GPL-2.0-or-later, which this stub
 * links against), and the prior art's reading of the vendor's standby code
 * (kailashrs, https://github.com/ROCKNIX/distribution/pull/3316) for the three
 * writes that appear in neither the manual nor U-Boot.
 *
 * There are two ways down and two ways back, chosen by STUB_LEVEL:
 *
 *   1  self-refresh and nothing else. The controller and its PHY keep their
 *      clocks, so clearing the request is enough to come back. This is what
 *      our assembly stub does, written in C, and it exists to prove this
 *      environment before the PHY is involved.
 *   2  the whole DRAM side goes away -- DFI down, controller clock enables
 *      cleared, the clock path gated and held in reset, PLL_DDR0 stopped. From
 *      there the only way back is to build the controller and the PHY again,
 *      which is what U-Boot's driver is for.
 */

#include <asm/io.h>
#include <asm/arch/clock.h>
#include <asm/arch/prcm.h>
#include "stub.h"

#define CCU(offset)			(SUNXI_CCM_BASE + (offset))

static struct sunxi_mctl_com_reg *const mctl_com =
	(struct sunxi_mctl_com_reg *)SUNXI_DRAM_COM_BASE;
static struct sunxi_mctl_ctl_reg *const mctl_ctl =
	(struct sunxi_mctl_ctl_reg *)SUNXI_DRAM_CTL0_BASE;

/* uMCTL2 PWRCTL: bit 0 enables automatic self-refresh, bit 5 requests it. */
#define PWRCTL_SELFREF_EN		BIT(0)
#define PWRCTL_SELFREF_SW		BIT(5)

/* uMCTL2 STAT bits 2:0, the operating mode. */
#define STAT_MODE_MASK			0x7U
#define STAT_MODE_NORMAL		0x1U
#define STAT_MODE_SELFREF		0x3U

#define SWSTAT_DONE			0x1U

/*
 * H616 User Manual rev 1.0, 3.13.6.17: VDDOFF_GATING_SOF_REG at RTC + 0x1F4,
 * bit 0 DRAM_CH_PAD_HOLD, "1: hold dram pad". See STUB_PAD_HOLD in stub.h for
 * why this is off by default and why its polarity is an open question.
 */
#define DRAM_PAD_HOLD_REG		(SUNXI_RTC_BASE + 0x1f4)

#define SELFREF_TIMEOUT_US		100000UL
#define DFI_TIMEOUT_US			100000UL

/*
 * What the PHY's own training writes over when the controller is rebuilt. The
 * H616 PHY runs its read and write training against real memory at the bottom
 * of each rank, so a rebuild that is meant to preserve the memory has to put
 * those words back. Eighty words at the base and eighty at the half-way point
 * is the prior art's measure, arrived at empirically; nothing documents it,
 * and the six-minute sleep with an unchanged md5 over 256 MiB is the only
 * evidence here that it is enough.
 */
#define SAVED_WORDS			0x50

static u32 saved_low[SAVED_WORDS];
static u32 saved_high[SAVED_WORDS];
static unsigned long saved_high_address;
static u32 saved_pwrctl;
static u32 saved_maer0, saved_maer1, saved_maer2;

/*
 * The memory this build's copy of the DRAM driver was compiled for, in the
 * names U-Boot's own dram_sun50i_h616.h gives the MSTR device-type field.
 */
#if defined(CONFIG_SUNXI_DRAM_H616_LPDDR4)
#define STUB_MSTR_DEVICETYPE		MSTR_DEVICETYPE_LPDDR4
#elif defined(CONFIG_SUNXI_DRAM_H616_LPDDR3)
#define STUB_MSTR_DEVICETYPE		MSTR_DEVICETYPE_LPDDR3
#elif defined(CONFIG_SUNXI_DRAM_H616_DDR3_1333)
#define STUB_MSTR_DEVICETYPE		MSTR_DEVICETYPE_DDR3
#else
#error "the defconfig this stub was built from names no H616 DRAM type"
#endif
#define MSTR_RANKS_SHIFT		24

/* addrmap bytes left at 0x0f are unused; the rest count towards the rows. */
static unsigned int used_bytes(u32 word, unsigned int bytes)
{
	unsigned int i, used = 0;

	for (i = 0; i < bytes; i++)
		if (((word >> (8 * i)) & 0xffU) != 0x0fU)
			used++;

	return used;
}

/*
 * Rebuild the dram_config the SPL detected at boot by reading it back out of
 * the controller -- the inverse of U-Boot's mctl_set_addrmap() -- and refuse
 * to go anywhere if the controller is not the one this stub was built for.
 * Getting this wrong means re-training the memory with the wrong geometry,
 * which loses its contents, so every field is range-checked.
 */
bool dram_read_config(struct dram_config *config)
{
	u32 mstr = readl(&mctl_ctl->mstr);
	u32 pll5 = readl(CCU(CCU_H6_PLL5_CFG));
	unsigned int cols;

	if ((mstr & MSTR_DEVICETYPE_MASK) != STUB_MSTR_DEVICETYPE)
		return false;
	/* 3.3.5.2: PLL_DDR0's N is bits 15:8 plus one, and 2 * clk / 24 here. */
	if ((((pll5 >> 8) & 0xffU) + 1U) != (CONFIG_DRAM_CLK * 2U / 24U))
		return false;
	if ((readl(&mctl_ctl->statr) & STAT_MODE_MASK) != STAT_MODE_NORMAL)
		return false;

	config->ranks = (((mstr >> MSTR_RANKS_SHIFT) & 0x3U) == 0x3U) ? 2 : 1;
	config->bus_full_width = (mstr & MSTR_BUSWIDTH_HALF) ? 0 : 1;

	cols = (readl(&mctl_ctl->addrmap[1]) & 0x1fU) + 2U;
	if (!config->bus_full_width)
		cols += 1U;
	config->cols = cols;

	config->rows = 12U + used_bytes(readl(&mctl_ctl->addrmap[6]), 4) +
			     used_bytes(readl(&mctl_ctl->addrmap[7]), 2);

	if (config->cols < 7 || config->cols > 12 ||
	    config->rows < 13 || config->rows > 18)
		return false;

	return true;
}

u32 dram_config_word(const struct dram_config *config)
{
	return config->cols | (u32)config->rows << 8 |
	       (u32)config->ranks << 16 | (u32)config->bus_full_width << 24;
}

/* Keep the words the rebuild's training is going to write over. */
void dram_save_contents(const struct dram_config *config)
{
	saved_high_address = CFG_SYS_SDRAM_BASE + mctl_calc_size(config) / 2;

	memcpy(saved_low, (void *)CFG_SYS_SDRAM_BASE, sizeof(saved_low));
	memcpy(saved_high, (void *)saved_high_address, sizeof(saved_high));
	stage(STAGE_SAVED);
}

static void dram_restore_contents(void)
{
	memcpy((void *)CFG_SYS_SDRAM_BASE, saved_low, sizeof(saved_low));
	memcpy((void *)saved_high_address, saved_high, sizeof(saved_high));
	stage(STAGE_MEM_RESTORED);
}

static void masters_off(void)
{
	saved_maer0 = readl(&mctl_com->maer0);
	saved_maer1 = readl(&mctl_com->maer1);
	saved_maer2 = readl(&mctl_com->maer2);

	writel(0, &mctl_com->maer0);
	writel(0, &mctl_com->maer1);
	writel(0, &mctl_com->maer2);
}

static void masters_on(void)
{
	writel(saved_maer0, &mctl_com->maer0);
	writel(saved_maer1, &mctl_com->maer1);
	writel(saved_maer2, &mctl_com->maer2);
}

/*
 * Software self-refresh, the way U-Boot's mctl_ctrl_init() asks for it: close
 * the MBUS masters first, because a master blocked on a controller that has
 * stopped answering is a deadlock and a stopped master is not, then set the
 * request and wait for the controller to say it is in self-refresh.
 *
 * At level 1 only the request bit is set, which is exactly what our assembly
 * stub does and what sixteen proved sleeps were taken with. At level 2 the
 * automatic-self-refresh enable goes on as well, as the vendor's standby code
 * does by the prior art's reading of it, because from there the controller is
 * about to lose its clock and has to hold the memory on its own.
 */
bool dram_enter_selfrefresh(void)
{
	u32 request = PWRCTL_SELFREF_SW;

#if STUB_LEVEL >= 2
	request |= PWRCTL_SELFREF_EN;
#endif

	masters_off();

	saved_pwrctl = readl(&mctl_ctl->pwrctl);
	writel(saved_pwrctl | request, &mctl_ctl->pwrctl);

	if (!wait_reg((unsigned long)&mctl_ctl->statr, STAT_MODE_MASK,
		      STAT_MODE_SELFREF, SELFREF_TIMEOUT_US)) {
		fail((unsigned long)&mctl_ctl->statr, FAIL_SELFREF_ENTER);
		/* Put the controller back the way it was and do not sleep. */
		writel(saved_pwrctl, &mctl_ctl->pwrctl);
		if (!wait_reg((unsigned long)&mctl_ctl->statr, STAT_MODE_MASK,
			      STAT_MODE_NORMAL, SELFREF_TIMEOUT_US)) {
			fail((unsigned long)&mctl_ctl->statr,
			     FAIL_SELFREF_ROLLBACK);
			stub_reset(STAGE_SELFREF_STUCK);
		}
		masters_on();
		return false;
	}

	stage(STAGE_SELFREF);
	return true;
}

/*
 * Everything on the DRAM side after the memory is holding itself. The order is
 * the vendor standby order as the prior art reads it, and the last four writes
 * are U-Boot's mctl_sys_init() run backwards -- that function begins by
 * putting exactly these blocks into reset, so it is also the proof that a
 * rebuild can start from here.
 */
void dram_shutdown(void)
{
#if STUB_LEVEL >= 2
#if STUB_PAD_HOLD
	clrbits_le32(DRAM_PAD_HOLD_REG, BIT(0));
	sunxi_dram_pad_hold = true;
	stage(STAGE_PAD_HELD);
#endif

	/*
	 * Shut the DFI interface down. The value is the prior art's, from the
	 * vendor's standby code; neither the manual nor U-Boot writes it. Bit
	 * 0 of DFIMISC is the DFI init-complete enable and is cleared, and
	 * DFISTAT bit 0 going low is the interface acknowledging.
	 */
	writel(0, &mctl_ctl->swctl);
	clrsetbits_le32(&mctl_ctl->dfimisc, BIT(0), 0x1f20);
	writel(1, &mctl_ctl->swctl);
	if (!wait_reg((unsigned long)&mctl_ctl->dfistat, BIT(0), 0,
		      DFI_TIMEOUT_US)) {
		fail((unsigned long)&mctl_ctl->dfistat, FAIL_DFI_OFF);
		stub_reset(STAGE_DFI_STUCK);
	}
	stage(STAGE_DFI_OFF);

	/* The controller's own clock enables. U-Boot writes 0x8000 to start it. */
	writel(0, &mctl_ctl->clken);
	stage(STAGE_CTL_CLK_OFF);

#if STUB_DDR_PLL_OFF
	clrbits_le32(CCU(CCU_H6_PLL5_CFG), CCM_PLL_CTRL_EN);
	stage(STAGE_DDR_PLL_OFF);
#endif
	clrbits_le32(CCU(CCU_H6_DRAM_CLK_CFG), DRAM_MOD_RESET);
	clrbits_le32(CCU(CCU_H6_DRAM_GATE_RESET),
		     BIT(RESET_SHIFT) | BIT(GATE_SHIFT));
	clrbits_le32(CCU(CCU_H6_MBUS_CFG), MBUS_ENABLE | MBUS_RESET);
	stage(STAGE_DRAM_CLK_OFF);
#endif /* STUB_LEVEL >= 2 */
}

/*
 * Level 1's way back, which is U-Boot's mctl_phy_init() tail: clear the
 * request inside a SWCTL commit, wait for the commit, then wait for the
 * controller to report normal operating mode.
 */
bool dram_leave_selfrefresh(void)
{
	writel(0, &mctl_ctl->swctl);
	writel(saved_pwrctl, &mctl_ctl->pwrctl);
	writel(1, &mctl_ctl->swctl);

	if (!wait_reg((unsigned long)&mctl_ctl->swstat, SWSTAT_DONE,
		      SWSTAT_DONE, SELFREF_TIMEOUT_US) ||
	    !wait_reg((unsigned long)&mctl_ctl->statr, STAT_MODE_MASK,
		      STAT_MODE_NORMAL, SELFREF_TIMEOUT_US)) {
		fail((unsigned long)&mctl_ctl->statr, FAIL_SELFREF_ROLLBACK);
		return false;
	}

	masters_on();
	stage(STAGE_DRAM_BACK);
	return true;
}

/*
 * Level 2's way back: U-Boot's own DRAM driver, with our patch to it, run from
 * SRAM. It starts from blocks in reset, which is where dram_shutdown() left
 * them, brings the clocks and the PLL back, re-initialises the controller and
 * re-trains the PHY, and skips the cold SDRAM initialisation because the
 * memory has been refreshing itself the whole time. Then the words the
 * training wrote over go back.
 */
bool dram_rebuild(const struct dram_config *config)
{
#if STUB_LEVEL >= 2
	stage(STAGE_DRAM_REBUILD);
	sunxi_dram_resume = true;
	sunxi_dram_poll_failed = false;

	if (!sunxi_dram_resume_init(config)) {
		fail((unsigned long)&mctl_ctl->statr, FAIL_REBUILD_FALSE);
		return false;
	}
	if (sunxi_dram_poll_failed)
		return false;

	stage(STAGE_DRAM_BACK);
	dram_restore_contents();
#endif
	return true;
}

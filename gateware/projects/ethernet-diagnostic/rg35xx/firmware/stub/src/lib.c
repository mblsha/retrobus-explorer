// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * What the stub has instead of a C library, a console and a timer driver.
 *
 * Two rules run through all of it. Every wait is bounded, because a stub that
 * spins for ever on a board with no console leaves nothing behind; and every
 * wait that gives up writes the register it was watching and the stage it was
 * in into RTC general purpose registers, which survive the watchdog reset that
 * follows.
 */

#include <asm/io.h>
#include "stub.h"

/*
 * H616 User Manual rev 1.0, 3.6.6.11 to 3.6.6.13. The watchdog is clocked from
 * OSC24M/750, which nothing here stops, so it counts through WFI as well.
 * WDOG_CFG 01 resets the whole system; WDOG_MODE bits 7:4 are the interval and
 * bit 0 the enable; WDOG_CTRL takes the key 0xa57 in bits 12:1 and reloads.
 */
#define WDOG_CTRL_REG			(SUNXI_WDOG_BASE + 0x10)
#define WDOG_CFG_REG			(SUNXI_WDOG_BASE + 0x14)
#define WDOG_MODE_REG			(SUNXI_WDOG_BASE + 0x18)
#define WDOG_RELOAD			((0xa57U << 1) | 1U)
#define WDOG_CFG_WHOLE_SYSTEM		1U
#define WDOG_MODE_ENABLE		BIT(0)
#define WDOG_MODE_16S			(0xbU << 4)	/* the longest interval */
#define WDOG_MODE_HALF_SECOND		(0x0U << 4)

/* The architected counter runs from OSC24M, which this suspend never stops. */
#define STUB_COUNTER_HZ			24000000ULL

bool sunxi_dram_resume;
bool sunxi_dram_pad_hold;
bool sunxi_dram_poll_failed;

static u32 wdog_cfg_saved;
static u32 wdog_mode_saved;
static u32 await_count;

void *memcpy(void *destination, const void *source, size_t bytes)
{
	unsigned char *to = destination;
	const unsigned char *from = source;

	while (bytes--)
		*to++ = *from++;

	return destination;
}

void *memset(void *destination, int value, size_t bytes)
{
	unsigned char *to = destination;

	while (bytes--)
		*to++ = (unsigned char)value;

	return destination;
}

static u64 ticks(unsigned long us)
{
	return (STUB_COUNTER_HZ * (u64)us) / 1000000ULL + 1ULL;
}

void udelay(unsigned long us)
{
	u64 deadline = read_cntpct() + ticks(us);

	while (read_cntpct() < deadline)
		;
}

u64 stub_deadline(unsigned long us)
{
	return read_cntpct() + ticks(us);
}

void stage(u32 code)
{
	stub_params.stage = code;
	writel(STAGE_TAG | code, STUB_RTC_STAGE_REG);
}

/* The patched U-Boot driver's markers come through here, in its own range. */
void stub_mark(u32 code)
{
	stage(code);
}

/* Only the first failure is kept: the ones after it are its consequences. */
void fail(unsigned long reg, u32 why)
{
	if (readl(STUB_RTC_FAIL_INFO_REG) != 0U)
		return;

	stub_params.fail_reg = (u32)reg;
	stub_params.fail_info = (stub_params.stage << 16) | why;
	writel((u32)reg, STUB_RTC_FAIL_REG);
	writel(stub_params.fail_info, STUB_RTC_FAIL_INFO_REG);
}

bool wait_reg(unsigned long reg, u32 mask, u32 value, unsigned long us)
{
	u64 deadline = stub_deadline(us);

	while ((readl(reg) & mask) != value) {
		if (read_cntpct() > deadline)
			return false;
	}

	return true;
}

/*
 * U-Boot's driver polls with this and never gives up. Here it has a deadline,
 * and it leaves a trail: which poll it is on and which register, so that a
 * rebuild that hangs says where even though nothing can print.
 */
void mctl_await_completion(u32 *reg, u32 mask, u32 value)
{
	await_count++;
	writel((await_count << 24) | ((u32)(unsigned long)reg & 0x00ffffffU),
	       STUB_RTC_AWAIT_REG);

	if (!wait_reg((unsigned long)reg, mask, value, 1000000UL)) {
		sunxi_dram_poll_failed = true;
		fail((unsigned long)reg, FAIL_AWAIT);
		stub_reset(STAGE_REBUILD_FAILED);
	}
}

/* For the driver's two polls that are a loop and not an await. */
bool stub_overdue(u64 deadline, unsigned long reg)
{
	if (read_cntpct() <= deadline)
		return false;

	sunxi_dram_poll_failed = true;
	fail(reg, FAIL_PHY_POLL);

	return true;
}

/*
 * The OS may have the watchdog running for its own reasons, and it counts
 * through WFI. Take it, and give it back exactly as it was found.
 */
void wdog_save(void)
{
	wdog_cfg_saved = readl(WDOG_CFG_REG);
	wdog_mode_saved = readl(WDOG_MODE_REG);
	writel(wdog_mode_saved & ~WDOG_MODE_ENABLE, WDOG_MODE_REG);
}

void wdog_arm(void)
{
	writel(WDOG_CFG_WHOLE_SYSTEM, WDOG_CFG_REG);
	writel(WDOG_MODE_16S | WDOG_MODE_ENABLE, WDOG_MODE_REG);
	writel(WDOG_RELOAD, WDOG_CTRL_REG);
}

void wdog_off(void)
{
	writel(readl(WDOG_MODE_REG) & ~WDOG_MODE_ENABLE, WDOG_MODE_REG);
}

void wdog_restore(void)
{
	writel(wdog_mode_saved & ~WDOG_MODE_ENABLE, WDOG_MODE_REG);
	writel(wdog_cfg_saved, WDOG_CFG_REG);
	writel(WDOG_RELOAD, WDOG_CTRL_REG);
	writel(wdog_mode_saved, WDOG_MODE_REG);
}

/*
 * There is nowhere to return to once DRAM is unusable, so say where it went
 * wrong and let the watchdog take the board round again: the RTC registers
 * survive a warm reset and the next boot's job reads them.
 */
__attribute__((noreturn)) void stub_reset(u32 code)
{
	stage(code);
	stub_params.status = SUNXI_SUSPEND_BLOB_STATUS_FAILED;
	writel(WDOG_CFG_WHOLE_SYSTEM, WDOG_CFG_REG);
	writel(WDOG_MODE_HALF_SECOND | WDOG_MODE_ENABLE, WDOG_MODE_REG);
	writel(WDOG_RELOAD, WDOG_CTRL_REG);

	for (;;)
		cpu_wfi();
}

/* U-Boot's driver calls panic() when the memory is not one it supports. */
__attribute__((noreturn)) void stub_panic(void)
{
	stub_reset(STAGE_REBUILD_FAILED);
}

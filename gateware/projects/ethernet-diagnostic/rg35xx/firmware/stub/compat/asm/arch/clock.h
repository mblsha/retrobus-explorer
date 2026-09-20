/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * The CCU offsets and bits U-Boot's H616 DRAM driver and this stub use, from
 * U-Boot's own arch/arm/include/asm/arch-sunxi/clock_sun50i_h6.h. Each one is
 * also a register in the H616 User Manual rev 1.0 section 3.3.5; the manual's
 * numbering is given beside it.
 */

#ifndef STUB_ASM_ARCH_CLOCK_H
#define STUB_ASM_ARCH_CLOCK_H

#define CCU_H6_PLL1_CFG			0x000	/* 3.3.5.1  PLL_CPUX control */
#define CCU_H6_PLL5_CFG			0x010	/* 3.3.5.2  PLL_DDR0 control */
#define CCU_H6_CPU_AXI_CFG		0x500	/* 3.3.5.45 CPUX_AXI config */
#define CCU_H6_PSI_AHB1_AHB2_CFG	0x510	/* 3.3.5.46 PSI/AHB1/AHB2 config */
#define CCU_H6_APB1_CFG			0x520	/* 3.3.5.48 APB1 config */
#define CCU_H6_APB2_CFG			0x524	/* 3.3.5.49 APB2 config */
#define CCU_H6_MBUS_CFG			0x540	/* 3.3.5.50 MBUS config */
#define CCU_H6_DRAM_CLK_CFG		0x800	/* 3.3.5.71 DRAM clock */
#define CCU_H6_DRAM_GATE_RESET		0x80c	/* 3.3.5.73 DRAM bus gating/reset */

#define CCM_PLL_CTRL_EN			BIT(31)
#define CCM_PLL_LOCK_EN			BIT(29)
#define CCM_PLL_LOCK			BIT(28)
#define CCM_PLL_OUT_EN			BIT(27)
#define CCM_PLL5_CTRL_N(n)		(((n) - 1) << 8)

#define MBUS_ENABLE			BIT(31)
#define MBUS_RESET			BIT(30)

#define RESET_SHIFT			(16)
#define GATE_SHIFT			(0)

#define DRAM_MOD_RESET			BIT(30)
#define DRAM_CLK_SRC_PLL5		(0 << 24)

#endif /* STUB_ASM_ARCH_CLOCK_H */

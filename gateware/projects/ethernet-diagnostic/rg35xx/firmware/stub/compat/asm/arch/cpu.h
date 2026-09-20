/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * The H616 base addresses this stub and U-Boot's DRAM driver use. The values
 * are U-Boot's own, from arch/arm/include/asm/arch-sunxi/cpu_sun50i_h6.h under
 * CONFIG_MACH_SUN50I_H616; they are repeated here rather than included because
 * that header pulls in the whole of U-Boot's configuration machinery.
 */

#ifndef STUB_ASM_ARCH_CPU_H
#define STUB_ASM_ARCH_CPU_H

#define SUNXI_CCM_BASE			0x03001000
#define SUNXI_WDOG_BASE			0x030090a0	/* H616 manual 3.6.6 */
#define SUNXI_GICD_BASE			0x03021000
#define SUNXI_DRAM_COM_BASE		0x047fa000
#define SUNXI_DRAM_CTL0_BASE		0x047fb000
#define SUNXI_DRAM_PHY0_BASE		0x04800000
#define SUNXI_RTC_BASE			0x07000000	/* H616 manual 3.13 */
#define SUNXI_PRCM_BASE			0x07010000

#endif /* STUB_ASM_ARCH_CPU_H */

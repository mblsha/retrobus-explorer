/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * The two PRCM offsets U-Boot's DRAM driver uses, from its own
 * arch/arm/include/asm/arch-sunxi/prcm_sun50i.h. The manual does not document
 * this block; the driver's resistor-calibration writes are all we use.
 */

#ifndef STUB_ASM_ARCH_PRCM_H
#define STUB_ASM_ARCH_PRCM_H

#define CCU_PRCM_RES_CAL_CTRL		0x310
#define CCU_PRCM_OHMS240		0x318

#endif /* STUB_ASM_ARCH_PRCM_H */

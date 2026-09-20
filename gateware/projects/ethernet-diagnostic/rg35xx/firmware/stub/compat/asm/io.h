/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * The register accessors U-Boot's DRAM driver and this stub use, for a stub
 * that runs with the MMU off. Every one of these addresses is device memory,
 * so a barrier and not a cache operation is what orders them; U-Boot's own
 * readl/writel on arm64 are a load/store with a barrier, and these match.
 */

#ifndef STUB_ASM_IO_H
#define STUB_ASM_IO_H

#define __stub_reg(a)			((volatile u32 *)(unsigned long)(a))

/* U-Boot's driver calls this by name as well as through readl/writel. */
#define dmb()				__asm__ volatile ("dmb sy" ::: "memory")

#define readl(a)			({ u32 __v = *__stub_reg(a); dmb(); __v; })
#define writel(v, a)			do { dmb(); *__stub_reg(a) = (u32)(v); } while (0)
/* U-Boot uses the relaxed form only where it then orders the writes itself. */
#define writel_relaxed(v, a)		(*__stub_reg(a) = (u32)(v))

#define setbits_le32(a, s)		writel(readl(a) | (s), (a))
#define clrbits_le32(a, c)		writel(readl(a) & ~(u32)(c), (a))
#define clrsetbits_le32(a, c, s)	writel((readl(a) & ~(u32)(c)) | (s), (a))

#endif /* STUB_ASM_IO_H */

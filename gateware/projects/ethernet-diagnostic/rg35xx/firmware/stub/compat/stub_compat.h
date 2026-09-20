/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * The freestanding environment U-Boot's H616 DRAM driver is compiled in when
 * it is linked into this stub. Forced in front of every translation unit with
 * -include, because the driver expects a U-Boot and there is none here: no
 * libc, no console, no malloc, and a panic() that can only reset the board.
 */

#ifndef STUB_COMPAT_H
#define STUB_COMPAT_H

#ifndef __ASSEMBLY__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long ulong;

#define BIT(nr)				(1UL << (nr))
#define GENMASK(high, low)		((~0UL << (low)) & (~0UL >> (63 - (high))))
#define ARRAY_SIZE(a)			(sizeof(a) / sizeof((a)[0]))
#define DIV_ROUND_UP(n, d)		(((n) + (d) - 1) / (d))

#define max(x, y) ({					\
	__typeof__(x) __x = (x);			\
	__typeof__(y) __y = (y);			\
	__x > __y ? __x : __y;				\
})

/* U-Boot checks its register layouts with this; keep the check, drop the name. */
#define check_member(structure, member, offset)				\
	_Static_assert(offsetof(struct structure, member) == (offset),	\
		       "check_member " #member)

/* No console: the driver's debug() lines go nowhere, and must not be errors. */
#define debug(...)			do { } while (0)

/* The one address of DRAM itself the driver uses. */
#define CFG_SYS_SDRAM_BASE		0x40000000UL

void *memcpy(void *destination, const void *source, size_t bytes);
void *memset(void *destination, int value, size_t bytes);
void udelay(unsigned long us);

/*
 * Two functions the driver calls that U-Boot defines elsewhere. Both are ours,
 * in lib.c: the wait is bounded and records where it gave up, and the panic
 * cannot print, so it resets through the watchdog instead.
 */
void mctl_await_completion(u32 *reg, u32 mask, u32 value);
__attribute__((noreturn)) void stub_panic(void);
#define panic(...)			stub_panic()

/* Set by the stub: true while the driver is running on the resume path. */
extern bool sunxi_dram_resume;
/* Set by the stub: true if the pad hold was taken on the way down. */
extern bool sunxi_dram_pad_hold;
/* Set by the driver: true if a bounded poll inside it ran out of time. */
extern bool sunxi_dram_poll_failed;

/* Bounded polls for the driver's two unbounded ones; see lib.c. */
u64 stub_deadline(unsigned long us);
bool stub_overdue(u64 deadline, unsigned long reg);
void stub_mark(u32 code);

#endif /* __ASSEMBLY__ */

#endif /* STUB_COMPAT_H */

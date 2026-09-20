/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Entered from BL31 at EL3, with the MMU and the data cache off and every
 * exception masked, at SRAM A1's base. Leaves through the warm boot entry
 * point BL31 put in the parameter block, which is in DRAM and is therefore
 * only reachable once stub_main() has brought the DRAM back.
 *
 * The first sixteen bytes are a header: a branch, the image's size, and then
 * the parameter block at offset 0x10, which BL31 reads out of the image
 * before it copies it and writes into after it has. stub.lds places them.
 */

/* offsetof(struct sunxi_suspend_blob_params, resume_entry); checked in main.c */
#define RESUME_ENTRY_OFFSET	16

	.section .head, "ax"
	.globl	_head
_head:
	b	_start				/* 0x00 */
	.word	__stub_size			/* 0x04, from stub.lds */
	.quad	0				/* 0x08, reserved */
						/* 0x10: struct params */

	.text
	.globl	_start
_start:
	msr	daifset, #0xf

	/*
	 * BL31's vectors are in DRAM, which is about to stop answering. Take
	 * exceptions here instead: the handler records ESR and ELR in RTC
	 * registers that survive a reset and then resets, which on a board
	 * with no console is the difference between a clue and a power cycle.
	 */
	ldr	x0, =stub_vectors
	msr	vbar_el3, x0
	isb
	/* SErrors too: a bus fault should be recorded, not left hanging. */
	msr	daifclr, #4

	ldr	x0, =__stack_top
	mov	sp, x0

	ldr	x0, =__bss_start
	ldr	x1, =__bss_end
1:	cmp	x0, x1
	b.hs	2f
	str	xzr, [x0], #8
	b	1b
2:
	bl	stub_main

	/* Back into BL31, in DRAM, through the entry point PSCI was set up with. */
	ldr	x0, =stub_params
	ldr	x0, [x0, #RESUME_ENTRY_OFFSET]
	br	x0

	.globl	read_cntpct
read_cntpct:
	mrs	x0, cntpct_el0
	ret

	.globl	read_scr_el3
read_scr_el3:
	mrs	x0, scr_el3
	ret

	.globl	write_scr_el3
write_scr_el3:
	msr	scr_el3, x0
	isb
	ret

	.globl	cpu_wfi
cpu_wfi:
	dsb	sy				/* every MMIO write lands first */
	wfi
	ret

/*
 * Any exception while the stub runs. It cannot use the stack -- the fault may
 * be the stack -- so it rebuilds the two addresses it needs, records ESR and
 * ELR beside a stage code of 0xa5d500ee, and waits for the watchdog.
 *
 * H616 User Manual rev 1.0, 3.13.6.12 for the RTC general purpose registers
 * and 3.6.6.11 to 3.6.6.13 for the watchdog: CFG 01 resets the whole system,
 * MODE bits 7:4 are the interval and bit 0 the enable.
 */
	.balign	2048
	.globl	stub_vectors
stub_vectors:
	.rept	16
	b	.Lexception
	.balign	0x80
	.endr

.Lexception:
	movz	x1, #0x0000
	movk	x1, #0x0700, lsl #16		/* SUNXI_RTC_BASE */
	mrs	x0, esr_el3
	str	w0, [x1, #0x120]		/* general purpose register 8 */
	mrs	x0, elr_el3
	str	w0, [x1, #0x124]		/* general purpose register 9 */
	movz	w0, #0x00ee
	movk	w0, #0xa5d5, lsl #16
	str	w0, [x1, #0x130]		/* general purpose register 12 */
	movz	x1, #0x90a0
	movk	x1, #0x0300, lsl #16		/* SUNXI_WDOG_BASE */
	mov	w0, #1				/* CFG: whole system reset */
	str	w0, [x1, #0x14]
	mov	w0, #1				/* MODE: 0.5 s, enabled */
	str	w0, [x1, #0x18]
	movz	w0, #0x14af			/* CTRL: key 0xa57, reload */
	str	w0, [x1, #0x10]
1:	wfi
	b	1b

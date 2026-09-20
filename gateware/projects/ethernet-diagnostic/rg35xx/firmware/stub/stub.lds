/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * SRAM A1 is 32 KiB at 0x00020000. U-Boot's SPL ran from it at boot and
 * nothing has owned it since, so the whole of it is this stub's: its code, the
 * U-Boot DRAM driver linked into it, its variables and its stack.
 *
 * The assert is the point of this file. The stub is copied into SRAM by BL31
 * and run there; a build that has grown past the SRAM, or one whose variables
 * have grown into where the stack will be, does not fail at run time in a way
 * anything on this bench could see. It fails here instead.
 */

OUTPUT_FORMAT("elf64-littleaarch64")
OUTPUT_ARCH(aarch64)
ENTRY(_head)

MEMORY
{
	sram (rwx) : ORIGIN = 0x00020000, LENGTH = 0x8000
}

/*
 * U-Boot's DRAM driver is the deepest thing that runs here and it is not
 * recursive; its largest frames are the PHY training functions. 4 KiB is what
 * the prior art reserves for the same code.
 */
STACK_SIZE = 0x1000;

SECTIONS
{
	.text : {
		__stub_start = .;
		KEEP(*(.head))
		. = 0x10;
		KEEP(*(.params))
		*(.text .text.*)
		*(.rodata .rodata.*)
		*(.data .data.*)
		. = ALIGN(8);
		__stub_end = .;
	} > sram

	.bss (NOLOAD) : {
		__bss_start = .;
		*(.bss .bss.* COMMON)
		. = ALIGN(8);
		__bss_end = .;
	} > sram

	__stack_top = ORIGIN(sram) + LENGTH(sram);
	__stub_size = __stub_end - __stub_start;

	ASSERT(__bss_end <= __stack_top - STACK_SIZE,
	       "the suspend stub does not fit into SRAM A1 with room for its stack")

	/DISCARD/ : {
		*(.comment)
		*(.note*)
		*(.eh_frame*)
	}
}

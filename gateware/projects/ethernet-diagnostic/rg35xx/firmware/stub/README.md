# The SRAM suspend stub that rebuilds the DRAM PHY

`SPDX-License-Identifier: GPL-2.0-or-later` for everything in this directory.

This is the second of our two suspend stubs, and the licensing is why it lives
apart from the first. The stub in
`../0002-allwinner-h616-dram-self-refresh-from-an-sram-stub.patch` is
hand-written assembly that only asks the DRAM controller for self-refresh and
asks it to come out again; it needs no DRAM driver, so it is BSD-3-Clause like
the TF-A it is patched into. This one puts the controller, its PHY and
PLL_DDR0 away completely, and there is no way back from that except to run a
DRAM initialisation. The only open one for this PHY is U-Boot's
`arch/arm/mach-sunxi/dram_sun50i_h616.c`, which is GPL-2.0-or-later — so this
stub is compiled against it, is a derived work of it, and is licensed the same
way.

Nothing of U-Boot is copied into this repository. `uboot-dram-resume.patch` is
our small patch to that driver, and the build applies it to a copy taken from
the pinned U-Boot tree *inside the build container*
(`rg35xx/build_firmware.py`), never to the bootloader's own copy.

The idea — a PSCI `SYSTEM_SUSPEND` whose inner sequence runs from SRAM A1 so
that the LPDDR4 can be put into self-refresh, with U-Boot's DRAM driver used to
rebuild the controller and PHY on the way back — is kailashrs' work for ROCKNIX:

- <https://github.com/kailashrs/H700_rocknix_enhancement>
- <https://github.com/ROCKNIX/distribution/pull/3316>, merged 2026-09-19
- packaged as <https://github.com/Jacob-Matthew-Cook/h700-suspend-stub>

The code here is ours. Where a register write is theirs and not in any public
document, the comment beside it says so.

## What is in here

| file | what it is |
| --- | --- |
| `src/start.S` | entry from BL31: vectors, stack, `.bss`, then `stub_main()` |
| `src/main.c` | the suspend in order, and the ladder's switches |
| `src/dram.c` | self-refresh entry, the DRAM-side shutdown, and the rebuild |
| `src/clock.c` | the CPU, APB1 and APB2 clock tree around the wait |
| `src/lib.c` | `memcpy`, `udelay`, bounded polls, the watchdog, progress codes |
| `src/stub.h` | the declarations, the progress codes and the RTC register map |
| `compat/` | the freestanding environment U-Boot's DRAM driver compiles in |
| `stub.lds` | links it at SRAM A1, and asserts that it fits with its stack |
| `Makefile` | builds it out of tree from `$(UBOOT_DIR)` and `$(ATF_DIR)` |
| `uboot-dram-resume.patch` | our patch to U-Boot's H616 DRAM driver |

The parameter block BL31 and the stub exchange is
`plat/allwinner/sun50i_h616/include/sunxi_suspend_blob.h`, added by our
BSD-3-Clause TF-A patch `../0003-...patch` and included from there: an
interface description, used by both sides, that stays with the firmware it
belongs to.

## Building it by hand

```sh
make -C <builddir> -f <this>/Makefile \
    SRC_DIR=<this> UBOOT_DIR=<patched u-boot tree> ATF_DIR=<tf-a tree> \
    DEFCONFIG=<u-boot>/configs/anbernic_rg35xx_h700_lpddr4_defconfig \
    OUT=<builddir>/suspend_stub.bin CROSS_COMPILE= \
    STUB_DEFINES='-DSTUB_LEVEL=2'
```

`rg35xx.py build-firmware --suspend sr-phy` does exactly that in the container
and then builds TF-A with `SUNXI_SUSPEND_BLOB=` pointing at the result.

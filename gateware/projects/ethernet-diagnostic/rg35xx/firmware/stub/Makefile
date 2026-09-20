# SPDX-License-Identifier: GPL-2.0-or-later
#
# Builds one rung of the SRAM suspend stub, out of tree. The caller gives:
#
#   SRC_DIR        this directory
#   UBOOT_DIR      the patched U-Boot tree the bootloader is built from
#   ATF_DIR        the TF-A tree, for the parameter block's header
#   DEFCONFIG      the U-Boot defconfig, for the DRAM parameters
#   OUT            where to write the binary
#   STUB_DEFINES   the rung, e.g. -DSTUB_LEVEL=2 -DSTUB_DDR_PLL_OFF=0
#   CROSS_COMPILE  empty in the arm64 build container
#
# Run it with -C in a directory of its own. Nothing of U-Boot is copied into
# the repository: the two driver files and the timings are taken from
# $(UBOOT_DIR) here, at build time, and our patch is applied to that copy only.

CC := $(CROSS_COMPILE)gcc
OBJCOPY := $(CROSS_COMPILE)objcopy
KCONFIG := $(UBOOT_DIR)/arch/arm/mach-sunxi/Kconfig

CFLAGS := -I$(SRC_DIR)/compat -I$(SRC_DIR)/src -Iboards \
	-I$(ATF_DIR)/plat/allwinner/sun50i_h616/include \
	-I$(UBOOT_DIR)/arch/arm/include/asm/arch-sunxi \
	-include $(SRC_DIR)/compat/stub_compat.h -include boards/board.h \
	-Os -std=gnu11 -march=armv8-a -mgeneral-regs-only -mstrict-align \
	-mcmodel=small -ffreestanding -fno-builtin -fno-pic -fno-pie \
	-fno-stack-protector -fno-common -ffunction-sections -fdata-sections \
	-Wall -Wno-unused-function $(STUB_DEFINES)
LDFLAGS := -march=armv8-a -mgeneral-regs-only -ffreestanding -nostdlib -static \
	-no-pie -Wl,--gc-sections -Wl,-T,$(SRC_DIR)/stub.lds -Wl,--build-id=none \
	-Wl,--no-warn-rwx-segments

# Which memory the defconfig asks for decides which timing table is linked in.
DRAM_KCONFIG := $(shell grep -oE 'CONFIG_SUNXI_DRAM_H616_[A-Z0-9_]+' $(DEFCONFIG) | head -1)
ifeq ($(DRAM_KCONFIG),CONFIG_SUNXI_DRAM_H616_LPDDR4)
  TIMINGS := h616_lpddr4_2133.c
else ifeq ($(DRAM_KCONFIG),CONFIG_SUNXI_DRAM_H616_LPDDR3)
  TIMINGS := h616_lpddr3.c
else ifeq ($(DRAM_KCONFIG),CONFIG_SUNXI_DRAM_H616_DDR3_1333)
  TIMINGS := h616_ddr3_1333.c
else
  $(error suspend stub: $(DEFCONFIG) names no H616 DRAM type)
endif

OBJS := src/start.o src/main.o src/lib.o src/clock.o src/dram.o \
	uboot/dram_sun50i_h616.o uboot/dram_dw_helpers.o uboot/dram_timing.o

all: $(OUT)

$(OUT): stub.elf
	$(OBJCOPY) -O binary $< $@
	@size=$$(wc -c < $@); echo "suspend stub: $$size bytes"

stub.elf: $(OBJS) $(SRC_DIR)/stub.lds
	$(CC) $(LDFLAGS) $(OBJS) -o $@

src/start.o: $(SRC_DIR)/src/start.S boards/board.h | src
	$(CC) -march=armv8-a -D__ASSEMBLY__ -c $< -o $@

src/%.o: $(SRC_DIR)/src/%.c boards/board.h | src
	$(CC) $(CFLAGS) -c $< -o $@

uboot/%.o: uboot/%.c boards/board.h
	$(CC) $(CFLAGS) -c $< -o $@

# U-Boot's driver, with our resume patch, in a copy of its own: the
# bootloader's DRAM driver is never touched.
uboot/.patched: $(SRC_DIR)/uboot-dram-resume.patch | uboot
	cp $(UBOOT_DIR)/arch/arm/mach-sunxi/dram_sun50i_h616.c \
	   $(UBOOT_DIR)/arch/arm/mach-sunxi/dram_dw_helpers.c uboot/
	patch -d uboot -p1 < $<
	@touch $@

uboot/dram_sun50i_h616.c uboot/dram_dw_helpers.c: uboot/.patched

uboot/dram_timing.c: $(UBOOT_DIR)/arch/arm/mach-sunxi/dram_timings/$(TIMINGS) | uboot
	cp $< $@

src uboot boards:
	@mkdir -p $@

# The DRAM parameters: the defconfig's own values, and for any symbol the
# driver reads that the defconfig leaves out, that symbol's unconditional
# Kconfig default. A "default X if Y" is per-SoC and would bake in another
# chip's value, so it is refused rather than guessed at.
define KCONFIG_DEFAULT
$$0 == "config " symbol { found = 1; next } \
found && /^config / { exit } \
found && /^\tbool/ { print "bool"; exit } \
found && /^\tdefault / { if ($$0 !~ / if / && $$2 ~ /^(0x[0-9a-fA-F]+|[0-9]+)$$/) print $$2; exit }
endef

boards/board.h: $(DEFCONFIG) uboot/dram_sun50i_h616.c uboot/dram_dw_helpers.c uboot/dram_timing.c | boards
	@grep -E '^CONFIG_(DRAM_|SUNXI_DRAM_H616_)' $< | sed -e 's/=y$$/ 1/' -e 's/=/ /' -e 's/^/#define /' > $@
	@grep -q '^#define CONFIG_DRAM_CLK ' $@ || { echo "suspend stub: no CONFIG_DRAM_CLK in $<" >&2; exit 1; }
	@for symbol in $$(grep -ohE 'CONFIG_DRAM_[A-Z0-9_]+' $(SRC_DIR)/src/*.[ch] uboot/*.c | sort -u); do \
	  grep -q "^#define $$symbol " $@ && continue; \
	  value="$$(awk -v symbol="$${symbol#CONFIG_}" '$(KCONFIG_DEFAULT)' $(KCONFIG))"; \
	  [ "$$value" = bool ] && continue; \
	  [ -n "$$value" ] || { echo "suspend stub: the DRAM driver reads $$symbol, $(notdir $<) does not set it, and its Kconfig default is not a plain value" >&2; exit 1; }; \
	  echo "#define $$symbol $$value" >> $@; \
	done

.PHONY: all

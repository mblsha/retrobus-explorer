# Experiment 29. What the PHY-rebuild firmware offers, before any sleep.
#
# The bootloader on the card now carries a BL31 that copies a C stub into SRAM
# A1 and runs the whole wait from there. That stub is compiled against U-Boot's
# H616 DRAM driver, so on the way back it can build the DRAM controller and its
# PHY again rather than merely clearing a self-refresh request. This job does
# not sleep. It costs one boot and answers the five questions that decide
# whether the next experiment can be read at all.
#
#  1. Did `deep` arrive? Only a PSCI that advertises SYSTEM_SUSPEND gets it.
#  2. Can /dev/mem read SRAM A1? The stub's parameter block lives at 0x20010
#     and is where everything it has to say after a resume is kept -- its
#     status, the register any wait gave up on, and the CCU snapshot taken at
#     the last instruction before WFI. If this cannot be read, the RTC
#     registers are all the evidence there will be.
#  3. Is the parameter block the one this build was made with? Magic "SRAM"
#     (0x4d415253), version 1, the DRAM clock and the ladder rung.
#  4. Are RTC general purpose registers 8 to 11 free? The stub reports through
#     8 to 15 now, four more than the assembly one used. A register that reads
#     back non-zero on a board that has never suspended is one to leave alone.
#  5. Is the DRAM controller where the stub expects it, and is the watchdog
#     free? Same two checks as experiment 22, because the same two answers
#     decide whether it can enter self-refresh and whether it can disarm the
#     watchdog before a wait longer than any watchdog interval.

devmem_hex() {
    $BB devmem "$1" 2>/dev/null || echo UNREADABLE
}

# The stub's parameter block, at SRAM A1 + 0x10; see sunxi_suspend_blob.h.
params() {
    echo "params magic=$(devmem_hex 0x20010) version=$(devmem_hex 0x20014) dram_clk=$(devmem_hex 0x20018) level=$(devmem_hex 0x2001c)"
    echo "params resume_entry=$(devmem_hex 0x20024)$(devmem_hex 0x20020) flags=$(devmem_hex 0x20028) status=$(devmem_hex 0x2002c)"
    echo "params stage=$(devmem_hex 0x20030) wake_irq=$(devmem_hex 0x20034) fail_reg=$(devmem_hex 0x20038) fail_info=$(devmem_hex 0x2003c)"
    echo "params dram_cfg=$(devmem_hex 0x20040) dram_mb=$(devmem_hex 0x20044) snapshot_n=$(devmem_hex 0x20048)"
}

# The CCU snapshot the stub takes at the last instruction before WFI, in the
# order src/clock.c reads it.
snapshot() {
    n=0
    for name in PLL_CPUX PLL_DDR0 PLL_DDR1 PLL_PERI0 PLL_PERI1 PLL_GPU0 \
                PLL_VIDEO0 PLL_VIDEO1 PLL_VIDEO2 PLL_VE PLL_DE PLL_AUDIO \
                CPUX_AXI PSI_AHB APB1 APB2 MBUS_CFG DE_BGR GPU_BGR VE_BGR \
                DRAM_CLK DRAM_BGR SMHC_BGR USB_BGR; do
        addr=$($BB printf '0x%08x' $((0x20050 + n * 4)))
        echo "asleep $name = $(devmem_hex "$addr")"
        n=$((n + 1))
    done
}

echo "state=[$($BB cat /sys/power/state)]"
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)]"
echo "suspend_stats success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail)"
echo "uptime=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"

echo "--- the sixteen RTC general purpose registers ---"
n=0
while [ "$n" -le 15 ]; do
    addr=$($BB printf '0x%08x' $((0x07000100 + n * 4)))
    echo "rtc-gp$n $addr = $(devmem_hex "$addr")"
    n=$((n + 1))
done

echo "--- SRAM A1, where the stub and its parameter block live ---"
echo "sram head = $(devmem_hex 0x20000) $(devmem_hex 0x20004) $(devmem_hex 0x20008) $(devmem_hex 0x2000c)"
params
echo "--- the snapshot area, before any sleep has written it ---"
snapshot

echo "--- the DRAM controller, as the stub will find it ---"
# mctl_ctl 0x047fb000: MSTR +0x000, STAT +0x004 (bits 2:0 the operating mode,
# 1 is normal), CLKEN +0x00c, PWRCTL +0x030 (bit 5 requests self-refresh),
# DFIMISC +0x1b0, DFISTAT +0x1bc, ADDRMAP1/6/7, SWCTL +0x320, SWSTAT +0x324.
for pair in \
    "0x047fb000 MSTR" "0x047fb004 STAT" "0x047fb00c CLKEN" "0x047fb030 PWRCTL" \
    "0x047fb1b0 DFIMISC" "0x047fb1bc DFISTAT" "0x047fb204 ADDRMAP1" \
    "0x047fb218 ADDRMAP6" "0x047fb21c ADDRMAP7" "0x047fb320 SWCTL" \
    "0x047fb324 SWSTAT" "0x047fa020 MAER0" "0x047fa024 MAER1" "0x047fa028 MAER2"; do
    set -- $pair
    echo "mctl $2 $1 = $(devmem_hex "$1")"
done

echo "--- the clocks, awake ---"
for pair in \
    "0x03001000 PLL_CPUX" "0x03001010 PLL_DDR0" "0x03001020 PLL_PERI0" \
    "0x03001040 PLL_VIDEO0" "0x03001060 PLL_DE" \
    "0x03001500 CPUX_AXI" "0x03001520 APB1" "0x03001524 APB2" \
    "0x03001540 MBUS_CFG" "0x03001800 DRAM_CLK" "0x0300180c DRAM_BGR"; do
    set -- $pair
    echo "ccu $2 $1 = $(devmem_hex "$1")"
done

echo "--- the watchdog, and whether its enable bit can be cleared ---"
irq_en=$(devmem_hex 0x030090a0)
cfg=$(devmem_hex 0x030090b4)
mode=$(devmem_hex 0x030090b8)
echo "wdog IRQ_EN=$irq_en CFG=$cfg MODE=$mode"
if [ "$mode" = "0x00000000" ] && [ "$irq_en" = "0x00000000" ]; then
    $BB devmem 0x030090b4 32 0x2 2>/dev/null
    $BB devmem 0x030090b8 32 0xb1 2>/dev/null
    armed=$(devmem_hex 0x030090b8)
    $BB devmem 0x030090b8 32 0x0 2>/dev/null
    cleared=$(devmem_hex 0x030090b8)
    $BB devmem 0x030090b4 32 "$cfg" 2>/dev/null
    $BB devmem 0x030090b8 32 "$mode" 2>/dev/null
    echo "wdog armed=$armed cleared=$cleared restored=$(devmem_hex 0x030090b8) cfg=$(devmem_hex 0x030090b4)"
else
    echo "wdog already in use by the OS, not touched"
fi

echo "--- does deep exist? ---"
if echo deep > /sys/power/mem_sleep 2>/tmp/deep-error; then
    echo "mem_sleep deep accepted, now [$($BB cat /sys/power/mem_sleep)]"
    echo s2idle > /sys/power/mem_sleep 2>/dev/null
    echo "mem_sleep put back to [$($BB cat /sys/power/mem_sleep)]"
else
    echo "mem_sleep deep refused: $($BB cat /tmp/deep-error)"
fi

card_check

# Experiment 30. One sleep with the controller and the PHY rebuilt, to find
# out whether anything comes back at all.
#
# `deep` goes through the SMC into TF-A, which copies our C stub into SRAM A1,
# turns the MMU off and branches to it. The stub saves the words the PHY's
# training will write over, asks the controller for self-refresh, shuts the DFI
# down, clears the controller's clock enables, gates and resets the DRAM clock
# path, stops PLL_DDR0, parks the CPU and the APBs on the 32 kHz clock and
# waits. Coming back, it runs U-Boot's own DRAM driver from SRAM to build the
# controller and the PHY again, puts the saved words back, and branches into
# BL31 -- which is in DRAM, so the first instruction fetched after that is
# itself the test.
#
# A resume that works is not enough: DRAM cells hold their charge for a good
# fraction of a second unrefreshed. The 256 MiB probe is the real check, and
# experiment 34's six-minute sleep is the one that settles it.
#
# Run on its own before anything is measured with it, because a suspend that
# does not come back looks exactly like a target that stopped answering.
#
# Where to look if it does not come back: this job cannot say anything, because
# the harness cuts the power at --run-seconds and the RTC registers go with it.
# Experiment 31 is the one that leaves evidence.
#
# The stage codes, all tagged 0xa5d5xxxx: 0x01 to 0x09 are TF-A's own, 0x09
# being the jump into SRAM; 0x20 to 0x2b the stub on the way down, 0x2b being
# the WFI; 0x2c to 0x2e on the way up; 0x30 to 0x3a inside the patched U-Boot
# driver, in the order it reaches them; 0x40 to 0x42 the stub finishing; and
# 0x08 written by TF-A after the warm boot, which means the whole round trip
# finished. 0xe1 to 0xe5 are the waits that ran out and 0xee is an exception
# inside the stub, with ESR and ELR in RTC registers 8 and 9.

devmem_hex() {
    $BB devmem "$1" 2>/dev/null || echo UNREADABLE
}

markers() {
    echo "el3 stage=$(devmem_hex 0x07000130) entered=$(devmem_hex 0x07000134) resumed=$(devmem_hex 0x07000138) wake_irq=$(devmem_hex 0x0700013c)"
    echo "stub fail_reg=$(devmem_hex 0x07000120) fail_info=$(devmem_hex 0x07000124) await=$(devmem_hex 0x07000128) debug=$(devmem_hex 0x0700012c)"
    echo "params status=$(devmem_hex 0x2002c) stage=$(devmem_hex 0x20030) wake_irq=$(devmem_hex 0x20034) fail=$(devmem_hex 0x2003c)@$(devmem_hex 0x20038)"
    echo "params dram_cfg=$(devmem_hex 0x20040) dram_mb=$(devmem_hex 0x20044) snapshot_n=$(devmem_hex 0x20048) level=$(devmem_hex 0x2001c)"
}

# What the CCU looked like at the last instruction before WFI. Nobody has seen
# this before: the kernel cannot read a register while the core is in WFI, and
# by the time it is back its drivers have turned their clocks on again.
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

dram_probe_mb=256

dram_fill() {
    $BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count="$dram_probe_mb" 2>/dev/null
    DRAM_PROBE_MD5="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
    echo "dram-probe ${dram_probe_mb}MiB md5=$DRAM_PROBE_MD5 free=$($BB grep MemFree /proc/meminfo)"
}

dram_check() {
    now="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
    if [ "$now" = "$DRAM_PROBE_MD5" ]; then
        echo "dram-check ok $now"
    else
        echo "dram-check FAILED wanted $DRAM_PROBE_MD5 got $now"
    fi
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)] online=$($BB cat /sys/devices/system/cpu/online)"
echo "before:"
markers
echo "mctl MSTR=$(devmem_hex 0x047fb000) STAT=$(devmem_hex 0x047fb004) CLKEN=$(devmem_hex 0x047fb00c) PWRCTL=$(devmem_hex 0x047fb030)"
card_check
dram_fill

rtc_sleep 40 mem deep

echo "after:"
markers
dram_check
echo "--- the CCU as the stub left it, at the instruction before WFI ---"
snapshot
echo "--- and as it is now, awake ---"
echo "mctl MSTR=$(devmem_hex 0x047fb000) STAT=$(devmem_hex 0x047fb004) CLKEN=$(devmem_hex 0x047fb00c) PWRCTL=$(devmem_hex 0x047fb030)"
echo "mctl DFIMISC=$(devmem_hex 0x047fb1b0) DFISTAT=$(devmem_hex 0x047fb1bc) SWCTL=$(devmem_hex 0x047fb320) SWSTAT=$(devmem_hex 0x047fb324)"
echo "mctl MAER0=$(devmem_hex 0x047fa020) MAER1=$(devmem_hex 0x047fa024) MAER2=$(devmem_hex 0x047fa028)"
echo "ccu PLL_CPUX=$(devmem_hex 0x03001000) PLL_DDR0=$(devmem_hex 0x03001010) CPUX_AXI=$(devmem_hex 0x03001500)"
echo "ccu APB1=$(devmem_hex 0x03001520) APB2=$(devmem_hex 0x03001524) MBUS=$(devmem_hex 0x03001540)"
echo "ccu DRAM_CLK=$(devmem_hex 0x03001800) DRAM_BGR=$(devmem_hex 0x0300180c)"
echo "rtc pad_hold 0x070001f4 = $(devmem_hex 0x070001f4)"
echo "wdog CFG=$(devmem_hex 0x030090b4) MODE=$(devmem_hex 0x030090b8)"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail)"
echo "freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq) uptime=$($BB cut -d' ' -f1 /proc/uptime)"
card_check

# Experiment 33. The DRAM controller and PHY after one deep resume, in a form
# that can be diffed between two firmwares.
#
# The working reference is on the card whenever we want it: `--suspend
# rocknix-deep` is the published implementation, built from source, and it
# resumes. So when ours does not come back, or comes back drawing the wrong
# current, the cheapest evidence available is to run this same job on both and
# compare the register dumps line for line. Everything it prints is a read;
# it changes nothing.
#
# One deep sleep of forty seconds, then the dump. The sleep is there so that
# what is read is a controller and a PHY that have been through a resume, not
# ones the SPL left at boot.
#
# The PHY registers are the ones U-Boot's own driver reads back during
# training, so they are known to exist and to be readable; the region is
# enabled by a write the driver makes and leaves set.

devmem_hex() {
    $BB devmem "$1" 2>/dev/null || echo UNREADABLE
}

dump() {
    echo "--- $1"
    echo "mctl MSTR=$(devmem_hex 0x047fb000) STAT=$(devmem_hex 0x047fb004) CLKEN=$(devmem_hex 0x047fb00c)"
    echo "mctl PWRCTL=$(devmem_hex 0x047fb030) PWRTMG=$(devmem_hex 0x047fb034) HWLPCTL=$(devmem_hex 0x047fb038)"
    echo "mctl RFSHCTL3=$(devmem_hex 0x047fb060) RFSHTMG=$(devmem_hex 0x047fb064)"
    echo "mctl INIT0=$(devmem_hex 0x047fb0d0) INIT1=$(devmem_hex 0x047fb0d4) INIT3=$(devmem_hex 0x047fb0dc)"
    echo "mctl RANKCTL=$(devmem_hex 0x047fb0f4) ZQCTL0=$(devmem_hex 0x047fb180)"
    echo "mctl DFITMG0=$(devmem_hex 0x047fb190) DFITMG1=$(devmem_hex 0x047fb194)"
    echo "mctl DFIUPD0=$(devmem_hex 0x047fb1a0) DFIMISC=$(devmem_hex 0x047fb1b0) DFISTAT=$(devmem_hex 0x047fb1bc)"
    echo "mctl DBICTL=$(devmem_hex 0x047fb1c0) ODTCFG=$(devmem_hex 0x047fb240) ODTMAP=$(devmem_hex 0x047fb244)"
    echo "mctl SWCTL=$(devmem_hex 0x047fb320) SWSTAT=$(devmem_hex 0x047fb324)"
    n=0
    while [ "$n" -le 8 ]; do
        addr=$($BB printf '0x%08x' $((0x047fb200 + n * 4)))
        echo "mctl ADDRMAP$n $addr = $(devmem_hex "$addr")"
        n=$((n + 1))
    done
    echo "mctl_com CR=$(devmem_hex 0x047fa000) UNK008=$(devmem_hex 0x047fa008) UNK014=$(devmem_hex 0x047fa014)"
    echo "mctl_com MAER0=$(devmem_hex 0x047fa020) MAER1=$(devmem_hex 0x047fa024) MAER2=$(devmem_hex 0x047fa028)"
    echo "mctl_com UNK500=$(devmem_hex 0x047fa500)"
    for pair in \
        "0x04800004 phy_0x04" "0x04800008 phy_0x08" "0x0480003c phy_0x3c" \
        "0x04800054 phy_0x54" "0x04800058 phy_0x58" "0x04800060 phy_0x60" \
        "0x04800144 phy_0x144" "0x0480014c phy_0x14c" "0x04800180 phy_0x180" \
        "0x04800184 phy_0x184" "0x04800188 phy_0x188" "0x04800190 phy_0x190" \
        "0x04800198 phy_0x198" "0x04800840 phy_0x840" "0x04800850 phy_0x850" \
        "0x04800898 phy_0x898" "0x048008e0 phy_0x8e0" "0x04800a40 phy_0xa40"; do
        set -- $pair
        echo "phy $2 $1 = $(devmem_hex "$1")"
    done
    for pair in \
        "0x03001000 PLL_CPUX" "0x03001010 PLL_DDR0" "0x03001020 PLL_PERI0" \
        "0x03001040 PLL_VIDEO0" "0x03001060 PLL_DE" "0x03001500 CPUX_AXI" \
        "0x03001510 PSI_AHB" "0x03001520 APB1" "0x03001524 APB2" \
        "0x03001540 MBUS_CFG" "0x03001800 DRAM_CLK" "0x0300180c DRAM_BGR"; do
        set -- $pair
        echo "ccu $2 $1 = $(devmem_hex "$1")"
    done
    echo "rtc pad_hold 0x070001f4 = $(devmem_hex 0x070001f4)"
}

dram_probe_mb=256

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)] uptime=$($BB cut -d' ' -f1 /proc/uptime)"
card_check
dump "before any sleep"

$BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count="$dram_probe_mb" 2>/dev/null
before="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
echo "dram-probe ${dram_probe_mb}MiB md5=$before"

rtc_sleep 40 mem deep

after="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
if [ "$after" = "$before" ]; then
    echo "dram-check ok $after"
else
    echo "dram-check FAILED wanted $before got $after"
fi
echo "el3 stage=$(devmem_hex 0x07000130) entered=$(devmem_hex 0x07000134) resumed=$(devmem_hex 0x07000138) wake_irq=$(devmem_hex 0x0700013c)"
dump "after one deep resume"
card_check

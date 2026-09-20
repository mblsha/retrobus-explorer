# Experiment 22. What the self-refresh firmware offers, before any sleep.
#
# The bootloader on the card now carries a BL31 whose SYSTEM_SUSPEND copies a
# stub into SRAM A1 and runs the wait from there with the LPDDR4 in
# self-refresh. This job does not sleep. It costs one boot and answers the
# four questions that decide whether the next experiment is worth starting,
# and the two that decide how the DRAM-integrity check has to be written.
#
#  1. Did `deep` arrive? Only a PSCI that advertises SYSTEM_SUSPEND gets it.
#  2. Are all sixteen RTC general purpose registers free? The stub reports
#     through 12 to 15 and, on the exception path, writes ESR and ELR into 14
#     and 15. Anything the boot ROM or the vendor firmware uses is not free,
#     and a register that reads back non-zero on a board that has never
#     suspended is a register to leave alone.
#  3. Is the DRAM controller where the stub expects it -- normal operating
#     mode, self-refresh not already requested? STAT and PWRCTL are read
#     through /dev/mem at the addresses the stub writes.
#  4. Can the watchdog's enable bit be cleared again? The manual calls it
#     R/W1S, and the stub arms the watchdog around the two moments it touches
#     DRAM and must be able to disarm it before a wait that is longer than any
#     watchdog interval. This is tested with WDOG_CFG set to "only interrupt",
#     so a failure to disable cannot reset the board, and only if the OS is
#     not already using the watchdog.
#  5. How much memory is there, and how fast is md5sum? Those two size the
#     tmpfs probe that later jobs use to prove the DRAM contents survived.
#  6. Which PLLs are running? Evidence for what a later rung could stop.

devmem_hex() {
    $BB devmem "$1" 2>/dev/null || echo UNREADABLE
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

echo "--- the DRAM controller, as the stub will find it ---"
# mctl_ctl 0x047fb000: STAT +0x004 (bits 2:0 are the operating mode, 1 is
# normal), PWRCTL +0x030 (bit 5 is the software self-refresh request).
echo "mctl_ctl STAT   0x047fb004 = $(devmem_hex 0x047fb004)"
echo "mctl_ctl PWRCTL 0x047fb030 = $(devmem_hex 0x047fb030)"
echo "mctl_ctl SWCTL  0x047fb320 = $(devmem_hex 0x047fb320)"
echo "mctl_ctl SWSTAT 0x047fb324 = $(devmem_hex 0x047fb324)"
echo "mctl_com MAER0  0x047fa020 = $(devmem_hex 0x047fa020)"
echo "mctl_com MAER1  0x047fa024 = $(devmem_hex 0x047fa024)"
echo "mctl_com MAER2  0x047fa028 = $(devmem_hex 0x047fa028)"

echo "--- the clocks the stub touches, awake ---"
for pair in \
    "0x03001000 PLL_CPUX" "0x03001010 PLL_DDR0" "0x03001018 PLL_DDR1" \
    "0x03001020 PLL_PERI0" "0x03001028 PLL_PERI1" "0x03001030 PLL_GPU0" \
    "0x03001040 PLL_VIDEO0" "0x03001048 PLL_VIDEO1" "0x03001050 PLL_VIDEO2" \
    "0x03001058 PLL_VE" "0x03001060 PLL_DE" \
    "0x03001500 CPUX_AXI" "0x03001540 MBUS_CFG" \
    "0x03001800 DRAM_CLK" "0x0300180c DRAM_BGR"; do
    set -- $pair
    echo "ccu $2 $1 = $(devmem_hex "$1")"
done

echo "--- the watchdog, and whether its enable bit can be cleared ---"
# H616 manual 3.6.6.9 to 3.6.6.13: IRQ_EN 0x030090a0, CTRL 0x030090b0,
# CFG 0x030090b4 (01 whole system, 10 only interrupt), MODE 0x030090b8
# (7:4 interval, bit 0 enable, documented R/W1S).
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

echo "--- memory, and how long a checksum of it takes ---"
$BB grep -E '^(MemTotal|MemFree|MemAvailable|Cached)' /proc/meminfo
$BB df -k /tmp
for mb in 16 64; do
    t0=$(rtc_now)
    $BB dd if=/dev/urandom of=/tmp/probe bs=1M count=$mb 2>/dev/null
    t1=$(rtc_now)
    sum=$($BB md5sum /tmp/probe | $BB cut -d' ' -f1)
    t2=$(rtc_now)
    echo "probe ${mb}MiB fill=$((t1 - t0))s md5=$((t2 - t1))s $sum"
    $BB rm -f /tmp/probe
done
$BB grep -E '^(MemFree|MemAvailable)' /proc/meminfo

echo "--- does deep exist? ---"
if echo deep > /sys/power/mem_sleep 2>/tmp/deep-error; then
    echo "mem_sleep deep accepted, now [$($BB cat /sys/power/mem_sleep)]"
    echo s2idle > /sys/power/mem_sleep 2>/dev/null
    echo "mem_sleep put back to [$($BB cat /sys/power/mem_sleep)]"
else
    echo "mem_sleep deep refused: $($BB cat /tmp/deep-error)"
fi

card_check

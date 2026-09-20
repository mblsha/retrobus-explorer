# Experiment 23. One self-refresh sleep, to find out whether DRAM comes back.
#
# The first thing the SRAM stub has to survive. `deep` goes through the SMC
# into TF-A, which copies the stub into SRAM A1, turns the MMU off, calls it,
# and from there on nothing in DRAM is running: the stub stops the MBUS
# masters, asks the controller for software self-refresh, waits for STAT to
# say so, stops PLL_CPUX and waits in WFI. Coming back it relocks PLL_CPUX,
# clears the self-refresh request, waits for normal operating mode, reopens
# the masters and returns into BL31 -- which is in DRAM, so the first
# instruction fetched after that return is itself a test.
#
# A resume that works is not enough. DRAM cells hold their charge for a good
# fraction of a second unrefreshed, so a suspend that never really refreshed
# anything can still come back looking healthy. This job therefore fills a
# large tmpfs file with random bytes, records its md5, sleeps, and checks the
# md5 again: pages that only the DRAM was holding, read back after the sleep.
#
# Run on its own before anything is measured with it, because a suspend that
# does not come back looks exactly like a target that stopped answering.
#
# EL3's own account, in the RTC general purpose registers: stage 0xa5d50008 is
# written by the PSCI resume hook after the warm boot, so it means the whole
# round trip finished. The stage codes in between belong to the stub, and the
# ones that matter if this goes wrong are 0xa5d500e1 (the controller refused
# self-refresh, and the stub returned without sleeping), 0xa5d500e2 (it would
# not come out again), 0xa5d500e3 (the SWCTL commit never completed) and
# 0xa5d500ee (an exception inside the stub, with ESR in register 14 and ELR in
# 15). The last four end in a watchdog reset, and the registers survive it.

markers() {
    echo "el3 stage=$($BB devmem 0x07000130 2>/dev/null) entered=$($BB devmem 0x07000134 2>/dev/null) resumed=$($BB devmem 0x07000138 2>/dev/null) wake_irq=$($BB devmem 0x0700013c 2>/dev/null)"
}

dram_probe_mb=192

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
echo "mctl STAT=$($BB devmem 0x047fb004) PWRCTL=$($BB devmem 0x047fb030)"
card_check
dram_fill

rtc_sleep 40 mem deep

echo "after:"
markers
dram_check
echo "mctl STAT=$($BB devmem 0x047fb004) PWRCTL=$($BB devmem 0x047fb030)"
echo "mctl MAER0=$($BB devmem 0x047fa020) MAER1=$($BB devmem 0x047fa024) MAER2=$($BB devmem 0x047fa028)"
echo "ccu PLL_CPUX=$($BB devmem 0x03001000) PLL_DDR0=$($BB devmem 0x03001010) CPUX_AXI=$($BB devmem 0x03001500)"
echo "ccu MBUS=$($BB devmem 0x03001540) DRAM_CLK=$($BB devmem 0x03001800) DRAM_BGR=$($BB devmem 0x0300180c)"
echo "wdog CFG=$($BB devmem 0x030090b4) MODE=$($BB devmem 0x030090b8)"
echo "freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq) uptime=$($BB cut -d' ' -f1 /proc/uptime)"
card_check

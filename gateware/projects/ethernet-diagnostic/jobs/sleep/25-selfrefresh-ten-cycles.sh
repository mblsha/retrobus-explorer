# Experiment 25. Ten consecutive self-refresh sleeps in one boot.
#
# The same shape as experiments 17 and 21, which did this for s2idle and for
# the DRAM-less suspend. One boot rather than ten, because ten boots would put
# seven milliamps of between-boot noise between the first cycle and the last
# and would say nothing about whether the tenth suspend in a row still works,
# which is the thing a timed sleep has to do.
#
# What makes a cycle count here: the RTC's own account of the sleep against
# the forty seconds requested, `suspend_stats/success` up by one with `fail`
# unchanged, a card check after the resume, EL3's counters up by one each with
# a stage of 0xa5d50008, and the DRAM probe's md5 unchanged. The probe is
# filled once at the top; a tenth check that still matches is ten sleeps'
# worth of self-refresh on the same pages.
#
# Three seconds of quiet between cycles, because the host reads the card's
# passive trace five times a second and a wake followed immediately by the
# next suspend puts the end of one window and the start of the next into a
# single poll.

markers() {
    echo "el3 stage=$($BB devmem 0x07000130 2>/dev/null) entered=$($BB devmem 0x07000134 2>/dev/null) resumed=$($BB devmem 0x07000138 2>/dev/null) wake_irq=$($BB devmem 0x0700013c 2>/dev/null)"
}

dram_probe_mb=256

dram_fill() {
    $BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count="$dram_probe_mb" 2>/dev/null
    DRAM_PROBE_MD5="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
    echo "dram-probe ${dram_probe_mb}MiB md5=$DRAM_PROBE_MD5"
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
echo deep > /sys/power/mem_sleep 2>/dev/null
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)]"
markers
card_check
dram_fill

n=1
while [ "$n" -le 10 ]; do
    echo "=== cycle $n"
    rtc_sleep 40 mem deep
    markers
    dram_check
    echo "cycle $n ended at uptime $($BB cut -d' ' -f1 /proc/uptime) rtc $(rtc_now) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    n=$((n + 1))
    [ "$n" -le 10 ] && $BB sleep 3
done

echo "=== ten cycles done"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail) last_failed_dev=[$($BB cat /sys/power/suspend_stats/last_failed_dev)]"
markers
echo "mctl STAT=$($BB devmem 0x047fb004) PWRCTL=$($BB devmem 0x047fb030)"
card_check

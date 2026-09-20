# Experiment 24. Self-refresh against s2idle, A B B A A B in one boot.
#
# The same shape as experiment 20, which priced the DRAM-less suspend, so the
# two can be read against each other with the same reference in the same
# place: A is `mem` resolved to s2idle, B is `mem` resolved to `deep`, which
# on this firmware is the SRAM stub with the LPDDR4 in self-refresh. The
# `powersave` governor is set once at the top and is in force in both arms,
# because it is worth eleven milliamps on its own and would otherwise be the
# only thing this measured.
#
# Alternating inside one boot is the only comparison this bench believes: two
# cold boots of the same state differ by about seven milliamps, and the
# current also climbs about one and a half per cycle through a boot.
#
# The DRAM probe is filled once, before the first sleep, and checked after
# every one of the six. An s2idle sleep does not touch DRAM at all, so the
# three A checks are the control: they say the probe survives being read six
# times, and only the three B checks say anything about self-refresh.
#
# Six labels in this order: A1 B1 B2 A2 A3 B3.

markers() {
    echo "el3 stage=$($BB devmem 0x07000130 2>/dev/null) entered=$($BB devmem 0x07000134 2>/dev/null) resumed=$($BB devmem 0x07000138 2>/dev/null) wake_irq=$($BB devmem 0x0700013c 2>/dev/null)"
}

dram_probe_mb=192

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
markers
card_check
dram_fill

for arm in s2idle deep deep s2idle s2idle deep; do
    echo "=== $arm"
    rtc_sleep 40 mem "$arm"
    markers
    dram_check
    $BB sleep 3
done

echo "=== six sleeps done"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail) last_failed_dev=[$($BB cat /sys/power/suspend_stats/last_failed_dev)]"
markers
card_check

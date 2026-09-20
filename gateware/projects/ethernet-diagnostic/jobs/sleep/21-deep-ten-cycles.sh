# Experiment 20. Ten consecutive deep sleeps in one boot.
#
# The same shape as experiment 17, which did this for s2idle, so the two can
# be read against each other: one boot rather than ten, because ten boots
# would put seven milliamps of between-boot noise between the first cycle and
# the last and would say nothing about whether the tenth suspend in a row
# still works, which is the thing a timed sleep has to do.
#
# What makes a cycle count: the RTC's own account of the sleep against the
# forty seconds requested, `suspend_stats/success` up by one with `fail`
# unchanged, and a card check after the resume -- all three printed by
# `rtc_sleep` itself. On top of those, EL3's own counters have to agree: one
# more suspend entered and one more resume completed per cycle, and a stage
# code of 0xa5d50008, which is only written after the warm boot has handed
# control back to the PSCI resume path.
#
# Three seconds of quiet between cycles, because the host reads the card's
# passive trace five times a second and a wake followed immediately by the
# next suspend puts the end of one window and the start of the next into a
# single poll.

markers() {
    echo "el3 stage=$($BB devmem 0x07000130 2>/dev/null) entered=$($BB devmem 0x07000134 2>/dev/null) resumed=$($BB devmem 0x07000138 2>/dev/null) wake_irq=$($BB devmem 0x0700013c 2>/dev/null)"
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo deep > /sys/power/mem_sleep 2>/dev/null
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)]"
markers
card_check

n=1
while [ "$n" -le 10 ]; do
    echo "=== cycle $n"
    rtc_sleep 40 mem deep
    markers
    echo "cycle $n ended at uptime $($BB cut -d' ' -f1 /proc/uptime) rtc $(rtc_now) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    n=$((n + 1))
    [ "$n" -le 10 ] && $BB sleep 3
done

echo "=== ten cycles done"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail) last_failed_dev=[$($BB cat /sys/power/suspend_stats/last_failed_dev)]"
markers
card_check

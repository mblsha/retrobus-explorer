# Experiment 17. Ten consecutive sleep/wake cycles in the kept configuration,
# in one boot.
#
# One boot rather than ten, deliberately: ten boots would put seven milliamps
# of between-boot noise between the first cycle and the last and would say
# nothing about whether the tenth suspend in a row still works, which is the
# thing a timed sleep has to do. Each `rtc_sleep` arms the alarm, marks the
# card, suspends, and on waking reports the RTC's account of how long it
# really slept, the suspend counters either side, and a card check. The host
# measures each of the ten as its own window.
#
# Three seconds of quiet between cycles, because the host reads the card's
# passive trace five times a second and a wake followed immediately by the
# next suspend puts the end of one window and the start of the next into a
# single poll.

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
for r in /sys/class/regulator/*; do
    [ -e "$r" ] || continue
    [ "$($BB cat $r/name 2>/dev/null)" = "vdd-cpu" ] && echo "vdd-cpu $($BB cat $r/state) $($BB cat $r/microvolts)"
done
card_check

n=1
while [ "$n" -le 10 ]; do
    echo "=== cycle $n"
    rtc_sleep 40 freeze
    echo "cycle $n ended at uptime $($BB cut -d' ' -f1 /proc/uptime) rtc $(rtc_now) governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    n=$((n + 1))
    [ "$n" -le 10 ] && $BB sleep 3
done

echo "=== ten cycles done"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail) last_failed_dev=[$($BB cat /sys/power/suspend_stats/last_failed_dev)]"
card_check

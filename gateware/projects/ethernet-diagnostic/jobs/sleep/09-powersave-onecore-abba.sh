# Experiment 9. The `powersave` governor and three offlined cores together,
# alternated with the default in the drift-cancelling order.
#
# This combination is the one observation worth chasing. Experiment 6 measured
# it at 109 mA against 121 for the default in the same boot, but it was the
# third of four sleeps in a run whose control came back five and a half
# milliamps high, and experiment 7 then showed that offlining the cores on its
# own, with the governor left at `performance`, is worth nothing at all. So
# either the two together do something neither does alone, or the 109 was a
# well-placed sleep in a drifting run. Six sleeps in the order A B B A A B
# decide it.

set_state() {
    if [ "$1" = B ]; then
        for p in /sys/devices/system/cpu/cpufreq/policy*; do
            [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
        done
        for n in 1 2 3; do echo 0 > "/sys/devices/system/cpu/cpu$n/online" 2>/dev/null; done
    else
        for n in 1 2 3; do echo 1 > "/sys/devices/system/cpu/cpu$n/online" 2>/dev/null; done
        for p in /sys/devices/system/cpu/cpufreq/policy*; do
            [ -e "$p/scaling_governor" ] && echo performance > "$p/scaling_governor" 2>/dev/null
        done
    fi
    echo "online=$($BB cat /sys/devices/system/cpu/online) governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        [ "$($BB cat $r/name 2>/dev/null)" = "vdd-cpu" ] && echo "vdd-cpu $($BB cat $r/state) $($BB cat $r/microvolts)"
    done
}

for step in A B B A A B; do
    echo "=== sleep $step"
    set_state "$step"
    $BB sleep 1
    rtc_sleep 40 freeze
    $BB sleep 3
done

set_state A
echo "=== six sleeps done"

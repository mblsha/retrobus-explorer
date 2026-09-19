# Experiment 10. The `powersave` governor on its own, with all four cores
# online, alternated with the default.
#
# Experiment 9 measured the governor and three offlined cores together at
# about eleven milliamps below the default, three times over. Experiment 7
# measured offlining the cores on its own, at `performance`, at nothing. This
# asks whether the governor is the whole of it, which decides whether the best
# configuration has to offline anything at all -- offlining costs a second of
# hotplug at each end and puts three PSCI CPU_OFF calls between the job and
# its wake, and is not worth carrying if the clock is doing the work.
#
# `powersave` takes the policy to 480 MHz, and the operating point table takes
# vdd-cpu from 1.1 V to 0.9 V with it; that rail is the thing the milliamps
# are expected to come from.

set_state() {
    if [ "$1" = B ]; then
        want=powersave
    else
        want=performance
    fi
    for p in /sys/devices/system/cpu/cpufreq/policy*; do
        [ -e "$p/scaling_governor" ] && echo "$want" > "$p/scaling_governor" 2>/dev/null
    done
    line="online=$($BB cat /sys/devices/system/cpu/online) governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        [ "$($BB cat $r/name 2>/dev/null)" = "vdd-cpu" ] && line="$line vdd-cpu=$($BB cat $r/microvolts)"
    done
    echo "$line"
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

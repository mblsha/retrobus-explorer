# Experiment 7. Offlining cpus 1-3, alternated with the default three times in
# one boot.
#
# Experiment 6 measured 121, 119, 109 and 126 for default, powersave,
# powersave-with-one-core and default again: the control came back five and a
# half milliamps above where it started, so a single before/after in this boot
# would have been reading drift as much as a knob. Alternating gives each
# measurement of the knob two neighbours to be compared against.
#
# The governor stays at `performance` throughout so that what is measured here
# is the cores and nothing else.

offline() {
    for n in 1 2 3; do
        echo "$1" > "/sys/devices/system/cpu/cpu$n/online" 2>/dev/null
    done
    echo "online=$($BB cat /sys/devices/system/cpu/online) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
}

for round in 1 2 3; do
    echo "=== round $round, all four cores"
    offline 1
    rtc_sleep 40 freeze
    $BB sleep 3
    echo "=== round $round, cores 1-3 offline"
    offline 0
    rtc_sleep 40 freeze
    echo "online after the sleep=$($BB cat /sys/devices/system/cpu/online)"
    $BB sleep 3
done

offline 1
echo "=== six sleeps done"
$BB grep -E 'arch_timer|i2c|ths' /proc/interrupts

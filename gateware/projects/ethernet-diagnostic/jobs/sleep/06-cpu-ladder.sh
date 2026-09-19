# Experiment 6. The CPU half, as a ladder that comes back down.
#
# Four sleeps in one boot: the default, then the `powersave` governor, then
# three of the four cores offlined on top of it, then everything put back. The
# last sleep is the control. Between-boot noise is about seven milliamps and
# two sleeps in one boot differ by about three, so a knob is only believed if
# the return to the default comes back to where it started.
#
# Offlining goes through PSCI CPU_OFF, which is the only way this kernel has of
# powering a core down: there is no cpuidle driver and no `cpus/idle-states`
# in the device tree, so an online core in s2idle only ever sits in WFI.

cpus() {
    echo "   online=$($BB cat /sys/devices/system/cpu/online) governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        case "$($BB cat $r/name 2>/dev/null)" in
            vdd-cpu|cpusldo) echo "   $($BB cat $r/name) $($BB cat $r/state) $($BB cat $r/microvolts)" ;;
        esac
    done
}

echo "=== step A: as the kernel left it"
cpus
rtc_sleep 40 freeze
$BB sleep 3

echo "=== step B: powersave governor"
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] || continue
    echo powersave > "$p/scaling_governor" 2>/dev/null
done
cpus
rtc_sleep 40 freeze
$BB sleep 3

echo "=== step C: cpus 1-3 offline as well"
for n in 1 2 3; do
    echo 0 > "/sys/devices/system/cpu/cpu$n/online" 2>/dev/null
    echo "   cpu$n online=$($BB cat /sys/devices/system/cpu/cpu$n/online)"
done
cpus
rtc_sleep 40 freeze
echo "   online after the sleep=$($BB cat /sys/devices/system/cpu/online)"
$BB sleep 3

echo "=== step A': everything back"
for n in 1 2 3; do
    echo 1 > "/sys/devices/system/cpu/cpu$n/online" 2>/dev/null
done
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] || continue
    echo performance > "$p/scaling_governor" 2>/dev/null
done
cpus
rtc_sleep 40 freeze

echo "=== all four steps woke"
$BB grep -E 'arch_timer|i2c|ths' /proc/interrupts
$BB dmesg | $BB tail -n 12

# The best sleep configuration this bench found, as a job that can be sourced
# from another job or run on its own.
#
# It is one knob. Twelve experiments on 2026-09-20 measured every other
# runtime knob sysfs offers on this kernel -- offlining three of the four
# cores, unbinding the two card controllers that are not the root device, the
# GPU, both audio codecs, the whole display pipeline, the PMIC's pollers, the
# SoC's ADC, the thermal sensor, the backlight PWM, the watchdog, the spare
# UART and the eFuse, and turning both LEDs off -- and none of them moved the
# sleeping current by more than the few milliamps two sleeps in one boot
# differ by. The governor moved it by eleven.
#
# `powersave` pins every cpufreq policy at the bottom of its ladder, 480 MHz,
# and the operating point table takes vdd-cpu from 1.1 V to 0.9 V with it.
# That rail is where the milliamps come from; the clock itself is not the
# point, since a suspended CPU is not running anyway.
#
# Set it before suspending. It survives a resume -- the governor is policy,
# not device state -- so it only has to be set once per boot.

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] || continue
    echo powersave > "$p/scaling_governor" 2>/dev/null
done

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] || continue
    echo "best-config $($BB basename $p) governor=$($BB cat $p/scaling_governor) freq=$($BB cat $p/scaling_cur_freq)"
done
for r in /sys/class/regulator/*; do
    [ -e "$r" ] || continue
    [ "$($BB cat $r/name 2>/dev/null)" = "vdd-cpu" ] || continue
    echo "best-config vdd-cpu $($BB cat $r/state) $($BB cat $r/microvolts)"
done

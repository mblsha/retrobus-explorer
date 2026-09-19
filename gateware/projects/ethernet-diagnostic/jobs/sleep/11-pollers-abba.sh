# Experiment 11. Everything that polls, plus the two LEDs, on top of the
# `powersave` governor that experiment 10 kept.
#
# What is left running while the target sleeps and is not a rail: the PMIC's
# ADC and its battery and USB power-supply drivers, the SoC's own general
# purpose ADC, the thermal sensor behind four step_wise thermal zones, and the
# green power LED, which is lit. The PMIC drivers are the interesting ones,
# because the only interrupt that counts up appreciably across a sleep is
# `mv64xxx_i2c`, about two hundred and seventy of them per forty-second
# suspend, and the PMIC is what is on that bus.
#
# A screen, not five experiments: these are all small and all in the same
# place, and if switching the lot off does not move the current then none of
# them will separately.

TARGETS="platform:axp20x-adc:axp717-adc
platform:axp20x-battery-power-supply:axp20x-battery-power-supply
platform:axp20x-usb-power-supply:axp20x-usb-power-supply
platform:sun20i-gpadc:5070000.adc
platform:sun8i-thermal:5070400.thermal-sensor"

apply() {
    # apply off | on
    for t in $TARGETS; do
        bus=$(echo "$t" | $BB cut -d: -f1)
        drv=$(echo "$t" | $BB cut -d: -f2)
        dev=$(echo "$t" | $BB cut -d: -f3)
        if [ "$1" = off ]; then
            echo "$dev" > "/sys/bus/$bus/drivers/$drv/unbind" 2>/dev/null
        else
            echo "$dev" > "/sys/bus/$bus/drivers/$drv/bind" 2>/dev/null
        fi
    done
    for l in /sys/class/leds/*; do
        [ -e "$l" ] || continue
        if [ "$1" = off ]; then echo 0 > "$l/brightness" 2>/dev/null
        else echo "$($BB cat $l/max_brightness)" > "$l/brightness" 2>/dev/null; fi
    done
    bound=""
    for t in $TARGETS; do
        bus=$(echo "$t" | $BB cut -d: -f1)
        drv=$(echo "$t" | $BB cut -d: -f2)
        dev=$(echo "$t" | $BB cut -d: -f3)
        [ -e "/sys/bus/$bus/drivers/$drv/$dev" ] && bound="$bound $dev"
    done
    leds=""
    for l in /sys/class/leds/*; do
        [ -e "$l" ] || continue
        leds="$leds $($BB basename $l)=$($BB cat $l/brightness)"
    done
    echo "bound:$bound leds:$leds zones=$($BB ls /sys/class/thermal 2>/dev/null | $BB tr '\n' ' ')"
}

# The governor is the kept configuration this experiment starts from.
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"

for step in A B B A A B; do
    echo "=== sleep $step"
    if [ "$step" = A ]; then apply on; else apply off; fi
    $BB sleep 1
    rtc_sleep 40 freeze
    echo "i2c=$($BB grep mv64xxx /proc/interrupts | $BB tr -s ' ' | $BB cut -d' ' -f3)"
    $BB sleep 3
done

apply on
echo "=== six sleeps done"

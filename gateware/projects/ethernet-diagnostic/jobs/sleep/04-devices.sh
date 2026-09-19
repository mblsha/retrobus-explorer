# Experiment 4. The device half of the screen: everything that is switched off
# by unbinding a driver, and the two LEDs. No CPU knob here.
#
# The screen in experiment 3 applied the device knobs and the CPU knobs
# together and the target never woke, so the two halves are measured apart.
# This is the half that leaves all four CPUs online at 1416 MHz.
#
# Reference sleep, then the knobs, then two more sleeps: the second pair says
# whether whatever the first pair showed repeats inside the same boot.

unbind() {
    if [ ! -e "/sys/bus/$1/drivers/$2/$3" ]; then
        echo "unbind $3: not bound to $2"
        return
    fi
    if echo "$3" > "/sys/bus/$1/drivers/$2/unbind" 2>/tmp/unbind-error; then
        echo "unbind $3 from $2: ok"
    else
        echo "unbind $3 from $2: FAILED $($BB cat /tmp/unbind-error)"
    fi
}

state() {
    echo "-- state $1"
    echo "   online-cpus=$($BB cat /sys/devices/system/cpu/online) governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        [ "$($BB cat $r/state 2>/dev/null)" = "enabled" ] || continue
        echo "   reg $($BB cat $r/name 2>/dev/null) $($BB cat $r/microvolts 2>/dev/null) users=$($BB cat $r/num_users 2>/dev/null)"
    done
}

state before
rtc_sleep 40 freeze
$BB sleep 2

echo "== applying the device knobs"
for l in /sys/class/leds/*; do
    [ -e "$l" ] || continue
    echo 0 > "$l/brightness" 2>/dev/null
    echo "led $($BB basename $l) now $($BB cat $l/brightness 2>/dev/null)"
done
unbind spi panel-mipi spi0.0
unbind platform panfrost 1800000.gpu
unbind platform sun4i-codec 5096000.codec
unbind platform sunxi-mmc 4021000.mmc
unbind platform sunxi-mmc 4022000.mmc
state applied
card_check
$BB sleep 3

rtc_sleep 40 freeze
state "after sleep 2"
$BB sleep 5

rtc_sleep 40 freeze
state "after sleep 3"
echo "-- log tail"
$BB dmesg | $BB tail -n 16

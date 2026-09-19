# Experiment 3. Every runtime knob at once, paired inside one boot.
#
# A screen rather than a measurement: if switching off the GPU, the codec, the
# two card controllers that are not the root device, the panel's SPI poller,
# the power LED, three of the four CPUs and the CPU clock together does not
# move the sleeping current by more than the few milliamps two identical
# sleeps in one boot differ by, then none of them separately will, and fifteen
# experiments are saved. If it does move, the next experiments bisect it.
#
# 4020000.mmc is deliberately absent from the list. It is the emulated card
# and the root device, and a gain that needed it unbound would not survive a
# move to a real SD card.

unbind() {
    # unbind BUS DRIVER DEVICE -- say what happened, never fail the job
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

echo "== applying every knob"
for l in /sys/class/leds/*; do
    [ -e "$l" ] || continue
    echo 0 > "$l/brightness" 2>/dev/null
    echo "led $($BB basename $l) now $($BB cat $l/brightness 2>/dev/null)"
done
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] || continue
    echo powersave > "$p/scaling_governor" 2>/dev/null
    echo "governor $($BB basename $p) now $($BB cat $p/scaling_governor) at $($BB cat $p/scaling_cur_freq)"
done
unbind spi panel-mipi spi0.0
unbind platform panfrost 1800000.gpu
unbind platform sun4i-codec 5096000.codec
unbind platform sunxi-mmc 4021000.mmc
unbind platform sunxi-mmc 4022000.mmc
for n in 1 2 3; do
    echo 0 > "/sys/devices/system/cpu/cpu$n/online" 2>/dev/null
    echo "cpu$n online now $($BB cat /sys/devices/system/cpu/cpu$n/online)"
done
state applied
card_check
$BB sleep 3

rtc_sleep 40 freeze
state "after sleep 2"
$BB sleep 5

rtc_sleep 40 freeze
state "after sleep 3"
echo "-- log tail"
$BB dmesg | $BB tail -n 20

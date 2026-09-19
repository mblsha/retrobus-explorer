# Experiment 5. The device knobs one at a time, each added to the last, with a
# sleep after every step.
#
# Experiment 4 applied five of them at once and the target never woke, so a
# ladder is worth more than a bisection: every rung that wakes is a
# measurement of what that knob added, and the rung that does not wake names
# the knob that costs the wake. The order is the one this note would guess:
# the two card controllers that are not the root device first, because they
# each own a regulator and are the least entangled, then the GPU, then the
# audio codec, then the panel's SPI driver, which is the one the display
# pipeline still holds a reference to.
#
# Everything before each sleep is flushed to the card by rtc_sleep itself, so
# a rung that hangs still reports every rung under it.

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

rails() {
    on=""
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        [ "$($BB cat $r/state 2>/dev/null)" = "enabled" ] || continue
        on="$on $($BB cat $r/name 2>/dev/null)"
    done
    echo "rails$on"
}

echo "=== rung 0: nothing"
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== rung 1: leds off, both non-root card controllers unbound"
for l in /sys/class/leds/*; do
    [ -e "$l" ] || continue
    echo 0 > "$l/brightness" 2>/dev/null
done
unbind platform sunxi-mmc 4021000.mmc
unbind platform sunxi-mmc 4022000.mmc
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== rung 2: panfrost unbound"
unbind platform panfrost 1800000.gpu
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== rung 3: audio codec unbound"
unbind platform sun4i-codec 5096000.codec
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== rung 4: panel-mipi unbound"
unbind spi panel-mipi spi0.0
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== all rungs woke"
$BB dmesg | $BB tail -n 16

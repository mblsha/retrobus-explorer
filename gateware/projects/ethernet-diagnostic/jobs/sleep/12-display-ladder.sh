# Experiment 12. The display pipeline, taken down from the top.
#
# Experiment 5 showed that unbinding `panel-mipi` from spi0.0 costs the wake:
# the panel's driver goes while the DRM device still holds a reference to it,
# and the resume never finishes. So this takes the master away first --
# `display-engine`, which is what `sun4i-drm` binds -- and only then the
# pieces underneath, which by that point nothing points at.
#
# The panel is already asleep here (`echo 4 > /sys/class/graphics/fb0/blank`,
# which is how init leaves it in job-runner mode) and the backlight is off, so
# what is left to save is whatever the display engine, the two TCONs, the two
# mixers and the HDMI PHY cost while idle. `vdd-lcd` is the visible part: it
# is disabled at boot, and every resume turns it back on.
#
# A ladder rather than an alternation, because this cannot be undone -- there
# is no putting a DRM master back -- and a rung that hangs is the answer to
# whether it can be done at all.

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
    echo "rails$on drm=$($BB ls /sys/class/drm 2>/dev/null | $BB tr '\n' ' ') fb=$($BB ls /sys/class/graphics 2>/dev/null | $BB tr '\n' ' ')"
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)"

echo "=== rung 0: the kept configuration, display as it is"
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== rung 1: the DRM master unbound"
unbind platform sun4i-drm display-engine
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== rung 2: the pieces underneath it as well"
unbind spi panel-mipi spi0.0
unbind platform sun8i-dw-hdmi 6000000.hdmi
unbind platform sun8i-hdmi-phy 6010000.hdmi-phy
unbind platform sun4i-tcon 6511000.lcd-controller
unbind platform sun4i-tcon 6515000.lcd-controller
unbind platform sun8i-mixer 1280000.mixer
unbind platform sun8i-mixer 12a0000.mixer
unbind platform sun8i-tcon-top 6510000.tcon-top
unbind platform sun50i-planes 1100000.planes
unbind platform sun50i-de2-bus 1000000.bus
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== rung 2 again"
rails
rtc_sleep 40 freeze

echo "=== all rungs woke"
$BB dmesg | $BB tail -n 14

# Experiment 1. Two identical sleeps in one boot, and an inventory of what is
# still switched on while the target is dark.
#
# The pair comes first in importance: between-boot noise is about 7 mA, so
# every later experiment is a before/after inside one boot, and this says what
# that design's own repeatability is. The probe is printed before the pair so
# that nothing at all sits between the two sleeps.
#
# The interrupt counters either side of a sleep are the cheap instrument this
# kernel still has: in s2idle every interrupt wakes a CPU, so the delta across
# a suspend names whatever is keeping the thing busy while it is supposed to
# be doing nothing.

echo "== identity"
echo "uptime=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo "online-cpus=$($BB cat /sys/devices/system/cpu/online)"

echo "== leds"
for l in /sys/class/leds/*; do
    [ -e "$l" ] || continue
    echo "led $($BB basename $l) brightness=$($BB cat $l/brightness 2>/dev/null) max=$($BB cat $l/max_brightness 2>/dev/null) trigger=$($BB sed -n 's/.*\[\([^]]*\)\].*/\1/p' $l/trigger 2>/dev/null)"
done

echo "== platform drivers and their devices"
for d in /sys/bus/platform/drivers/*; do
    [ -d "$d" ] || continue
    devs=""
    for e in "$d"/*; do
        [ -L "$e" ] || continue
        devs="$devs $($BB basename $e)"
    done
    [ -n "$devs" ] && echo "driver $($BB basename $d) <-$devs"
done

echo "== other buses"
for b in i2c spi usb mmc platform soc; do
    [ -d /sys/bus/$b ] || continue
    echo "bus $b devices: $($BB ls /sys/bus/$b/devices 2>/dev/null | $BB tr '\n' ' ')"
done

echo "== mmc hosts"
for h in /sys/class/mmc_host/mmc*; do
    [ -e "$h" ] || continue
    n=$($BB basename $h)
    dev=$($BB readlink -f $h/device 2>/dev/null)
    card=$($BB ls -d $h/$n:* 2>/dev/null | $BB tr '\n' ' ')
    echo "mmc $n device=$($BB basename $dev) card=[$card]"
done

echo "== input"
$BB grep -E '^(N|H|P):' /proc/bus/input/devices 2>/dev/null | $BB head -n 24

echo "== power supplies and thermal"
for p in /sys/class/power_supply/*; do
    [ -e "$p" ] || continue
    echo "psy $($BB basename $p) type=$($BB cat $p/type 2>/dev/null) online=$($BB cat $p/online 2>/dev/null) present=$($BB cat $p/present 2>/dev/null)"
done
for t in /sys/class/thermal/*; do
    [ -e "$t" ] || continue
    echo "thermal $($BB basename $t) type=$($BB cat $t/type 2>/dev/null) policy=$($BB cat $t/policy 2>/dev/null) temp=$($BB cat $t/temp 2>/dev/null)"
done

echo "== regulators"
for r in /sys/class/regulator/*; do
    [ -e "$r" ] || continue
    echo "regulator $($BB cat $r/name 2>/dev/null) state=$($BB cat $r/state 2>/dev/null) uV=$($BB cat $r/microvolts 2>/dev/null) users=$($BB cat $r/num_users 2>/dev/null)"
done

echo "== modules"
echo "modules: $($BB cat /proc/modules 2>/dev/null | $BB cut -d' ' -f1 | $BB tr '\n' ' ')"

echo "== interrupts before"
$BB cat /proc/interrupts

card_check
rtc_sleep 40 freeze

echo "== interrupts after the first sleep"
$BB cat /proc/interrupts

# Three seconds of quiet before the next suspend. Without them the host, which
# reads the card's passive trace five times a second, sees the wake, the mark,
# the card check and the next suspend as one event, closes the first window on
# it and never opens the second. That is what the first run of this script did.
$BB sleep 3
rtc_sleep 40 freeze

echo "== interrupts after the second sleep"
$BB cat /proc/interrupts

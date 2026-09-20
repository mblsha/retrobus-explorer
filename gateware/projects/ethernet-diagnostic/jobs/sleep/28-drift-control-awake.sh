# Experiment 28. The drift control: six awake windows with the same work
# between them that the sleep alternations do, and no suspend at all.
#
# Inside one boot the sleeping current climbs about a milliamp and a half per
# cycle (six identical sleeps: 121, 125, 125, 128, 126, 129). Inside the one
# six-minute sleep it does not climb: 104, 102 and 107 mA by thirds. So it goes
# with the transitions or with the awake work between them, not with time
# asleep. This separates those two: the same 256 MiB md5 and the same dwell,
# six times, with the target never suspended. If the awake current climbs the
# same way, the drift is the board warming under the work and not something a
# suspend leaves behind.

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
$BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count=256 2>/dev/null
echo "probe md5=$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
temp() { for z in /sys/class/thermal/thermal_zone*/temp; do [ -r "$z" ] && echo -n "$($BB cat $z) "; done; }

cycle=1
while [ "$cycle" -le 6 ]; do
    echo "=== awake window $cycle uptime=$($BB cut -d' ' -f1 /proc/uptime) temp=$(temp)"
    mark_sector "w$cycle-begin"
    $BB sleep 40
    mark_sector "w$cycle-end"
    $BB md5sum /tmp/dram-probe > /dev/null
    $BB sleep 3
    cycle=$((cycle + 1))
done
echo "=== done temp=$(temp)"

# Experiment 27. What the kernel's unused-regulator cleanup is worth, caught
# as a step in the awake current, and a sleep taken after it has run.
#
# Every sleep measured so far began about two seconds into the boot. The
# regulator core disables regulators nobody uses once, at about 32 s of uptime,
# and when that moment falls inside a suspend the PMIC's I2C controller is
# suspended, the write times out (`aldo3: couldn't disable: -ETIMEDOUT`) and
# it is never tried again. So every figure so far has `aldo3` and whatever
# else the cleanup would have taken down still up. The adviser's first point:
# remove that race before believing anything about what is left.
#
# Awake, the step is visible inside one boot, which between-boot noise cannot
# hide: the same idle state measured before 32 s and after it. Then two sleeps,
# so that a sleep with the cleanup done exists to compare with the ~105 mA the
# self-refresh firmware has read every time without it.
#
# It also lists what the power-supply class offers, because the next question
# is whether charging can be switched off through the driver with no battery
# fitted, and that needs the attribute's name before anything is written.

regulators() {
    for r in /sys/class/regulator/*; do
        [ -e "$r/name" ] || continue
        echo "reg $1 $($BB cat $r/name) state=$($BB cat $r/state 2>/dev/null) uV=$($BB cat $r/microvolts 2>/dev/null) users=$($BB cat $r/num_users 2>/dev/null)"
    done
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) uptime=$($BB cut -d' ' -f1 /proc/uptime)"
regulators before

echo "=== awake and idle, before the cleanup"
mark_sector before-begin
$BB sleep 25
mark_sector before-end
echo "before window ended at uptime $($BB cut -d' ' -f1 /proc/uptime)"

# Past the cleanup, with a margin: it has been seen at 32.05 s.
while [ "$($BB cut -d. -f1 /proc/uptime)" -lt 38 ]; do $BB sleep 1; done
regulators after
$BB dmesg | $BB grep -i "disabling\|couldn't disable\|I2C bus locked" | $BB tail -n 8

echo "=== awake and idle, after the cleanup"
mark_sector after-begin
$BB sleep 40
mark_sector after-end
echo "after window ended at uptime $($BB cut -d' ' -f1 /proc/uptime)"
$BB sleep 3

echo "=== power supplies, read only"
for s in /sys/class/power_supply/*; do
    [ -d "$s" ] || continue
    echo "supply $($BB basename $s): $($BB ls $s | $BB tr '\n' ' ')"
    for a in status present online health charge_behaviour charge_control_limit constant_charge_current input_current_limit usb_type; do
        [ -r "$s/$a" ] && echo "  $a=$($BB cat $s/$a 2>/dev/null)"
    done
done

echo "=== two sleeps with the cleanup done"
rtc_sleep 40 mem deep
$BB sleep 3
rtc_sleep 40 mem deep
regulators end
echo "=== done"

# Experiment 16. What the target draws awake and idle in the kept
# configuration, and what it draws asleep in it, in the same boot.
#
# The awake figure is the one that says how much of the saving is "asleep" and
# how much is "the clock is slower now". Phase 0 measured an awake idle target
# with the panel already asleep at 144 and 151 mA with the `performance`
# governor; this is the same state with `powersave`.
#
# The awake window is marked by hand rather than by rtc_sleep, and nothing
# inside it touches the card: BusyBox is in tmpfs and `sleep` is a syscall, so
# forty seconds of it is forty seconds of silence, which is what the host
# needs to line a current window up against a state.

echo "=== the kept configuration"
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo "fb0-blank=$($BB cat /sys/class/graphics/fb0/blank 2>/dev/null) backlight-power=$($BB cat /sys/class/backlight/backlight/bl_power 2>/dev/null)"
for r in /sys/class/regulator/*; do
    [ -e "$r" ] || continue
    [ "$($BB cat $r/name 2>/dev/null)" = "vdd-cpu" ] && echo "vdd-cpu $($BB cat $r/state) $($BB cat $r/microvolts)"
done
card_check

echo "=== awake and idle, panel asleep, powersave"
mark_sector awake-idle-begin
$BB sleep 40
mark_sector awake-idle-end
echo "awake window done at uptime $($BB cut -d' ' -f1 /proc/uptime)"
$BB sleep 3

rtc_sleep 40 freeze
$BB sleep 3
rtc_sleep 40 freeze
echo "=== done"

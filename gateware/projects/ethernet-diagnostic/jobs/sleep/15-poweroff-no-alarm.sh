# Experiment 15. The control for experiment 14: power off with no alarm armed.
#
# Experiment 14 set the RTC alarm sixty seconds out, powered the board off,
# and watched it come back twice, sixty seconds apart each time, at 33 mA in
# between. Two explanations fit that: the alarm woke it, or the PMIC restarts
# whenever it is powered off with 5 V still on the port. This decides which,
# and it decides whether "power off and let the RTC switch it back on" is a
# timed wake or just a board that will not stay off.
#
# The alarm is cleared rather than simply not set, because the runner's own
# rtc_sleep may have left one armed from an earlier job in the same card.

echo "uptime=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"
echo 0 > /sys/class/rtc/rtc0/wakealarm 2>/dev/null
echo "wakealarm after clearing=[$($BB cat /sys/class/rtc/rtc0/wakealarm)]"
card_check
echo "powering off with no alarm at uptime $($BB cut -d' ' -f1 /proc/uptime) rtc $(rtc_now)"
flush_result running
mark_sector poweroff-enter
$BB poweroff -f
$BB sleep 20
echo "STILL RUNNING at uptime $($BB cut -d' ' -f1 /proc/uptime)"
card_check

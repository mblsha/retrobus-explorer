# Experiment 14. A reference point, and NOT a sleep: what the board draws when
# Linux has powered it off while the 5 V supply is still connected, and
# whether an RTC alarm brings it back.
#
# This is the number every suspend figure should be read against. If a
# powered-off board draws about what a sleeping one does then the suspend is
# not the thing to optimise; if it draws almost nothing then everything
# between the two is SoC state that s2idle is not reaching.
#
# The job cannot report anything after the poweroff, so it writes its output
# to the card first, with the runner's own `flush_result`, and marks the
# moment it is about to go. The host keeps sampling the supply for the rest of
# `--run-seconds` and powers the channel off at the end whatever happened;
# the window is read out of the recorded samples rather than from a pair of
# marks, because nothing will ever write the closing one.

echo "uptime=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"
echo "state=$($BB cat /sys/power/state) success=$($BB cat /sys/power/suspend_stats/success)"
card_check

echo 0 > /sys/class/rtc/rtc0/wakealarm 2>/dev/null
if echo "+60" > /sys/class/rtc/rtc0/wakealarm 2>/tmp/alarm-error; then
    echo "wakealarm=$($BB cat /sys/class/rtc/rtc0/wakealarm) now=$(rtc_now)"
else
    echo "wakealarm refused: $($BB cat /tmp/alarm-error)"
fi

echo "powering off now at uptime $($BB cut -d' ' -f1 /proc/uptime) rtc $(rtc_now)"
flush_result running
mark_sector poweroff-enter
$BB poweroff -f
# Not reached if the poweroff works. If it is reached, that is the finding.
$BB sleep 20
echo "STILL RUNNING at uptime $($BB cut -d' ' -f1 /proc/uptime)"
card_check

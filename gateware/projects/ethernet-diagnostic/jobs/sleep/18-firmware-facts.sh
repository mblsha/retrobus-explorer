# Experiment 18. What the firmware on the card offers, before any sleep.
#
# The bootloader is no longer the one ROCKNIX ships: it is mainline U-Boot
# v2026.01 and TF-A v2.12.0 built here from pinned sources, and on the deep
# sleep builds TF-A carries our PSCI SYSTEM_SUSPEND. Two things decide whether
# that arrived: whether `/sys/power/mem_sleep` has gained `deep`, which only
# happens when PSCI advertises SYSTEM_SUSPEND, and whether the four RTC
# general-purpose registers EL3 writes its progress into can be read back.
#
# The registers are RTC + 0x100 + 4N (H616 manual 3.13.6.12), N = 12 to 15:
# the stage code with an 0xa5d5 tag, the number of suspends entered, the
# number of resumes completed, and the interrupt that ended the last wait.
# They are in the always-on domain, so they survive a suspend and a warm
# reset, but not the 5 V going away on a board with no battery. All zero here
# means the firmware has not suspended yet, which is the expected answer on a
# job that does not sleep.
#
# This job does not suspend. It is the first thing to run after a new
# bootloader is deployed: it costs one boot and says whether the next
# experiment is worth starting.

markers() {
    for reg in 0x07000130 0x07000134 0x07000138 0x0700013c; do
        echo "rtc-gp $reg = $($BB devmem $reg 2>/dev/null || echo UNREADABLE)"
    done
}

echo "state=[$($BB cat /sys/power/state)]"
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)]"
echo "suspend_stats success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail)"
echo "uptime=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] || continue
    echo "cpufreq $($BB basename $p) governor=$($BB cat $p/scaling_governor) freq=$($BB cat $p/scaling_cur_freq)"
done
echo "online=$($BB cat /sys/devices/system/cpu/online)"

echo "--- can EL3's progress registers be read? ---"
markers

echo "--- does deep exist? ---"
if echo deep > /sys/power/mem_sleep 2>/tmp/deep-error; then
    echo "mem_sleep deep accepted, now [$($BB cat /sys/power/mem_sleep)]"
    echo s2idle > /sys/power/mem_sleep 2>/dev/null
    echo "mem_sleep put back to [$($BB cat /sys/power/mem_sleep)]"
else
    echo "mem_sleep deep refused: $($BB cat /tmp/deep-error)"
fi

card_check

# Experiment 31. Short sleeps with the watchdog armed across the wait, so that
# a hang leaves its evidence behind.
#
# This is the job that was missing when the `sr-pll` rung hung. That rung
# suspended and never returned; the stub writes a progress code into an RTC
# general purpose register at every step, and those registers are in the
# always-on domain -- but this board has no battery, so "always on" means
# "while the USB-C port is powering it", and the harness cuts the power at
# --run-seconds. The evidence died with the 5 V, twice.
#
# The way out is to make the hang reset the board instead. The SoC watchdog
# keeps counting through WFI and its longest interval is about sixteen seconds,
# so it cannot cover a forty-second measurement -- but it can cover a ten-second
# one. Writing 0x57440001 into RTC general purpose register 11 asks the stub for
# exactly that: the watchdog stays armed from the entry, through the wait, to
# the end of the resume. The stub clears the register as it reads it, so the
# request cannot outlive its own sleep and reset the board in the middle of the
# next measurement.
#
# So: three ten-second sleeps, each asking for the watchdog. If one hangs, the
# board warm-resets, the runner comes back up and takes the next job, and the
# stage code from the hang is still in the RTC. If none hangs, the three
# resumes are three more of them and the markers say which path was taken.
#
# Not a measurement. Ten-second windows are too short for the measurement rule,
# and the watchdog being armed is itself a difference.

devmem_hex() {
    $BB devmem "$1" 2>/dev/null || echo UNREADABLE
}

markers() {
    echo "el3 stage=$(devmem_hex 0x07000130) entered=$(devmem_hex 0x07000134) resumed=$(devmem_hex 0x07000138) wake_irq=$(devmem_hex 0x0700013c)"
    echo "stub fail_reg=$(devmem_hex 0x07000120) fail_info=$(devmem_hex 0x07000124) await=$(devmem_hex 0x07000128) debug=$(devmem_hex 0x0700012c)"
    echo "params status=$(devmem_hex 0x2002c) stage=$(devmem_hex 0x20030) fail=$(devmem_hex 0x2003c)@$(devmem_hex 0x20038)"
}

# The stub reads this once and clears it; see STUB_DEBUG_WATCHDOG in stub.h.
ask_for_the_watchdog() {
    $BB devmem 0x0700012c 32 0x57440001 2>/dev/null
    echo "debug request written, reads back $(devmem_hex 0x0700012c)"
}

dram_probe_mb=256

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "uptime at start=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"
echo "whatever the last boot left behind:"
markers
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail)"
card_check

$BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count="$dram_probe_mb" 2>/dev/null
before="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
echo "dram-probe ${dram_probe_mb}MiB md5=$before"

n=1
while [ "$n" -le 3 ]; do
    echo "=== short sleep $n, watchdog through the wait"
    ask_for_the_watchdog
    rtc_sleep 10 mem deep
    markers
    now="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
    if [ "$now" = "$before" ]; then
        echo "dram-check ok $now"
    else
        echo "dram-check FAILED wanted $before got $now"
    fi
    echo "uptime=$($BB cut -d' ' -f1 /proc/uptime)"
    n=$((n + 1))
    $BB sleep 2
done

echo "=== three short sleeps done"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail)"
echo "debug register left as $(devmem_hex 0x0700012c), which should be zero"
markers
card_check

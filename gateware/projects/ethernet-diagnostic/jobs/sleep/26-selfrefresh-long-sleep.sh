# Experiment 26. One long self-refresh sleep, because forty seconds proves
# nothing about refreshing.
#
# A DRAM cell holds its charge for a good fraction of a second with nobody
# refreshing it, and a controller that quietly did not enter self-refresh --
# or a PHY that stopped driving CKE -- would still be inside the retention
# time of a short sleep for the parts of the array that were read recently.
# Six minutes is four hundred times the worst-case retention of an LPDDR4
# part at room temperature, so a probe whose md5 still matches afterwards is
# refresh actually happening and not luck.
#
# It is also the only measurement here whose sleep is long enough that the
# harness's own overheads are a rounding error, so its current is the cleanest
# single figure this rung produces. One window: `long`.

markers() {
    echo "el3 stage=$($BB devmem 0x07000130 2>/dev/null) entered=$($BB devmem 0x07000134 2>/dev/null) resumed=$($BB devmem 0x07000138 2>/dev/null) wake_irq=$($BB devmem 0x0700013c 2>/dev/null)"
}

dram_probe_mb=192

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)"
echo deep > /sys/power/mem_sleep 2>/dev/null
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)]"
markers
card_check

$BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count="$dram_probe_mb" 2>/dev/null
before="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
echo "dram-probe ${dram_probe_mb}MiB md5=$before"

rtc_sleep 360 mem deep

after="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
if [ "$after" = "$before" ]; then
    echo "dram-check ok after a long sleep $after"
else
    echo "dram-check FAILED after a long sleep wanted $before got $after"
fi
markers
echo "mctl STAT=$($BB devmem 0x047fb004) PWRCTL=$($BB devmem 0x047fb030)"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail)"
card_check

# Experiment 32. The PHY-rebuild suspend against s2idle, A B B A A B in one
# boot.
#
# The same shape as experiments 20 and 24, so the three can be read against
# each other with the same reference in the same place: A is `mem` resolved to
# s2idle, B is `mem` resolved to `deep`. The `powersave` governor is set once
# at the top and is in force in both arms, because it is worth eleven
# milliamps on its own and would otherwise be the only thing this measured.
#
# Alternating inside one boot is the only comparison this bench believes: two
# cold boots of the same state differ by about seven milliamps, and the current
# also climbs about one and a half per cycle through a boot.
#
# The DRAM probe is filled once, before the first sleep, and checked after
# every one of the six. An s2idle sleep does not touch DRAM at all, so the
# three A checks are the control: they say the probe survives being read six
# times, and only the three B checks say anything about a controller and a PHY
# that were switched off and built again.
#
# Six labels in this order: A1 B1 B2 A2 A3 B3.
#
# Expect more windows than labels: the md5 check between sleeps takes about
# four seconds and the harness calls the gap a state of its own. Those windows
# are 9 or 10 seconds long and read 160 to 180 mA, which is the target awake.
# Read the windows by their dwell, or pass --min-window-seconds 30 to the job
# runner, which drops the short ones before the labels are handed out.
#
# This job works on any firmware that offers `deep`, ours or theirs. What it
# prints from SRAM only means something on ours.

devmem_hex() {
    $BB devmem "$1" 2>/dev/null || echo UNREADABLE
}

markers() {
    echo "el3 stage=$(devmem_hex 0x07000130) entered=$(devmem_hex 0x07000134) resumed=$(devmem_hex 0x07000138) wake_irq=$(devmem_hex 0x0700013c)"
    echo "stub fail_reg=$(devmem_hex 0x07000120) fail_info=$(devmem_hex 0x07000124) await=$(devmem_hex 0x07000128)"
    echo "params status=$(devmem_hex 0x2002c) stage=$(devmem_hex 0x20030) fail=$(devmem_hex 0x2003c)@$(devmem_hex 0x20038)"
}

dram_probe_mb=256

dram_fill() {
    $BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count="$dram_probe_mb" 2>/dev/null
    DRAM_PROBE_MD5="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
    echo "dram-probe ${dram_probe_mb}MiB md5=$DRAM_PROBE_MD5"
}

dram_check() {
    now="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
    if [ "$now" = "$DRAM_PROBE_MD5" ]; then
        echo "dram-check ok $now"
    else
        echo "dram-check FAILED wanted $DRAM_PROBE_MD5 got $now"
    fi
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)]"
markers
card_check
dram_fill

for arm in s2idle deep deep s2idle s2idle deep; do
    echo "=== $arm"
    rtc_sleep 40 mem "$arm"
    markers
    dram_check
    $BB sleep 3
done

echo "=== six sleeps done"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail) last_failed_dev=[$($BB cat /sys/power/suspend_stats/last_failed_dev)]"
markers
echo "mctl STAT=$(devmem_hex 0x047fb004) PWRCTL=$(devmem_hex 0x047fb030) MAER0=$(devmem_hex 0x047fa020)"
echo "ccu PLL_DDR0=$(devmem_hex 0x03001010) MBUS=$(devmem_hex 0x03001540) DRAM_BGR=$(devmem_hex 0x0300180c)"
card_check

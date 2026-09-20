# Experiment 19. Our own PSCI SYSTEM_SUSPEND against s2idle, alternated.
#
# A is `mem` resolved to s2idle, which is every sleep this bench measured
# before the firmware changed; B is `mem` resolved to `deep`, which goes
# through the SMC into EL3, stops PLL_CPUX and waits in WFI with DRAM still
# running. The order is A B B A A B for the reason experiments 7 to 10 use it:
# two identical sleeps in one boot differ by about three milliamps and the
# current climbs about one and a half per cycle through a boot, so only an
# alternation inside one boot decides anything, and only by more than about
# eight milliamps.
#
# The `powersave` governor is set once at the top and is in both arms. It is
# worth eleven milliamps on its own and survives every resume, so leaving it
# out would put the larger effect on top of the one being measured.
#
# After every sleep the four RTC general-purpose registers EL3 writes are read
# back: the stage code says how far the suspend got, and the two counters say
# how many suspends were entered against how many resumes completed. A deep
# sleep that did not reach EL3 leaves them at whatever the last one left.

markers() {
    stage=$($BB devmem 0x07000130 2>/dev/null || echo UNREADABLE)
    entered=$($BB devmem 0x07000134 2>/dev/null || echo UNREADABLE)
    resumed=$($BB devmem 0x07000138 2>/dev/null || echo UNREADABLE)
    wake=$($BB devmem 0x0700013c 2>/dev/null || echo UNREADABLE)
    echo "el3 stage=$stage entered=$entered resumed=$resumed wake_irq=$wake"
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)]"
markers
card_check

for step in A B B A A B; do
    echo "=== sleep $step"
    if [ "$step" = B ]; then
        rtc_sleep 40 mem deep
    else
        rtc_sleep 40 mem s2idle
    fi
    markers
    echo "after $step: uptime=$($BB cut -d' ' -f1 /proc/uptime) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
    $BB sleep 3
done

echo "=== six sleeps done"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail) last_failed_dev=[$($BB cat /sys/power/suspend_stats/last_failed_dev)]"
markers
card_check

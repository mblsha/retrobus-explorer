# Experiment 19. One deep sleep, to find out whether it comes back.
#
# The first thing a new EL3 suspend has to survive. `deep` goes through the
# SMC into TF-A, which stops PLL_CPUX and waits in WFI; coming back means the
# core saw the RTC's interrupt, restarted the PLL and re-entered BL31 through
# its warm boot entry, and that PSCI then returned to the address Linux gave
# it. Any one of those failing looks the same from here -- the target stops
# answering the card -- so this is run on its own before anything is measured
# with it.
#
# It is deliberately a whole forty-second sleep rather than a short one: the
# window is long enough for the host to price it, so if it does come back this
# job has also produced the first deep-sleep current of the bench.
#
# The RTC general-purpose registers are read before and after. Before, they
# say whether an earlier attempt in this boot got anywhere; after, the stage
# code says the resume path finished (0xa5d50008 is written from the PSCI
# resume hook, after the warm boot) and the counters say one suspend was
# entered and one resume completed.

markers() {
    echo "el3 stage=$($BB devmem 0x07000130 2>/dev/null) entered=$($BB devmem 0x07000134 2>/dev/null) resumed=$($BB devmem 0x07000138 2>/dev/null) wake_irq=$($BB devmem 0x0700013c 2>/dev/null)"
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)] online=$($BB cat /sys/devices/system/cpu/online)"
echo "before:"
markers
card_check

rtc_sleep 40 mem deep

echo "after:"
markers
echo "freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq) uptime=$($BB cut -d' ' -f1 /proc/uptime)"
for r in /sys/class/regulator/*; do
    [ -e "$r" ] || continue
    [ "$($BB cat $r/name 2>/dev/null)" = "vdd-cpu" ] && echo "vdd-cpu $($BB cat $r/microvolts)"
done
card_check

# Experiment 2. What the regulator core's delayed cleanup costs when it lands
# inside the sleep, and what two sleeps in one boot differ by once it has run.
#
# The kernel log of every first sleep says `aldo3: disabling` at 32 s of
# uptime and then `mv64xxx: I2C bus locked` every two seconds until the wake.
# That is `regulator_init_complete_work`, which runs thirty seconds after late
# init and turns off every regulator nobody claimed. The job harness starts a
# job at two seconds of uptime, so it always lands in the middle of the first
# suspend, where the PMIC's I2C controller is suspended and cannot answer, and
# the core retries for the rest of the sleep.
#
# Three sleeps: the first with the cleanup inside it, the second and third
# after it has finished. The first pair says what the cleanup costs; the
# second pair says what a paired before/after design's own repeatability is.
#
# Five seconds of quiet between sleeps, because the host reads the card's
# passive trace five times a second and a wake followed straight away by the
# next suspend puts the end of one window and the start of the next into a
# single poll, which loses the second window entirely.

regulators() {
    echo "-- regulators $1"
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        s=$($BB cat $r/state 2>/dev/null)
        [ "$s" = "enabled" ] || continue
        echo "   $($BB cat $r/name 2>/dev/null) $($BB cat $r/microvolts 2>/dev/null) users=$($BB cat $r/num_users 2>/dev/null)"
    done
}

irqs() {
    echo "-- interrupts $1"
    $BB grep -E 'arch_timer|i2c|ths|rtc|sunxi-mmc|panfrost|adc' /proc/interrupts
}

echo "uptime at job start: $($BB cut -d' ' -f1 /proc/uptime)"
echo "spi drivers: $($BB ls /sys/bus/spi/drivers 2>/dev/null | $BB tr '\n' ' ')"
for d in /sys/bus/spi/drivers/*; do
    [ -d "$d" ] || continue
    for e in "$d"/*; do
        [ -L "$e" ] || continue
        echo "spi driver $($BB basename $d) <- $($BB basename $e)"
    done
done
regulators before
irqs before

rtc_sleep 40 freeze

echo "uptime after sleep 1: $($BB cut -d' ' -f1 /proc/uptime)"
regulators "after sleep 1"
irqs "after sleep 1"
$BB sleep 5

rtc_sleep 40 freeze

echo "uptime after sleep 2: $($BB cut -d' ' -f1 /proc/uptime)"
regulators "after sleep 2"
irqs "after sleep 2"
$BB sleep 5

rtc_sleep 40 freeze

echo "uptime after sleep 3: $($BB cut -d' ' -f1 /proc/uptime)"
regulators "after sleep 3"
irqs "after sleep 3"
echo "-- regulator lines in the log"
$BB dmesg | $BB grep -iE 'regulator|aldo|dcdc|couldn.t disable' | $BB tail -n 12

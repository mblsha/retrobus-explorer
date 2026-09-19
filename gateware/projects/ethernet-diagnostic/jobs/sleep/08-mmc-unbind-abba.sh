# Experiment 8. The two card controllers that are not the root device, taken
# away and given back three times in one boot.
#
# 4021000.mmc is the SDIO slot the Wi-Fi part sits on -- no driver is bound to
# the part and no rfkill device exists, but `vcc-wifi` is powered anyway.
# 4022000.mmc is the second card slot, which on this bench holds a 128 GB SDXC
# card and owns `vcc3v3-mmc2`. Unbinding either drops its regulator, which is
# the reason to expect anything at all; the ladder in experiment 5 put the two
# of them together at about ten milliamps.
#
# 4020000.mmc is never touched. It is the emulated card and the root device,
# and a saving that needed it gone would not survive a move to a real card.
#
# The sleeps go A B B A A B rather than A B A B: the current in this boot
# drifts upward by about a milliamp and a half per sleep, so a knob that is
# always measured second reads about three milliamps worse than it is. In this
# order the two groups sit at almost the same mean position in the run.

HOSTS="4021000.mmc 4022000.mmc"

apply() {
    for h in $HOSTS; do
        if [ "$1" = off ]; then
            echo "$h" > /sys/bus/platform/drivers/sunxi-mmc/unbind 2>/dev/null
        else
            echo "$h" > /sys/bus/platform/drivers/sunxi-mmc/bind 2>/dev/null
        fi
    done
    bound=""
    for h in $HOSTS; do
        [ -e "/sys/bus/platform/drivers/sunxi-mmc/$h" ] && bound="$bound $h"
    done
    on=""
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        case "$($BB cat $r/name 2>/dev/null)" in
            vcc-wifi|vcc3v3-mmc2)
                on="$on $($BB cat $r/name)=$($BB cat $r/state)" ;;
        esac
    done
    echo "bound:$bound rails:$on hosts=$($BB ls /sys/class/mmc_host 2>/dev/null | $BB tr '\n' ' ')"
}

for step in A B B A A B; do
    echo "=== sleep with the controllers $step"
    if [ "$step" = A ]; then apply on; else apply off; fi
    $BB sleep 1
    rtc_sleep 40 freeze
    $BB sleep 3
done

apply on
echo "=== six sleeps done"

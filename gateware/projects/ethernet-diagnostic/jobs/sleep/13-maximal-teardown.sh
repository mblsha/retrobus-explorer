# Experiment 13. Everything that can be unbound without taking the root card,
# the PMIC's bus, the clocks, the pin controller or the RTC with it.
#
# The last screen the runtime path has. If taking away the display pipeline,
# the GPU, the IOMMU, both audio codecs, the HDMI PHY, the two card
# controllers that are not the root device, the backlight PWM, the watchdog,
# the spare UART, the eFuse, the PMIC's pollers and the SoC's ADC all at once
# does not move the sleeping current, then nothing reachable from sysfs will,
# and what is left is a device-tree and firmware question.
#
# The order matters: the DRM master goes first, because experiment 5 showed
# that unbinding a panel the master still holds costs the wake, and
# experiment 12 showed that with the master gone the same unbind is harmless.
#
# Never in this list: 4020000.mmc (the root device and the emulated card),
# 7081400.i2c (the PMIC's bus), 300b000.pinctrl, 3001000.clock, 7010000.clock,
# 7000000.rtc (the alarm that ends the sleep), 3000000.syscon.
#
# Three sleeps with everything off against one with nothing off. The current
# in a boot drifts upward by about a milliamp and a half per sleep, so a null
# result here is the conservative one: the three sleeps being compared sit
# later in the run than the sleep they are compared against.

unbind() {
    if [ ! -e "/sys/bus/$1/drivers/$2/$3" ]; then
        echo "  $3: not bound to $2"
        return
    fi
    if echo "$3" > "/sys/bus/$1/drivers/$2/unbind" 2>/tmp/unbind-error; then
        echo "  $3 off $2"
    else
        echo "  $3 FAILED $($BB cat /tmp/unbind-error)"
    fi
}

rails() {
    on=""
    for r in /sys/class/regulator/*; do
        [ -e "$r" ] || continue
        [ "$($BB cat $r/state 2>/dev/null)" = "enabled" ] || continue
        on="$on $($BB cat $r/name 2>/dev/null)=$($BB cat $r/microvolts)"
    done
    echo "rails$on"
}

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done
echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"

echo "=== A: the kept configuration only"
rails
rtc_sleep 40 freeze
$BB sleep 3

echo "=== unbinding everything that can go"
unbind platform sun4i-drm display-engine
unbind spi panel-mipi spi0.0
unbind platform sun8i-dw-hdmi 6000000.hdmi
unbind platform sun8i-hdmi-phy 6010000.hdmi-phy
unbind platform sun4i-tcon 6511000.lcd-controller
unbind platform sun4i-tcon 6515000.lcd-controller
unbind platform sun8i-mixer 1280000.mixer
unbind platform sun8i-mixer 12a0000.mixer
unbind platform sun8i-tcon-top 6510000.tcon-top
unbind platform sun50i-planes 1100000.planes
unbind platform sun50i-de2-bus 1000000.bus
unbind platform sun50i-iommu 30f0000.iommu
unbind platform panfrost 1800000.gpu
unbind platform sun4i-codec 5096000.codec
unbind platform hdmi-audio-codec hdmi-audio-codec.2.auto
unbind platform dw-hdmi-i2s-audio dw-hdmi-i2s-audio.1.auto
unbind platform display-connector connector
unbind platform sunxi-mmc 4021000.mmc
unbind platform sunxi-mmc 4022000.mmc
unbind platform pwm-backlight backlight
unbind platform sun8i-pwm 300a000.pwm
unbind platform sunxi-wdt 30090a0.watchdog
unbind platform eeprom-sunxi-sid 3006000.efuse
unbind platform dw-apb-uart 5000400.serial
unbind platform axp20x-adc axp717-adc
unbind platform axp20x-battery-power-supply axp20x-battery-power-supply
unbind platform axp20x-usb-power-supply axp20x-usb-power-supply
unbind platform sun20i-gpadc 5070000.adc
unbind platform sun8i-thermal 5070400.thermal-sensor
for l in /sys/class/leds/*; do
    [ -e "$l" ] || continue
    echo 0 > "$l/brightness" 2>/dev/null
done
rails
card_check
$BB sleep 3

for round in 1 2 3; do
    echo "=== B round $round"
    rtc_sleep 40 freeze
    $BB sleep 3
done

echo "=== all four sleeps woke"
rails
$BB grep -E 'arch_timer|i2c|ths' /proc/interrupts
$BB dmesg | $BB tail -n 10

# Gateware to test that all pins are correctly mapped in software

NOTE: v1 version of Pin Tester board doesn't have pull-down resistors, so
unconnected pins will be floating and the FPGA will likely not notice when
they're disconnected.

Used Bus Pirate v5 in DIO mode, power-supply at 5V. Connect to the Alchitry USB UART with baud rate of 1_000_000 to control the mode and the selected level shifter bank.

The following Bus Pirate command blinks leds in order:

```
DIO> [0x0 d:500000 0b1 d:500000 0b10 d:500000 0b100 d:500000 0b1000 d:500000 0b10000 d:500000 0b100000 d:500000 0b1000000 d:500000 0b10000000 d:500000 0xf0 d:500000 0xff]
```

# Level Shifter Banks

Each level shifter converts the voltage of 8 data pins, and there are 6 of them in total.

Selecting bank `0` will work with data pins `0`-`7`, bank `1` will work with pins `8`-`15` and so on.

Pin Tester adapter board has separate pin headers for each bank.

# UART Commands

* `R` / `r`: Receive signals mode (default)

  * `0`-`5`: select level shifter bank to input

LEDs and Saleae ports will reflect input signals from 8 data pins of the selected bank.

* `S` / `s`: Send square signals (helpful to test for signal integrity / reflections / etc)

  * `0`-`9`: select position within the counter value; bigger position == slower updates

In this mode there's an internal counter, and the "bank" selects a position within the counter to transmit to the first 8 data pins of the FFC connector.

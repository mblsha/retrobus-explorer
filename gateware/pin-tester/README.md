# Gateware to test that all pins are correctly mapped in software

NOTE: v1 version of Pin Tester board doesn't have pull-down resistors, so
unconnected pins will be floating and the FPGA will likely not notice when
they're disconnected.

Used Bus Pirate v5 in DIO mode, power-supply at 5V. Connect to the USB UART
with baud rate of 1_000_000. Number 0-5 selects current level-shifter bank.

The following command blinks leds in order:

```
DIO> [0x0 d:500000 0b1 d:500000 0b10 d:500000 0b100 d:500000 0b1000 d:500000 0b10000 d:500000 0b100000 d:500000 0b1000000 d:500000 0b10000000 d:500000 0xf0 d:500000 0xff]
```

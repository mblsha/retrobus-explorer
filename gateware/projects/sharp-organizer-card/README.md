# Sharp organizer passive bus monitor

This Spade project samples the IQ-7000-style organizer bus and sends trace
words through the Alchitry Ft Element FT600. Organizer address, data, and
control pins are inputs; this project observes an organizer acting as bus
master.

## Related organizer tools

- [sharp-organizer-emulator](../sharp-organizer-emulator/README.md#quick-start)
  supplies ROM/SRAM2 read data, runs a native resident eval loop, accepts UART
  programming/timing commands, and supports bidirectional FT600 streams.
- [sharp-organizer-probe](../sharp-organizer-probe/README.md#quick-start)
  drives the Host Adapter to dump removable cards and program their SRAM.
- [Choose an organizer tool](../../README.md#choose-an-organizer-tool) lists
  each project's fixture, bus role, and release behavior.

## Source and simulation

The [top-level integration](src/main.spade), [command handling](src/cmd.spade),
[trace packing](src/trace_words.spade), and [transport](src/transport.spade)
define this monitor's interface. Its trace format and UART commands belong to
this project; the emulator uses the separate OEM1 protocol documented in its
[wire formats](../sharp-organizer-emulator/README.md#wire-formats).

From `gateware/`, run:

```sh
uv run --frozen --no-sync python tools/run_tb.py --project projects/sharp-organizer-card
```

Use the [gateware guide](../../README.md) for shared build and waveform tools.

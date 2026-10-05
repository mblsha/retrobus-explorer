# sharp-organizer-card-py

Python JITX port scaffold for the retrobus `sharp-organizer-card` board.

This is a thin two-layer polyimide flex PCB using the shared JLCPCB 0.11 mm FPC process defaults.

## Related Au1 gateware

For the organizer-card connector interface, see the
[ROM/SRAM2 emulator and native eval loop](../../gateware/projects/sharp-organizer-emulator/README.md#quick-start)
with UART control and bidirectional FT600 streaming, or the
[passive organizer bus monitor](../../gateware/projects/sharp-organizer-card/README.md).
The emulator guide describes its fixture requirements and qualification status.
The [organizer tool guide](../../gateware/README.md#choose-an-organizer-tool)
also covers the removable-card dumper using the Host Adapter.

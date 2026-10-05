# Organizer emulator verification and hardware qualification

## Current status

The initial implementation was verified on **2026-10-05**. Pin-level
simulation, host tooling, native code in a CPU model, and a Spade/nextpnr
bitstream build passed. The bitstream was **not flashed to an organizer
fixture** during this work. Native firmware entry, electrical operation and
sustained FT600 throughput remain unqualified on IQ-7000/OZ hardware.

See the [quick start](README.md#quick-start) for commands and the
[organizer tool guide](../../README.md#choose-an-organizer-tool) for the correct
fixture and bus role.

## Recorded verification

| Check | Initial result |
| --- | --- |
| Spade compiler | v0.20.0, commit `7e0bf7883d8a23dff89b5e38ce5c5f24761fafe5`; zero compiler warnings |
| Cocotb + Verilator integration | 7 tests passed, including pin release, live timing, SRAM writes, upload guards, FT backpressure/overflow and parser timeout |
| Shared dual-port card memory | 1 focused test passed; invalid address-width instantiation rejected by the compiler |
| Host/native tests | 8 passed in an environment with the SC62015 assembler/CPU model; 7 run in the normal workspace with the optional native test skipped |
| Native supervisor witness | READY output, invalid magic ignored, each sequence executed once, returning smoke payload, idle restoration, stack restoration |
| Continuous input witness | Receive/echo payload assembles and echoes data in the CPU model |
| Registry/constraints | Inventory, project discovery, CI scheduling and constraint-generator checks passed |
| nextpnr target | Au1 v1, `xc7a35tftg256-1`, seed 3, requested core and FT clocks 100 MHz |
| Final post-route frequency | Core 108.25 MHz; FT clock 163.13 MHz; both pass the requested 100 MHz |
| Bitstream round trip | 89,492 configuration bits verified after packing and decoding |
| Connector directions | Address/control/protected/NC pins confirmed input-only; data and FT buses retain their intended bidirectional ports |

Initial bitstream size: **2,192,116 bytes**.

Initial bitstream SHA-256:

```text
470c5192a7707e902f1b5aeb07fc6aa33fb77a218087bde9e422b8c64f0c1c40
```

These identify the initial build, not every future rebuild. The build's
`build/nextpnr-au1/result.json` is authoritative for a newly generated
bitstream. Generated bitstreams, logs and test results stay outside source
control. This document records verification; it does not designate a hardware
qualified release.

The initial implementation was saved in commit `4f896e7`. The subsequent
[Spade/FT600 source cleanup](../../docs/spade-modernization-2026-10-05.md)
records its own compilation, simulation and interface checks. The initial
bitstream identity above does not qualify a newly routed image from those
updated sources.

## Reproduce the checks

Use [Build and verification](README.md#build-and-verification) for gateware,
shared memory, host tests and nextpnr commands. The optional native test needs
an assembler environment and `SC62015_ASSEMBLER_ROOT`; its path is provided by
the caller. The normal workspace host suite skips that test if the environment
variable is absent.

The CPU model supplies an explicit PC entry and stack. It validates the native
loop's logic without establishing how stock organizer firmware enters it.
Post-route clock checks also do not establish asynchronous organizer bus
setup/hold margins or level-shifter turnaround timing.

## Remaining organizer tests

1. **Fixture and passive observation.** Confirm Card Adapter wiring and FFC
   orientation, then observe the organizer's select, RW, OE and address timing
   using the [passive monitor](../sharp-organizer-card/README.md). Record the
   exact organizer model and adapter/level-shifter revisions.
2. **Native entry.** Establish a repeatable entry into CPU base + `0x0100`,
   with a valid stack and the supervisor's reserved internal bytes available.
   Determine whether that organizer requires a minimal card header or a
   firmware launch descriptor. The current image leaves the header area zero.
3. **Emulated reads and writes.** Verify ROM response timing, raw read-end
   release, SRAM2 scratch writes, mailbox commit/idle guards, and the returning
   smoke payload on the actual bus. Record the CPU mapping and selected ROM
   pin; qualify timing values per organizer.
4. **FT600 traffic and loss.** Measure binary capture rate with tracing alone
   and with concurrent input. Test receive backpressure, overflow counters,
   record gaps and native TX-status polling. Measure disk and optional live
   JSON decoding separately. The documented 200 MB/s serializer ceiling is a
   calculation, not an observed USB transfer rate.

For each live run, retain the bitstream result, native image metadata,
capture binary and manifest. Record timing changes, errors, drops and how the
organizer was reset/re-entered. Finish by issuing `disarm` and confirming the
reported armed state is false before disconnecting the fixture or powering
down the organizer.

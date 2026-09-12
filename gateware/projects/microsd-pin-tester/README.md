# Arty A7-35T microSD pin probe

This Spade diagnostic samples all eight JD GPIO pins and never drives the SD
bus. Its two fixed board builds match the PCB's bottom-header and top-header-r180
profiles. This is an observation tool: activity alone does not prove wiring.

From `gateware/`:

```sh
uv sync --locked --all-packages
uv run python tools/run_tb.py --project projects/microsd-pin-tester
uv run python tools/run_tb.py --project projects/microsd-pin-tester --top probe_uart --test-module test_uart
python3 experiments/openxc7-macos/build_probe.py
```

The build script uses the [native installation](../../experiments/openxc7-macos/README.md),
requires the `xc7a35tcsg324.bin` chip database, checks 100 MHz post-route timing,
checks input-only synthesis, and compares configuration frames after decoding
each generated bitstream. Output is in `build/microsd-probe/<profile>/design.bit`.
It does not program the FPGA.

| SD signal | Bottom Pmod pin | Top R180 Pmod pin |
|---|---:|---:|
| DAT2 | 7 | 4 |
| DAT3 | 8 | 10 |
| CMD | 9 | 3 |
| CLK | 3 | 9 |
| DAT0 | 10 | 8 |
| DAT1 | 4 | 7 |

JD physical GPIO order 1,2,3,4,7,8,9,10 maps to D4,D3,F4,F3,E2,D2,H2,G2.
`constraints/pins.xdc` is specific to the Arty A7-35T, not the Alchitry Au.
The reset input is the Arty active-low reset C2. UART RX A9 and TX D10 use
1,000,000 baud, 8N1.

After later hardware connection and programming, capture a report on the Mac:

```sh
uv run python tools/microsd_probe.py --port /dev/cu.usbserial-REPLACE \
  --profile bottom-header --clear --seconds 2 --output probe.json
```

A profile mismatch is an error. Reports contain raw levels, saturating transition
counts, high/low observations, valid host command count, and last CRC7-validated
48-bit command. Counters ignore the initial synchronizer settling interval.
Snapshot fields are atomic even if the inputs change while the UART transmits.
The uptime wraps at 2^32 system cycles (42.95 seconds); it is not wall time.

The request is `A5 01 opcode sequence crc8 5A`; CRC8 uses polynomial 0x07 over
version/opcode/sequence. Opcode 1 snapshots; opcode 2 snapshots **then clears**.
Responses are 64 bytes: `MP`, version, opcode, sequence, raw pins, seen-high,
seen-low, uptime u32, eight u32 edge counters, last command u48, command count
u32, saturation mask, profile, four reserved zero bytes, IEEE CRC32 of bytes
0..59. Multibyte fields are little-endian. Requests expire after 1 ms if truncated;
invalid packets have no side effects. Wait for a response before sending another
request. There is no SD drive command.

## Later physical verification procedure

1. With power off, verify continuity from each microSD contact to the mapped JD
   GPIO and verify the two unused GPIOs are isolated. Test both orientations.
2. Supply an explicit common ground: this PCB leaves Pmod GND 5/11 disconnected.
   SD VDD and Pmod VCC are disconnected too. See the
   [PCB power-isolation notes](../../../jitx-py/microsd-pmod-breakout/README.md) before attaching it.
3. First validate the Linux native SD controller/reader with a real microSD card:
   record CID/CSD, block size, capacity, clock settings, and repeated hashes of a
   small read-only region (for example 64 KiB). A USB reader may hide native bus
   controls and is not automatically suitable for this test.
4. Replace the card with the adapter and input-only probe. Correlate CMD0, CMD8,
   CMD55/ACMD41 attempts with Linux logs. A probe cannot enumerate as a card.
5. Independently stimulate or continuity-test every DAT signal. Unused/static
   pins remain unverified. Never report six-pin success based only on CMD/CLK.

The default report deliberately keeps `pinout_verified` false for every signal;
store external continuity/stimulus evidence alongside it. Host clock decoding
requires pulses long enough for the 100 MHz synchronizer; this is not a logic
analyzer with guaranteed full-speed SD timing. The probe itself never drives SD pins.

## Measured assembled connector

The [2026-09-07 GKD-to-JD hardware test](../../docs/hardware/gkd-arty-jd-pinout-2026-09-07.md)
found a row-swapped bottom-header assembly. Its six measured signals do not
match either complete profile above. Use the measured table for that assembly;
silkscreen alone does not determine connector pin numbering after assembly.

The measured assembly is now selectable as `bottom-header-row-swap` (wire profile
ID 2). Build it with `python3 experiments/openxc7-macos/build_probe.py --profile
bottom-header-row-swap` from `gateware/`. The parser validates all three profile
IDs; the old IDs 0 and 1 retain their meanings.

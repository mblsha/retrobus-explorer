# Sharp organizer card probe for Alchitry Au1

See [BENCH.md](./BENCH.md) for the live Au1 test and IQ-704B dump results.

This is a removable-card host for the IQ-7000 system bus. It uses Spade and
the shared UART primitives at 5 Mbaud. The physical target is the **Sharp
Organizer Host Adapter v1 (2025-05-11)**, the **Level Shifter Element Au1 v2
(2025-05-11)**, and the **inverted FFC cable**. The generated XDC uses the
existing `constraints/targets/sharp-organizer-card.acf` mapping; it has the
same 43 card-facing signals as the passive `sharp-organizer-card` project.

The passive project samples an organizer acting as bus master and streams a
trace over FT600. This probe instead drives selected address and control pins
as a card host, and returns pin snapshots or sequential read data over USB-UART.
It does not use FT600.

## Electrical behavior

All card-facing FPGA outputs are released at reset. STNBY, VBATT, VPP and the
four NC contacts are input-only. Address and the eight control pins have
independent output-enable masks. Data is input-only during reads and is driven
only during the bounded SRAM write command. A
malformed unlock, `Z`, reset, or one second without probe activity releases every
drive-capable pin. A burst also releases its pins after the last byte. The
TXB0108s on the Au1 level shifter have OE tied high in
hardware: the FPGA cannot turn off the translators. Their 3.3 V side is on the
Au1; the card side follows the adapter's 5 V supply.

The IQ-704B was read with idle control `0xff`, active control
`0x7d`, and mask `0xff`. Its header includes `thesaurus`; the entire 20-bit
address scan repeated every 256 KiB and matched on two passes. These values
are observed for that card. The OZ-707 Basic card was then read with EPROM
selected for its 128 KiB ROM and SRAM2 selected for its 32 KiB data area;
both matched on two passes. The operator supplies *idle*, *active*, and mask
for other cards. The FPGA never drives VPP.

Before inserting a card into a newly assembled cable/adapter, validate the
physical FFC orientation and Au1 mapping with `projects/pin-tester`, then use
this probe's `sample` command with no card. The pin mapping was checked against
both PCB source files, but that is not a live continuity test.

## Build and verification

From `gateware/`:

```sh
uv run --frozen python tools/run_tb.py --project projects/sharp-organizer-probe
uv run --frozen python tools/project_inventory.py --check
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.92.0/lib ./.venv/bin/python projects/sharp-organizer-probe/scripts/build_nextpnr.py --seed 3
```

The last command runs Swim/Spade, Yosys, nextpnr-xilinx, Project X-Ray FASM
packing, and a bitstream decode round trip for `xc7a35tftg256-1`. It writes
`build/nextpnr-au1/design.bit` and `result.json`; both are generated files.
The selected nextpnr seed is 3; its post-route estimate is 100.84 MHz against
the 100 MHz clock. The bitstream is for the Au1 v1 FPGA, not Au1 v2.

To load the checked bitstream into FPGA SRAM through the tested Au1 JTAG path:

```sh
openFPGALoader -b alchitry_au --ftdi-serial FT4ZS6I3 -m \
  projects/sharp-organizer-probe/build/nextpnr-au1/design.bit
```

Replace the FTDI serial for another Au1. The SRAM load is volatile.

## USB-UART commands

`scripts/organizer_probe.py` uses pyserial at 5 Mbaud. The CLI requires the
UART port explicitly and identifies the bitstream before each operation.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART sample
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART shell
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART \
  cycle --address 0x00000 --idle 0xff --active 0x7d --mask 0xff
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART \
  dump --start 0 --length 0x40000 --idle 0xff --active 0x7d --mask 0xff --output iq704b.bin
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART \
  --read-phase-ns 500 dump-card --output-dir projects/sharp-organizer-probe/build/oz707-fast
```

The control bytes above are the verified IQ-704B read profile. By default,
`dump` uses FPGA-timed bursts with 5 µs address/idle setup and 5 µs selected
read time. `--read-phase-ns` sets both phases to 200–5000 ns in 50 ns steps;
500 ns has been checked on the OZ-707 ROM and SRAM2, while other cards still
need their own timing checks. It makes at least two passes,
compares each byte,
and writes a binary image plus a JSON manifest with the SHA-256 hash only
after the passes agree. `dump --slow` uses the original host-timed cycles
for diagnosis. `shell` accepts `a VALUE MASK` for address bits,
`c VALUE MASK` for controls, `s` for a snapshot, `r ADDRESS IDLE ACTIVE MASK
[SETTLE_US]` for one timed cycle, and `z` to release the pins. Values accept
`0x` notation. Driving commands re-arm the probe; the watchdog releases it
after one second without a command or burst progress.

The host batches reads in 65,535-byte UART requests. On the OZ-707, a full
1 MiB scan at the old 1 Mbaud/5 µs setting took 26.6 seconds for two passes.
At 5 Mbaud/500 ns, 48 MiB of complete repeated scans matched the baseline
without a timeout: about 2.65 seconds per MiB pass, or 5.3 seconds for the
usual two passes, plus startup and file overhead. Faster 8 Mbaud experiments
lost UART bytes and are not the selected configuration. The fast timing has
only been qualified on this OZ-707 card and bench setup.

## Named bank dumps

`dump-banks` reads a JSON plan of named banks. Each bank specifies an address
range and the electrical idle/read levels for the control pins. A pin entry is
`[idle, active]`; omitted pins are high impedance. The plan must drive RW high
in both phases, as in the verified read cycle. The tool reads a preflight byte
for each bank, records the observed active control and protected input pins,
then compares at least two full passes before publishing the bundle.

The known IQ-704B EPROM plan is
[`plans/iq704b-eprom.json`](./plans/iq704b-eprom.json). To inspect its decoded
pin settings without touching hardware:

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py \
  dump-banks --plan projects/sharp-organizer-probe/plans/iq704b-eprom.json \
  --output-dir projects/sharp-organizer-probe/build/iq704b-attributed --dry-run
```

The observed OZ-707 ROM/SRAM plan is
[`plans/oz707-eprom-sram2.json`](./plans/oz707-eprom-sram2.json). With the Au1
UART connected, omit `--dry-run` and add `--port /dev/cu.YOUR_AU_UART`.
For an SRAM bank, add another bank entry with its own address range and pin
map, such as `"SRAM1": [1, 0]`, while holding unused selects high if the
card requires that. The IQ-704B run verified only its EPROM selection; the
OZ-707 run verified EPROM and SRAM2. Other cards' SRAM patterns need to come
from their wiring or measured host cycles. A bank plan describes pin-selected
banks; it does not perform writes
to internal bank registers.

For the known OZ-707, `dump-card` checks the whole ROM image and then captures
both ROM and SRAM2 by default. Unknown images require an explicit
`dump-banks --plan`, so missing SRAM is not silently treated as captured.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py \
  --port /dev/cu.YOUR_AU_UART dump-card --output-dir build/card-capture
```

The output is a new directory containing the exact input `plan.json`, a
`manifest.json`, and one `.bin` plus `.bin.json` sidecar per bank. Each record
includes the source-plan hash, address range, raw control bytes and mask,
named driven/undriven pin levels, pins driven low during the read, observed
preflight pin levels, byte count, and SHA-256. The directory is published only
after every bank passes comparison. Electrical low is recorded as low; the
manifest does not infer a pin's assertion polarity.

## SRAM write test

Capture the current card with `dump-card`, archive its SRAM bank, and commit
that image and sidecar before testing writes. `test-sram-write` checks that the
backup bytes are in Git `HEAD`, compares the live SRAM against the full backup,
changes one byte, reads it back, restores the original byte, and compares all
SRAM bytes again. It writes `before.bin`, `after-restore.bin`, and `result.json`
to a new result directory. The default test address is the final byte of the
backup; `--address` selects another byte.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py \
  --port /dev/cu.YOUR_AU_UART test-sram-write \
  --backup-image /path/to/committed/capture/bank-01.bin \
  --sram 2 --result-dir build/sram-write-test
```

The bounded `W` command accepts only SRAM1 or SRAM2. It keeps OE and the ROM
selects high, drives data before selecting SRAM, pulses RW low for 5 µs, and
releases all driven pins after the cycle. The read commands never drive data.

## Wire protocol

UART framing is 8N1. The host and FPGA use 5 Mbaud with the current bitstream;
the FPGA's 20-cycle divider at 100 MHz is exact. Use `--baud` for a different
bitstream's UART rate. The protocol is binary and deliberately small:

| Request | Reply | Meaning |
| --- | --- | --- |
| `I` | `OBP3\n` | Identify gateware and protocol version |
| `?` | 16 bytes starting `S` | Latched pin and drive snapshot |
| `UREAD` | `U` | Unlock address/control outputs |
| `A` + 3-byte address + 3-byte OE mask | `A` or `!` | Set 20 address values and output enables |
| `C` + control value + OE mask | `C` or `!` | Set control values and output enables |
| `R` + 3-byte start + 2-byte count + idle + active + control mask | `R` then count bytes, or `!` | Read sequential bytes and release after the last byte |
| `T` + one byte in 50 ns units (4–100) | `T` or `!` | While disarmed, set each read phase to 200–5000 ns; default is 5000 ns |
| `W` + 3-byte address + data byte + SRAM selector (1 or 2) | `W` or `!` | Drive one byte with OE high, pulse RW low for 5 µs, restore idle, and release |
| `Z` | `Z` | Release pins and disarm |

The 16-byte snapshot is `S`, three address bytes, data, control, protected,
three address-drive bytes, three address-OE bytes, control drive, control OE,
and armed flag. Address values are big endian; the high four bits of each
three-byte field are unused. Control bit order from LSB is RW, OE, CI, E2,
MSKROM, SRAM1, SRAM2, EPROM. Protected bit order from LSB is STNBY, VBATT,
VPP, NC02, NC42, NC43, NC44. A snapshot reports synchronized inputs and
the currently configured output masks; it does not claim to identify the
card type.

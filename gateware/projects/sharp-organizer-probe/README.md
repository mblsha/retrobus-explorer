# Sharp organizer card probe for Alchitry Au1

See [BENCH.md](./BENCH.md) for live tests, captures, and throughput measurements.

This is a removable-card host for the IQ-7000 system bus. It uses Spade and
the shared UART primitives at 4 Mbaud. The physical target is the **Sharp
Organizer Host Adapter v1 (2025-05-11)**, the **Level Shifter Element Au1 v2
(2025-05-11)**, and the **inverted FFC cable**. The generated XDC uses the
existing `constraints/targets/sharp-organizer-card.acf` mapping; it has the
same 43 card-facing signals as the passive `sharp-organizer-card` project.

The passive project samples an organizer acting as bus master and streams a
trace over FT600. This probe instead drives selected address and control pins
as a card host. UART carries commands and pin snapshots. Sequential data can
use UART, or the Ft Element's FT600 USB interface with OBP5 or newer gateware.

## Electrical behavior

All card-facing FPGA outputs are released at reset. STNBY, VBATT and VPP are
input-only. NC02/NC42/NC43/NC44 default to inputs and have a separate four-bit
value/output-enable mask in OBP6. Address and the eight control pins have
independent output-enable masks. Data is input-only during reads and is driven
only during the bounded SRAM write command. A
malformed unlock, `Z`, reset, or one second without probe activity releases every
drive-capable pin. A burst also releases its pins after the last byte. The
TXB0108s on the Au1 level shifter have OE tied high in
hardware: the FPGA cannot turn off the translators. Their 3.3 V side is on the
Au1; the card side follows the adapter's 5 V supply.

For a card swap, **release the FPGA outputs rather than drive the pins low**:
several card selects and `RW` are active low. The host CLI now sends `Z` and
checks that `armed`, address drive mask, control drive mask and NC drive mask are zero before
closing UART after every identified command, including a failed capture or
write. Gateware disables the data output with the same disarm state. Use
`park` to check explicitly, then power off the card adapter before unplugging
the card. A failed UART release or snapshot is not a verified park; wait for
the gateware watchdog and power off before swapping.

The IQ-704B was read with idle control `0xff`, active control
`0x7d`, and mask `0xff`. Its header includes `thesaurus`; the entire 20-bit
address scan repeated every 256 KiB and matched on two passes. These values
are observed for that card. The OZ-707 Basic card was then read with EPROM
selected for its 128 KiB ROM and SRAM2 selected for its 32 KiB data area;
both matched on two passes. Generic discovery tests the four single memory
selects at each CI/E2 level with RW high. The FPGA never drives VPP.

Before inserting a card into a newly assembled cable/adapter, validate the
physical FFC orientation and Au1 mapping with `projects/pin-tester`, then use
this probe's `sample` command with no card. The pin mapping was checked against
both PCB source files, but that is not a live continuity test.

## Build and verification

From `gateware/`:

```sh
uv run --frozen python tools/run_tb.py --project projects/sharp-organizer-probe
uv run --frozen python tools/project_inventory.py --check
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.92.0/lib ./.venv/bin/python projects/sharp-organizer-probe/scripts/build_nextpnr.py --seed 7
```

The last command runs Swim/Spade, Yosys, nextpnr-xilinx, Project X-Ray FASM
packing, and a bitstream decode round trip for `xc7a35tftg256-1`. It writes
`build/nextpnr-au1-seed7/design.bit` and `result.json`; both are generated files.
The checked OBP6 seed-7 build passes the 100 MHz target at 136.44 MHz for
the core and 189.00 MHz for FT. It decoded 62,654 configuration bits; SHA-256:
`bce83320aaf53f4fb60a43bd69f3ba98ac6347511b76e8227a7f5ee58a648566`.
The bitstream is for the Au1 v1 FPGA, not Au1 v2.

To load the checked bitstream into FPGA SRAM through the tested Au1 JTAG path:

```sh
openFPGALoader -b alchitry_au --ftdi-serial FT4ZS6I3 -m \
  projects/sharp-organizer-probe/build/nextpnr-au1-seed7/design.bit
```

Replace the FTDI serial for another Au1. The SRAM load is volatile.

## USB-UART commands

`scripts/organizer_probe.py` uses pyserial at 4 Mbaud. Use `--baud 5000000`
with an older 5 Mbaud bitstream. The CLI requires the
UART port explicitly and identifies the bitstream before each operation.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART sample
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART park
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART shell
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART \
  cycle --address 0x00000 --idle 0xff --active 0x7d --mask 0xff
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART \
  dump --start 0 --length 0x40000 --idle 0xff --active 0x7d --mask 0xff --output iq704b.bin
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py --port /dev/cu.YOUR_AU_UART \
  dump-card --output-dir projects/sharp-organizer-probe/build/card-discovery
```

`park` sends `Z` and reports a snapshot with zero drive masks and
`armed=False`; it can be run after any probe or write before powering down for
a card swap. The control bytes above are the verified IQ-704B read profile.
By default, `dump` uses FPGA-timed bursts with 5 µs address/idle setup and
5 µs selected read time. `--read-phase-ns` sets both phases to 200–5000 ns in
50 ns steps. Every CLI invocation explicitly programs its requested phase,
including the conservative default; timing cannot silently carry over from
a previous fast run.
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

The host defaults to 65,535-byte burst read requests. The global option
`--burst-bytes 8192` reduces each request to 8 KiB for transport diagnosis;
it applies to dumps, discovery, and the reads used for SRAM verification.
It changes the burst size while retaining the selected card timing and
full-pass comparisons. A timed-out UART payload read is retried up to twice at the same
address, after clearing pending UART input and verifying a parked state. Short
payloads are discarded; both complete passes must still agree. Writes are not
retried. Capture metadata records the request size and recovered read timeouts.
An unrecovered failure discards the incomplete discovery; run it again before
archiving.

### FT600 payload transport

Connect the Ft Element USB cable to a USB 3 port. The FT600 must already be
configured for FT245 FIFO mode and one bidirectional channel; the client
checks this without changing its configuration. Use its exact USB serial:

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py \
  --port /dev/cu.YOUR_AU_UART --ft600-serial YOUR_FT600_SERIAL \
  --read-phase-ns 1000 capture-card \
  --archive-dir /path/to/git-repo/card-captures --reported-model MODEL
```

The command uses the repository's `py/d3xx` bindings and installed D3XX shared
library. OBP5 acknowledges a burst on UART and reads its complete payload into the
shared 8192-word FPGA FIFO, then releases the card before USB transmission.
One FIFO slot is reserved, so FT requests are capped at 8191 card bytes;
`--burst-bytes` is capped automatically and metadata records the effective
size. Every FT word contains a sampled card byte and
an `0xa5` marker; the host checks the word count and markers, then performs
the same full-pass comparisons and attributed deduplication as UART captures.
USB backpressure holds the buffered data while the card is already released.
The watchdog protects an interrupted card read. This retains a chunk, not a
whole-bank image.

On the connected PA-7C18, 200 ns phases checked 4 MiB of ROM/SRAM mirrors
against committed images in 2.59 seconds (1.54 MiB/s), with no retry or framing
error. The complete 16-view, two-pass capture, backup commits and SRAM
write/restore probes finished in 33.2 seconds, versus 509.5 seconds for the
earlier 5 µs UART capture. The ROM matched the conservative image, and SRAM
matched the separately committed current snapshot. An independent two-pass
5 µs read verified every SRAM byte after restoration. This qualifies 200 ns
for this card and bench; the generic default remains 5 µs.

USB-UART carries commands only in this mode. The observed payload rate is
over four times its 4 Mbaud 8N1 ceiling. Faster card phases improve FT throughput;
the present card cycles and chunk command overhead limit the measured rate.
The FT600's USB 3 bandwidth has not been saturated by this experiment.

The client parks and drains stale FT data before starting. An FT read failure
aborts the capture without automatic replay; the next operation must start
with another park and drain. Capture metadata records both UART control and
payload transports, plus the FT600 serial. Keep 5 µs phases for an unqualified
card and compare faster timings against its committed conservative capture.

For direct FT2232H UART diagnostics, `--port ftdi://YOUR_AU_SERIAL/B` reuses
the existing `ethernet-diagnostic` libftdi backend. Interface A is JTAG;
the URI requires interface B and an explicit serial number.

In earlier OZ-707 experiments, a full
1 MiB scan at the old 1 Mbaud/5 µs setting took 26.6 seconds for two passes.
At 5 Mbaud/500 ns, 48 MiB of complete repeated scans matched the baseline
without a timeout: about 2.65 seconds per MiB pass, or 5.3 seconds for the
usual two passes, plus startup and file overhead. Faster 8 Mbaud experiments
lost UART bytes and were rejected. Sustained PA-7C18 experiments later stalled
the 5 Mbaud link, so the current build uses 4 Mbaud; see [BENCH.md](./BENCH.md)
for measurements and qualification limits. Card timing needs qualification
against a conservative backup on each card and connected bench.

## Read pipeline and speed qualification

The FPGA generates each sequential address and the two read phases without a
host round trip per byte. It holds one sampled byte in `burst_data`, sends that
byte through the shared UART transmitter, and overlaps the next card read
with transmission. It waits when the transmitter is busy. UART payloads have
no BRAM block buffer; FT600 payloads are read into the shared FPGA FIFO first
and then transmitted as a continuous burst, as described above.

A UART block buffer could add checksums and retransmission without rereading
the card, and decouple card timing from UART timing. It cannot increase the
sustained 8N1 link capacity: 4 Mbaud carries at most 400,000 payload bytes/s;
5 Mbaud carries at most 500,000. The generic 16-view, two-pass scan transfers
32 MiB before host deduplication, so those wire-only lower bounds are 83.9 s
and 67.1 s. Commands, timing gaps, discovery, and SRAM probes add overhead.
FPGA hashes or comparisons could avoid transmitting duplicate ranges, but
the current implementation transfers and compares every byte on the host.

`benchmark_card.py` checks candidate timing and request sizes against an
existing committed schema-2 capture. It compares complete unique ROM/SRAM
images first, then scans their full observed mirrors on at least two passes.
It performs no writes and records bytes, hashes, elapsed time, retries, and
final park verification. The JSON records a failure when an experiment or
cleanup fails; a short successful benchmark does not qualify a complete
capture.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/benchmark_card.py \
  --port /dev/cu.YOUR_AU_UART --baud 4000000 \
  --capture-dir /path/to/git-repo/card-captures/CONSERVATIVE_CAPTURE \
  --output build/read-benchmark.json --case 1000:65535
```

Add `--ft600-serial YOUR_FT600_SERIAL` to benchmark buffered FT payloads.
If SRAM changed, first save and commit a new two-pass 5 µs `dump` and its
sidecar. `--reference-image bank-NN.bin=/path/to/current.bin` uses that
committed current snapshot for the named SRAM-only image. The report records
the replacement and uses the prior capture's address period to form expected
mirrors; include a 5000 ns full-scan case before testing faster cases.

Use a new output filename for each experiment. The baud must match the loaded
bitstream. The default matrix includes more aggressive phases; specify
`--case` repeatedly to choose a smaller matrix. Finish qualification with a
complete capture and compare its unique images and per-view full-scan hashes
against the conservative capture. Keep timing qualifications specific to the
card and connected bench.

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

### Read-only transition experiments

`scripts/transition_probe.py` captures views selected by an ordered preamble.
Its [example plan](plans/read-transition-example.json) pulses CI while A16 is
high and MSKROM/OE are asserted, then samples a short window with the controls
held. It is a hypothesis to test, not a confirmed bank-selection recipe.
The [NC example](plans/nc-read-example.json) drives the four auxiliary contacts
with OBP6 while retaining the same read-only control restrictions.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/transition_probe.py \
  --plan projects/sharp-organizer-probe/plans/read-transition-example.json --dry-run
uv run --frozen python projects/sharp-organizer-probe/scripts/transition_probe.py \
  --port /dev/cu.YOUR_AU_UART --ft600-serial YOUR_FT600_SERIAL \
  --plan /path/to/measured-read-sequences.json --output-dir /path/to/new-experiment
```

Steps are full-mask `address` or `control` commands, an optional OBP6 `nc`
command with a four-bit `value` and `mask` (default `0xf`), or a `hold_us` delay
up to 100 ms. NC bit order is NC02, NC42, NC43, NC44, from least significant.
All control states must keep RW high and select at most one memory.
Data stays input-only during reads; VPP, VBATT and STNBY always stay inputs.
NC outputs are opt-in and require RW driven high. Firmware rejects a control
command that would lower or release RW with NC outputs on, and rejects SRAM
writes while an NC mask is enabled. A preamble starts
from a verified park, initializes controls to `0xff` and address to zero, then
replays before **every chunk of every pass**. This initialization is recorded;
parking does not prove a card latch was reset. Use only with the card adapter
acting as host, not alongside an organizer driving the bus.

Read mode `burst` uses the existing FPGA-timed read cycle, which applies idle
controls and the chunk address before sampling. Mode `held_select` preserves
the preamble's final active controls and changes only addresses during a chunk;
the preamble must end with the requested active control byte. It samples through
UART snapshots and is much slower, so use short diagnostic windows. Its timing
is host latency, not `--read-phase-ns`. Both modes park between chunks.

The bundle stores the exact `plan.json`, source hashes, pass/full-window hashes,
named pin levels, and compressed `observations.jsonl.gz` containing every
preamble snapshot, held sample and chunk's verified park. Full pass agreement
is required before saving an image; a failed run retains an explicitly failed
manifest and diagnostics, with no automatic retry. Identical byte content shares
a generic image while every selection sequence remains separately attributed.
Neither a matching fingerprint nor a repeated address period proves a physical
bank alias. Preserve the experiment beside the originating capture and record
its conservative references and coverage limits in the archive's documentation.

`dump-card` scans all 16 single-select CI/E2 states over the full 20-bit
address range. It reads each view twice, finds its fully observed address
period, and stores one image per unique byte sequence. Every view remains in
the manifest with its pin levels, full-scan hash, duplicate-data reference,
and observed mirror relation. Equal bytes do not establish that two selects
address the same physical chip. Read-only results remain `rom_candidate`,
`sram_candidate`, or `open_bus_or_echo`; a volume header supplies only a volume
ID and capacity hint. The scan cannot discover card-specific bank registers,
simultaneous-select modes, or addresses above 20 bits; use an explicit plan
for such cards. The default 5 µs phase is conservative for an unqualified card.
The 16-view, two-pass OZ-707 scan took about seven minutes at that setting.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py \
  --port /dev/cu.YOUR_AU_UART dump-card --output-dir build/card-capture
```

The schema-2 output contains `manifest.json`, one `bank-NN.bin` per unique
image, and JSON sidecars. Its `views` list preserves every tested selection,
including duplicate and open-bus reads. An observed period is a byte-level
alias across the scanned address space, not a physical capacity measurement.
The directory is published only after every two-pass comparison succeeds.

To save a capture in a Git archive and automatically test backed-up SRAM
candidates, use `capture-card`. It commits the capture in Git before the first
write probe, then commits the probe result separately. `--read-only` stops
after the backup commit. Pass the parent directory for capture IDs with
`--archive-dir`; it must be inside a writable Git repository with a configured
Git identity.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py \
  --port /dev/cu.YOUR_AU_UART capture-card \
  --archive-dir /path/to/git-repo/card-captures --reported-model OZ-707
```

If `dump-card` already produced a verified read-only directory, avoid another
full scan with `archive-discovery --source-dir build/card-capture
--archive-dir /path/to/git-repo/card-captures`. It validates every stored image and
full-scan hash, commits the copied backup, then runs the same SRAM probes.

The automatic probe skips selections whose reads track the last data-bus
value. For stable SRAM-select views it compares the live bank to the committed
backup, writes two trial addresses, reads after priming the bus from another
view, checks other SRAM views for physical aliases, restores both original
bytes, and compares the entire banks with their backups. A view is
`writable_ram_confirmed` only if both trials persist and restore.

To make an intentional write, supply a committed `write-probes/result.json`
from the same capture. `write-sram` checks that the live image still matches
the backup, writes the input bytes, verifies a full-bank read, and commits the
before/after images and transaction record. Put `--result-dir` inside the
archive repository. Later writes can use `--expected-image` with the committed
`after.bin` from the previous transaction; the tool still checks the entire
live bank before writing.

```sh
uv run --frozen python projects/sharp-organizer-probe/scripts/organizer_probe.py \
  --port /dev/cu.YOUR_AU_UART write-sram \
  --capture-dir /path/to/git-repo/card-captures/CAPTURE \
  --probe-result /path/to/git-repo/card-captures/CAPTURE/write-probes/result.json \
  --view sram2-ci1-e21 --address 0x100 --input payload.bin \
  --result-dir /path/to/git-repo/card-captures/CAPTURE/write-transaction-01
```

## SRAM write test

For the legacy one-bank test, capture the current card with an explicit plan,
archive its SRAM bank, and commit that image and sidecar. `test-sram-write` checks that the
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

UART framing is 8N1. The host and FPGA use 4 Mbaud with the current bitstream;
the FPGA's 25-cycle divider at 100 MHz is exact. Use `--baud` for a different
bitstream's UART rate. The protocol is binary and deliberately small:

| Request | Reply | Meaning |
| --- | --- | --- |
| `I` | `OBP6\n` | Identify gateware and protocol version |
| `?` | 16 bytes starting `S` | Latched pin and drive snapshot |
| `Q` | 18 bytes starting `S` | OBP6 snapshot: legacy 16 bytes plus NC value and output mask |
| `UREAD` | `U` | Unlock address/control outputs |
| `A` + 3-byte address + 3-byte OE mask | `A` or `!` | Set 20 address values and output enables |
| `C` + control value + OE mask | `C` or `!` | Set control values and output enables |
| `N` + NC value + NC OE mask | `N` or `!` | OBP6: set four NC contacts with RW driven high; upper nibble must be zero; invalid command releases all outputs |
| `R` + 3-byte start + 2-byte count + idle + active + control mask | `R` then count bytes, or `!` | Read sequential bytes and release after the last byte |
| `F` + the same fields as `R` | UART `F`, then count FT600 words, or UART `!` | OBP5: buffer 1–8191 card bytes as little-endian `0xa5XX`, with both byte enables set; release the card before FT transmission |
| `T` + one byte in 50 ns units (4–100) | `T` or `!` | While disarmed, set each read phase to 200–5000 ns; default is 5000 ns |
| `W` + 3-byte address + data byte + config | `W` or `!` | Drive one byte with OE high, pulse RW low for 5 µs, restore idle, and release. Config bits 0–1 select SRAM1 (1) or SRAM2 (2); bits 2–3 lower CI/E2. Other bits must be zero. The original 1/2 codes remain valid. |
| `Z` | `Z` | Release pins and disarm |

The host also accepts OBP2–OBP5 for their supported commands. FT600
payloads require OBP5 or newer. An `F` failure, including a lost UART acknowledgement,
aborts without replay because the FIFO may already contain that burst.

The 16-byte snapshot is `S`, three address bytes, data, control, protected,
three address-drive bytes, three address-OE bytes, control drive, control OE,
and armed flag. Address values are big endian; the high four bits of each
three-byte field are unused. Control bit order from LSB is RW, OE, CI, E2,
MSKROM, SRAM1, SRAM2, EPROM. Protected bit order from LSB is STNBY, VBATT,
VPP, NC02, NC42, NC43, NC44. A snapshot reports synchronized inputs and
the currently configured output masks; it does not claim to identify the
card type. OBP6 retains `?` unchanged and adds `Q`, appending NC drive and mask
bytes in NC02/NC42/NC43/NC44 bit order. The host uses `Q` with OBP6 so `park`
checks auxiliary masks too. `shell` accepts `n VALUE MASK` for NC drive after
RW has been driven high; scripted transition plans replay these commands
automatically before each read chunk. Every release path clears NC enables.

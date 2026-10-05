# Sharp organizer native execution card

Spade gateware for Alchitry Au1 v1, with the Ft v1 FT600 Element and the
organizer card connector mapping. It provides a resident native experiment
loop, local code memory, small SRAM2 scratch memory, adjustable bus timing,
and bidirectional USB3 transport.

The intended use is a **ROM/SRAM card emulator and native eval loop for the
IQ-7000-style bus and OZ family**, including OZ-9600 experiments. The exact
organizer launch path and electrical compatibility need bench qualification.

## Start here

- [Quick start](#quick-start): assemble, load, enter the supervisor, and run a job.
- [CLI command reference](#cli-command-reference): UART control, SRAM2 access,
  timing, FT600 capture/input, and disarm.
- [Execution and streaming](#how-execution-and-streaming-work): mailbox
  commits, code memory, FPGA buffers, and continuous host-fed data.
- [Qualification record and next bench steps](QUALIFICATION.md): verified
  tests/builds and remaining organizer work.
- [Choose an organizer tool](../../README.md#choose-an-organizer-tool):
  emulator, removable-card dumper, or passive monitor.

**Status:** pin-level simulation, native supervisor CPU-model tests, and a
100 MHz nextpnr bitstream build pass. Organizer boot entry and electrical
operation of this emulator have not yet been qualified on IQ-7000/OZ hardware.
A native entry into the supervisor is still required. This project does not
supply a stock firmware launch/header implementation. The
[qualification record](QUALIFICATION.md) contains the initial verification
results and bitstream identity.

## Hardware and directions

Use the **Sharp Organizer Card Adapter** plugged into the organizer, the Level
Shifter Element Au1 v2, and the same checked connector mapping as the passive
`sharp-organizer-card` monitor. The **Host Adapter used for dumping removable
cards is the opposite fixture**. Validate FFC orientation and the organizer
side of the fixture before flashing/arming. Keep the FT600 USB3 port connected
for captures and host-fed streams; the Au1 USB-UART carries control at 4 Mbaud.

Only D0..D7 are driven, and only during a qualified selected read. Address,
RW, OE, CI, E2, all four chip selects, STNBY, VBATT, VPP and NC contacts remain
inputs. Reset starts disarmed. Raw reset, direction, select, OE and address
changes immediately inhibit data output, before the synchronizers settle.
Unselected or ambiguous multiple selections do not get an emulated response.

The emulator stays armed when a UART command or CLI process finishes. Use
`disarm` before disconnecting the fixture or powering down the organizer.
Disarm releases the data bus to high impedance; it does not drive the
organizer's control/address lines low. Stopping a capture also leaves native
code running, unless `--disarm-on-exit` was supplied.

## Build and verification

From `gateware/`, using the existing development environment:

```sh
uv run --frozen --no-sync python tools/project_inventory.py --check
uv run --frozen --no-sync python tools/run_tb.py --project projects/sharp-organizer-emulator
uv run --frozen --no-sync python lib/shared-components/scripts/test_component.py card_memory
uv run --frozen --no-sync python -m unittest discover -s projects/sharp-organizer-emulator/test_host -v
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.92.0/lib \
  ./.venv/bin/python projects/sharp-organizer-emulator/scripts/build_nextpnr.py
```

`--no-sync` preserves this checkout's working environment. The lock metadata
registers the new package using the existing pinned dependencies. Do not run
`uv sync` on the bench checkout. The client uses `pyserial`. Native
assembly additionally requires an environment containing the SC62015 assembler
and its dependencies; supply that checkout via `--assembler-root`.

The build uses shared UART, synchronizers, FIFO, FT245 transport, and a new
shared same-clock dual-port memory primitive. It generates tracked
`constraints/pins.xdc`, checks all organizer inputs remain inputs, checks
100 MHz post-route timing, and verifies packed configuration bits by decoding
the bitstream again. Output is `build/nextpnr-au1/design.bit` and `result.json`.
It does not flash hardware.

Cocotb covers UART framing/bounds, ROM mirrors, asynchronous turnaround,
address changes under a held select, short-write cancellation, live timing
updates during an existing window, SRAM writes, native idle upload guards,
FT byte enables, held-read consumption, receive backpressure, bidirectional
service, overflow accounting, native trace control, and parser timeout without
disarming emulation.

Optional CPU-model test (run in an assembler environment):

```sh
FORCE_BINJA_MOCK=1 SC62015_ASSEMBLER_ROOT="$SC62015_SOURCE_ROOT" \
  python -m unittest discover -s projects/sharp-organizer-emulator/test_host -v
```

This is a software witness for the assembled native loop; it does not qualify
the organizer's launch ABI or FPGA electrical timing.

## Quick start

The build and simulation commands are in [Build and verification](#build-and-verification).
Hardware use below requires the Card Adapter and a separately established
native entry method. Loading FPGA gateware and loading its ROM image are
separate operations: `build_nextpnr.py` builds the FPGA bitstream;
`emulator.py load` writes code into the already loaded emulator over UART.

Examples below run from `gateware/`. Set an exact UART path and FT600 serial:

```sh
export ORGANIZER_UART=/dev/cu.usbserial-REPLACE
export ORGANIZER_FT_SERIAL=REPLACE
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" status
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py --help
```

Build the supervisor using your assembler's Python environment. `0x40000` is
an IQ-7000 mapping candidate; pass the CPU base verified for your actual host.
The code image is 16 KiB and is mirrored through the selected ROM window.

```sh
python projects/sharp-organizer-emulator/scripts/emulator.py build-supervisor \
  --assembler-root "$SC62015_SOURCE_ROOT" --cpu-base 0x40000 --output /tmp/supervisor.bin
python projects/sharp-organizer-emulator/scripts/emulator.py build-supervisor \
  --assembler-root "$SC62015_SOURCE_ROOT" --cpu-base 0x40000 \
  --template boot_smoke --output /tmp/smoke.bin
```

After the fixture and native entry method are ready:

```sh
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" load /tmp/supervisor.bin
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" config --eval
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" arm
# Enter CPU base+0x0100 through a separately verified native launch method.
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" job /tmp/smoke.bin
```

`load` disarms, writes the full image, reads it back, and seals it before an
explicit arm. The gateware seal is a host verification declaration, not an
FPGA CRC. Any disarmed UART memory write invalidates it. Runtime `job` uploads
and verifies code and mailbox first, then commits the sequence byte last.
Only payload/mailbox ROM writes are permitted while the native supervisor
reports idle. Committing a nonzero sequence closes the upload window immediately,
covering the interval before the CPU reports busy. Resident/header updates
require disarm. A non-returning job remains busy and cannot be overwritten;
a timeout does not halt the CPU.

To collect bus traffic or exchange data with a continuous payload, continue
with [FT600 capture and host-fed streams](#ft600-capture-and-host-fed-streams).
When the session is finished, release the emulator explicitly:

```sh
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" disarm
```

This releases the FPGA data output. The organizer may still be executing
card code, so reset/re-enter its normal firmware before removing the fixture
or restarting native experiments.

### Timing, profile, and scratch memory

```sh
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" timing --read-ns 50 --write-ns 100
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" read 0x8000 0x800 /tmp/sram2.bin
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" write 0x8000 /tmp/scratch.bin
```

Delays are qualification clocks in 10 ns steps, 0..2550 ns. Each bus window
snapshots its delay, so a UART timing change affects subsequent windows.
Synchronizers, detection and registered memory add roughly 40..60 ns beyond
the configured delay; zero is not zero physical latency. Current defaults
are 50 ns read and 100 ns write qualification, pending hardware measurement.
There is no programmable drive after a read ends. Raw termination always
releases immediately. SRAM2 mirrors its low 11 address bits (2 KiB), ROM its
low 14 bits (16 KiB); full 32 KiB SRAM behavior is intentionally not implemented.

Default ROM selection is active-low EPROM. `config --rom-select MSKROM` changes
it while disarmed. `--trace` enables all qualified bus-cycle records; `--eval`
enables mapped control registers; `--no-sram` disables the SRAM2 response.
Profile changes need an inactive bus window. CI/E2 are recorded, not assigned
an invented banking protocol. Every trace retains all 20 address bits.

## CLI command reference

Entrypoint: [scripts/emulator.py](scripts/emulator.py). Run from `gateware/`:

```sh
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py --help
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py capture --help
```

Place the global `--port "$ORGANIZER_UART"` before hardware subcommands.
`--help`, `build-supervisor`, and `decode` work without connected hardware.

| Command | Purpose | Key arguments / result |
| --- | --- | --- |
| `status` | Read emulator state, settings, and counters | Armed/idle/sealed state, timing, trace drops, RX underflows |
| `build-supervisor` | Assemble a native supervisor or example payload | `--assembler-root`, `--cpu-base`, `--output`; optional `--template boot_smoke` or `stream_echo` |
| `load IMAGE` | Disarm, upload and verify a complete ROM image, then seal | Exactly 16384 bytes; arming is a separate command |
| `config` | Select eval registers, tracing, ROM select and SRAM2 response | `--eval`, `--trace`, `--rom-select` (`EPROM` or `MSKROM`), `--no-sram`; omitted flags are cleared |
| `arm` | Enable selected-read responses for the sealed image | Keeps running across CLI exits |
| `timing` | Change qualification delays without rebuilding | `--read-ns`, `--write-ns`; 10 ns steps, 0..2550 ns |
| `read ADDRESS SIZE OUTPUT` | Read local code or SRAM2 memory through UART | ROM `0x0000..0x3fff`; SRAM2 `0x8000..0x87ff` |
| `write ADDRESS INPUT` | Write local memory and verify readback | Native busy/protected-region guards apply |
| `job PAYLOAD` | Verify an experiment and commit its mailbox sequence | Default waits for return; `--timeout` or `--no-wait` for continuous work |
| `capture` | Save FT600 bus records, optionally send host data concurrently | `--ft-serial`, `--output`, `--seconds`, optional `--input`, `--decode-live`, `--disarm-on-exit` |
| `decode INPUT OUTPUT` | Convert binary FT records to JSONL offline | Reports sequence gaps; rejects incomplete final records |
| `disarm` | Release data-bus output explicitly | Required before disconnecting or powering down the organizer |

## How execution and streaming work

1. The UART client uploads local FPGA code memory and verifies it before
   declaring the image sealed. FPGA memory serves organizer reads locally.
2. The resident supervisor polls the mailbox. While it reports idle, the host
   can upload and verify a payload and arguments. The final sequence write
   closes the upload window immediately and makes that job visible to the CPU.
3. The supervisor calls the payload at CPU base + `0x0400`. START, ECHO, STOP,
   and state writes become decoded control events. A returning payload uses
   `RETF`; the supervisor then reports idle for the next job.
4. The FPGA qualifies bus windows and packs address, data, pin levels,
   timestamp and sequence into buffered records. FT600 carries these to the
   host independently of UART command bandwidth.
5. The opposite FT600 pipe fills an FPGA receive FIFO. Native code polls
   receive status and consumes bytes through mapped registers. A held read
   consumes one byte. Full receive queues apply backpressure to the host.

The [bus controller](src/bus.spade), [transport](src/transport.spade),
[UART protocol](src/protocol.spade), and [top-level integration](src/main.spade)
reuse the shared UART, synchronizers, memory and FT245 primitives.
The [supervisor](asm/supervisor.asm.in), [returning smoke payload](asm/boot_smoke.asm.in),
and [continuous receive/echo payload](asm/stream_echo.asm.in) provide the native
examples. Their CPU-model test is in [test_host/test_emulator.py](test_host/test_emulator.py).

## FT600 capture and host-fed streams

```sh
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" config --eval --trace
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" capture --ft-serial "$ORGANIZER_FT_SERIAL" \
  --seconds 10 --output /tmp/organizer-capture
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  decode /tmp/organizer-capture/trace.bin /tmp/organizer-capture/events.jsonl
```

The capture directory must be new. It contains binary records, a manifest with
start/end settings and hardware counters, and optional live JSONL. Binary-only
capture is the default fast path; `--decode-live` trades throughput for live
JSON events. The decoder reports reads, writes, register writes, addresses,
data, all control and auxiliary pin levels, timestamps and sequence gaps.
It does not claim CPU instruction disassembly. Reset the FPGA before the first
capture of a fresh session; a previous capture ending mid-record must be
continued as the same stream before decoding. A partial final record is
reported in the manifest and rejected by standalone strict decoding.

Add `--input stream.bin` to send exact bytes concurrently through the opposite
FT pipe. Input length must be even for the 16-bit FT interface. Reads drain in
the foreground while a bounded-time writer thread handles input backpressure.
Partial transfers are retried from their confirmed byte count. The manifest
records sent bytes and incomplete input. This client uses the macOS/Linux D3XX
ABI and reuses the probe client's exact-serial and FIFO configuration checks.
It does not reconfigure the FT600 EEPROM.

Use `build-supervisor --template stream_echo` to assemble a continuous payload
that polls FT receive status and echoes bytes into FT control records. Submit it
with `job --no-wait /tmp/stream-echo.bin`; the command returns after committing
the sequence. It never returns to the supervisor. In another step,
`capture --input ...` can feed it and collect its output.
Reset/re-enter the supervisor to replace such a payload.

### Continuous input example

Using your assembler environment, prepare the payload for the same CPU base
as the resident supervisor:

```sh
python projects/sharp-organizer-emulator/scripts/emulator.py build-supervisor \
  --assembler-root "$SC62015_SOURCE_ROOT" --cpu-base 0x40000 \
  --template stream_echo --output /tmp/stream-echo.bin
```

With the supervisor already entered and idle:

```sh
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" job /tmp/stream-echo.bin --no-wait
uv run --frozen --no-sync python projects/sharp-organizer-emulator/scripts/emulator.py \
  --port "$ORGANIZER_UART" capture --ft-serial "$ORGANIZER_FT_SERIAL" \
  --input /tmp/stream.bin --seconds 10 --output /tmp/organizer-stream-capture
```

Supply an even-length `/tmp/stream.bin`. The echoed input bytes are ECHO
register-write records, identifiable by ROM offset `address & 0x3fff == 0x3ff1`;
general bus tracing may remain disabled. `--no-wait` reports that a job was
committed. START/state records and `status` show whether native code entered it.

### Output files and storage

Output paths are caller-selected. Store code images and capture directories
where your experiment or archive workflow expects them. The tool has no
dependency on a separate ROM/card catalog repository.

| Artifact | Contents |
| --- | --- |
| Assembler `--output` file | Full 16 KiB supervisor image, or payload bytes for an example template |
| `<output>.asm` / `<output>.json` | Rendered source, CPU base, entries, image size and SHA-256; appended to the full output filename, e.g. `supervisor.bin.json` |
| `CAPTURE/trace.bin` | Binary FT600 event records; preserve as the original capture |
| `CAPTURE/manifest.json` | FT device/configuration, before/after settings and counters, input byte count, completion/error and disarm status |
| `CAPTURE/events.jsonl` | Populated by `--decode-live` or subsequent offline `decode`; initially empty in binary-only capture |

Retain the image metadata alongside the capture to attribute the CPU mapping
and code used. Inspect `capture_complete`, `input_complete`, trailing record
bytes, sequence gaps and hardware drop counters before treating a run as
complete. A failed final UART status/release check is recorded in the manifest;
requested disarm is distinguished from confirmed disarm.

### Buffering and throughput

On the FPGA, 255 complete 16-byte records are buffered before serialization;
the FT transmit clock-crossing FIFO adds 8191 16-bit words. Incoming storage is
511 16-bit words plus the shared 63-word FT receive queue. FT receive fullness
applies backpressure. Outbound fullness drops new records, increments a 32-bit
counter, and leaves gaps in attempted sequence numbers. It never stalls the
organizer. Native output code can poll TX status first. Burst preemption lets
input interrupt outbound activity.

The serializer has a theoretical ceiling of 12.5 million records/s at 100 MHz
(200 MB/s), before FT turnarounds, USB, host decoding and disk overhead. This is
not a measured throughput claim. Actual sustained rates and loss behavior
must be measured on the organizer fixture. UART bandwidth does not limit bus
capture; it limits initial image loading and small control transactions.
Sequence numbers wrap at 65536 and timestamps at 42.95 s. The decoder unwraps
observed timestamp rollovers; intervals spanning unseen whole wraps remain
ambiguous. Use 32-bit hardware counters to audit loss, including trailing loss
without a subsequent record. Counter reset/reprogramming starts a new session.

## Native layout and mapped registers

| ROM offset | Use |
| --- | --- |
| `0000..00ff` | Reserved optional firmware header, initially zero |
| `0100..03ff` | Resident supervisor |
| `0400..3fbf` | Uploaded native experiment, entry `0400` |
| `3fc0..3fde` | Mailbox: `XR`, version 1; remainder available as arguments |
| `3fdf` | Nonzero commit sequence; execute only when it changes |
| `3fe0..3fef` | Reserved |
| `3ff0..3fff` | Control page when eval mode is enabled |

The supervisor needs a valid system stack, leaves IMR untouched, and reserves
internal bytes `0x30/0x31`. Returning payloads must preserve those two bytes and
the stack and use `RETF`. Other A/B/X/Y values may be clobbered. Boot metadata is
optional; no BASIC engine or stock card filesystem is supplied.

| Offset | Operation |
| --- | --- |
| `3ff0` write | START marker and last-begin sequence |
| `3ff1` write | ECHO byte in an FT register-write record |
| `3ff2` write | STOP marker and last-end sequence |
| `3ff4` read/write | Native trace enable, low bit only |
| `3ff5` write | Supervisor state: 0 idle, nonzero busy |
| `3ff7` read | FT RX status: bit 0 available, bit 1 full |
| `3ff8` read | Consume one RX byte, latched once for a held read; empty gives 0 and increments underflows |
| `3ffa` read | Bit 0 indicates space in the complete-record TX FIFO |
| `3ffb` read | Low byte of configured timing version |

Writes require the selected ROM window and RW low; ordinary ROM writes have no
memory effect. Register-write records are generated even when general bus
tracing is disabled. Undocumented control offsets have no write effect; reads
return underlying ROM data. SRAM1 is observed but not emulated.

## Wire formats

UART requests are eight bytes: `a5`, ASCII opcode, little-endian 16-bit host
memory address, three argument bytes, then XOR of the first seven bytes.
Replies are sixteen bytes: `d5`, opcode, status, twelve payload bytes, XOR of the
first fifteen bytes. One command is outstanding. Status 0 succeeds; 1 checksum,
2 range/argument, 3 busy/protected, 4 unsealed, 5 unknown opcode. Partial requests
expire after 10 ms without releasing the emulator. Memory BUSY can be retried;
timeouts and malformed replies fail without automatic write retries.

Opcodes: `I` identity, `S` settings/counters (address 0/1), `R/W` one memory byte,
`T` read/write qualification clocks in args 0/1, `F` flags and ROM mask in args
0/1, `V` host-verification seal, `A` arm, `Z` disarm. `V/A` require address
`5241`, args `4d 21 00` (`ARM!`). Host memory space is ROM `0000..3fff`, SRAM2
`8000..87ff`. See the client for the precise settings/counter payload layout.

FT records are four little-endian 32-bit words:

1. `e7010000 | sequence16` (sequence advances for every attempted record).
2. 100 MHz timestamp ticks, modulo 2^32.
3. Address bits 0..19, control bits 20..27, kind bits 28..31 (read 1, write 2,
   register write 3).
4. Data bits 0..7, auxiliary pins 8..14, armed bit 16, supervisor idle bit 17,
   data drive state at the event bit 18.

Control order, low bit first: RW, OE, CI, E2, MSKROM, SRAM1, SRAM2, EPROM.
Auxiliary order: STNBY, VBATT, VPP, NC02, NC42, NC43, NC44. Pin values retain
physical polarity. Data drive bit 18 is normally low on the initial read event;
the FPGA latches/turns on its response at the following clock edge.

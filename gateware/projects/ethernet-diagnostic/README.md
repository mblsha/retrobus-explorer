# Arty A7 Ethernet and USB SD image service

Load and retrieve the Arty A7-35T's 256 MiB DDR-backed microSD image over
100 Mbps Ethernet. SD remains a writable, four-bit, 13 MHz card on JD using
the bottom-header microSD-Pmod adapter and a common ground. New combined
builds include a full-image USB UART fallback alongside Ethernet; it reuses the reviewed SD frontend,
DDR controller, full-memory BIST, and board wiring.

## Integration status

The implementation at `805c5f7` was requalified on Arty/GKD hardware on
2026-09-14: full 256 MiB SD integrity, cross-interface read/write, filesystem
checks, and about 90 Mbps Ethernet reads passed. See [qualification provenance](QUALIFICATION.md) for the historical
build checks and exact revisions, bitstream identities, rates and retries.
The new combined candidate passed USB transfer and RG35XX Plus boot checks
with Ethernet disconnected on 2026-10-01; see the
[USB qualification record](../../docs/hardware/arty-usb-fallback-2026-10-01.md)
for its separate artifact identity and the scope of that campaign.

## Build and test

Install the [macOS toolchain](../../experiments/openxc7-macos/README.md) and
[DDR prerequisites](../microsd-emulator/ddr/README.md) first. From `gateware/`:

```sh
uv run --frozen python tools/project_inventory.py --check
uv run --frozen python projects/ethernet-diagnostic/scripts/test_with_vcd.py
uv run --frozen python -m unittest discover -t projects/ethernet-diagnostic \
  -s projects/ethernet-diagnostic/test_host -p test_images_host.py
uv run --frozen python -O -m unittest discover -t projects/ethernet-diagnostic \
  -s projects/ethernet-diagnostic/test_host -p test_images_host.py
python3 experiments/openxc7-macos/build_ddr.py --ethernet --seed 12
```

The output is `build/microsd-ddr-ethernet/`. The builder regenerates DDR support,
requires patched negative-edge timing, checks all clocks, native and Ethernet
Gray-pointer domains, widths, two-stage topology and crossing delays, direct
SD outputs, and bitstream round-trip
verification before atomically publishing `result.json`. Require successful
exit and a matching `bitstream_sha256` before programming. Intermediate files
from a failed build are not programming approval. Omitting `--ethernet` builds
the existing UART-managed card.

The simulations cover frame queues, ARP/ping, malformed IP/UDP packets, CRCs,
ordered retries, bulk reads, native DDR backpressure, and the complete
Ethernet → SD write → Ethernet readback path. They also stall accepted SD
reads and writes while disarming and verify that network access waits for
them to drain, and vary PHY clock phase and reset release.
`--waves` retains waveforms when diagnosing a failure.

Tests come in two sets. Host tests need neither hardware nor a simulator; the
Cocotb testbenches need Verilator and a built design:

```sh
uv run --frozen python -m unittest discover -t projects/ethernet-diagnostic \
  -s projects/ethernet-diagnostic/test_host -p 'test_*.py'
uv run --frozen python tools/run_tb.py --project projects/ethernet-diagnostic
```

## Where the RG35XX Plus tooling went

The host tooling that boots an Anbernic RG35XX Plus (Allwinner H700) from the
emulated card — the kernel and rootfs builds, the card images, the trial and job
harnesses, the suspend firmware and the ten notes that go with them — moved to
the **`linux-consoles`** repository, under `docs/rg35xx-plus/` and
`devices/rg35xx-plus/`, along with the bench rig that drives the card and the
supply. It reaches this client rather than vendoring a copy of it:
`SD_EMULATOR_CLIENT_DIR` names the directory holding `scripts/images.py`
(default `~/src/github/retrobus-explorer/gateware/projects/ethernet-diagnostic/scripts`)
and `SD_EMULATOR_BUILD_DIR` the build directory holding the qualified bitstream.
Treat `images.py`, its importability as `scripts.images`, `PROTOCOL.md` and the
`build/<experiment>/` layout as an interface that repository depends on. What
that host taught *this* gateware stayed here, in
[H700-HOST-NOTES.md](H700-HOST-NOTES.md).

## Documentation map

Every fact has one home, and the other documents summarise it and point at it.
In reading order:

| document | what it is | when to read it |
| --- | --- | --- |
| [PROTOCOL.md](PROTOCOL.md) | the shared image protocol over Ethernet and USB: packet formats, the ordered-command API, bulk reads, TRACE and INFO | you are writing or debugging a client |
| [H700-HOST-NOTES.md](H700-HOST-NOTES.md) | what a real Allwinner H700 host taught this emulator: the clock ladder it picks, how the frontend samples, the pull-up findings, what TRACE keeps and loses, and how the qualified H700 bitstream was built | you are changing the SD frontend, the trace, or an H700 build |
| [QUALIFICATION.md](QUALIFICATION.md) | the provenance of the hardware results: revisions, bitstream hashes, rates and retry counts, campaign by campaign | you need to know exactly what was tested, and on what |

## Ownership rules

Only one image region exists. A/B slots for uploading while another image is
served are a future extension. Network reads and writes are refused while SD
is armed. Disarming stops new SD activity; accepted writes and outstanding
reads retain DDR ownership until they finish.

An upload declares a sector count, writes that prefix in order, then reads it
back completely and compares every byte. Arming is a separate operation and
requires a completed upload. The host also requires a persisted record that
the initial upload passed full readback verification. Failed or interrupted
verification leaves ARM disabled across client restarts. This is a host-side
guard, not a hardware interlock; the FPGA itself checks upload completeness.
Later legitimate SD writes do not invalidate initial-upload verification.
The client exclusively locks its session file until it closes. Bulk downloads are read-only, but require the image to stay disarmed and
unchanged for the entire transfer.

Power loss, BTN0, or FPGA reprogramming destroys the volatile card. Startup
BIST verifies and zeroes all 256 MiB before accepting uploads. A later upload
changes only its prefix; it does not erase the remainder, and SD still
advertises 256 MiB.

## Connect and program

Connect the Arty RJ45 directly to the Mac's USB Ethernet dongle. Identify that
specific interface with `networksetup -listallhardwareports` and `ifconfig`;
it was AX88179B / `en20` on the qualified setup. Configure it on the Mac:

```sh
sudo ifconfig en20 inet 192.168.10.1 netmask 255.255.255.0 up
```

The FPGA is `192.168.10.2`, MAC `02:00:00:00:00:01`, UDP port 4000. Require
100baseTX full duplex after boot. The onboard PHY receives a 25 MHz reference,
10 ms reset, and 200 ms startup delay. This service has no authentication;
use the direct cable or an isolated trusted network. Ordinary UDP and ping
need no raw-packet capture privileges.

Before reprogramming, preserve any needed image, unmount the external card,
and follow the [guarded preparation procedure](../microsd-emulator/ddr/README.md#program-and-initialize).
Copy the current `tools/microsd_*.py` helpers together to a temporary directory
on the GKD. Run there as root:

```sh
python3 microsd_prepare_linux.py
```

This checks the exact external controller and rejects an unexpected card,
mounts (including aliases), holders, and swap before detaching. It also supports
first use with no enumerated card. Never detach or write the internal `mmcblk0`.
Then, on the Mac:

```sh
openFPGALoader -b arty_a7_35t -m build/microsd-ddr-ethernet/design.bit
ping -c 3 192.168.10.2
```

BIOS output starts on USB UART at 115200 baud. In new combined builds the
1 Mbaud framed image service takes exclusive transmit ownership on its first
recognized service reply. A format/CRC failure temporarily selects binary TX
only while its error reply drains, then restores BIOS TX. The qualified
historical artifact predates this fallback. Full-memory BIST takes tens of seconds;
`--upload` waits for readiness. STATUS acknowledges a session, rather than
reporting detailed BIST counters.

## Small image round trip

Create the same deterministic 64 KiB prefix used by the SD read-only checks:

```sh
python3 - <<'PYIMAGE'
from pathlib import Path
Path('small-image.bin').write_bytes(bytes(
    (i * 37 + (i >> 8) * 11 + 17) & 255 for i in range(65536)))
PYIMAGE
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/arty-network-session.json --upload small-image.bin --bulk
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/arty-network-session.json --arm
```

Keep that session file between commands: it journals sequence state and an
outstanding ordered request so restarting the client can safely retry it.
Inspect that local state without contacting the FPGA:

```sh
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/arty-network-session.json --inspect
```

Inspection reports local knowledge only; it does not claim that the FPGA is
reachable or in the same state. The loader validates request length, header,
CRC, opcode, session, sequence, and verification metadata before it creates a
socket. Malformed recovery state is refused rather than discarded or replayed.
Read/download/status operations refuse to replay an unfinished mutating request;
resume its original operation explicitly first. Requesting the exact pending
command (including its address, count, and payload) returns the recovered reply
without issuing a second command. A different mutating command first completes
the pending operation, then performs the new one. BEGIN and bulk reads use
dedicated protocol paths, outside the ordered-command API.

The journal binds verification to the upload session, sector count, and image
SHA-256. Older journals without this record remain usable for reads, status,
and disarm, but require a new verified upload before ARM. A new FPGA boot also
requires a new upload session. Completed downloads replace their destination
atomically, preserving an existing file if writing the replacement fails.
Journal replacement protects against a torn process-level update, but journal
writes are not explicitly synchronised to storage and are not promised to
survive sudden host power loss. Transfer phases and progress go to stderr;
stdout remains machine-readable JSON.

Recovering one pending ordered request completes that operation. A normal
`--upload` starts again at LBA zero. `--resume-upload --upload IMAGE` instead
requires the same saved image identity, reconciles the FPGA session through
INFO and continues from the written prefix, then compares the entire readback.
It refuses an FPGA reload, a different image, or a pending control operation.

## Passive SD trace

For targets without a serial console, read the SD frontend's passive activity
counters over Ethernet:

```sh
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/arty-network-session.json --trace
```

TRACE uses an unsequenced, compact read request. It does not recover a pending
operation, update the journal, access DDR, or change SD ownership. The counters
report sampled SD clock edges, complete and CRC-valid command frames, invalid
frames, the last valid command and argument, and block read/write activity.
They are cumulative from FPGA reset and wrap at 32 bits, so take a baseline
before powering the target and compare the deltas. An unpowered or floating SD
clock can still produce sampled edges or invalid frames; only valid commands
and backend requests establish useful protocol progress.

The trace records observation points already present in the SD frontend rather
than instantiating another command decoder. It deliberately keeps only the last
command, not a command log, to preserve timing in the combined DDR/Ethernet
build. See [the H700 host notes](H700-HOST-NOTES.md) for what these counters
do and do not preserve, learned booting an H700 handheld from the emulated
card.

On the GKD, bind the external controller and apply the 13 MHz, four-bit,
keep-awake settings from the [DDR guide](../microsd-emulator/ddr/README.md).
Run its read-only prefix check before any SD writes:

```sh
python3 microsd_verify_linux.py --bus-width 4 --writable-card \
  --capacity-mib 256 --clock-hz 13000000 --actual-clock-hz 12913043
```

For writable-media qualification, the same guide supplies bounded raw writes,
full-memory stress, and FAT filesystem tests. Those intentionally replace the
image and monitor MMC error counters and controller recovery. After all SD
operations, unmount and run `microsd_prepare_linux.py` again before disarming.
On the Mac, retrieve the prefix:

```sh
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/arty-network-session.json --disarm
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/arty-network-session.json \
  --download readback.bin --blocks 128 --bulk
cmp small-image.bin readback.bin
```

The comparison applies if SD performed reads only. After intentional SD writes,
compare against the written pattern instead. `--blocks` counts 512-byte sectors;
`--start` selects the first LBA. `--blocks 524288` retrieves the full DDR image.
The client reports SHA-256, elapsed time, and recovered retries. For repeatable
read-only throughput measurements, use `scripts/benchmark_reads.py --bulk`
with the same state file and an independently known `--expected-sha256`.

## Code map and limits

- `src/mac.spade`: complete-frame asynchronous RX/TX queues and Ethernet CRC.
- `src/network.spade`: ARP, ICMP echo, IPv4/UDP validation and replies.
- `src/blocks.spade`: image session, ordered retry cache, bounds, and arm control.
- `src/native.spade`: one/two-sector transfers over the native DDR interface.
- `src/serial.spade`: UART framing, immutable request buffer and reply serializer.
- `src/arbiter.spade`: fair request ownership and reply routing between transports.
- `src/server.spade`: shared block-service composition and independent PHY startup.
- `src/integrated.spade`: exclusive SD/network DDR ownership and draining.
- `src/trace.spade`: passive SD activity counters and registered word readout.
- `scripts/images.py`: validated UDP/serial client and persistent ordered-request state.
- `scripts/ftdi_uart.py`: exact-board FT2232H interface B stream via libftdi.

See [wire protocol and bulk reads](PROTOCOL.md) and
[historical hardware qualification](QUALIFICATION.md). There is no DHCP, VLAN,
fragmentation, IPv4 options, routing, or half-duplex collision handling. Timing
checks bound internal clocks and specified crossings; they are not a complete
external MII setup/hold or signal-integrity qualification.

### PHY reset boundary

BTN0 holds the startup counter and reference-clock divider reset, and keeps
the PHY in reset. Pressing and releasing BTN0 restarts startup; **it destroys
the volatile card image**, so this is not a nondestructive network recovery.
After release, the reference clock runs, PHY reset releases at 10 ms, and
MAC-local reset remains asserted until 200 ms. The PHY clocks must start during
that MAC-reset interval so their release chains are loaded.

RX rising-edge and TX falling-edge logic each use the shared two-stage reset
conditioner: assertion is immediate and release waits for two local edges.
The fixed startup timer does not detect stopped clocks or guarantee recovery
from arbitrarily late PHY-clock startup. Simulation covers delayed clock start,
reassertion, and release near both sides of a clock edge; it does not model
metastability or replace physical reset/CDC analysis.


## USB fallback on the H700 card

Build a separate candidate; preserve the qualified historical artifact:

```sh
DYLD_LIBRARY_PATH=<boost-lib> ./.venv/bin/python \
  experiments/openxc7-macos/build_ddr.py --profile h700-rg35xx \
  --output build/microsd-ddr-ethernet-usb-h700-registered-tx --seed <timing-passing-seed>
```

Require successful timing and bitstream verification before programming.
Keep the target's exact PSU2 channel off, hold the lab device lease, program
the candidate, and wait for DDR initialization. Ethernet may remain unplugged.
Use the Arty's FT2232H UART interface B, leaving DTR/RTS inactive. The
direct USB backend requires libftdi 1.5 or newer 1.x and selects the exact
board by its USB serial number; interface A remains the JTAG interface:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/images.py \
  --ftdi-serial <arty-ftdi-serial> --state <session.json> --info
uv run --frozen python projects/ethernet-diagnostic/scripts/images.py \
  --ftdi-serial <arty-ftdi-serial> --state <session.json> --upload <image.img> --bulk
```

The direct backend temporarily claims interface B and requests kernel-driver
reattachment on close. It restores the previous USB latency setting and never
writes the EEPROM. Use one UART client at a time. The original macOS TTY test
produced truncated/corrupt replies. After keeping
the pySerial read timeout fixed, a read-only 1 Mbaud retest passed 100 INFO
queries and a 128 KiB DDR comparison against direct libftdi, with zero retries;
see [the TTY retest record](../../docs/hardware/arty-usb-tty-retest-2026-10-01.md).
`--serial-port <arty-uart>` selects this pySerial backend. Both backends use the
same UART framing and baud rate. The rate is fixed in
`uart_config.py` when building the FPGA. Pass `--build-manifest
<candidate-build>/result.json` to check the host rate before opening USB; a
nondefault `--baud` requires this manifest. The default rate assumes the
standard combined build. CLI results and journals record the actual backend,
selector, rate, and whether it was selected by argument or environment;
`--host` and `--source` apply only to UDP. Transport provenance is advisory so
the same session can resume over the other link.

Without a saved session, `--disarm` queries INFO but refuses to adopt another
client's session. Use `--recover-session --disarm` only after acquiring exclusive
device and emulator ownership under the lab lease.

Upload includes complete DDR readback comparison and leaves the image
disarmed. ARM only for the powered target test under its lease, capture the
target's debug-partition evidence, then disarm and prove PSU2 off. The existing
linux-consoles trial/job tooling uses direct USB when
`SD_EMULATOR_FTDI_SERIAL=<arty-ftdi-serial>` is set, or the TTY path with
`SD_EMULATOR_SERIAL_PORT=<arty-uart>`. It keeps the same client, journal,
6 MHz card limit and supply discipline.

Additional focused simulations are `--top serial_packet --test-module
test_serial` and `--top request_arbiter --test-module test_arbiter`, alongside
the expanded `test_blocks` and default `test_network_sd`. Host discovery must
include all `test_*.py` files to cover serial framing and upload recovery.


### Repeat the USB qualification

The device harness lives in linux-consoles as `devices/rg35xx-plus/rg35xx.py
qualify-usb`; its device and supply gates run under both normal and optimized
Python. It imports this repository's client through `SD_EMULATOR_CLIENT_DIR`.
The smoke phase reconfigures the FPGA and replaces its volatile DDR image:

```sh
<zaurus>/lab lease --device anbernic-rg35xx-plus --sd-emulator -- \
  <gateware>/.venv/bin/python <linux-consoles>/devices/rg35xx-plus/rg35xx.py \
  qualify-usb --gateware <gateware> --build <candidate-build> \
  --port <arty-uart> --ftdi-serial <arty-ftdi-serial> \
  --output <private-evidence-dir> --image <rg35xx-sleep-image> --phase smoke
```

Repeat with the same arguments and `--phase full`, then `--phase boot`.
The default backend is direct libftdi; `--uart-backend tty` selects pySerial.
`--port` also identifies the 115200 baud BIOS capture port in the smoke phase.

For normal linux-consoles deployment, select the combined candidate explicitly
with `deploy --build-dir <candidate-build>` and set
`SD_EMULATOR_FTDI_SERIAL=<arty-ftdi-serial>` or `SD_EMULATOR_SERIAL_PORT=<arty-uart>`.
The default build directory still names the historical Ethernet artifact,
which does not contain the UART fallback.

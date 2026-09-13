# Arty A7 Ethernet SD image service

Load and retrieve the Arty A7-35T's 256 MiB DDR-backed microSD image over
100 Mbps Ethernet. SD remains a writable, four-bit, 13 MHz card on JD using
the bottom-header microSD-Pmod adapter and a common ground. The Ethernet
transport replaces the UART image loader; it reuses the reviewed SD frontend,
DDR controller, full-memory BIST, and board wiring.

## Integration status

This revision passes simulation and host tests, but is not ready to program.
The best checked local placement reaches 99.38 MHz against the required
100 MHz fabric clock; the build correctly refuses to publish success. See
[validation details](QUALIFICATION.md#current-integration-2026-09-13).
Close timing and repeat hardware qualification before treating this as a
replacement for the previously qualified image.

## Build and test

Install the [macOS toolchain](../../experiments/openxc7-macos/README.md) and
[DDR prerequisites](../microsd-emulator/ddr/README.md) first. From `gateware/`:

```sh
uv sync --locked --all-packages
uv run python tools/project_inventory.py --check
uv run python projects/ethernet-diagnostic/scripts/test_with_vcd.py
uv run python -m unittest discover -s projects/ethernet-diagnostic/test -p test_images_host.py
uv run python -O -m unittest discover -s projects/ethernet-diagnostic/test -p test_images_host.py
python3 experiments/openxc7-macos/build_ddr.py --ethernet --seed 6
```

The output is `build/microsd-ddr-ethernet/`. The builder regenerates DDR support,
requires patched negative-edge timing, checks all clocks, native and Ethernet
Gray-pointer crossing delays, direct SD outputs, and bitstream round-trip
verification before atomically publishing `result.json`. Require successful
exit and a matching `bitstream_sha256` before programming. Intermediate files
from a failed build are not programming approval. Omitting `--ethernet` builds
the existing UART-managed card.

The simulations cover frame queues, ARP/ping, malformed IP/UDP packets, CRCs,
ordered retries, bulk reads, native DDR backpressure, and the complete
Ethernet → SD write → Ethernet readback path. They also stall an accepted SD
write while disarming and verify that network reads wait for it to drain.
`--waves` retains waveforms when diagnosing a failure.

## Ownership rules

Only one image region exists. A/B slots for uploading while another image is
served are a future extension. Network reads and writes are refused while SD
is armed. Disarming stops new SD activity; accepted writes and outstanding
reads retain DDR ownership until they finish.

An upload declares a sector count, writes that prefix in order, then reads it
back completely and compares every byte. Arming is a separate operation and
requires the declared upload to be complete. Use one client/session file at a
time. Bulk downloads are read-only, but require the image to stay disarmed and
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

BIOS output remains on USB UART at 115200 baud. The 1 Mbaud UART image commands
are unavailable in this build. Full-memory BIST takes tens of seconds;
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
Read/download/status operations refuse to replay an unfinished mutating request;
resume its original operation explicitly first. A new FPGA boot requires a new
upload session.

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
- `src/server.spade`: packet-layer composition and PHY startup.
- `src/integrated.spade`: exclusive SD/network DDR ownership and draining.
- `scripts/images.py`: validated UDP client and persistent ordered-request state.

See [wire protocol and bulk reads](PROTOCOL.md) and
[historical hardware qualification](QUALIFICATION.md). There is no DHCP, VLAN,
fragmentation, IPv4 options, routing, or half-duplex collision handling. Timing
checks bound internal clocks and specified crossings; they are not a complete
external MII setup/hold or signal-integrity qualification.

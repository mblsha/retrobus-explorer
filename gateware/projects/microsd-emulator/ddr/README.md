# DDR-backed SD build and hardware qualification

The qualified target is Arty A7-35T (`xc7a35tcsg324-1`), JD with the measured
`bottom-header-row-swap` mapping. See the [pin table](../README.md#verified-wiring-and-clock).
The host/adapter and FPGA require an explicit common ground because the PCB
leaves Pmod ground pins disconnected.

| Item | Configuration |
| --- | --- |
| SD frontend | 100 MHz, native SDR card interface |
| DDR controller | 80 MHz |
| DDR clock / transfer rate | 320 MHz / 640 MT/s |
| IDELAY reference | 200 MHz |
| Physical DDR3 | MT41K128M16, 256 MiB |
| SD capacity | 524288 sectors, SDSC byte addressing |
| Reset | BTN0 / D9, active high |

CPU firmware performs PHY training from ROM/SRAM, then releases the native
port. The Spade BIST checks every 128-bit word with an address-sensitive
pattern, its complement and zeros. SD and UART loading remain blocked on any
failure. Read/write ownership and cancellation logic preserve accepted writes.

## Build

Install the [native openXC7 toolchain](../../../experiments/openxc7-macos/README.md),
Swim/Spade and Verilator as described in the [gateware guide](../../../README.md).
From `gateware/`, install the pinned DDR generator dependencies and the xPack
RISC-V GCC 15.2.0-1 macOS arm64 toolchain:

```sh
uv venv --python /opt/homebrew/bin/python3.11 build/litedram-py311
uv pip install --python build/litedram-py311/bin/python \
  -r projects/microsd-emulator/ddr/requirements.txt
# Extract xPack's release to build/xpack-riscv-none-elf-gcc-15.2.0-1/.
# Its bin/ directory must contain riscv-none-elf-gcc.

build/litedram-py311/bin/python -m unittest discover \
  -s projects/microsd-emulator/ddr -p 'test_*.py'
uv run python tools/test_microsd_suite.py --fast-sd
python3 experiments/openxc7-macos/build_ddr.py \
  --toolchain build/openxc7-macos --output build/microsd-ddr-sd \
  --seed 8
```

The default toolchain prefix is `build/openxc7-macos`, shared with the probe
and BRAM builders. Every invocation reruns support tests and regenerates DDR
HDL/firmware. One configurable placement seed is checked per build.

For a deterministic Linux legacy-MMC probe over the Ethernet-managed DDR
target, use the slow diagnostic profile:

```sh
python3 experiments/openxc7-macos/build_ddr.py \
  --ethernet --slow-mmc --mmc-only --seed 4
```

The H700 profile boots an Anbernic RG35XX Plus from the emulated card:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib \
  ./.venv/bin/python experiments/openxc7-macos/build_ddr.py \
  --ethernet --slow-mmc --h700-mmc --sd-io-clock-hz 64000000 --seed 8
```

It answers SD negotiation normally and lets the payload choose MMC itself, and
it holds the idle data lines at the pull-up level the adapter lacks, which the
host's R1b busy check requires. `--sd-io-clock-hz` selects the SD fabric clock;
50, 64, 80 and 100 MHz divide the same 1600 MHz VCO as the DDR outputs. This
profile builds at 64 MHz because the telemetry-rich design does not place
within 80 MHz, and the card interface it serves runs three orders of magnitude
slower. See [the H700 host notes](../../ethernet-diagnostic/H700-HOST-NOTES.md)
for the clock ladder this host picks, the pull-up findings and how the
qualified seed-19 build was made.

`build_ddr.py` routes exactly one seed and rejects the build if that placement
misses a constraint, and this design is close enough to its bounds that a seed
often does. Re-synthesizing to try another costs about ten minutes, while
routing the finished netlist costs about ninety seconds, so search first and
feed the winner back to `--seed`:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib \
  ./.venv/bin/python tools/search_placement_seeds.py \
  --output build/microsd-ddr-ethernet-h700 --h700-mmc \
  --seeds 8 9 10 11 12 19 21 30
```

That output directory currently holds the hardware-qualified H700 bitstream,
compiled by Spade v0.17.0 from an earlier source revision. The sources are now
on Spade v0.20.0, whose netlist is different, so a rebuild there would
overwrite a qualified artifact with an unqualified one. Search into a new
directory and read
[QUALIFICATION.md](../../ethernet-diagnostic/QUALIFICATION.md) first.

The `--mmc-only` profile above suppresses the complete initial SD negotiation
boundary so a host which permits MMC falls back to CMD1. Its MMC CSD advertises 5 MHz; the tested
GKD clock tree generates 4 MHz from that request. CMD23 bounds the next CMD18
without requiring an on-wire CMD12 after the final requested block. The GKD
validation record is the "GKD-350H legacy-MMC validation" entry in the
`linux-consoles` repository's `docs/rg35xx-plus/history.md`.

The build checks support tests, clock timing, native Gray-pointer crossings,
direct SD outputs and a configuration-frame round trip. The builder removes any old success manifest before preflight and publishes
`result.json` atomically only after all checks pass. Require a successful exit
and verify its bitstream hash before programming. Seed 8 passed the prior qualified build;
placement results can change with sources, compiler output and dependencies.

The [2026-09-10 record](../../../docs/hardware/README.md)
records the pre-extraction source at `f993db1`: nextpnr 0.9.4 with the negative-edge
patch, 106.62 MHz fabric and 80.80 MHz DDR timing estimates, full 256 MiB BIST,
three full SD readbacks, 512 mixed updates and FAT16 checks with no controller
reinitialization. Reads measured 4.261–4.277 MB/s and writes 4.543 MB/s.
These are prior hardware measurements; an extracted source build must pass its
own timing checks and be qualified before replacing that image.

## Program and initialize

Choose the Linux SSH destination and Mac UART path for your setup:

```sh
GKD_SSH=root@YOUR_GKD_ADDRESS
UART_PORT=/dev/cu.YOUR_ARTY_UART
ssh "$GKD_SSH"
```

Only **`mmc1` / `2a310000.mmc`** is the guarded external test controller.
Internal eMMC is `mmc0`; Wi-Fi is `mmc2`.
The helpers check controller, card CID, capacity, mounts, holders and swaps.

Before first programming, reprogramming, or uploading, copy all
`tools/microsd_*.py` helpers to one directory on the GKD. Unmount the test card
and stop any swap or device-mapper use, then run there as root:

```sh
python3 microsd_prepare_linux.py
```

The command verifies the external platform device, device-tree node, driver,
and MMC host. It detaches a controller with no enumerated card (`no-card`), or
an expected SPADE emulator whose disk and partitions are unused
(`unused-emulator`). An already detached, verified controller returns
`already-unbound`. Unexpected cards, missing controller identity, mounts,
holders, and swap cause refusal before any unbind write. This supports starting
with the input-only probe as well as replacing an existing emulator.

On the Mac, program volatile FPGA SRAM:

```sh
openFPGALoader -b arty_a7_35t -m build/microsd-ddr-sd/design.bit
# Allow about 35 seconds for BIOS training and full-memory self-test.
uv run python tools/microsd_image.py --status --port "$UART_PORT"
```

BIOS output is 115200 baud; the loader is 1 Mbaud. Require status **`0x20000047`**
before loading: initialized, BIST passed, not armed. BIST writes and reads an
address-sensitive pattern, its complement, and zeros across **every native
word**. Any failure blocks the loader and SD. Do not force initialization.

Generate the known 64 KiB prefix and upload it:

```sh
python3 - <<'PY'
from pathlib import Path
Path('small-image.bin').write_bytes(bytes(
    (i * 37 + (i >> 8) * 11 + 17) & 255 for i in range(65536)))
PY
uv run python tools/microsd_image.py small-image.bin \
  --port "$UART_PORT"
```

The loader arms the card; status becomes **`0x2000004f`**. BIST has zeroed the
remaining memory. Uploading another prefix does not clear the rest of DDR.
BTN0, power loss, or reprogramming destroys the volatile card and reruns BIST.
Opening UART does not reset this BTN0 configuration.

On the GKD, bind the external controller to enumerate in 4-bit mode:

```python
from pathlib import Path
base = Path('/sys/bus/platform/drivers/dwmmc_rockchip')
if (base / '2a310000.mmc').exists():
    raise RuntimeError('Controller is already bound')
(base / 'bind').write_text('2a310000.mmc')
```

For a 1-bit test, immediately after that bind, before the first scan:

```python
caps = Path('/sys/kernel/debug/mmc1/caps')
if int(caps.read_text().strip(), 16) != 0x400c0007:
    raise RuntimeError('Unexpected controller capabilities')
caps.write_text('0x400c0006')
```

A normal detach/rebind restores 4-bit capability. Verify SPADE, the expected
CID, 524288 sectors, width, and clock in `/sys/kernel/debug/mmc1/ios`.
Copy all `tools/microsd_*.py` helpers to one directory on the host. Configure the
qualified rate after enumeration and keep the external controller awake:

```sh
python3 microsd_clock_linux.py --clock-hz 13000000 --bus-width 4 \
  --max-request-kib 256 --keep-awake
```

Verify the requested 13 MHz and actual 12,913,043 Hz in debugfs. Host power
management can otherwise change the clock during transfers.

## Hardware integrity and speed checks

Copy all `tools/microsd_*.py` into one temporary directory on the GKD
(create it with `mktemp -d`). Run the following there. Each transfer checker
automatically captures controller error counters, clock/width, and kernel-log
continuity before and after. Any error, recovery, or missing evidence fails the
command. Save stdout for transfer results and stderr for qualification evidence.
All writes target only the positively identified, unmounted, volatile FPGA
card. The first check expects the known prefix and zeros, so run it before
write stress or formatting.

```sh
python3 microsd_verify_linux.py --bus-width 4 --writable-card \
  --capacity-mib 256 --clock-hz 13000000 --actual-clock-hz 12913043
python3 microsd_verify_linux_rw.py --bus-width 4 \
  --capacity-mib 256 --clock-hz 13000000 --actual-clock-hz 12913043
python3 microsd_stress_linux.py --bus-width 4 \
  --capacity-mib 256 --clock-hz 13000000 --actual-clock-hz 12913043 \
  --span-mib 256 --random-writes 1024 --passes 2 --verify-whole-card
python3 microsd_verify_linux_fs.py --bus-width 4 \
  --capacity-mib 256 --clock-hz 13000000 --actual-clock-hz 12913043
```

Use `--bus-width 1` after forcing 1-bit enumeration. To verify data across a
width change, run the bounded RW checker, detach/rebind, then run the same
checker with the new width and `--read-only`. The filesystem checker also
accepts `--read-only` to verify the existing files without formatting. After a
**full 256 MiB** stress run, add `--read-only` to the same stress command
(with the same seed, passes and random-write count) to verify 1 MiB windows at
the beginning, middle and end across a bus-width change. This complements the
complete readbacks performed during the write run.

The stress test uses direct I/O, unique address/generation/seed-sensitive
4 KiB patterns, complete readbacks after random updates, and before/after
neighbor checks. For a quick experiment use `--span-mib 1 --random-writes 16`;
`--verify-whole-card` then hashes the untouched tail before and after. The
full 256 MiB run verifies all blocks instead of sampling them. The filesystem
check uses FAT16, exercises file/metadata operations, runs fsck, remounts
read-only and checks contents. It leaves the card unmounted.

## Diagnostics and limits

```sh
uv run python tools/microsd_image.py --clock-status \
  --port "$UART_PORT"
# Only after a failed BIST:
uv run python tools/microsd_image.py --diagnostics \
  --port "$UART_PORT"
```

Status bits: 0 initialized, 5 BIST busy, 6 pass, 7 fail; bits 8–26 report a
512-byte sector, bits 27–29 phase, bits 30–31 error. The detailed failure
query adds exact native-word address, actual/expected 128-bit data and XOR.
The clock meter is input-only. Single-period estimates are quantized to
80 MHz cycles; use the millisecond edge count for non-integer clock ratios.
Also inspect `/sys/kernel/debug/mmc1/err_stats`; successful reads alone do not
prove that the host encountered no CRC errors or retries.

The qualified lab record used `root@192.168.50.39`, UART
`/dev/cu.usbserial-210319B0C1CC1`, and a locally verified SSH host-key file at
`/private/tmp/gkd-microsd-known-hosts`. These are historical connection details,
not portable defaults. Never disable SSH host-key verification.

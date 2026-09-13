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
  --route-seeds 8
```

The default toolchain prefix is `build/openxc7-macos`, shared with the probe
and BRAM builders. Every invocation reruns support tests and regenerates DDR
HDL/firmware; multiple placement seeds share one synthesis within that run.

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

Before reprogramming or uploading, unmount the test card if mounted. On the
GKD, verify identity and detach only the external controller:

```python
from pathlib import Path
host = Path('/sys/class/mmc_host/mmc1')
if '2a310000.mmc' not in str(host.resolve()):
    raise RuntimeError('Wrong controller')
if (host / 'mmc1:0001/cid').read_text().strip() != \
        '7f52425350414445101234567801916b':
    raise RuntimeError('Wrong card')
if '/dev/mmcblk1' in Path('/proc/mounts').read_text():
    raise RuntimeError('Unmount the card first')
Path('/sys/bus/platform/drivers/dwmmc_rockchip/unbind').write_text('2a310000.mmc')
```

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

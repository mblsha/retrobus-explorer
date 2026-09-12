# Native microSD emulator for Arty A7-35T

The Spade gateware emulates a volatile **256 MiB read/write SDSC card** backed
by the Arty's DDR3. The qualified GKD 350H Ultra configuration requests 13 MHz
and runs at **12,913,043 Hz**, with sustained reads around **4.27 MB/s**.
The SD link uses ordinary single-data-rate signaling; DDR3 is the backing
memory, not SD DDR50 mode. Native 1-bit and 4-bit transfers are supported.

The staged targets are an input-only pin probe, a read-only BRAM card with a
64 KiB resident prefix, and the writable DDR card. SPI, SDHC, UHS and voltage
switching are not implemented. The hardware results establish this board/host
pairing, not universal SD-reader compatibility.

See the [DDR build and hardware guide](ddr/README.md),
[PCB designs](../../../jitx-py/microsd-pmod-breakout/README.md), and
[qualification record](../../docs/hardware/arty-nextpnr-0.9.4-timing-refactor-2026-09-10.json).

## Verified wiring and clock

The photographed bottom-header assembly on JD has a row swap relative to the
PCB labels. Use **`bottom-header-row-swap`**, not the historical bottom-header
or top-header-r180 profile. The DDR board wrapper uses this measured mapping:

| Signal | JD pin | FPGA ball |
|---|---:|---|
| CLK | 9 | H2 |
| CMD | 3 | F4 |
| DAT0 | 4 | F3 |
| DAT1 | 10 | G2 |
| DAT2 | 1 | D4 |
| DAT3 | 2 | D3 |

The explicit common ground was confirmed. JD7/JD8 are unused and remain inputs.
CLK also remains input-only. All six lanes passed independent high/low tests
with the [input-only probe](../microsd-pin-tester/README.md); see the
[measured pinout](../../docs/hardware/gkd-arty-jd-pinout-2026-09-07.md).

The qualified frontend uses a 100 MHz domain, with buffered crossings to the
80 MHz DDR controller and prepared falling-edge outputs. The SD host generates
CLK. CSD TRAN_SPEED advertises a rate, but the host determines the actual clock;
verify it in Linux debugfs. Raising the advertised rate alone does not establish
reliable operation. The 13 MHz setting was selected after faster mixed-write
runs triggered host recovery; signal integrity remains a possible contributor.

## Build and test

From `gateware/`, after the [native toolchain setup](../../experiments/openxc7-macos/README.md):

```sh
uv sync --locked --all-packages
uv run python tools/test_microsd_suite.py --fast-sd
python3 experiments/openxc7-macos/build_probe.py
python3 experiments/openxc7-macos/build_emulator.py --profile bottom-header-row-swap
```

The full suite checks nonempty JUnit results and records each top/test-module
under `build/microsd-tests/`. The [DDR guide](ddr/README.md) gives the full build,
programming, memory qualification and Linux read/write test commands.

The UART loader replaces the first 64 KiB. Inputs may contain 1..65536 bytes
and are padded to 64 KiB. It validates packet CRC32, commits all 128 sectors,
and then arms SD; `--no-arm` leaves SD disabled. Loading a prefix does not clear
sectors beyond it. A fresh full-memory BIST does. A raw pattern is not a filesystem.

## Protocol and storage behavior

Implemented commands: CMD0/8/55/ACMD41/2/3/9/7/13/16/17/18/12,
ACMD51, ACMD6, ACMD13, and (writable DDR builds) CMD24/CMD25. Addresses are
bytes, sectors are 512 bytes, RCA is 1, and the qualified DDR capacity is 256 MiB. Unsupported
commands report illegal-command status; read-only targets reject writes.

Malformed command CRC7 receives no response. Read data has per-lane CRC16.
Write packets are buffered completely and CRC-checked before any DDR commit.
CRC rejection leaves storage unchanged. CMD13 reports receive/programming state
and a latched write CRC error. DAT0 carries the CRC response and programming
busy. CMD12 discards incomplete reception while preserving an accepted commit;
CMD0/deselect release SD pins while an accepted commit drains. Only a shared
DDR/global reset may interrupt that commit.

Generation tags discard stale read completions. The native adapter buffers
command/data pairs and serializes transactions: LiteDRAM schedules native data
consumption from commands and cannot be treated as independently backpressurable
AXI streams. Tests cover this ordering, masked loader writes, delayed responses,
reset/cancel, multiblock progress, CRC/status/busy, and native SD readback.

The loader uses 532-byte `MSD1` packets and 16-byte `MSA1` acknowledgments with
IEEE CRC32 and little-endian integers. Opcodes: 1=write sector, 2=arm,
3=disarm/clear loaded map, 4=status. `tools/microsd_image.py` implements retries
and acknowledgments; use it instead of constructing packets manually.

BTN0, loss of power, or reprogramming erases the volatile card and reruns BIST.
Opening UART preserves SD state and DDR contents in the BTN0 configuration.

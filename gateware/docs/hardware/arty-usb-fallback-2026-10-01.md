# Arty A7 USB fallback qualification on RG35XX Plus

The combined Spade v0.20.0 candidate passed USB image transfer and three
RG35XX Plus cold starts with Ethernet disconnected on 2026-10-01
(Australia/Sydney). The full 131 MiB image was uploaded and compared against
its complete DDR readback before the target was powered. This establishes
the USB fallback and H700 boot path for the artifact below.

## Artifact and fixture

- Arty A7-35T, 256 MiB DDR3, JD microSD-Pmod adapter and common ground.
- RG35XX Plus on the bench's exact PSU2 registry channel; setpoints remained
  5.000 V and 1.200 A. PSU1 output and setpoints were untouched.
- Ethernet cable disconnected throughout. USB used FT2232H interface B,
  direct libftdi 1.5, 1,000,000 baud 8N1, DTR/RTS inactive.
- Candidate: `build/microsd-ddr-ethernet-usb-h700-registered-tx`, profile
  `h700-rg35xx`, placement seed 15.
- Bitstream SHA-256: `c2561a978724c9bbcf69659d3f3b5515d0ea089c73fee0fb16043e3b91393bf7`.
- 859,184 configuration bits verified by round trip;
  2,192,116 bytes in the `.bit` file.
- Source baseline: `6b8f615`, with the USB fallback changes in this commit.
  The local build manifest retains SHA-256 identities for all 44 consumed
  source and netlist inputs. Host documentation and selector guards were
  completed after synthesis; consumed HDL inputs did not change.

The previous qualified artifact at `build/microsd-ddr-ethernet-h700`
was preserved byte-for-byte, SHA-256 `cf5fb75dadfd8dcb65a89f4df8772986cdfd26b2dee3bbfab50979eeb28a30c3`.
It remains available for the historical Ethernet and GKD qualification.

## Build and simulation evidence

The candidate uses the existing registered native DDR path, full-memory BIST
and SD pin serializers. A fresh placement search selected seed 15 from the
same synthesized netlist. The finalizer required unchanged source/netlist
hashes, all clock targets, patched negative-edge timing, native FIFO register
storage, routed CDC checks, direct SD output checks and bitstream round-trip
verification before publishing `result.json`.

| Clock | Achieved MHz | Required MHz | Result |
| --- | ---: | ---: | --- |
| `core.clk` | 772.80 | 100 | PASS |
| `core.iodelay_clk` | 287.69 | 200 | PASS |
| `dclk` | 82.03 | 80 | PASS |
| `eth_rx_global` | 154.04 | 25 | PASS |
| `eth_tx_global` | 92.74 | 25 | PASS |
| `fclk` | 69.08 | 64 | PASS |

The block service (five tests), serial packet adapter, request arbiter and
network/SD integration passed Cocotb/Verilator tests. The USB integration
also passed at the actual 64 MHz fabric divisor with stopped PHY clocks and
DDR uninitialized. Host tests passed 45/45 normally and under optimized
Python; existing DDR support tests passed 60/60 and linux-consoles bench
compatibility tests passed 68/68. No Spade compiler warnings remained.

## USB transport and recovery

The always-present UART adapter and Ethernet adapter share one block service,
session, ordered retry cache and ARM register. The arbiter retains request
ownership until the reply is buffered and routes that reply to its source.
UART reply drain runs independently of the service. UDP remains the default
host transport; USB is selected explicitly or through the bench environment.

The 128 KiB smoke image exceeded the old UART loader's 64 KiB limit. Its
ninth WRITE was committed while its acknowledgements were deliberately
discarded. Closing and reopening USB preserved the FPGA session and DDR
contents; the saved journal resumed from the accepted prefix and the complete
readback matched. The last physical sector (524287) was also read and remained
zero. There were 0 unexpected retries after recovery.

On this Mac, pySerial through the TTY path received truncated or corrupt
1 Mbaud replies. Direct libftdi received a complete CRC-valid INFO reply from
the same bitstream, and passed the following transfer. The evidence does not
establish a general cause for the TTY corruption. The TTY backend remains
available for hosts where it works.

## Full image transfer

- Image: linux-consoles `rg35xx-plus-sleep.img`, job runner, 6 MHz card limit.
- 137,363,456 bytes, 268,288 sectors; SHA-256
  `7463e0a3c0f35a8b24bd46719fbf53ba95851335d1699d83bacbffb4c1646624`.
- Complete upload plus complete readback comparison: 5135.93 seconds
  (85.60 minutes), 0 recovered retries.
- UART bulk read window was one; each reply held up to two sectors. The
  host set its verification marker only after the complete byte comparison.
- PSU2 remained OFF and the card disarmed during transfer.

## RG35XX Plus cold starts

The existing linux-consoles trial harness performed three 45-second
observation windows, with an eight-second powered-off interval before each
cold start. Every trial reached a userspace write milestone with a valid
quiet baseline. After shutdown and disarm, debug-partition readback confirmed
`rootfs-init-entered` and `job-runner-ready` records for each trial. New reads
of the job command region after the userspace milestone established that
each boot's job runner was polling, independently of retained records.

| Trial | Userspace seconds from first valid host command | Rootfs init record | Job runner ready record |
| --- | ---: | --- | --- |
| 1 | 5.571 | yes | yes |
| 2 | 5.775 | yes | yes |
| 3 | 5.757 | yes | yes |

Each phase ended with INFO proving the FPGA disarmed and quiescent, and the
exact PSU2 channel independently read back OFF. The final verified image
remains in volatile DDR, disarmed. BTN0, FPGA reconfiguration or Arty power
loss destroys it.

## Reproduction and scope

Use the [USB fallback instructions](../../projects/ethernet-diagnostic/README.md#usb-fallback-on-the-h700-card)
and `scripts/qualify_rg35xx_usb.py` under the exact device and emulator leases.
Set `SD_EMULATOR_FTDI_SERIAL` for direct USB in linux-consoles and select the
candidate build explicitly. Retain the same session journal between transfer
and trial phases. The historical default build does not contain this fallback.

This campaign did not repeat physical Ethernet throughput, GKD full-memory
stress, FAT filesystem checks or external pin timing measurements. Those
historical results do not apply automatically to this candidate. It verified
all bytes of the Linux image over USB, the final capacity sector, recovery
after lost acknowledgements and USB reopening, and three H700 cold starts.
Raw reports, BIOS bytes, failed TTY captures, trial traces and debug records
remain in the private bench evidence directory; generated logs and bitstreams
are not committed.

UTC campaign: 2026-09-30T15:15:03Z through 2026-09-30T16:49:23Z.

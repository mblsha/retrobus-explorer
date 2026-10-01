# Arty USB control smoke after review, 2026-10-01

## Scope and identity

Observed on the connected Arty A7-35T with the RG35XX Plus attached through
the JD microSD-Pmod, using USB with the Ethernet cable disconnected.
The exact RG35XX PSU2 channel was independently read online and OFF before
and after the test; its limits were unchanged. The device and SD emulator
leases were held throughout. The RG35XX remained unpowered.

- Source revision: `aae9c9d8bbf2ccd0e97c17cc5821c96dc05d0341` (Spade v0.20.0).
- Separate build: `build/microsd-ddr-ethernet-usb-h700-review2`.
- Profile: `h700-rg35xx`, 64 MHz fabric, 80 MHz DDR, 1 Mbaud image UART.
- Placement seed: 16, selected by a fresh search on
  this candidate's synthesized netlist.
- Bitstream SHA-256: `a78e3a6d8a450cfa8c90a86ee0b8c04f7e803df067e1dd64910180731ddc6c37`.
- Verified configuration bits: 871,185.
- 60 source/generated input hashes
  are retained in the local manifest and were checked before programming.
- Control smoke: 2026-10-01T11:13:20Z to 2026-10-01T11:13:54Z.
- Private report SHA-256: `4c944d0613ff6448a4166b77d88cca3bfeeaacfeb7e9f77aa132e60a41735165`.

This covers the current console-ownership logic, including the registered
TX select and the earlier BAD_FORMAT ownership fix. The preserved feature
bitstream's [full transfer and RG35XX boot evidence](arty-usb-fallback-2026-10-01.md)
remains evidence for that older artifact. This smoke did not repeat image
upload, target boot, SD traffic or physical Ethernet throughput.

## Build checks

All 60 DDR support tests passed. The negative-edge timing probe, native FIFO
register-storage checks, routed CDC checks, five direct SD output checks and
configuration round-trip verification passed. Spade compiled without warnings.

| Clock | Achieved MHz | Required MHz | Result |
| --- | ---: | ---: | --- |
| `core.clk` | 593.82 | 100 | PASS |
| `core.iodelay_clk` | 212.72 | 200 | PASS |
| `dclk` | 87.21 | 80 | PASS |
| `eth_rx_global` | 151.86 | 25 | PASS |
| `eth_tx_global` | 101.96 | 25 | PASS |
| `fclk` | 74.74 | 64 | PASS |

The two affected Spade/Verilator integration cases passed before and after
registering TX selection, with strict nonempty JUnit results. Characterization
samples ownership near the end of each physical stop bit, including a rejected
reply's final delimiter. A rejected frame releases BIOS ownership before INFO;
after INFO, rejection preserves the established binary mode. The generated
HDL comparison preserved all 65 public interface entries and changed only the
`serial_frontend` body. The 53 host tests passed normally and under `python -O`.

## Hardware sequence and observations

Before reconfiguration, INFO and the passive SD trace were captured. The old
card was disarmed and quiescent. Its volatile image was cleared by the reload;
the saved 131 MiB Linux image was independently hashed and remains available:
`7463e0a3c0f35a8b24bd46719fbf53ba95851335d1699d83bacbffb4c1646624`.

The first request after reload was a compact INFO packet with its CRC's final
byte XORed with 1. The complete 540-byte reply had valid reply CRC32 and
BAD_FORMAT status 1. No valid INFO was sent first: a recognized reply
deliberately latches binary mode until FPGA reset.

After that rejected frame, the host reopened the UART at the BIOS's 115200
baud and captured 1,580 bytes of BIOS
startup text, including SDRAM initialization output. This directly observes
the physical TX mux returning to the BIOS. Console capture SHA-256:
`db5a778d51277301329d2ee14ae7fc845e4d50a0a5369e58d47a2671e4bff8da`.

The host then used 1 Mbaud and tested direct libftdi, the macOS TTY backend,
and direct libftdi again. Each passed 100 unchanged INFO replies, another
bad-CRC frame, a valid INFO afterward, and fresh-client disarm with zero
retries. DDR BIST completed; the candidate stayed empty, disarmed and
quiescent, with no image session adopted or ordered command issued.

Final state: candidate FPGA programmed, DDR initialized and empty, card
disarmed/quiescent, PSU2 online and independently read OFF, leases released.
An image must be uploaded and verified before this candidate can boot a target.
Both earlier qualified bitstream files retain their original hashes.

## Repeating the control sequence

Build a separate candidate from the source revision above:

```sh
DYLD_LIBRARY_PATH=<pinned-boost-lib> ./.venv/bin/python \
  experiments/openxc7-macos/build_ddr.py --profile h700-rg35xx \
  --output build/<candidate> --seed <passing-seed>
```

Search placements with `tools/search_placement_seeds.py`, retaining the
H700/slow-MMC flags, and require every build/timing/configuration check before
programming. Hold the exact device and SD emulator leases, prove PSU2 OFF,
capture the existing INFO/trace, then program through FTDI interface A with
`openFPGALoader -b arty_a7_35t --ftdi-serial <exact-serial> -m <candidate>/design.bit`.

Through interface B, use the published `scripts.images` client:
`encode(Opcode.INFO, 0, 0, compact=True)`, corrupt only its final CRC byte,
send it with `SerialTransport`, and validate the reply using `decode` against
the original request. Capture BIOS text at 115200 baud before sending valid
INFO at `SERIAL_BAUD`. After valid INFO, repeat rejection and require INFO
to remain responsive. Repeat through both backends, then require disarmed
INFO and an independent online PSU2 OFF readback before releasing the leases.

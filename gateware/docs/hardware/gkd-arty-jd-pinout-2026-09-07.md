# GKD 350H Ultra → Arty A7-35T JD: measured pinout

2026-09-07: Wi-Fi SSH, Arty JTAG and 1 Mbaud UART connectivity all worked.
JTAG ID 0x0362d093 identified an XC7A35. An input-only probe was loaded into
SRAM; no SD-emulator image was enabled and flash was not written. The user
confirmed an explicit common ground.

**The photographed assembly, as connected to JD, swaps the two Pmod rows relative
to the bottom-header PCB labels. The two original firmware profiles did not
match all six signals. The subsequently implemented `bottom-header-row-swap`
profile now matches this measured assembly; use that profile.** The previous identification from
the photograph's silkscreen was incorrect for the assembled connector.

| SD signal | GKD GPIO | Actual JD physical pin | FPGA ball |
|---|---:|---:|---|
| CLK | 69 (GPIO2_A5) | 9 | H2 |
| CMD | 68 (GPIO2_A4) | 3 | F4 |
| DAT0 | 64 (GPIO2_A0) | 4 | F3 |
| DAT1 | 65 (GPIO2_A1) | 10 | G2 |
| DAT2 | 66 (GPIO2_A2) | 1 | D4 |
| DAT3 | 67 (GPIO2_A3) | 2 | D3 |

Pmod row swap: 1↔7, 2↔8, 3↔9, 4↔10. JD7/JD8 are unused/floating in this
assembly. The probe raw-bit ordering is physical pins 1,2,3,4,7,8,9,10; the active
mask for this connection is 0xCF. Floating unused bits are excluded from verdicts.

Evidence:

- Rescanning the external controller produced clock activity on JD9 and command
  activity on JD3. The alternative input-only decoder recognized 24 CRC7-valid
  native SD commands; its last frame was CMD55 (`770000000065`). Its DAT names
  do not describe this assembly and were not used to certify the data lanes.
- The GKD external slot is `mmc1`, platform device `2a310000.mmc`. Internal eMMC
  is mmc0; Wi-Fi SDIO is mmc2. The external slot has no enumerated card while the
  input-only probe is attached, as expected.
- Live pinmux/device-tree data identified GPIO2_A0..A5 as the external SD bus.
  Signal identity was cross-checked against the
  [upstream RK3576 pinctrl definition](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/rockchip/rk3576-pinctrl.dtsi).
- Only the empty external controller was temporarily unbound. GPIO64..69 were
  exported, held low, then individually driven high and low while the FPGA
  remained entirely input-only. **All 12 measured states passed** the mapping
  above, with every other active lane held low.
- GPIOs were returned to inputs and unexported; the original external controller
  was rebound in a cleanup block. eMMC and Wi-Fi controllers were not detached.

The machine-readable measurements are in
[gkd-arty-jd-pinout-2026-09-07.json](gkd-arty-jd-pinout-2026-09-07.json).
This verifies low-speed signal continuity and identity, not full-speed signal
integrity or SD protocol operation. CLK currently lands on ordinary I/O H2;
the existing oversampled frontend still requires a controlled ≤1 MHz host clock.

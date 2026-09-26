# What an Allwinner H700 taught the emulated card

Between 2026-09-16 and 2026-09-21 this emulator served an Anbernic RG35XX Plus
(Allwinner H700) as its only boot medium, several hundred cold starts of it.
That is the only real, unmodified SD host the card has faced for any length of
time, and it exercised corners no testbench had: a host with no usable pull-ups,
a bootloader and a kernel that pick different clocks from the same CSD, and a
link that works until a display controller starts competing for the bus.

**The device-side work is not here.** The kernel, the rootfs, the card images,
the sleep ladder and the suspend firmware live in the **`linux-consoles`**
repository, under `docs/rg35xx-plus/` and `devices/rg35xx-plus/`, and it reaches
this repository's client through `SD_EMULATOR_CLIENT_DIR` and
`SD_EMULATOR_BUILD_DIR`. That repository is not published, so its file names
below are pointers for whoever has it, not links. This note keeps only what is
about *this* gateware, so that an emulator maintainer does not have to read a
handheld's notes to find it.
Each item says where it was measured and which file in those notes tells the
story; every claim about this repository's behaviour carries a `file:line`.

Measured and inferred are kept apart on purpose. Several of the most useful
facts below are **inferred**: the mechanism was never observed, because the
board offers no console and the FPGA sees only the bus.

## The card contract this host was served

`--profile h700-rg35xx` (`experiments/openxc7-macos/build_ddr.py:35-43`) is the
exact option set the qualified build was made from: Ethernet transport, the slow
command frontend, the H700 compatibility profile, placement seed 19, a 64 MHz SD
fabric clock, a 13 MHz advertised `TRAN_SPEED`, and the kernel's first sector as
the block-capture LBA.

The card is **SDSC and byte-addressed**. `tools/sd_csd.py:19` holds
`SD_CSD = 0x0026001A115903FFC002800002400023`; bits [127:126] are zero, so it is
a CSD version 1.0 register and capacity comes from `C_SIZE`, `C_SIZE_MULT` and
`READ_BL_LEN` (`sd_csd.py:sd_properties`) — 268,435,456 bytes. Hosts therefore
address it in bytes, not blocks. This was never in doubt on the bench, but it is
the single assumption every LBA figure below rests on, and a future SDHC profile
would invalidate all of them at once.

`--sd-tran-speed` is not free-form: `tran_speed_code` refuses any rate the
SD `TRAN_SPEED` byte cannot name exactly, rather than rounding, and recomputes
the CRC7 that shares the register (`tools/sd_csd.py:60-93`). That is why each
rung of the ladder below cost a bitstream.

## The clock ladder: 6 MHz or 25 MHz, nothing between

*Measured 2026-09-18, closed 2026-09-19. See `linux-consoles`
`docs/rg35xx-plus/findings.md` ("The card interface") and `history.md`
("The host has no clock between 6 and 25 MHz", "15 MHz closes the
advertised-speed ladder").*

Every rung between 6 and 25 MHz was built and measured through the frontend's
own block capture:

| advertised | U-Boot clocks it at | block span | result |
| --- | --- | --- | --- |
| 12, 13, 15, 20 MHz | 6.00 MHz | 11,103 fabric ticks | boots |
| 25 MHz | 25.00 MHz | 2,665 fabric ticks | fails after ACMD6, 83 sectors served |

The span is bit-identical at 12, 13, 15 and 20, so this is not rounding: the
host lands on 6.00 MHz for every advertisement below the SD default and jumps
straight to 25.00 MHz at 25. **Why it does is not known** — the board has no
console, so the divider cannot be observed. 6.001 MHz is consistent with a
24 MHz oscillator divided by four, which would put 12 MHz at a divisor of two,
and the host does not take 12 MHz when asked. Inferred, unresolved.

Then **Linux does not agree with U-Boot**. From the same 13 MHz CSD, U-Boot runs
the card at 6.00 MHz and Linux at 12.5 MHz, visible in the trace as a change of
edge rate at handover. Every interface figure quoted in the `linux-consoles`
notes is U-Boot's.

The measurement comes from the gateware, not from anything the host reports: the
block capture in `projects/ethernet-diagnostic/src/trace.spade:240-275` arms on a
backend read of `capture_lba` and counts 1 start-bit edge + 1,024 payload nibble
edges (`payload_last = 1023` in four-bit mode) + 16 CRC edges = 1,041 sampled
edges, timestamped against the fabric clock. `sd_clock_meter`
(`projects/microsd-emulator/src/clock_meter.spade`) supplies the free-running
period and edge counters alongside it.

25 MHz is reachable and unusable, and the reason is in the sampling below:
2.56 fabric cycles per SD period at a 64 MHz SD fabric clock is not enough to
resolve both edges. Serving it would need roughly 100 MHz `fclk` in a design
that already needs a seed search to close 80 MHz.

## Sampling: one fabric cycle of slack, and no glitch filter

*Measured 2026-09-19. See `docs/rg35xx-plus/findings.md` ("The display") and
`history.md` ("The card failed at Linux's clock, not at the display").*

SD_CLK, CMD and DAT each go through a plain two-flop synchroniser, and the
sample event is the synchronised rising edge:

- `projects/microsd-emulator/src/main.spade:162-168` — `clk_meta`/`clk_sync`,
  `cmd_meta`/`cmd_sync`, `dat_meta`/`dat_sync`.
- `main.spade:182` — `let sd_sample_tick = clk_sync && !clk_prev;`

CMD and DAT travel the same two-flop depth as the clock, so the pipeline delay
cancels and what is left is quantisation: **the card reads the line as it stood
at the first fabric edge at or after the host's rising edge, up to one 64 MHz
fabric period — 15.6 ns — late.**

A default-speed host changes its lines on the falling edge: 83 ns after the
rising edge at 6 MHz, 40 ns at 12.5 MHz. At Linux's rate the sample therefore
sits much nearer the moment the line moves. Without a display running, 12.5 MHz
never failed. With the panel up it failed reliably — 4 to 37 command frames
failing CRC7 per boot against 0 or 1, `sunxi-mmc 4020000.mmc: data error,
sending stop command` from the host, and within 1 to 25 of those the controller
wedges: it stops the clock and issues nothing further. Capping Linux at 6 MHz in
the target's device tree fixed it completely: 2,855 writes in 31 s, backlight at
full, no controller error and no bad frame, **on the qualified bitstream
unchanged**. That *the display* consumes the remaining margin is measured; *how*
it does — noise, DMA contention, or both — is not.

**There is no glitch filter and no debounce anywhere on SD_CLK.** A grep of
`projects/microsd-emulator/src/` and `lib/shared-components/src/` finds none.
The only edge-rate logic in the design is `host_clock_active`
(`main.spade:192-208`), which requires at least 4 transitions inside a
4096-cycle (~64 us) window, and it gates *driving*, not sampling — see below.

## Pull-ups: this host has none that work

*Measured 2026-09-18 and 2026-09-19. See `docs/rg35xx-plus/history.md`
("R1b busy and the missing data-line pull-up", "Pull-ups: one helps, five stop
the boot").*

The SD bus expects the host to pull CMD and DAT high, and the card releases
those lines between the blocks of a multi-block write and after every response.
**The H700 adapter path provides no effective pull-up** — released response ones
were observed as lows on CMD, and DAT0 sits low once an R1b select pulse
releases it, which the host reads as a card permanently busy
(`main.spade:1292-1301`).

The emulator's answer is an explicit idle-high drive in the H700 profile, and it
is deliberately conditional (`main.spade:1306-1318`):

```
reg(clk) h700_idle_data_armed reset(local_rst: false) = h700_mode && armed &&
    host_clock_active && !select_busy && !write_active;
```

So the idle-high drive is **gated on host clock activity and is off for the
whole of a write**. Both matter: the clock gate is what stops an armed FPGA
driving an unpowered target (it releases within two windows, about 128 us), and
the write exclusion is what leaves DAT0 floating between the blocks of a
multi-block write on a host with no pull-up of its own. That is the leading
suspect for the write failures seen at 12.5 MHz — **inferred, not established**;
the trace records nothing about the write path.

The FPGA's own weak pull-ups exist as `build_ddr.py --sd-pullups`
(`experiments/openxc7-macos/build_ddr.py:110-115, 183-203`), applying
`PULLTYPE PULLUP` to the five lines the card shares with the host —
`SD_SHARED_LINES = {0, 1, 2, 3, 7}`, i.e. CMD and DAT0..3; `pmod[6]` is the
clock and is always host-driven. On this host:

- **All five: worse.** The target reads the SPL, 83 sectors ending at LBA 96,
  then sends nothing more while going on clocking at about 200 kHz.
- **DAT0 alone: better but not sufficient.** The display image booted and drew.
  A single error stopped being fatal — the link survived 56 to 370 writes
  instead of about 20 — but the errors themselves were unchanged. So DAT0
  floating was making one error fatal, and was not what caused the errors.

Neither is needed at 6 MHz and **the qualified bitstream has no pull-ups**.

Two monitors that look like they should settle this do not: the pin monitors and
the clock-period monitor in the trace read the same in a healthy boot as in a
failed one (a clean control run showed `pin_data.serializer_mismatch` at 331 and
a minimum clock period of zero fabric cycles while writing 67 sectors without
error). The count of invalid command frames is the signal; those are not.

## The write receiver's start bit

`projects/microsd-emulator/src/write_rx.spade:38`:

```
if state == WAIT_START_BIT && (if width { dat == 0 } else { !dat.to_bits()[0] })
```

In four-bit mode the start bit is **all four DAT lines low at once**; in one-bit
mode it is DAT0 alone. On a bus with working pull-ups that is the standard and
is also conveniently hard to fake. On this host, where the lines float between
blocks, it is the only thing standing between charge on four undriven pins and a
spurious sector.

## Writes are an ascending run from sector zero

`projects/ethernet-diagnostic/src/blocks.spade:117` and `:128-130`: `OP_BEGIN`
declares a sector count and zeroes `written_sectors`; an `OP_WRITE` whose LBA is
not exactly `written_sectors`, or that would exceed `declared_sectors`, is
`STATUS_BAD_RANGE`; `OP_ARM` is `STATUS_INCOMPLETE_IMAGE` until
`written_sectors == declared_sectors`. **There is no such thing as writing one
sector in the middle of an image.**

This is a gateware invariant worth knowing because of what it costs a user.
`linux-consoles` delivers a new experiment to the target by rewriting a *prefix*
of the deployed image with the job patched into it and re-uploading that prefix
(`devices/rg35xx-plus/rg35xx/job.py:273-310`). The whole point of where its job
sector sits is to make that prefix short: about 1 MB and three seconds, against
57 MB and three minutes had the job lived in the debug partition.

## What the passive TRACE keeps, and what it throws away

*See `docs/rg35xx-plus/findings.md` ("The measurement zero") and
`devices/rg35xx-plus/rg35xx/debug_partition.py` / `job.py` for how a client
copes with each of these.*

The trace is a set of counters, not a log (`src/trace.spade`), and the cost of
that shows up in three specific ways:

- **A write's LBA does not survive.** `last_command` and `last_argument`
  (`trace.spade:60-69`) are overwritten by *every* valid command. Linux sends a
  card-status poll after each transfer, whose argument is the card's address, so
  a write's own sector is gone before the host can read it back. A target that
  wants to be seen through an armed card must therefore signal by **reading**.
- **A read's sector is one of two values.** `last_read_lba`
  (`trace.spade:91-102`) is updated on every backend block request, so a read of
  an 8-sector page is reported either at the page's first sector or at the
  sector after its last, depending on whether the backend had begun prefetching
  when the poll landed. Measured 2026-09-19: a 512-byte O_DIRECT read of sector
  2048 reported as 2056, and of 114952 as 114960. Signals must therefore be two
  pages apart to be distinguishable.
- **The clock-edge counter distinguishes asleep from off.** `clock_edges`
  (`trace.spade:37-41`) counts `sd_sample_tick` while armed
  (`main.spade:535`). A *suspended* H700 gates its clock off and holds the line:
  **exactly zero edges a second**, for the whole of a 45 or 70 second sleep. An
  *unpowered* target leaves the pin floating and the counter still advances, at
  **about fifty rising edges a second**. (The gateware comment at
  `main.spade:183-191` says "a few hundred transitions per second" for the same
  floating case — the same order, counting both edges.)

That last pair is also why **the first valid command, not the first clock edge,
is the only sound time zero for a boot measurement.** A floating line produces
edges and produces frames, but does not produce a frame that passes CRC7:
`valid_commands` and `invalid_frames` are separate counters
(`trace.spade:50-59`), and power-up edges land in the second. Anchoring a boot
clock on the first edge puts the zero at the first poll of every run.

## Building one of these: the seed lottery, and patching a pull-up in

*See `docs/rg35xx-plus/history.md` (the 2026-09-18 and 2026-09-19 bitstream
entries) and `QUALIFICATION.md` here.*

Timing closure on this design is a lottery over placement seeds, and the losing
tickets are expensive. Two data points: no seed through 20 closed with a runtime
mux added for the command phase, so the choice was compiled in instead
(`--h700-early-command`); and every placement of the enhanced-telemetry design
missed the 80 MHz `fclk` constraint across fifteen seeds on one netlist and ten
on another, which is why `--sd-io-clock-hz` exists and why the H700 profile runs
its SD fabric at 64 MHz. `build_ddr.py`'s `route()` re-checks each clock's
constraint from the nextpnr log and refuses a build that is missing one
(`build_ddr.py:419-468`).

**Seed 19 is the qualified H700 build.** `build/microsd-ddr-ethernet-h700`,
bitstream SHA-256 `cf5fb75dadfd8dcb65a89f4df8772986cdfd26b2dee3bbfab50979eeb28a30c3`,
847,723 verified configuration bits, `fclk` 65.78 MHz against a 64 MHz
constraint and `dclk` 80.38 against 80. That is the build every RG35XX figure
was measured on, and the margin is why "rebuild it and see" is not an option.

That bitstream was compiled by **Spade v0.17.0**; the sources have since moved
to **v0.20.0**, which emits the same ports and the same `#[no_mangle]` names
but a different netlist (`microsd-emulator` in 274 modules rather than 336).
A rebuild is therefore a new netlist needing its own placement-seed search,
its own timing check and its own hardware qualification before it could stand
in for seed 19. [QUALIFICATION.md](./QUALIFICATION.md) has the details.

**A pull-up can be added to a routed design without re-running place and
route.** `PULLTYPE` is a per-IOB configuration feature, and nextpnr emits one
line per IOB half — 79 `PULLTYPE.NONE` lines in the qualified design's
`design.fasm`. prjxray's segbits show `NONE` and `PULLUP` differ in exactly one
bit per IOB half (`share/prjxray/artix7/segbits_riob33.db`: `IOB_Y0` differs at
`39_93`, `IOB_Y1` at `38_34`), so five pins is five configuration bits. The
method:

1. Find the five IOB halves the shared lines were placed at, from `routed.json`:
   in the seed-19 route `pmod[0..3]` and `pmod[7]` are `IOB_X1Y77`, `Y75`,
   `Y74`, `Y73` and `Y69`. DAT0 is `pmod[3]`, package pin F3, FASM site
   `RIOB33_X43Y73.IOB_Y1` (`design.fasm`, `PULLTYPE.NONE`).
2. Change those `PULLTYPE.NONE` lines to `PULLTYPE.PULLUP` in a copy of
   `design.fasm`. Touch nothing else.
3. Re-run only the packing stage — `fasm2frames.py`, `xc7frames2bit`, then
   `bitread` to decode and compare (`experiments/openxc7-macos/build_common.py`,
   `pack_and_verify_bitstream` and `verify_frames`). Routing, timing and CDC
   results carry over from the parent build unchanged.

The two bitstreams built that way are pruned, but their manifests survive in
`build/pruned-manifests/`: `microsd-ddr-h700-seed19-pullups-fasm.json` (all
five) and `microsd-ddr-h700-s19-pull-dat0.json` (DAT0 only), both recording
`derived_from: "microsd-ddr-ethernet-h700 seed-19 fasm … routing untouched"`.
Note that their `verified_configuration_bits` field reads 847,723, the parent's
value, because the patch procedure copied the parent manifest rather than
recomputing it — do not read that as evidence that the bit count is unchanged.

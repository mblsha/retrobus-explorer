# RG35XX Plus: build, flash, boot, measure

Everything needed to produce the delivered boot and measure it, in the order
it has to happen. What the numbers mean is in
[RG35XX-PLUS-FINDINGS.md](RG35XX-PLUS-FINDINGS.md); how they were arrived at is
in [RG35XX-PLUS-HISTORY.md](RG35XX-PLUS-HISTORY.md). Nothing below needs
either of them.

Run every command from `gateware/`.

Three steps need the bench and are marked as such: they were **not executed
while this was written**, and a coordinator runs them. The kernel and rootfs
builds were not re-run either; they take about an hour in a container and their
outputs are already in `build/`, so those two sections are marked as well.
Everything else here was run as written, and what is shown below a command is
that run's own output.

## 0. Environment

Use `uv run --frozen` for every Python command in this file. Never run
`uv sync`: the user's global `~/.config/uv/uv.toml` sets `exclude-newer`, so
`uv sync --locked --all-packages` fails outright, and a plain `uv run` resolves
and rewrites `uv.lock` behind you. `--frozen` uses the environment as it
stands and touches nothing. If a sync is genuinely unavoidable, add
`--no-config` so the global `exclude-newer` is not applied.

Do not delete or recreate `gateware/.venv`. The one that exists has a working
`cocotb` 1.9.2; building that version from source on this Mac with the current
uv fails at link time with `ld: library 'gpilog' not found`, so a fresh clone
should expect the cocotb install to need attention rather than assume
`uv sync` will produce a working testbench environment.

If `gateware/uv.lock` ever shows as modified, `git checkout gateware/uv.lock`
before committing.

## 1. Bitstream

**Bench step: not executed while writing; the coordinator runs it.**

One profile expands to the qualified build, so the options cannot drift:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib \
  ./.venv/bin/python experiments/openxc7-macos/build_ddr.py \
  --profile h700-rg35xx
```

Output is `build/microsd-ddr-ethernet-h700/`, with `design.bit` and a
`result.json` that records the bitstream's sha256, the placement seed and the
options. Require a successful exit and a matching `bitstream_sha256` before
programming anything; intermediate files from a failed build are not approval.

Two rules are not optional:

- `DYLD_LIBRARY_PATH` must point at Boost 1.90. `nextpnr-xilinx` here is linked
  against Homebrew's Boost by absolute path and Homebrew has moved on, so
  without the pin the binary cannot load at all and dies on SIGABRT — which
  looks exactly like a placement failure and is not one.
  `build_common.check_place_and_route_runs` probes `nextpnr-xilinx --version`
  before anything spawns it and turns that into one line naming the mismatch
  and the Cellar paths to try.
- `./.venv/bin/python`, not `uv run`. macOS strips `DYLD_LIBRARY_PATH` when a
  process is re-executed through a signed launcher, so the pin above would be
  gone by the time nextpnr starts. This and the seed search below are the only
  commands in this file that must avoid `uv run`.

`--profile` supplies defaults, so a flag given alongside it still wins and an
experiment can start from the shipped build and change one thing.

### When a seed misses timing

`build_ddr.py` routes exactly one seed and rejects the build if that placement
misses a constraint. Re-synthesizing to try another costs about ten minutes;
routing the netlist that is already there costs about ninety seconds:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/boost/1.90.0/lib \
  ./.venv/bin/python tools/search_placement_seeds.py \
  --output build/microsd-ddr-ethernet-h700 --h700-mmc \
  --seeds 1 2 3 4 5 6 7 8
```

It reports which seeds meet every clock and SD output-delay bound. Feed a
winner back as `build_ddr.py --profile h700-rg35xx --seed N` to produce the
verified artifact. `--h700-mmc` applies the legacy-MMC output-edge
expectations, which is what this profile is routed against.

## 2. Kernel

**Not executed while writing.** The build runs in an arm64 container; its
output is already in `build/rg35xx-kernel-trim/out/Image` and rebuilding it
costs about an hour. The manifest check it starts with was run against that
tree, and the gzip step at the end of this section was run.

The kernel is mainline plus ROCKNIX's patches and configuration, which live in
ROCKNIX's repository. `rg35xx/rocknix-sources.json` records the commit they
come from with a SHA-256 for each, and `--fetch` turns that manifest back into
files: `patches/*.patch` and `base.config` in the work directory, each requested
at the pinned commit and written only if its hash matches. All 27 arrive in
under ten seconds (run on 2026-09-19 into an empty directory, and the manifest
check below passed on the result). The build then verifies the work tree against
the manifest whether or not it fetched, and refuses a missing, extra or altered
file, because all three change the kernel:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-kernel --work build/rg35xx-kernel-trim --fetch --trim-network-and-crypto
```

The recorded tree is ROCKNIX/distribution at `5eb06fab68fa` with 26 patches,
which is what `build/rg35xx-kernel-trim` still matches. Moving to a newer
ROCKNIX tree is done deliberately with `--allow-unpinned`, and the manifest
re-recorded.

Two options decide what comes out:

- `--trim-network-and-crypto` drops every wireless vendor but Realtek, the
  wired ethernet drivers, the protocol menus this device never speaks, and the
  crypto outside what WPA selects. It is worth 172,570 compressed bytes, which
  is 0.07 s of boot. It is in the delivered kernel.
- `--toolchain clang` builds with `LLVM=1` and ThinLTO, and refuses to continue
  if `olddefconfig` did not keep the option. **Do not use it.** It produces a
  smaller kernel and a slower boot: on the identical configuration it costs
  778,737 compressed bytes, 0.30 s of reading. The delivered kernel is gcc.

The result is `<work>/out/Image`, 18,323,464 bytes. U-Boot loads it gzipped, so
make the payload the boot partition carries:

```sh
cp -p build/rg35xx-kernel-trim/out/Image /tmp/Image
gzip -9 /tmp/Image
```

That leaves `/tmp/Image.gz`, 7,190,891 bytes. `cp -p` matters: gzip stores the
source file's name and mtime in its header, so without the timestamp the
payload's bytes differ from the delivered one even though the kernel inside is
identical.

## 3. Rootfs

**Not executed while writing.** Also an arm64 container build; its output is
already in `build/rg35xx-bare/`.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-rootfs --cluster 65536
```

It writes `build/rg35xx-bare/system-c65536.erofs` (1,835,008 bytes) and
`build/rg35xx-bare/data.ext2`. `--cluster` is the EROFS physical cluster size,
the unit the kernel reads and decompresses, and the image is named after it so
that two of them can coexist and be compared on hardware. 64 KiB is the
measured choice; see the findings for what it costs.

## 4. Card image

Start from the base image, replace the kernel the boot partition carries, then
append the system slots and the data volume. The two steps below were run as
written and reproduce the delivered image byte for byte.

```sh
cp build/rg35xx-bare/rg35xx-plus-bare-64m-trimmed.img /tmp/base.img
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --replace-file /tmp/base.img --name KERNEL --payload /tmp/Image.gz \
  --output /tmp/base-kernel.img
```

```text
{
  "replaced": "KERNEL",
  "bytes": 7190891,
  "sha256": "0ccd052d9f0980d7746e282719df46b1d1ad618a145af5602a4667a2e2ab9994"
}
```

`--replace-file` reallocates the file rather than overwriting in place, prefers
one contiguous run, rewrites every FAT copy together, and leaves the other
files untouched.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --make-erofs-image /tmp/base-kernel.img \
  --system build/rg35xx-bare/system-c65536.erofs \
  --data build/rg35xx-bare/data.ext2 --slot a --card-max-hz 6000000 \
  --output /tmp/rg35xx-plus-erofs.img
```

```text
{
  "bytes": 137363456,
  "sha256": "93e49da1e5a1313f19539018b3354b5c25b4ebe3de4ff432519daa81a3980cb3",
  "root": "/dev/mmcblk0p5",
  "logical_partitions": [
    {"index": 5, "ebr_lba": 131072, "type": 131, "start_lba": 133120, "sectors": 32768},
    {"index": 6, "ebr_lba": 165888, "type": 131, "start_lba": 167936, "sectors": 32768},
    {"index": 7, "ebr_lba": 200704, "type": 131, "start_lba": 202752, "sectors": 65536}
  ]
}
```

That sha256 is the delivered card image, kept as
`build/rg35xx-bare/rg35xx-plus-bare-erofs-6mhz.img`. `--card-max-hz 6000000`
caps the clock Linux gives the emulated card, in the image's device tree: left
alone Linux runs the card at 12.5 MHz, twice U-Boot's rate, where the link has
little margin and fails outright once a display is running (see the display
section of the findings). It is for the emulated card only; an image meant for a
real card must not carry it. Without the option the same command gives
`bd44e08c0aa567a4b3aa4104d6dc447860d7ff8b4b597e467b2d618759034620`, the image
delivered on 2026-09-19 and measured in the findings' stage table. `--slot b`
roots from the other system partition instead; the slot is compiled into `BOOT.SCR`, so switching it
rewrites one file and changes nothing else.

Verify the contract before any upload. A matching whole-image hash alone does
not prove it:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --verify-image /tmp/rg35xx-plus-erofs.img
```

```text
"spl": {"offset": 8192, "length": 40960, "checksum": "a629138d"},
"boot_files": {"BOOT.SCR": 493, "BOOTMARK": 512, "KERNEL": 7190891, "DTB.IMG": 49511},
"debug_command": "boot-shell",
"card_max_hz": 6000000
```

It checks the MBR layout, the H700 eGON SPL at byte 8192 and its checksum, the
FAT16 `BOOT.SCR` with its legacy framing and length table, `BOOTMARK`, the
arm64 kernel and the DTB, that a compressed kernel is matched by a script able
to expand it, the EROFS superblocks of both system slots and the ext2 data
volume behind the debug partition, and a pristine raw debug command sector with
empty milestone sectors.

Two more things the image tool does. `--describe` names a single sector,
following the real FAT chain rather than assuming a file is contiguous, which
is how a trace row is read:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --describe /tmp/rg35xx-plus-erofs.img --lba 32985 --lba 114720 --lba 133120
```

```text
32985 KERNEL+10240
114720 partition 2 sector 32
133120 system A+0
```

And `--make-command` encodes the host-to-target command that sector 0 of the
raw debug partition carries, while `--decode` reads the milestones back out of
sectors 1 through 31.

## 5. Deploy

**Bench step: not executed while writing; the coordinator runs it.**

```sh
MDP_CLI=/path/to/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py deploy \
  --build-dir build/microsd-ddr-ethernet-h700 \
  --image /tmp/rg35xx-plus-erofs.img \
  --state /private/tmp/rg35xx-boot-session.json
```

Four steps with their premises checked: it verifies the image before the FPGA
is programmed, refuses to program while the target's channel reports its output
on, uploads and reads the image back complete, and compares the sha the card
reports with the file's before arming. Nothing here powers the target on; it
only leaves a card armed with a known image.

`--channel` defaults to `psu2`. **`psu2` is the RG35XX. `psu1` carries the
Zaurus on this bench and must never be switched by a card trial or a deploy.**

## 6. Trial

**Bench step: not executed while writing; the coordinator runs it.**

One standardized cold start:

```sh
MDP_CLI=/path/to/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py trial \
  --state /private/tmp/rg35xx-boot-session.json --observe 25 \
  --image /tmp/rg35xx-plus-erofs.img --output /tmp/run-1.json
```

It takes a baseline trace, holds the target's channel off for the settle
interval, switches it on without waiting for the power CLI while polling is
already running, collapses the poll series to the moments card activity
changed, names the sectors each stage touched, and always powers the target off
and disarms the card afterwards. It prints `userspace milestone at X.XXs` and,
with `--output`, writes the timeline as JSON for `report`.

`--settle` defaults to six seconds; trials run back to back have repeatedly
produced a cold start with no card activity at all, which the longer off
interval avoids. `--fabric-clock-hz` must match the SD fabric clock the
bitstream was built with, 64 MHz for this profile, because the block timestamps
are counted in it.

## 7. Report

A single run is not a result. `report` reduces a set of trial JSON files to the
distribution that compares them, and it is where every boot figure quoted
anywhere in these documents comes from:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py report \
  'stage1-baseline=/tmp/trials/q2-*.json' \
  'stage2-initramfs=/tmp/trials/t2-*.json' \
  'stage3-erofs=/tmp/trials/[er]3-*.json' \
  'delivered=/tmp/trials/fin-*.json'
```

```text
stage1-baseline                n=10/10 median  9.93  min  9.88  max 11.07  stdev 0.36  IQR 0.06
stage2-initramfs               n=10/10 median  5.75  min  5.72  max  5.83  stdev 0.03  IQR 0.05
stage3-erofs                   n=20/21 median  5.44  min  5.41  max  6.72  stdev 0.29  IQR 0.02
delivered                      n=20/21 median  5.38  min  5.34  max  6.68  stdev 0.39  IQR 0.05
```

`n=20/21` is twenty comparable runs out of twenty-one recorded: a run whose
zero was never established is skipped rather than reported optimistically.
Quote the glob as shown so the shell hands the pattern through intact.

## 8. Tests

Host tests, fast, no hardware and no simulator:

```sh
uv run --frozen python -m unittest discover -t projects/ethernet-diagnostic \
  -s projects/ethernet-diagnostic/test_host -p 'test_*.py'
```

```text
Ran 163 tests in 0.399s
OK
```

Cocotb testbenches against the built design, about a minute:

```sh
uv run --frozen python tools/run_tb.py --project projects/ethernet-diagnostic
```

`run_tb.py` must finish successfully and its strict JUnit XML check must report
at least one testcase with no failures or errors.

## 9. Housekeeping

A routed Arty build leaves about a gigabyte behind and a campaign leaves
thirty of them. `prune_builds.py` prints what is there, largest first, with the
seed and options each `result.json` records, and removes only what you do not
name. Nothing is deleted without `--delete`:

```sh
uv run --frozen python tools/prune_builds.py --include-unfinished \
  --keep microsd-ddr-ethernet-h700 microsd-ddr-h700-15mhz \
         microsd-ddr-sd microsd-ddr-ethernet \
         microsd-ddr-ethernet-slow-mmc microsd-ddr-ethernet-mmc-only \
         ethernet-diagnostic microsd-edge-timing-check microsd-litedram-bios
```

```text
ACTION  DIRECTORY                      BITSTREAM     SEED  PROFILE  H700  IO MHz  CARD MHz  SIZE
keep    microsd-ddr-ethernet           unfinished    -     -        -     -       -         5.4 GiB
keep    microsd-ddr-ethernet-slow-mmc  da2579b8f06d  5     -        yes   80      13        3.0 GiB
keep    microsd-ddr-sd                 990544fb7d44  4     -        -     100     13        1.1 GiB
keep    microsd-ddr-ethernet-h700      cf5fb75dadfd  19    -        yes   64      13        997.3 MiB
keep    microsd-ddr-ethernet-mmc-only  2df4bdeff49e  4     -        no    80      13        399.8 MiB
keep    microsd-ddr-h700-15mhz         fde8dbe0b519  7     -        yes   64      15        338.8 MiB
keep    microsd-litedram-bios          d7e12b41c809  1     -        -     -       -         141.5 MiB
keep    ethernet-diagnostic            056df268d31a  -     -        -     -       -         27.5 MiB
keep    microsd-edge-timing-check      -             -     -        -     -       -         10.1 MiB
```

That keep-set is the qualified H700 build, the measured 15 MHz build, the
default output directories of the four supported profiles, and three small
directories of unclear provenance. Run with `--delete` on 2026-09-19 it took the
tree from 53 GB to 24 GB: 22 finished experiments and 25 unfinished builds,
28.9 GiB, which is why the listing above has nothing left to prune. Naming only
the first two would delete the other profiles' builds as well.

`--include-unfinished` is what reaches most of the space. `build_ddr.py` deletes
the previous manifest when a build starts and publishes a new one only on
success, so every placement that missed timing leaves a gigabyte with no
`result.json`, and by default such a directory is refused because it cannot say
what it is. The option admits one only if it holds `board.v`, the first file a
bitstream build writes, which nothing else in `build/` contains; `--keep`
reaches these too, as `microsd-ddr-ethernet` above shows. The kernel trees, card
images, the openxc7 toolchain and the pinned LiteX interpreter are refused by
name and by pattern whatever is asked.

Before a finished experiment is removed its `result.json` is copied to
`build/pruned-manifests/`, so the seed and options to build it again outlive
the netlists.

## 10. Display bring-up and the flight recorder

The panel's init sequence is firmware, and it is compiled into the kernel:
`build-kernel` takes it from `--firmware-dir` (default `build/rg35xx-firmware`),
checks it against the hashes in `rg35xx/rocknix-sources.json`, and refuses to
build without it; `--fetch` downloads it together with the patches. A rootfs
carries no firmware.

`build-rootfs` puts a test picture at `/usr/share/rg35xx/display-proof.ppm`,
colour bars, a grey ramp, a one-pixel border and up to four lines of text given
with `--proof-line`, and init draws it with `fbsplash` once the kernel has
registered `/dev/fb0`, reporting the geometry and the result in the stage-5
milestone. Build into a directory of its own: `build/rg35xx-bare` holds the
inputs that reproduce the delivered image.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-rootfs --out build/rg35xx-display --proof-line "RG35XX PLUS" --proof-line "DISPLAY OK"
```

Sectors 24..31 of the debug partition are a flight recorder: the tail of the
kernel log, rewritten ten times a second from init's first milestone on. After a
run, with the card disarmed:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/images.py \
  --state "$STATE" --download /tmp/debug.bin --start 114688 --blocks 32
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image --decode /tmp/debug.bin
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image --kernel-log /tmp/debug.bin
```

A trial's JSON also keeps `final_trace`, everything the FPGA knew when the run
ended, and `trial` does not report itself finished until the supply has
confirmed its output off.

An image whose kernel starts the display has to be built with
`--card-max-hz 6000000`, which caps the clock Linux gives the card in the
image's device tree; without it Linux runs the card at 12.5 MHz and the link
fails within a second of the panel starting (see the display section of
RG35XX-PLUS-FINDINGS.md). `--verify-image` reports the cap as `card_max_hz`.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --make-erofs-image BASE.img --system build/rg35xx-display/system-c65536.erofs \
  --data build/rg35xx-display/data.ext2 --slot a --card-max-hz 6000000 \
  --output build/rg35xx-display/rg35xx-plus-display-6mhz.img
```

Nobody has to look at the panel. The stage-5 milestone ends in
`fbsplash-0 fb-md5-<16 digits>`, the checksum of what the panel is scanning out,
and this prints what it must be for the same `--proof-line`s:

```sh
uv run --frozen python projects/ethernet-diagnostic/rg35xx/display_proof.py \
  --line "RG35XX PLUS" --line "DISPLAY OK" --expect
```

`display-sweep` is a host command like `poweroff`: put it in sector 0 of the
debug partition (`image --make-command display-sweep`, written at LBA 114688)
and init puts the display to sleep, then does the same card work asleep, lit at
0, 100 and 50 percent, and asleep again, counting the controller's errors in
each state and writing every record to stage 6 with the display asleep. At
12.5 MHz the link dies before it can measure anything; it is for a clock at
which the link survives.

Replacing a file in the boot partition moves it, and the boot script reads
`KERNEL` and `DTB.IMG` by sector. `--replace-file` alone therefore leaves U-Boot
loading the old copy; `--make-erofs-image` rewrites the script, and
`--verify-image` refuses an image whose script and files disagree.

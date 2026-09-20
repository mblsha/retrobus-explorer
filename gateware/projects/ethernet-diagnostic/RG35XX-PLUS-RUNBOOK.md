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
written and reproduce the delivered image byte for byte. The base image also
carries the bootloader, which section 12 builds from source and replaces.

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
Ran 301 tests in 0.763s
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

## 11. The job harness

A job is a shell script. The host writes it into the card, the runner init
execs reads it, runs it, and writes back what it printed; the host samples the
bench supply meanwhile and reports what each state the job marked off drew.
Changing an experiment costs a file on this Mac, not a rootfs and an image.

Build a rootfs and an image whose debug sector already says `job-runner`, and
deploy it once. The image must carry the command, because the debug partition
is at sector 114688 and the gateware only takes writes as an ascending run
from sector zero:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-rootfs --out "$PWD/build/rg35xx-sleep" --proof-line "RG35XX PLUS" \
  --proof-line "JOB RUNNER" --proof-line "SLEEP HARNESS" --proof-line "2026-09-20"

uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --make-erofs-image build/rg35xx-display/base-display-kernel.img \
  --system build/rg35xx-sleep/system-c65536.erofs \
  --data build/rg35xx-sleep/data.ext2 --slot a --card-max-hz 6000000 \
  --debug-command job-runner \
  --output build/rg35xx-sleep/rg35xx-plus-sleep.img

MDP_CLI=/Users/mblsha/src/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py deploy \
  --build-dir build/microsd-ddr-ethernet-h700 \
  --image build/rg35xx-sleep/rg35xx-plus-sleep.img \
  --state /private/tmp/rg35xx-sleep-session.json
```

The deploy is eight minutes and is needed only when the rootfs or the image
changes. Every job after it is one command:

```sh
MDP_CLI=/Users/mblsha/src/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py job \
  --state /private/tmp/rg35xx-sleep-session.json \
  --image build/rg35xx-sleep/rg35xx-plus-sleep.img \
  --script /tmp/experiment.sh --name idle-dark --run-seconds 120 \
  --label idle-dark --output /tmp/idle-dark.json
```

```text
job idle-dark-2: done exit=0 | idle-dark 145 mA (126-156, IQR 10, n=16)
first card command at 5.28s
  idle-dark: {"start": 11.73, "end": 56.78, "dwell_seconds": 45.05, ...}
result sequence=3 status=done exit=0 uptime 2.98..48.06 rtc 86405..86452 flush=blockdev
```

It powers the target off, writes the job, arms the card, powers the target on,
watches what the card sees, powers it off again, disarms and reads the result.
Ninety seconds for a job that holds a state for forty-five, of which about
twenty-five is overhead: six seconds settling, six booting, three writing the
job and the rest switching and confirming the supply. `--print-output` prints
what the script printed; `--mode fetch` reads the last result off a disarmed
card without touching anything.

### What a job may call

The script is sourced into a subshell of the runner, so everything the runner
defines is available to it and nothing it defines survives. `$BB` is BusyBox in
tmpfs and always works; the applets are also on `PATH` as `/tmp/bin/*`.

- `rtc_sleep SECONDS [STATE [MEM_SLEEP]]` arms the RTC alarm, writes everything
  printed so far to the card, marks the sleep, suspends, and on waking reports
  the requested duration against the RTC's and `/proc/uptime`'s accounts of it,
  `suspend_stats` either side, and a card check.
- `card_check` writes a unique pattern to a scratch sector, drops the buffers,
  reads it back and prints `card-check ok` or what it got instead.
- `mark_sector LABEL` puts a boundary in the card's trace. A state the host is
  to measure is `mark_sector x-begin`, the state, `mark_sector x-end`, and each
  marked state becomes one `--label` in order.
- `rtc_now` is the RTC's seconds since the epoch. `/proc/uptime` is not a
  substitute: whether it advances across a suspend is a thing being measured.

A job that wedges the target costs one power cycle: the run ends at
`--run-seconds`, the target is switched off, and whatever the job flushed
before it stopped is still on the card.

### Measuring current

Every window is summarised the way this note quotes a figure: median, range
and interquartile range of the readings taken wholly inside it, after
discarding the first three seconds, over a dwell of at least twenty. A reading
costs a second or more, so about one every two and a half seconds; a window
that is too short, too sparse, or contains a moment when the supply's link was
down is marked `UNSOUND` rather than quietly averaged. The supply reports
zeroes while its link is down, and a zero averaged into a current is a wrong
answer rather than a missing one.

### Exchanging a job through the target's sleep

`--mode exchange` runs a job that ends in a long `rtc_sleep`, and while the
target is suspended -- issuing no card command at all -- disarms the frontend,
reads the result the job flushed before suspending, writes the next job and
re-arms, all before the alarm fires:

```sh
MDP_CLI=/Users/mblsha/src/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py job \
  --state /private/tmp/rg35xx-sleep-session.json \
  --image build/rg35xx-sleep/rg35xx-plus-sleep.img --mode exchange \
  --script /tmp/sleeps-70s.sh --second-script /tmp/next-job.sh \
  --name swap --dwell 25 --wait-seconds 100 --label asleep \
  --output /tmp/swap.json
```

The exchange itself takes three seconds. See the findings for what it proves
and what it does not.

### Re-running the sleep experiments

The scripts are in `projects/ethernet-diagnostic/jobs/sleep/`, one per row of
the experiment tables in
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md), numbered in the order they were
run. They are job scripts, not host scripts: each is passed to
`rg35xx.py job --script`. There are twenty-eight of them:

```text
 1-17  the sysfs experiments, on any image
18-21  firmware stage 1, the CPU PLL stopped; needs the --suspend wfi image
22-26  firmware stage 2, the LPDDR4 in self-refresh; needs a self-refresh image
27-28  the checks that followed the outside review; 27 needs --suspend sr,
       28 never suspends and runs on any image
```

Rows 1 to 17 and 28 need nothing rebuilt or redeployed -- the image on the card
already carries the `job-runner` debug command -- so the only thing that
changes between them is the path and the labels. The firmware rows each need
their own image and their own eight-minute `deploy`, because the bootloader is
part of the card image: section 12 builds them.

```sh
MDP_CLI=/Users/mblsha/src/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py job \
  --state /private/tmp/rg35xx-sleep-session.json \
  --image build/rg35xx-sleep/rg35xx-plus-sleep.img \
  --script projects/ethernet-diagnostic/jobs/sleep/10-powersave-only-abba.sh \
  --name powersave --run-seconds 360 \
  --label A1 --label B1 --label B2 --label A2 --label A3 --label B3 \
  --output /tmp/powersave.json --print-output
```

One `--label` per marked window, in the order the job marks them; each
`rtc_sleep` marks one. `--run-seconds` has to cover the whole job, which is
roughly twelve seconds of boot plus forty-three per sleep plus the gaps: 360
for the six-sleep alternations, 540 for the ten-cycle run, 150 for a single
sleep. A job that overruns is cut off at `--run-seconds` with its power, which
costs a power cycle and nothing else.

The two review checks mark windows that are not all sleeps, so they have their
own label lists:

```text
27-regulator-cleanup-step.sh  --run-seconds 260 \
    --label before --label after --label deep1 --label deep2
28-drift-control-awake.sh     --run-seconds 400 \
    --label w1 --label w2 --label w3 --label w4 --label w5 --label w6
```

In both, and in the self-refresh rows, read the windows by their dwell rather
than by their labels: the 256 MiB md5 check between cycles is long enough to
open a short window of its own at about 170 mA, which shifts everything after
it.

Two things that are easy to get wrong:

- **Leave at least three seconds between one `rtc_sleep` and the next.** The
  host reads the card's passive trace five times a second, and on this target
  the wake, the mark, the card check and the next suspend all fit inside one
  poll: the end of one window and the start of the next are then the same
  event, and the second window is never opened at all. Every script here has
  `$BB sleep 3` between cycles for that reason and no other.
- **An UNSOUND window is not a measurement.** The supply's wireless link drops
  for a minute or two about once per eight-minute run and reports zeroes while
  it is down; the harness marks the window rather than averaging them in. Run
  it again.

### Applying the best sleep configuration

`jobs/sleep/apply-best.sh` is the whole of it and it is one knob: the
`powersave` cpufreq governor, set before suspending, which takes the policy to
480 MHz and `vdd-cpu` from 1.1 V to 0.9 V and is worth 11 mA asleep and about
8 mA awake. It sets the governor and then prints what it got, so it can be
used as a job on its own to check the target agrees. From another job, put the
same loop at the top:

```sh
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    echo powersave > "$p/scaling_governor" 2>/dev/null
done
```

It is policy rather than device state, so one write per boot is enough and it
survives every resume. Nothing else measured above the noise: see
[RG35XX-PLUS-SLEEP.md](RG35XX-PLUS-SLEEP.md) for the twenty-five devices that
can be unbound for nothing, the one that costs the wake, and the powered-off
reference point at 33 mA.

## 12. The bootloader from source

**The two builds take about eight minutes each in an arm64 container.** Both
were run as written on 2026-09-20 and what is shown below each command is that
run's own output; their results are in `build/rg35xx-firmware-src/`.

The bootloader is the one part of the card the boot ROM reads before anything
here can check it, and PSCI -- which decides whether Linux can offer anything
deeper than s2idle -- lives inside it. `build-firmware` builds it: mainline
U-Boot v2026.01 with ROCKNIX's one patch to the H616 DRAM driver and their
`anbernic_rg35xx_h700_lpddr4_defconfig`, carrying a BL31 from TF-A v2.12.0,
which is exactly what ROCKNIX's `u-boot-DDR4` package builds for this device.

`rg35xx/firmware-sources.json` pins all of it: a SHA-256 for each upstream
tarball, and the ROCKNIX commit with a hash for each file taken from it.
`--fetch` turns the ROCKNIX half of that manifest back into files through the
GitHub API, writing each only if its hash matches; the build then checks the
work directory against the manifest whether or not it fetched, and refuses a
missing, extra or altered file.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-firmware --suspend none --fetch
```

```text
{
  "suspend": "none",
  "u_boot": "v2026.01",
  "tf_a": "v2.12.0",
  "rocknix_commit": "7f1b3abece2c7d263cebd16b5a2ba4268d6ddaa5",
  "our_patches": {},
  "built": {
    "bl31.bin": {"bytes": 45161, "sha256": "fb70c9a9..."},
    "u-boot-sunxi-with-spl.bin": {"bytes": 629313, "sha256": "44472766..."}
  }
}
```

The result is `build/rg35xx-firmware-src/none/u-boot-sunxi-with-spl.bin`, and
the build is reproducible: U-Boot and TF-A are given a fixed build date rather
than the clock, so a second run into another directory produced the same two
files byte for byte. `--suspend wfi` is the same two trees with our TF-A patch
applied and `SUNXI_SYSTEM_SUSPEND=1`, which is the deep sleep firmware; the
SPL is identical either way, since BL31 rides inside the FIT.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-firmware --suspend wfi
```

Put it into a base image, then make a card image from that as usual. The
bootloader lives at byte 8192, in front of every partition; the region is
cleared before the new one is written, so a shorter bootloader cannot leave
the tail of a longer one where the SPL would go on reading it, and one that
would grow into the job sector at LBA 2048 or the first partition is refused.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --install-bootloader build/rg35xx-display/base-display-kernel.img \
  --bootloader build/rg35xx-firmware-src/none/u-boot-sunxi-with-spl.bin \
  --output build/rg35xx-firmware-src/none/base-ourboot.img
```

```text
{
  "bootloader_bytes": 629313,
  "last_lba": 1245,
  "reserved_lba": 2048,
  "sha256": "a61bf8e6144ec1cde0212e7b02162db60f82c1a83290ce29ed5443476ad47d1c"
}
```

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --make-erofs-image build/rg35xx-firmware-src/none/base-ourboot.img \
  --system build/rg35xx-sleep/system-c65536.erofs \
  --data build/rg35xx-sleep/data.ext2 --slot a --card-max-hz 6000000 \
  --debug-command job-runner \
  --output build/rg35xx-firmware-src/none/rg35xx-plus-sleep-ourboot.img
```

`--verify-image` then reports the new SPL and its checksum (`f9c6a0ec` for
every one of ours, `a629138d` for the bootloader ROCKNIX ships), and the image
is deployed by section 5 with no other change. A bad bootloader cannot brick
the device: the firmware lives on the emulated card, so recovering is a
power-off and another `deploy`.

The SPL checksum does **not** tell our bootloaders apart, because BL31 rides
inside the FIT behind it and the SPL is the same either way. What does is the
`sha256` of `u-boot-sunxi-with-spl.bin`, which `build-firmware` prints and
writes to `build.json` beside it. As built on 2026-09-20:

```text
--suspend        bl31.bin sha256  what it does while the core waits
none             fb70c9a9...      nothing: the parity build
wfi              03ca25d5...      PLL_CPUX stopped, DRAM left running
wfi32            ...              + the cluster parked on the 32 kHz clock
sr               e232991c...      + LPDDR4 in self-refresh, from an assembly stub
sr-gate          deada33f...      + the DRAM bus gate and the MBUS clock gate
sr-pll           d8d584de...      + PLL_DDR0 stopped and relocked (does not resume)
sr-c             da866b55...      sr again, from the C stub: proves the environment
sr-phy           b084eb68...      + DFI off, CLKEN 0, clock path gated and reset,
                                  PLL_DDR0 off, CPU and both APBs on 32 kHz, and
                                  the controller and PHY rebuilt on resume
sr-phy-pllon     77e37f6a...      sr-phy with PLL_DDR0 left running
sr-phy-fastapb   56f6bffb...      sr-phy with the CPU and APBs left on OSC24M
sr-phy-padhold   cd6f5391...      sr-phy plus the prior art's DRAM pad-hold write
rocknix-deep     bca96e13...      not ours: kailashrs' TF-A patch and SRAM stub
```

`none` and `sr` were rebuilt after the `sr-phy` work went in and are byte for
byte what they were: `fb70c9a9` and `e232991c`, with the same
`u-boot-sunxi-with-spl.bin` either side. Adding a mode does not move a card
that was already measured.

### The self-refresh rungs

`--suspend sr`, `sr-gate` and `sr-pll` apply the same two patches and differ
only in `SUNXI_SUSPEND_DRAM_LEVEL`, which decides how much of the DRAM side of
the SoC the SRAM stub puts away. Each is built, installed and imaged exactly
like the one above, with its own name throughout:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-firmware --suspend sr

uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --install-bootloader build/rg35xx-display/base-display-kernel.img \
  --bootloader build/rg35xx-firmware-src/sr/u-boot-sunxi-with-spl.bin \
  --output build/rg35xx-firmware-src/sr/base-ourboot.img

uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --make-erofs-image build/rg35xx-firmware-src/sr/base-ourboot.img \
  --system build/rg35xx-sleep/system-c65536.erofs \
  --data build/rg35xx-sleep/data.ext2 --slot a --card-max-hz 6000000 \
  --debug-command job-runner \
  --output build/rg35xx-firmware-src/sr/rg35xx-plus-sleep-sr.img
```

Then section 5's `deploy` with that image, and jobs 22 to 26 of
`jobs/sleep/` against it, and job 27 as well. 22 first and always: it does not
sleep, it costs one boot, and it is what says the DRAM controller is where the
stub expects it and that the watchdog's enable bit can still be cleared after
being set.

Two things about the stub that are easy to break and hard to notice:

- **It must contain no literal pool and no absolute address of its own.** It
  runs from `0x20000`, not from where it was linked, so a `ldr x0, =label`
  would load an address in DRAM that is in self-refresh at the time. Every
  constant in it is built with `movz`/`movk` and every label is reached with
  `adr`. The check is to find the blob in `bl31.bin` -- it starts with
  `0a 00 82 d2 0a 60 a0 f2`, which is `movz x10, #0x1000; movk x10,
  #0x0300, lsl #16` -- and disassemble it:

  ```sh
  llvm-mc --disassemble --triple=aarch64 < blob.hex
  ```

- **It must not grow past SRAM A1's 32 KiB**, and the build cannot check that
  for you: a `.if` on a difference of two labels in the same section is not a
  constant as far as the assembler is concerned, and the guard was removed
  again for that reason. It was 4224 bytes on 2026-09-20.

### The PHY-rebuild rungs

`--suspend sr-c`, `sr-phy` and the three `sr-phy-*` ablations apply patches
0001 and **0003** -- never 0002, because 0002's assembly stub and 0003's C one
are two answers to the same question. The C stub is a separate program in
`rg35xx/firmware/stub/`, GPL-2.0-or-later because it is compiled against
U-Boot's H616 DRAM driver, and `build-firmware` builds it inside the container
from the patched U-Boot tree before TF-A embeds it. The commands are the ones
above with the mode's own name throughout:

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-firmware --suspend sr-phy

uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --install-bootloader build/rg35xx-display/base-display-kernel.img \
  --bootloader build/rg35xx-firmware-src/sr-phy/u-boot-sunxi-with-spl.bin \
  --output build/rg35xx-firmware-src/sr-phy/base-ourboot.img

uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --make-erofs-image build/rg35xx-firmware-src/sr-phy/base-ourboot.img \
  --system build/rg35xx-sleep/system-c65536.erofs \
  --data build/rg35xx-sleep/data.ext2 --slot a --card-max-hz 6000000 \
  --debug-command job-runner \
  --output build/rg35xx-firmware-src/sr-phy/rg35xx-plus-sleep-sr-phy.img
```

Then section 5's `deploy`, then jobs 29 to 34 of `jobs/sleep/`. **29 first and
always**: it costs one boot, does not sleep, and says whether the controller is
where the stub expects it, whether the watchdog's enable bit can still be
cleared, and whether `/dev/mem` can reach SRAM A1 -- which is where everything
the stub has to say after a resume is kept. Then 30, one sleep on its own,
because a suspend that does not come back looks exactly like a target that
stopped answering. 32 is the alternation, 25 the ten cycles and 26 the
six-minute sleep; those two are the self-refresh jobs unchanged, because they
only ask for `mem` resolved to `deep` and check the memory afterwards.

```sh
MDP_CLI=/path/to/miniware-mdp-m01/cli \
  uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py job \
  --state /private/tmp/rg35xx-sleep-session.json \
  --image build/rg35xx-firmware-src/sr-phy/rg35xx-plus-sleep-sr-phy.img \
  --script projects/ethernet-diagnostic/jobs/sleep/32-phy-vs-s2idle-abba.sh \
  --name sr-phy-abba --run-seconds 480 \
  --label A1 --label B1 --label B2 --label A2 --label A3 --label B3 \
  --min-window-seconds 30 --output /tmp/sr-phy-abba.json --print-output
```

`--min-window-seconds 30` is what keeps the labels on the right arms: the md5
check between sleeps opens a window of its own, about ten seconds at 170 mA,
and without the rule every label after the first gap lands on the wrong sleep.
Those windows are still printed, as `short-1`, `short-2` and so on.

Three things about this stub that are easy to break:

- **Everything it runs must be in SRAM A1**, including U-Boot's DRAM driver,
  its `.bss` and its stack. `stub.lds` asserts that at link time, so a build
  that does not fit fails rather than hanging on the bench. It was 18,544
  bytes at `sr-phy` on 2026-09-20, against 8,776 at `sr-c`, where the linker
  drops the driver because nothing calls it.
- **It must not be built beside 0002.** The manifest lists which modes take
  which patch and `test_build_firmware.py` checks the two sets do not overlap.
- **Nothing of U-Boot is in this repository.** `stub/uboot-dram-resume.patch`
  is applied in the container to a copy of the driver taken from the pinned
  tree, never to the bootloader's own copy. Re-pinning U-Boot means re-checking
  that patch applies.

Debugging it blind is job 31: it writes `0x57440001` into RTC general purpose
register 11 before a ten-second sleep, which asks the stub to keep the watchdog
armed across the wait as well as around it. A hang then becomes a warm reset
and the next boot's job reads the stage code out of register 12. The watchdog's
longest interval is about sixteen seconds, so **a measured forty-second or
six-minute sleep cannot be covered**, and a hang in one of those still ends
with the harness cutting the power and taking the evidence with it.

### Their firmware, for measuring beside ours

`--suspend rocknix-deep` builds nothing of ours: kailashrs' TF-A patch at the
pinned ROCKNIX commit and his SRAM stub at the commit ROCKNIX pins
(`firmware-sources.json` has both hashes), with the stub compiled from the same
patched U-Boot tree the bootloader is built from and embedded in BL31. `--fetch`
is needed once after the manifest gained their patch. It is not called
`rocknix` because the default output directory is `<work>/<mode>` and
`<work>/rocknix` is where the pinned files live.

```sh
uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py \
  build-firmware --suspend rocknix-deep --fetch

uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --install-bootloader build/rg35xx-display/base-display-kernel.img \
  --bootloader build/rg35xx-firmware-src/rocknix-deep/u-boot-sunxi-with-spl.bin \
  --output build/rg35xx-firmware-src/rocknix-deep/base-theirboot.img

uv run --frozen python projects/ethernet-diagnostic/scripts/rg35xx.py image \
  --make-erofs-image build/rg35xx-firmware-src/rocknix-deep/base-theirboot.img \
  --system build/rg35xx-sleep/system-c65536.erofs \
  --data build/rg35xx-sleep/data.ext2 --slot a --card-max-hz 6000000 \
  --debug-command job-runner \
  --output build/rg35xx-firmware-src/rocknix-deep/rg35xx-plus-sleep-rocknix-deep.img
```

As built on 2026-09-20: `bl31.bin` 65,641 bytes, sha256 `bca96e13...`;
`u-boot-sunxi-with-spl.bin` 649,793 bytes, sha256 `baa2f493...`, last sector
1285; card image sha256 `a212799d...`. Deploy it as in section 5 and run jobs
23, 24 and 26 against it unchanged: they only ask for `mem` resolved to `deep`
and check the memory afterwards, which is the same question whoever wrote the
firmware. Their firmware keeps its own progress codes in the RTC registers, so
the `el3` line those jobs print reads `stage=0x00000400`, a wake interrupt, and
zero counters; that is theirs and not a fault.

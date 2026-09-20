#!/usr/bin/env python3
"""Run one experiment on the target and bring back what it measured.

A job is a shell script. The host writes it into a reserved region of the raw
debug partition, the runner that init execs reads it, runs it, and writes what
it printed into another region. Nothing else has to be rebuilt: an experiment
costs a script and a boot rather than a rootfs, an image and a deployment.

While that runs, this samples the bench supply. The supply's wireless link
drops for a minute or two at a time and reports zeroes while it is down, so a
sample is kept only if the module said it was online when it was taken, and a
window that contains a dropout is reported as unsound rather than averaged.

The host cannot read the card while it is armed, so what it knows during a run
comes from the FPGA's passive trace: the counters and the last command the card
saw. The target writes one sector nothing else uses to mark the boundaries of
whatever it wants measured, and the LBA of that write, visible in the trace, is
how a current window is lined up with what the target was doing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import threading
import time
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from rg35xx.debug_partition import DEBUG_SECTORS
from rg35xx.debug_partition import JOB_LBA
from rg35xx.debug_partition import JOB_SECTORS
from rg35xx.debug_partition import PAGE_SECTORS
from rg35xx.debug_partition import RESULT_SECTOR
from rg35xx.debug_partition import RESULT_SECTORS
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import SLEEP_MARK_SECTOR
from rg35xx.debug_partition import decode_job
from rg35xx.debug_partition import decode_records
from rg35xx.debug_partition import decode_result
from rg35xx.debug_partition import encode_job
from rg35xx.debug_partition import kernel_log
from rg35xx.debug_partition import read_reported_at
from rg35xx.deploy import UPLOAD_WINDOW
from rg35xx.deploy import checked_channel
from rg35xx.deploy import psu_status
from rg35xx.deploy import supply_is_online
from rg35xx.trial import power
from rg35xx.trial import power_off_confirmed
from scripts import images

# The debug partition's first sector on the delivered image. It is an argument
# rather than a constant everywhere it is used, but every image built by this
# tooling puts it here and a bench command should not have to say so.
DEFAULT_DEBUG_START = 114688
# The measurement rule these notes quote: hold a state for at least this long,
# throw away what the first seconds of it show, and report the spread.
MIN_DWELL_SECONDS = 20.0
DISCARD_SECONDS = 3.0
# How long a marked state is left alone before anything is taken for its end.
# Entering a suspend, the kernel syncs filesystems, and that sync can put a
# write on the card a fraction of a second after the target's own mark. Once
# that has been read as the end of the state, the host no longer believes the
# target is asleep and the whole sleep window is lost -- which happened on the
# first exchange attempt on 2026-09-20 and not on the five runs around it.
GRACE_SECONDS = 2.0
# Every conversation with the supply goes through this. The CLI opens the one
# serial port the modules are behind, and two of them open at once is not an
# error: the bytes interleave and a command is silently lost. On 2026-09-19
# that lost a power-off, and the target ran on for several minutes after the
# run that was measuring it had reported itself finished.
CLI_LOCK = threading.Lock()
CURRENT = re.compile(r"^\s*Current:\s*([0-9]+(?:\.[0-9]+)?)\s*A", re.MULTILINE)
VOLTAGE = re.compile(r"^\s*Voltage:\s*([0-9]+(?:\.[0-9]+)?)\s*V", re.MULTILINE)


def current_amps(status: str) -> float:
    """The current one `--status` report shows, in amps."""
    found = CURRENT.findall(status)
    if len(found) != 1:
        raise ValueError("PSU status does not report exactly one current")
    return float(found[0])


def voltage_volts(status: str) -> float:
    found = VOLTAGE.findall(status)
    if len(found) != 1:
        raise ValueError("PSU status does not report exactly one voltage")
    return float(found[0])


def locked_status(cli: Path, channel: str) -> str:
    with CLI_LOCK:
        return psu_status(cli, channel)


def locked_power(cli: Path, channel: str, state: str) -> None:
    """Switch the channel with nothing else on the port, and wait for it.

    A job does not need the sub-second accuracy a boot trial needs, so this
    waits rather than launching the CLI alongside the sampler. What a job
    measures is a state the target holds for half a minute, and the target
    says when that state began.
    """
    with CLI_LOCK:
        power(cli, checked_channel(channel), state)


def locked_power_off(cli: Path, channel: str) -> bool:
    with CLI_LOCK:
        return power_off_confirmed(cli, checked_channel(channel))


@dataclass
class Sample:
    """One reading, with what was known about the link when it was taken."""

    elapsed: float
    online: bool
    amps: float | None
    volts: float | None
    note: str = ""


def percentile(values: list[float], fraction: float) -> float:
    """Linear-interpolated percentile, for the handful of samples a dwell has.

    A dwell of twenty seconds holds between five and twenty samples, because
    each one costs a Node process and a serial exchange. `statistics.quantiles`
    refuses fewer than two points and cuts them a different way at these
    sizes, so the rule is written out here and is the same in every report.
    """
    if not values:
        raise ValueError("no samples")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(samples: list[Sample], start: float, end: float,
              discard: float = DISCARD_SECONDS) -> dict:
    """Reduce one window of samples to the figure a note would quote.

    Median rather than mean, because a boot or a card burst inside a window
    pulls a mean and leaves a median alone, and because the supply quantises
    to a milliamp. A window is sound only if it held the state long enough,
    kept enough samples, and saw no dropout: a supply whose link went down
    reports zeroes, and a zero averaged into a current is a wrong answer
    rather than a missing one.
    """
    # A reading counts only if the state held for the whole time the reading
    # took. One costs a second or more -- a Node process starts and a serial
    # exchange happens -- and a sample timestamped just inside a window can
    # have been taken while the target was already waking. Those are what put
    # a 264 mA maximum in a window whose quartiles were 241 to 250.
    spans = list(zip(samples, [s.elapsed for s in samples[1:]] + [None]))
    inside = [
        sample for sample, finished in spans
        if start + discard <= sample.elapsed <= end
        and (end if finished is None else finished) <= end
    ]
    usable = [s.amps for s in inside if s.online and s.amps is not None]
    offline = [s for s in inside if not s.online or s.amps is None]
    span = max(0.0, end - start)
    summary = {
        "start": round(start, 2),
        "end": round(end, 2),
        "dwell_seconds": round(span, 2),
        "discarded_seconds": discard,
        "n": len(usable),
        "offline_samples": len(offline),
        "sound": bool(usable) and not offline and span >= MIN_DWELL_SECONDS
        and len(usable) >= 4,
    }
    if usable:
        summary.update(
            {
                "median_a": round(statistics.median(usable), 4),
                "min_a": round(min(usable), 4),
                "max_a": round(max(usable), 4),
                "p25_a": round(percentile(usable, 0.25), 4),
                "p75_a": round(percentile(usable, 0.75), 4),
                "iqr_a": round(percentile(usable, 0.75) - percentile(usable, 0.25), 4),
            }
        )
    return summary


class PsuSampler(threading.Thread):
    """Record the target's current in the background while a run proceeds.

    It is a thread because one reading costs a second or more -- a Node process
    starts and a serial exchange happens -- and the run it is measuring has to
    be watched at a tenth of that interval. Nothing here switches anything; a
    sampler only reads.
    """

    def __init__(self, cli: Path, channel: str, zero: float | None = None,
                 status=psu_status):
        super().__init__(daemon=True)
        self.cli = cli
        self.channel = checked_channel(channel)
        self.zero = time.monotonic() if zero is None else zero
        self.samples: list[Sample] = []
        self._status = status
        # Not _stop: Thread already has one, and shadowing it breaks join().
        self._halt = threading.Event()

    def take(self) -> Sample:
        elapsed = time.monotonic() - self.zero
        try:
            # The port lock, not the status function's: a sample must wait for
            # a power command rather than interleave its bytes with it.
            with CLI_LOCK:
                status = self._status(self.cli, self.channel)
            online = supply_is_online(status)
            sample = Sample(
                elapsed, online,
                current_amps(status) if online else None,
                voltage_volts(status) if online else None,
                "" if online else "supply offline",
            )
        except (RuntimeError, ValueError, subprocess.SubprocessError) as failure:
            sample = Sample(elapsed, False, None, None, str(failure))
        self.samples.append(sample)
        return sample

    def run(self) -> None:
        while not self._halt.is_set():
            self.take()

    def stop(self) -> None:
        self._halt.set()
        self.join(timeout=180)


def trace_fields(trace: dict) -> dict:
    """The few counters that say what the card is doing, per poll.

    `read_lba` is the one that carries a message. A read is a single command
    with its sector in it and the trace keeps that sector until the next read;
    a write is followed by the card-status poll Linux sends after every
    transfer, whose argument is the card's address, so a write's own LBA is
    gone before the host can look. Everything the target wants seen while the
    card is armed it therefore reads.
    """
    return {
        "frames": trace["command_frames"],
        "valid": trace["valid_commands"],
        "invalid": trace["invalid_frames"],
        "writes": trace["writes"],
        "reads": trace["read_requests"],
        "read_lba": trace["last_read_lba"],
        "edges": trace["clock_edges"],
        "last_command": trace["last_command"],
        "card_state": trace["protocol_status"]["card_state"],
    }


@dataclass
class Watch:
    """What the passive trace showed while a job ran.

    Everything the host knows about a live target is in here: when it first
    spoke, when it last polled for a job, and when it marked the boundary of a
    state it wants measured. Marks come in pairs -- one entering the state and
    one leaving it -- so an odd count means the target is inside one, which for
    a suspend means it is asleep and the card can safely be taken away.
    """

    first_command: float | None = None
    marks: list[dict] = field(default_factory=list)
    windows: list[dict] = field(default_factory=list)
    polls: int = 0
    last_poll: float | None = None
    job_started: float | None = None
    job_finished: float | None = None
    last_write: float | None = None
    last_read: float | None = None
    samples: list[dict] = field(default_factory=list)
    resumed_card_state: int | None = None

    @property
    def inside_window(self) -> bool:
        return len(self.marks) % 2 == 1


def watch_trace(client, watch: Watch, zero: float, seconds: float,
                interval: float, debug_start: int,
                done=None, record_every: float = 1.0) -> str:
    """Poll the card's passive trace until something ends the wait.

    Returns why it stopped. The poll is fast because the events that matter --
    the runner's once-a-second look at the job region, a mark -- are single
    read commands that the next read overwrites in the trace's register, and a
    poll slower than the target's own would miss them.
    """
    mark = read_reported_at(debug_start + SLEEP_MARK_SECTOR)
    job_region = read_reported_at(JOB_LBA)
    # Where a read of the whole script ends. The runner reads the job's header
    # and then its body without pausing, so a host polling every fifth of a
    # second nearly always sees the second of the two: that read, and not the
    # header's, is what says a job has been taken up.
    script = range(JOB_LBA + JOB_SECTORS - PAGE_SECTORS,
                   JOB_LBA + JOB_SECTORS + PAGE_SECTORS + 1)
    previous = None
    recorded = 0.0
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        now = time.monotonic() - zero
        try:
            fields = trace_fields(client.trace())
        except (ValueError, OSError):
            time.sleep(interval)
            continue
        if previous is not None:
            if fields["valid"] > previous["valid"] and watch.first_command is None:
                watch.first_command = now
            read = fields["reads"] > previous["reads"]
            wrote = fields["writes"] > previous["writes"]
            if wrote:
                watch.last_write = now
            if read:
                watch.last_read = now
                if fields["read_lba"] in job_region:
                    watch.polls += 1
                    if watch.job_started is not None and watch.job_finished is None:
                        watch.job_finished = now
                    watch.last_poll = now
                elif fields["read_lba"] in script and watch.job_started is None:
                    watch.job_started = now
            signalled = read and fields["read_lba"] in mark
            settled = (watch.marks
                       and now - watch.marks[-1]["elapsed"] >= GRACE_SECONDS)
            if watch.inside_window:
                # Anything at all ends the state, once it has had a moment to
                # settle. The closing mark is a read like the opening one, but a
                # poll that lands after the target has already gone on to its
                # next card operation sees only the later one: on waking the
                # runner marks, checks the card and writes a result inside a
                # third of a second. So the window ends at the first sign of
                # life, which is the same instant to within one poll and does
                # not depend on the mark being caught.
                #
                # Nothing ends it before it has settled, a second sight of the
                # mark included. The read that carries the opening mark can
                # still be counting when the next poll lands a fifth of a
                # second later, and the kernel syncs on its way into a suspend;
                # taken for the end, either costs the whole window. On
                # 2026-09-20 the first did: a 45 s sleep was measured as 0.23 s
                # with no readings in it.
                if settled and (read or wrote):
                    watch.marks.append({"elapsed": round(now, 2), "opening": False})
                    watch.windows.append(
                        {"start": watch.marks[-2]["elapsed"], "end": round(now, 2)}
                    )
            elif signalled:
                watch.marks.append({"elapsed": round(now, 2), "opening": True})
        if previous is None or now - recorded >= record_every:
            watch.samples.append({"elapsed": round(now, 2), **fields})
            recorded = now
        previous = fields
        if done is not None:
            reason = done(watch, fields, now)
            if reason:
                watch.resumed_card_state = fields["card_state"]
                return reason
        time.sleep(interval)
    return "time"


def job_is_done(quiet: float, reboots: int = 0):
    """A job has finished once the runner is steadily polling for the next one.

    The runner reads the job region once a second when it has nothing to run,
    and not at all while a job runs. A job is always on the card before the
    boot or the wake that finds it, so the runner's first poll takes it up
    immediately and there is no steady polling until the job is over: two
    polls are the job's epitaph.

    Nothing simpler works. A write's LBA does not survive in the trace, so the
    result being written cannot be seen; the runner reads the header and then
    the script without pausing, so a host polling five times a second usually
    sees only the second of the two; and silence, the other candidate, is
    exactly what a suspended target looks like.

    A firmware experiment breaks that count on purpose. The suspend stub arms
    the watchdog across a short sleep so that a hang is a warm reset rather
    than a wedge, and the runner that comes back up polls once before it takes
    the same job again -- which reads exactly like the second poll that ends a
    run. Ending there costs the evidence: the failure's markers are in RTC
    registers that the next pass of the job is what prints, and a target that
    is powered off loses them. `reboots` is how many warm resets the caller is
    willing to sit through, and each one is one more poll before the epitaph.
    """
    threshold = 2 + max(0, int(reboots))

    def done(watch: Watch, fields: dict, now: float) -> str | None:
        if watch.polls >= threshold:
            watch.job_finished = watch.job_finished or now
            return "job-done"
        if watch.job_started is None and watch.last_poll is not None:
            if now - watch.last_poll >= quiet:
                watch.job_started = watch.last_poll
        return None

    return done


def target_is_asleep(quiet: float):
    """The target is asleep once it has marked a state and stopped entirely.

    A mark is not proof by itself: the target reads that sector at both ends of
    a state. Quiet after an opening mark is, because a suspended host drives no
    clock at all, and the runner's own poll would otherwise touch the card
    every second.
    """

    def done(watch: Watch, fields: dict, now: float) -> str | None:
        if not watch.inside_window or watch.last_read is None:
            return None
        return "asleep" if now - watch.last_read >= quiet else None

    return done


def prefix_sectors() -> int:
    """How many sectors a job costs to deliver."""
    return JOB_LBA + JOB_SECTORS


def submit(client, image: bytes, script: str, name: str,
           previous: dict | None = None) -> dict:
    """Put one job on the card, in the only way the gateware accepts a write.

    A session declares how many sectors it will receive and then takes them in
    one ascending run from sector zero; there is no writing a sector in the
    middle. So a job is delivered by replaying the first 2112 sectors of the
    deployed image with the job region substituted -- three seconds, against
    the three minutes it would take to reach the debug partition.

    Everything above those sectors is left exactly as the deploy verified it.
    The bytes below are read back and compared before the frontend is armed,
    which is what the client's own arm guard is for; it is satisfied here with
    the digest of the prefix rather than of the whole image, because the whole
    image is no longer what was just written.
    """
    if len(image) < prefix_sectors() * SECTOR_SIZE:
        raise ValueError("image is shorter than the job region it must carry")
    sequence = next_sequence(previous)
    job = encode_job(sequence, script, name)
    prefix = bytearray(image[: prefix_sectors() * SECTOR_SIZE])
    prefix[JOB_LBA * SECTOR_SIZE : JOB_LBA * SECTOR_SIZE + len(job)] = job
    prefix = bytes(prefix)

    client.begin(prefix_sectors())
    client.initial_upload["sha256"] = hashlib.sha256(prefix).hexdigest()
    client.save()
    for lba in range(prefix_sectors()):
        client.command(images.Opcode.WRITE, lba, 1,
                       prefix[lba * SECTOR_SIZE : (lba + 1) * SECTOR_SIZE])
    if client.bulk_download(prefix_sectors(), window=UPLOAD_WINDOW) != prefix:
        raise RuntimeError("the job readback differs from what was written")
    client.initial_upload["verified"] = True
    client.save()
    return {"sequence": sequence, "previous": previous}


def fetch(client, debug_start: int) -> dict | None:
    """Read the result region back; the card must be disarmed."""
    return decode_result(
        client.download(RESULT_SECTORS, debug_start + RESULT_SECTOR)
    )


def current_result(client, debug_start: int, sequence: int) -> dict | None:
    """The result of this job, or nothing.

    The region cannot be cleared before a run any more -- clearing it would
    cost the same three minutes that putting the job there would -- so a
    result left by the job before it is still on the card. The sequence number
    is what tells them apart, and a result numbered for another job is no
    result at all rather than a quietly wrong one.
    """
    result = fetch(client, debug_start)
    if result is None or result.get("sequence") != sequence:
        return None
    return result


def fetch_boot_records(client, debug_start: int) -> dict:
    """The milestones and the flight recorder, as `image --decode` shows them."""
    dump = client.download(DEBUG_SECTORS, debug_start)
    return {
        "records": decode_records(dump),
        "kernel_log": kernel_log(dump),
    }


def next_sequence(previous: dict | None) -> int:
    """Number a job one past whatever the card last carried.

    The runner only runs a job whose sequence it has not run, and it starts
    each boot having run none, so any number would do for a cold start. It
    would not do for a target that stayed up between jobs, which is the point
    of counting rather than toggling.
    """
    try:
        return int(previous["sequence"]) + 1 if previous else 1
    except (KeyError, TypeError, ValueError):
        return 1


def require_online(cli: Path, channel: str) -> str:
    status = locked_status(cli, checked_channel(channel))
    if not supply_is_online(status):
        raise RuntimeError(
            f"{channel} is offline; nothing it reports is evidence and nothing "
            "sent to it will arrive. Wait for the link and try again"
        )
    return status


def one_line(name: str, result: dict | None, windows: list[dict]) -> str:
    """The summary a bench log keeps: what ran, and what it drew."""
    if result is None:
        state = "NO RESULT"
    else:
        state = f"{result.get('status', '?')} exit={result.get('exit', '?')}"
    parts = [f"job {name}: {state}"]
    for window in windows:
        summary = window["current"]
        if summary.get("n"):
            parts.append(
                f"{window['label']} {summary['median_a'] * 1000:.0f} mA "
                f"({summary['min_a'] * 1000:.0f}-{summary['max_a'] * 1000:.0f}, "
                f"IQR {summary['iqr_a'] * 1000:.0f}, n={summary['n']}"
                f"{'' if summary['sound'] else ', UNSOUND'})"
            )
    return " | ".join(parts)


def measured_windows(watch: Watch, sampler: PsuSampler | None,
                     labels: list[str] | None = None,
                     min_seconds: float = 0.0) -> list[dict]:
    """Attach a current summary to every state the target marked off.

    Labels are handed out in order, and that order is broken by anything the
    job does between two states that looks like a state itself: checking a
    256 MiB md5 after a wake takes about ten seconds, the harness opens a
    window over it, and every label after it lands on the wrong sleep.

    `min_seconds` is the dwell below which a window is not one of the states
    being counted. Such a window is still reported -- it is what the target
    drew while awake, which is worth seeing -- but it is named `short-N` and
    the label it would have taken goes to the next real one instead. A sleep
    here is forty seconds or more and the gaps are ten, so any threshold
    between them separates them.
    """
    windows = []
    counted = 0
    short = 0
    for window in watch.windows:
        summary = (summarize(sampler.samples, window["start"], window["end"])
                   if sampler else {"n": 0})
        if window["end"] - window["start"] >= min_seconds:
            counted += 1
            label = (labels[counted - 1] if labels and counted <= len(labels)
                     else f"window-{counted}")
        else:
            short += 1
            label = f"short-{short}"
        windows.append({"label": label, **window, "current": summary})
    return windows


def run_reboot(arguments, client, script: str) -> dict:
    """One job on a target that is powered up for it and powered down after.

    This is the cycle that always works. The card is only ever exchanged while
    the target has no power, so nothing about it depends on how Linux takes a
    card being withdrawn, and a job that wedges the target costs one power
    cycle rather than a bench visit.
    """
    channel = checked_channel(arguments.channel)
    require_online(arguments.psu_cli, channel)
    if not locked_power_off(arguments.psu_cli, channel):
        raise RuntimeError(f"{channel} never confirmed its output off")
    if client.trace()["armed"]:
        client.command(images.Opcode.DISARM)
    submitted = submit(client, arguments.image.read_bytes(), script,
                       arguments.name, fetch(client, arguments.debug_start))
    client.command(images.Opcode.ARM)
    time.sleep(arguments.settle)

    zero = time.monotonic()
    sampler = PsuSampler(arguments.psu_cli, channel, zero)
    sampler.start()
    watch = Watch()
    reason = "aborted"
    try:
        locked_power(arguments.psu_cli, channel, "on")
        reason = watch_trace(
            client, watch, zero, arguments.run_seconds, arguments.interval,
            arguments.debug_start,
            done=job_is_done(arguments.quiet, arguments.expect_reboots),
        )
    finally:
        finished = time.monotonic() - zero
        # The sampler stops before the power-off rather than after it: they
        # share one serial port, and an "off" lost to a collision is the one
        # thing this bench must never leave behind.
        sampler.stop()
        powered_off = locked_power_off(arguments.psu_cli, channel)
        time.sleep(2)
        client.command(images.Opcode.DISARM)
    if not powered_off:
        print(f"WARNING: {channel} never confirmed its output off")
    result = current_result(client, arguments.debug_start, submitted["sequence"])
    return {
        "mode": "reboot",
        "stopped_because": reason,
        "run_seconds": round(finished, 2),
        "powered_off": powered_off,
        "sequence": submitted["sequence"],
        "watch": watch,
        "sampler": sampler,
        "result": result,
        "boot": fetch_boot_records(client, arguments.debug_start),
    }


def run_exchange(arguments, client, script: str) -> dict:
    """Swap the next job in through the window where the target sleeps.

    One job runs to its timed sleep. While the target is suspended it issues no
    card command at all, so the frontend can be disarmed, the result the job
    flushed before suspending read off, the next job written and the frontend
    re-armed, all before the RTC alarm fires. The target then wakes onto a card
    that was withdrawn and put back while it was not looking, and the second
    job's card check says whether Linux forgave that.

    This is the whole experiment in one command rather than two, because the
    interesting part is the seam: a target left asleep between two commands
    would wake with nobody watching.
    """
    channel = checked_channel(arguments.channel)
    require_online(arguments.psu_cli, channel)
    if not locked_power_off(arguments.psu_cli, channel):
        raise RuntimeError(f"{channel} never confirmed its output off")
    if client.trace()["armed"]:
        client.command(images.Opcode.DISARM)
    first = submit(client, arguments.image.read_bytes(), script, arguments.name,
                   fetch(client, arguments.debug_start))
    client.command(images.Opcode.ARM)
    time.sleep(arguments.settle)

    zero = time.monotonic()
    sampler = PsuSampler(arguments.psu_cli, channel, zero)
    sampler.start()
    watch = Watch()
    exchange: dict = {"first_sequence": first["sequence"]}
    try:
        locked_power(arguments.psu_cli, channel, "on")
        reason = watch_trace(
            client, watch, zero, arguments.wait_seconds, arguments.interval,
            arguments.debug_start, done=target_is_asleep(arguments.quiet),
        )
        exchange["asleep"] = reason == "asleep"
        if reason != "asleep":
            # Not an exception: the trace of the attempt is the only account of
            # why it did not work, and an exception here would throw it away
            # along with the run that produced it.
            print(
                "the target never marked a sleep the host could see; no "
                "exchange was attempted"
            )
            return finish_exchange(arguments, client, channel, exchange, watch,
                                   sampler)
        asleep_at = watch.marks[-1]["elapsed"]
        while time.monotonic() - zero < asleep_at + arguments.dwell:
            time.sleep(0.2)
        began = time.monotonic()
        client.command(images.Opcode.DISARM)
        flushed = fetch(client, arguments.debug_start)
        second = submit(client, arguments.image.read_bytes(),
                        arguments.second_script.read_text(),
                        arguments.name + "-second", flushed)
        client.command(images.Opcode.ARM)
        exchange.update(
            {
                "asleep_at": asleep_at,
                "disarmed_at": round(began - zero, 2),
                "rearmed_at": round(time.monotonic() - zero, 2),
                "exchange_seconds": round(time.monotonic() - began, 2),
                "second_sequence": second["sequence"],
                "flushed_result": flushed,
            }
        )
        # From here the target wakes, finishes the first job, finds the second
        # and runs that. Both have to happen for the exchange to have worked,
        # and the poll count is zeroed so that the polling before the sleep
        # cannot be read as the second job already being over.
        watch.job_started = watch.job_finished = None
        watch.polls = 0
        reason = watch_trace(
            client, watch, zero, arguments.wait_seconds, arguments.interval,
            arguments.debug_start, done=job_is_done(arguments.quiet),
        )
        exchange["second_ran"] = reason == "job-done"
        run = finish_exchange(arguments, client, channel, exchange, watch,
                              sampler)
    finally:
        if not exchange.get("finished"):
            run = finish_exchange(arguments, client, channel, exchange, watch,
                                  sampler)
    return run


def finish_exchange(arguments, client, channel, exchange, watch, sampler) -> dict:
    """Put the bench back and read off whatever the attempt left behind."""
    exchange["finished"] = True
    sampler.stop()
    powered_off = locked_power_off(arguments.psu_cli, channel)
    time.sleep(2)
    client.command(images.Opcode.DISARM)
    if not powered_off:
        print(f"WARNING: {channel} never confirmed its output off")
    return {
        "mode": "exchange",
        "exchange": exchange,
        "powered_off": powered_off,
        "watch": watch,
        "sampler": sampler,
        "result": current_result(client, arguments.debug_start,
                                 exchange.get("second_sequence", -1)),
        "boot": fetch_boot_records(client, arguments.debug_start),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="images.py session file")
    parser.add_argument("--script", type=Path, help="Shell script to run on the target")
    parser.add_argument(
        "--image", type=Path,
        help="The image deployed on the card. A job is delivered by replaying "
             "this image's first sectors with the job substituted, so it must "
             "be the file the card was loaded from",
    )
    parser.add_argument("--name", default="job", help="Name carried in the record")
    parser.add_argument(
        "--mode", choices=("reboot", "exchange", "fetch"), default="reboot",
        help="reboot: power the target up for this job and down after. "
        "exchange: run a job that sleeps and swap the next one in through the "
        "sleep. fetch: read the last result off a disarmed card and print it",
    )
    parser.add_argument(
        "--second-script", type=Path,
        help="The job to swap in during the sleep, for --mode exchange",
    )
    parser.add_argument("--run-seconds", type=float, default=90.0)
    parser.add_argument("--wait-seconds", type=float, default=120.0)
    parser.add_argument(
        "--dwell", type=float, default=25.0,
        help="Seconds to sample a resident target's sleep before disarming",
    )
    parser.add_argument(
        "--quiet", type=float, default=3.0,
        help="Seconds of no card write that end a job or confirm a sleep",
    )
    parser.add_argument(
        "--expect-reboots", type=int, default=0,
        help="How many warm resets this job may cause and carry on from. A "
             "suspend that hangs with the debug watchdog armed resets the "
             "board; the runner then polls for a job before running it again, "
             "and without this that poll is read as the job being over and the "
             "power goes off before the next pass can report what happened",
    )
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument(
        "--settle", type=float, default=6.0,
        help="Seconds to hold the target off before powering it on",
    )
    parser.add_argument("--debug-start", type=int, default=DEFAULT_DEBUG_START)
    parser.add_argument("--label", action="append", default=[],
                        help="Name for each marked window, in order")
    parser.add_argument(
        "--min-window-seconds", type=float, default=0.0,
        help="Dwell below which a marked window is not one of the states being "
             "labelled. A job that checks a large md5 between sleeps opens a "
             "ten-second window over the check; without this the labels after "
             "it land on the wrong sleep. Such windows are still reported, as "
             "short-N",
    )
    parser.add_argument(
        "--psu-cli", type=Path, default=os.environ.get("MDP_CLI"),
        help="Miniware MDP CLI checkout (default: $MDP_CLI)",
    )
    parser.add_argument(
        "--channel", default="psu2",
        help="PSU channel powering the target. psu2 is the RG35XX; psu1 is the "
        "Zaurus on this bench and must not be switched by a job",
    )
    parser.add_argument("--output", type=Path, help="Write the run as JSON")
    parser.add_argument("--print-output", action="store_true",
                        help="Print what the job printed")
    arguments = parser.parse_args(argv)
    if arguments.mode != "fetch":
        if arguments.script is None:
            parser.error("--script is required unless --mode fetch")
        if arguments.image is None:
            parser.error("--image is required to deliver a job")
        if arguments.mode == "exchange" and arguments.second_script is None:
            parser.error("--second-script is required for --mode exchange")
        if arguments.psu_cli is None:
            parser.error("--psu-cli or $MDP_CLI is required to power the target")

    client = images.Images(state=arguments.state)
    try:
        if arguments.mode == "fetch":
            result = fetch(client, arguments.debug_start)
            job = decode_job(client.download(JOB_SECTORS, JOB_LBA))
            print(json.dumps({"job": job, "result": result}, indent=2))
            return
        script = arguments.script.read_text()
        runner = run_reboot if arguments.mode == "reboot" else run_exchange
        run = runner(arguments, client, script)
    finally:
        client.close()

    watch: Watch = run.pop("watch")
    sampler: PsuSampler = run.pop("sampler")
    windows = measured_windows(watch, sampler, arguments.label,
                               arguments.min_window_seconds)
    result = run.get("result")
    print(one_line(arguments.name, result, windows))
    if watch.first_command is not None:
        print(f"first card command at {watch.first_command:.2f}s")
    for window in windows:
        print(f"  {window['label']}: {json.dumps(window['current'])}")
    if result is not None:
        print(
            f"result sequence={result.get('sequence')} "
            f"status={result.get('status')} exit={result.get('exit')} "
            f"uptime {result.get('start_uptime')}..{result.get('end_uptime')} "
            f"rtc {result.get('start_rtc')}..{result.get('end_rtc')} "
            f"flush={result.get('flush')} truncated={result.get('truncated')}"
        )
        if arguments.print_output:
            print(result.get("output", ""))
    boot = run.get("boot")
    if boot:
        stages = [
            f"{record.get('stage')}:{record.get('detail')}"
            for record in boot["records"] if "stage" in record
        ]
        print("stages " + " ".join(stages))
    if arguments.output is not None:
        arguments.output.write_text(
            json.dumps(
                {
                    **{key: value for key, value in run.items() if key != "boot"},
                    "windows": windows,
                    "marks": watch.marks,
                    "trace": watch.samples,
                    "first_command": watch.first_command,
                    "psu_samples": [asdict(sample) for sample in sampler.samples],
                    "boot_records": boot["records"] if boot else None,
                    "kernel_log": boot["kernel_log"] if boot else None,
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()

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
from rg35xx.debug_partition import JOB_SECTOR
from rg35xx.debug_partition import RESULT_SECTOR
from rg35xx.debug_partition import RESULT_SECTORS
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import SLEEP_MARK_SECTOR
from rg35xx.debug_partition import decode_job
from rg35xx.debug_partition import decode_records
from rg35xx.debug_partition import decode_result
from rg35xx.debug_partition import encode_job
from rg35xx.debug_partition import kernel_log
from rg35xx.deploy import checked_channel
from rg35xx.deploy import output_is_off
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
    inside = [s for s in samples if start + discard <= s.elapsed <= end]
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
        self._stop = threading.Event()

    def take(self) -> Sample:
        elapsed = time.monotonic() - self.zero
        try:
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
        while not self._stop.is_set():
            self.take()

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=180)


def trace_fields(trace: dict) -> dict:
    """The few counters that say what the card is doing, per poll."""
    return {
        "frames": trace["command_frames"],
        "valid": trace["valid_commands"],
        "invalid": trace["invalid_frames"],
        "writes": trace["writes"],
        "reads": trace["read_requests"],
        "edges": trace["clock_edges"],
        "last_command": trace["last_command"],
        "argument": trace["last_argument"],
        "card_state": trace["protocol_status"]["card_state"],
    }


@dataclass
class Watch:
    """What the passive trace showed while a job ran.

    Everything the host knows about a live target is in here: when it first
    spoke, when it wrote the mark that opens and closes a measured state, and
    when it went quiet. The marks come in pairs -- the target writes one
    entering a state and one leaving it -- so an odd count means the target is
    inside one, which for a suspend means it is asleep and the card can safely
    be taken away.
    """

    first_command: float | None = None
    marks: list[dict] = field(default_factory=list)
    windows: list[dict] = field(default_factory=list)
    results_written: int = 0
    last_write: float | None = None
    samples: list[dict] = field(default_factory=list)
    resumed_card_state: int | None = None

    @property
    def inside_window(self) -> bool:
        return len(self.marks) % 2 == 1


def watch_trace(client, watch: Watch, zero: float, seconds: float,
                interval: float, debug_start: int,
                done=None, record_every: float = 1.0) -> str:
    """Poll the card's passive trace until something ends the wait.

    Returns why it stopped. The poll is fast because the only events that
    matter -- a mark write, the card going quiet -- are single commands that
    the next command overwrites in the trace's "last command" register, and a
    poll slower than the target's own one-second job poll would miss them.
    """
    mark_lba = debug_start + SLEEP_MARK_SECTOR
    result_range = range(debug_start + RESULT_SECTOR,
                         debug_start + RESULT_SECTOR + RESULT_SECTORS)
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
            if fields["writes"] > previous["writes"]:
                watch.last_write = now
                if fields["argument"] == mark_lba:
                    watch.marks.append({"elapsed": round(now, 2),
                                        "opening": not watch.inside_window})
                    if not watch.inside_window and len(watch.marks) >= 2:
                        watch.windows.append(
                            {
                                "start": watch.marks[-2]["elapsed"],
                                "end": watch.marks[-1]["elapsed"],
                            }
                        )
                elif fields["argument"] in result_range:
                    watch.results_written += 1
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


def job_is_done(quiet: float):
    """A job has finished when it has written a result and gone quiet.

    Quiet alone is not enough: a job that suspends is quiet for as long as it
    sleeps, and a host that took that for the end would cut the target's power
    in the middle of the measurement. The target's marks say which it is --
    inside a marked state it is doing something on purpose.
    """

    def done(watch: Watch, fields: dict, now: float) -> str | None:
        if watch.inside_window or not watch.results_written:
            return None
        if watch.last_write is not None and now - watch.last_write >= quiet:
            return "job-done"
        return None

    return done


def target_is_asleep(quiet: float):
    """The target is asleep once it has marked a state and stopped entirely.

    A mark write is not proof by itself: the target writes one at both ends of
    a state. Quiet after an opening mark is, because a suspended host drives
    no clock at all, and the runner's own poll would otherwise touch the card
    every second.
    """

    def done(watch: Watch, fields: dict, now: float) -> str | None:
        if not watch.inside_window or watch.last_write is None:
            return None
        return "asleep" if now - watch.last_write >= quiet else None

    return done


def sector_writes(client, lba: int, payload: bytes) -> None:
    """Write whole sectors into DDR one at a time; the card must be disarmed."""
    if len(payload) % SECTOR_SIZE:
        raise ValueError("payload must be a whole number of sectors")
    for index in range(len(payload) // SECTOR_SIZE):
        client.command(
            images.Opcode.WRITE, lba + index, 1,
            payload[index * SECTOR_SIZE : (index + 1) * SECTOR_SIZE],
        )


def submit(client, debug_start: int, script: str, name: str) -> dict:
    """Put one job on the card, and take the previous result off it.

    The result region is cleared in the same disarmed window as the job is
    written. A run that ended early or a target that never started would
    otherwise leave the previous result there, and the next run would read it
    back and report the wrong experiment as a success.
    """
    previous = fetch(client, debug_start)
    sequence = next_sequence(previous)
    client.command(images.Opcode.WRITE, debug_start + RESULT_SECTOR, 1,
                   bytes(SECTOR_SIZE))
    sector_writes(client, debug_start + JOB_SECTOR,
                  encode_job(sequence, script, name))
    return {"sequence": sequence, "previous": previous}


def fetch(client, debug_start: int) -> dict | None:
    """Read the result region back; the card must be disarmed."""
    return decode_result(
        client.download(RESULT_SECTORS, debug_start + RESULT_SECTOR)
    )


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
    status = psu_status(cli, checked_channel(channel))
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
                     labels: list[str] | None = None) -> list[dict]:
    """Attach a current summary to every state the target marked off."""
    windows = []
    for index, window in enumerate(watch.windows):
        label = (labels[index] if labels and index < len(labels)
                 else f"window-{index + 1}")
        summary = (summarize(sampler.samples, window["start"], window["end"])
                   if sampler else {"n": 0})
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
    if not power_off_confirmed(arguments.psu_cli, channel):
        raise RuntimeError(f"{channel} never confirmed its output off")
    if client.trace()["armed"]:
        client.command(images.Opcode.DISARM)
    submitted = submit(client, arguments.debug_start, script, arguments.name)
    client.command(images.Opcode.ARM)
    time.sleep(arguments.settle)

    zero = time.monotonic()
    sampler = PsuSampler(arguments.psu_cli, channel, zero)
    sampler.start()
    watch = Watch()
    reason = "aborted"
    try:
        launch = power(arguments.psu_cli, channel, "on", wait=False)
        reason = watch_trace(
            client, watch, zero, arguments.run_seconds, arguments.interval,
            arguments.debug_start, done=job_is_done(arguments.quiet),
        )
        launch.wait(timeout=180)
    finally:
        finished = time.monotonic() - zero
        powered_off = power_off_confirmed(arguments.psu_cli, channel)
        sampler.stop()
        time.sleep(2)
        client.command(images.Opcode.DISARM)
    if not powered_off:
        print(f"WARNING: {channel} never confirmed its output off")
    result = fetch(client, arguments.debug_start)
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


def run_resident(arguments, client, script: str) -> dict:
    """Exchange a job for a result through the window where the target sleeps.

    The target must already be up and running a job that ends in a timed
    sleep. While it sleeps it issues no card commands at all, so the frontend
    can be disarmed, the result it flushed before suspending read, the next
    job written and the frontend re-armed, all before the RTC alarm fires.
    Whether Linux forgives the card for having been away is exactly what this
    is for; the answer is in the next result's card check.
    """
    channel = checked_channel(arguments.channel)
    status = require_online(arguments.psu_cli, channel)
    if output_is_off(status):
        raise RuntimeError(
            f"{channel} is off; a resident job needs a target already running "
            "the job runner"
        )
    zero = time.monotonic()
    sampler = PsuSampler(arguments.psu_cli, channel, zero)
    sampler.start()
    watch = Watch()
    exchange: dict = {}
    try:
        reason = watch_trace(
            client, watch, zero, arguments.wait_seconds, arguments.interval,
            arguments.debug_start, done=target_is_asleep(arguments.quiet),
        )
        if reason != "asleep":
            raise RuntimeError(
                "the target never marked a sleep; a resident job needs the "
                "previous job to end in rtc_sleep"
            )
        asleep_at = watch.marks[-1]["elapsed"]
        while time.monotonic() - zero < asleep_at + arguments.dwell:
            time.sleep(0.2)
        began = time.monotonic()
        client.command(images.Opcode.DISARM)
        submitted = submit(client, arguments.debug_start, script, arguments.name)
        client.command(images.Opcode.ARM)
        exchange = {
            "asleep_at": asleep_at,
            "disarmed_at": round(began - zero, 2),
            "rearmed_at": round(time.monotonic() - zero, 2),
            "exchange_seconds": round(time.monotonic() - began, 2),
            "sequence": submitted["sequence"],
            "result_read": submitted["previous"],
        }
        watch_trace(
            client, watch, zero, arguments.wait_seconds, arguments.interval,
            arguments.debug_start, done=job_is_done(arguments.quiet),
        )
    finally:
        sampler.stop()
    return {
        "mode": "resident",
        "exchange": exchange,
        "watch": watch,
        "sampler": sampler,
        "result": exchange.get("result_read"),
        "boot": None,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="images.py session file")
    parser.add_argument("--script", type=Path, help="Shell script to run on the target")
    parser.add_argument("--name", default="job", help="Name carried in the record")
    parser.add_argument(
        "--mode", choices=("reboot", "resident", "fetch"), default="reboot",
        help="reboot: power the target up for this job and down after. "
        "resident: exchange through a running target's sleep window. "
        "fetch: read the last result off a disarmed card and print it",
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
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument(
        "--settle", type=float, default=6.0,
        help="Seconds to hold the target off before powering it on",
    )
    parser.add_argument("--debug-start", type=int, default=DEFAULT_DEBUG_START)
    parser.add_argument("--label", action="append", default=[],
                        help="Name for each marked window, in order")
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
        if arguments.psu_cli is None:
            parser.error("--psu-cli or $MDP_CLI is required to power the target")

    client = images.Images(state=arguments.state)
    try:
        if arguments.mode == "fetch":
            result = fetch(client, arguments.debug_start)
            job = decode_job(
                client.download(2, arguments.debug_start + JOB_SECTOR)
            )
            print(json.dumps({"job": job, "result": result}, indent=2))
            return
        script = arguments.script.read_text()
        runner = run_reboot if arguments.mode == "reboot" else run_resident
        run = runner(arguments, client, script)
    finally:
        client.close()

    watch: Watch = run.pop("watch")
    sampler: PsuSampler = run.pop("sampler")
    windows = measured_windows(watch, sampler, arguments.label)
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
            f"direct={result.get('direct')} truncated={result.get('truncated')}"
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

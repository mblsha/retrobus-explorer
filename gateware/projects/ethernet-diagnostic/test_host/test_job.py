import threading
import time
import unittest

from rg35xx import job
from rg35xx.debug_partition import CARD_CHECK_SECTOR
from rg35xx.debug_partition import JOB_LBA
from rg35xx.debug_partition import JOB_SECTORS
from rg35xx.debug_partition import PAGE_SECTORS
from rg35xx.debug_partition import JOB_SECTORS
from rg35xx.debug_partition import RESULT_SECTOR
from rg35xx.debug_partition import RESULT_SECTORS
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import SLEEP_MARK_SECTOR
from rg35xx.debug_partition import decode_job
from rg35xx.debug_partition import encode_result
from scripts import images

DEBUG_START = 114688

ONLINE = """psu2 (P906) channel 1:
  Online: YES
  Voltage: 5.001 V (target 5.000 V)
  Current: 0.183 A (target 1.200 A)
  Temperature: 29.0 °C
  Output: ON
  Mode: CV
"""
OFFLINE = ONLINE.replace("Online: YES", "Online: NO").replace(
    "Current: 0.183 A", "Current: 0.000 A"
)


def samples(readings):
    """Build a sampler's record from (elapsed, amps) pairs; None means offline."""
    return [
        job.Sample(elapsed, amps is not None, amps, 5.0 if amps else None)
        for elapsed, amps in readings
    ]


class StatusParsingTests(unittest.TestCase):
    def test_the_current_is_read_from_the_status_report(self):
        self.assertEqual(job.current_amps(ONLINE), 0.183)
        self.assertEqual(job.voltage_volts(ONLINE), 5.001)

    def test_a_report_without_exactly_one_current_is_an_error(self):
        """A status that does not say what the current is is not a zero."""
        with self.assertRaisesRegex(ValueError, "exactly one current"):
            job.current_amps("psu2: nothing to report\n")


class WindowSummaryTests(unittest.TestCase):
    def test_the_first_seconds_of_a_window_are_discarded(self):
        readings = samples([(0.0, 0.5), (1.0, 0.4), (4.0, 0.2), (24.0, 0.2)])
        summary = job.summarize(readings, 0.0, 25.0)
        self.assertEqual(summary["n"], 2)

    def test_a_reading_that_straddles_the_end_of_a_window_is_dropped(self):
        """One reading costs a second or more, and a sample timestamped just
        inside a window can have been taken while the target was waking."""
        readings = samples([(4.0, 0.2), (8.0, 0.2), (12.0, 0.2), (16.0, 0.2),
                            (24.0, 0.9), (27.0, 0.9)])
        summary = job.summarize(readings, 0.0, 25.0)
        self.assertEqual(summary["n"], 4)
        self.assertEqual(summary["max_a"], 0.2)
        self.assertEqual(summary["median_a"], 0.2)
        self.assertEqual(summary["max_a"], 0.2)

    def test_a_dropout_inside_a_window_makes_it_unsound(self):
        """The supply reports zeroes while its link is down. A zero averaged
        into a current is a wrong answer rather than a missing one."""
        readings = samples(
            [(4.0, 0.2), (8.0, None), (12.0, 0.2), (16.0, 0.2), (24.0, 0.2)]
        )
        summary = job.summarize(readings, 0.0, 25.0)
        self.assertFalse(summary["sound"])
        self.assertEqual(summary["offline_samples"], 1)
        self.assertEqual(summary["n"], 4)
        self.assertEqual(summary["median_a"], 0.2)

    def test_a_window_shorter_than_the_rule_is_unsound(self):
        readings = samples([(4.0, 0.2), (6.0, 0.2), (8.0, 0.2), (9.0, 0.2)])
        self.assertFalse(job.summarize(readings, 0.0, 10.0)["sound"])
        self.assertTrue(job.summarize(readings + samples([(21.0, 0.2)]),
                                      0.0, 22.0)["sound"])

    def test_the_spread_is_reported_as_an_interquartile_range(self):
        readings = samples([(4.0, 0.10), (8.0, 0.20), (12.0, 0.30), (16.0, 0.40)])
        summary = job.summarize(readings, 0.0, 25.0)
        self.assertEqual(summary["p25_a"], 0.175)
        self.assertEqual(summary["p75_a"], 0.325)
        self.assertEqual(summary["iqr_a"], 0.15)

    def test_an_empty_window_reports_no_samples_rather_than_a_number(self):
        summary = job.summarize([], 0.0, 25.0)
        self.assertEqual(summary["n"], 0)
        self.assertNotIn("median_a", summary)
        self.assertFalse(summary["sound"])


class SamplerTests(unittest.TestCase):
    def test_an_offline_reading_is_kept_but_carries_no_current(self):
        """The reading is kept because a window has to be able to say that it
        contains a dropout; the number is dropped because it is not one."""
        sampler = job.PsuSampler("cli", "psu2", zero=0.0,
                                 status=lambda cli, channel: OFFLINE)
        sample = sampler.take()
        self.assertFalse(sample.online)
        self.assertIsNone(sample.amps)
        self.assertEqual(sample.note, "supply offline")

    def test_a_failing_status_command_is_a_sample_and_not_an_exception(self):
        def explode(cli, channel):
            raise RuntimeError("psu2 status failed: no reply")

        sampler = job.PsuSampler("cli", "psu2", zero=0.0, status=explode)
        self.assertFalse(sampler.take().online)
        self.assertIn("no reply", sampler.samples[0].note)

    def test_the_forbidden_channel_is_refused_before_anything_is_read(self):
        with self.assertRaisesRegex(ValueError, "another device"):
            job.PsuSampler("cli", "psu1")

    def test_a_reading_waits_while_the_port_is_being_used_to_switch_power(self):
        """The CLI opens the one serial port the supply modules are behind, and
        two of them open at once is not an error: the bytes interleave and a
        command is lost. That is how a power-off went missing on 2026-09-19 and
        left the target running after the run had reported itself done."""
        sampler = job.PsuSampler("cli", "psu2", zero=0.0,
                                 status=lambda cli, channel: ONLINE)
        with job.CLI_LOCK:
            reading = threading.Thread(target=sampler.take)
            reading.start()
            reading.join(timeout=0.3)
            self.assertTrue(reading.is_alive(), "sampler ignored the port lock")
        reading.join(timeout=10)
        self.assertFalse(reading.is_alive())
        self.assertEqual(sampler.samples[0].amps, 0.183)


class FakeClient:
    """A card that remembers the sectors written to it and replays a trace."""

    def __init__(self, traces=()):
        self.sectors: dict[int, bytes] = {}
        self.traces = list(traces)
        self.commands: list[str] = []
        self.initial_upload: dict | None = None
        self.verified = False
        self.corrupt: int | None = None

    def begin(self, blocks):
        self.commands.append("BEGIN")
        self.initial_upload = {"sectors": blocks, "verified": False}

    def save(self):
        self.verified = bool((self.initial_upload or {}).get("verified"))

    def command(self, opcode, lba=0, count=0, data=b""):
        self.commands.append(opcode.name)
        if opcode == images.Opcode.WRITE:
            self.sectors[lba] = data
        if opcode == images.Opcode.READ:
            return self.sectors.get(lba, bytes(SECTOR_SIZE))
        return b""

    def bulk_download(self, blocks, start=0, window=0):
        data = bytearray(self.download(blocks, start))
        if self.corrupt is not None:
            data[self.corrupt * SECTOR_SIZE] ^= 0xFF
        return bytes(data)

    def download(self, blocks, start=0):
        return b"".join(
            self.sectors.get(lba, bytes(SECTOR_SIZE))
            for lba in range(start, start + blocks)
        )

    def trace(self):
        return self.traces.pop(0) if self.traces else self.traces


def trace(writes=0, valid=0, reads=0, read_lba=0, command=0, frames=0, edges=0):
    return {
        "command_frames": frames,
        "valid_commands": valid,
        "invalid_frames": 0,
        "writes": writes,
        "read_requests": reads,
        "last_read_lba": read_lba,
        "clock_edges": edges,
        "last_command": command,
        "last_argument": 0,
        "protocol_status": {"card_state": 4},
    }


class ExchangeTests(unittest.TestCase):
    """A job is delivered by replaying the deployed image's first sectors with
    the job substituted, because the gateware takes writes only as one
    ascending run from sector zero."""

    def image(self):
        return bytes(range(256)) * 2 * job.prefix_sectors()

    def carrying(self, client, result):
        region = encode_result(result, result.pop("output", ""))
        for index in range(0, len(region), SECTOR_SIZE):
            client.sectors[DEBUG_START + RESULT_SECTOR + index // SECTOR_SIZE] = (
                region[index : index + SECTOR_SIZE]
            )

    def test_a_job_is_written_into_a_replay_of_the_images_first_sectors(self):
        client = FakeClient()
        image = self.image()
        self.carrying(client, {"sequence": "4", "status": "done",
                               "output": "earlier"})
        submitted = job.submit(client, image, "echo hi\n", "phase0",
                               job.fetch(client, DEBUG_START))
        self.assertEqual(submitted["sequence"], 5)
        written = client.download(job.prefix_sectors(), 0)
        self.assertEqual(len(written), job.prefix_sectors() * SECTOR_SIZE)
        self.assertEqual(written[: JOB_LBA * SECTOR_SIZE],
                         image[: JOB_LBA * SECTOR_SIZE])
        self.assertEqual(
            decode_job(written[JOB_LBA * SECTOR_SIZE :])["script"], "echo hi\n"
        )
        self.assertEqual(client.commands.count("BEGIN"), 1)

    def test_the_card_is_armed_only_after_the_readback_matches(self):
        """The client's own guard refuses ARM until an upload is verified, and
        what is verified here is the prefix, because the whole image is no
        longer what was just written."""
        client = FakeClient()
        client.corrupt = JOB_LBA + 1
        with self.assertRaisesRegex(RuntimeError, "readback differs"):
            job.submit(client, self.image(), "echo hi\n", "phase0")
        self.assertFalse(client.verified)

    def test_a_result_left_by_an_earlier_job_is_not_this_jobs_result(self):
        """The region cannot be cleared before a run any more: clearing it
        would cost the same three minutes as putting the job there."""
        client = FakeClient()
        self.carrying(client, {"sequence": "4", "status": "done",
                               "output": "earlier"})
        self.assertIsNone(job.current_result(client, DEBUG_START, 5))
        self.assertEqual(
            job.current_result(client, DEBUG_START, 4)["output"], "earlier"
        )

    def test_a_card_with_no_result_numbers_the_first_job_one(self):
        self.assertEqual(job.next_sequence(None), 1)
        self.assertEqual(job.next_sequence({}), 1)
        self.assertEqual(job.next_sequence({"sequence": "nonsense"}), 1)


class WatchTests(unittest.TestCase):
    """What the host knows about a live target is the trace and nothing else,
    and in the trace only a read carries a sector number."""

    def follow(self, traces, done=None):
        """Replay a series of trace readings, one per poll, and stop at its end.

        The watcher is otherwise bounded by wall-clock time, which a test
        cannot wait for, so running out of readings ends the wait here.
        """
        client = FakeClient(traces)
        watch = job.Watch()

        def stop(watching, fields, now):
            reason = done(watching, fields, now) if done else None
            return reason or ("exhausted" if not client.traces else None)

        reason = job.watch_trace(
            client, watch, zero=time.monotonic(), seconds=60.0, interval=0.0,
            debug_start=DEBUG_START, done=stop,
        )
        return watch, reason

    def marked(self, reads, page_after=True):
        """A mark, reported at either of the two LBAs a read can come back as."""
        lba = DEBUG_START + SLEEP_MARK_SECTOR + (PAGE_SECTORS if page_after else 0)
        return trace(reads=reads, read_lba=lba)

    def polled(self, reads):
        return trace(reads=reads, read_lba=JOB_LBA + PAGE_SECTORS)

    def test_a_mark_counts_at_either_lba_a_read_is_reported_as(self):
        for page_after in (False, True):
            watch, _ = self.follow([trace(), self.marked(1, page_after=page_after)])
            self.assertEqual(len(watch.marks), 1)
            self.assertTrue(watch.inside_window)

    def test_a_card_check_is_not_mistaken_for_a_mark(self):
        """It is the read a job does on waking, a page below the mark, and
        counting it would open a window that never closes."""
        check = DEBUG_START + CARD_CHECK_SECTOR
        watch, _ = self.follow(
            [trace(), trace(reads=1, read_lba=check),
             trace(reads=2, read_lba=check + PAGE_SECTORS)]
        )
        self.assertEqual(watch.marks, [])

    def test_a_read_of_the_mark_sector_opens_and_closes_a_window(self):
        watch, _ = self.follow([trace(), self.marked(1)])
        self.assertTrue(watch.inside_window)
        # The state has lasted a minute by the time the target marks again.
        watch.marks[-1]["elapsed"] = -60.0
        client = FakeClient([self.marked(1), self.marked(2), self.marked(2)])

        def stop(watching, fields, now):
            return "exhausted" if not client.traces else None

        job.watch_trace(client, watch, zero=time.monotonic(), seconds=60.0,
                        interval=0.0, debug_start=DEBUG_START, done=stop)
        self.assertEqual(len(watch.marks), 2)
        self.assertFalse(watch.inside_window)
        self.assertEqual(len(watch.windows), 1)

    def test_a_second_sight_of_the_opening_mark_does_not_close_the_window(self):
        """The read that carries the mark can still be counting when the next
        poll lands. Taken for the closing mark, it turned a 45 s sleep into a
        window of 0.23 s with no readings in it."""
        watch, _ = self.follow(
            [trace(), self.marked(1), self.marked(2), self.marked(3, page_after=False)]
        )
        self.assertEqual(len(watch.marks), 1)
        self.assertTrue(watch.inside_window)
        self.assertEqual(watch.windows, [])

    def test_the_first_sign_of_life_ends_a_state_even_if_the_mark_is_missed(self):
        """On waking the runner marks, checks the card and writes a result
        inside a third of a second, and a poll that lands after all of that
        sees only the last of them. The window has to end anyway."""
        watch = job.Watch(marks=[{"elapsed": -60.0, "opening": True}])
        client = FakeClient([trace(), trace(reads=1, writes=1, read_lba=99)])

        def stop(watching, fields, now):
            return "exhausted" if not client.traces else None

        job.watch_trace(client, watch, zero=time.monotonic(), seconds=60.0,
                        interval=0.0, debug_start=DEBUG_START, done=stop)
        self.assertEqual(len(watch.windows), 1)
        self.assertFalse(watch.inside_window)

    def test_the_kernels_own_sync_does_not_end_the_state_it_is_entering(self):
        """Going into a suspend the kernel syncs filesystems, and that write
        lands a fraction of a second after the target's mark. Read as the end
        of the state, it costs the whole sleep window."""
        watch, _ = self.follow(
            [trace(), self.marked(1), trace(reads=1, writes=1, read_lba=99)]
        )
        self.assertEqual(watch.windows, [])
        self.assertTrue(watch.inside_window)

    def test_two_polls_mean_the_runner_has_nothing_left_to_run(self):
        """A job is on the card before the boot that finds it, so the first
        poll takes it up and steady polling only resumes once it is over."""
        watch, reason = self.follow(
            [trace(), self.polled(1),
             trace(reads=2, read_lba=JOB_LBA + JOB_SECTORS),
             self.polled(3), self.polled(4)],
            done=job.job_is_done(quiet=30.0),
        )
        self.assertEqual(reason, "job-done")
        self.assertIsNotNone(watch.job_started)
        self.assertIsNotNone(watch.job_finished)

    def test_a_warm_reset_the_caller_expected_is_not_the_job_finishing(self):
        """A short sleep with the debug watchdog armed resets the board when it
        hangs, and the runner polls once more on the way back up. Read as the
        epitaph, that poll costs the evidence: the failure's markers are in RTC
        registers, the next pass of the job is what prints them, and a target
        whose power has been cut has none left to read."""
        watch, reason = self.follow(
            [trace(), self.polled(1),
             trace(reads=2, read_lba=JOB_LBA + JOB_SECTORS),
             self.polled(3)],
            done=job.job_is_done(quiet=30.0, reboots=1),
        )
        self.assertEqual(reason, "exhausted")
        self.assertEqual(watch.polls, 2)

    def test_the_epitaph_moves_by_one_poll_for_each_expected_reset(self):
        watch, reason = self.follow(
            [trace(), self.polled(1),
             trace(reads=2, read_lba=JOB_LBA + JOB_SECTORS),
             self.polled(3), self.polled(4)],
            done=job.job_is_done(quiet=30.0, reboots=1),
        )
        self.assertEqual(reason, "job-done")
        self.assertEqual(watch.polls, 3)

    def test_expecting_no_reset_is_what_every_earlier_run_was_watched_with(self):
        for reboots in (0, -1):
            watch, reason = self.follow(
                [trace(), self.polled(1),
                 trace(reads=2, read_lba=JOB_LBA + JOB_SECTORS),
                 self.polled(3), self.polled(4)],
                done=job.job_is_done(quiet=30.0, reboots=reboots),
            )
            self.assertEqual(reason, "job-done")
            self.assertEqual(watch.polls, 2, reboots)

    def test_one_poll_is_the_runner_taking_the_job_up(self):
        watch, reason = self.follow(
            [trace(), self.polled(1)], done=job.job_is_done(quiet=30.0)
        )
        self.assertEqual(reason, "exhausted")

    def test_a_suspended_target_is_not_a_finished_job(self):
        """Quiet is exactly what a sleeping target looks like, and cutting its
        power for being quiet is the mistake this exists to prevent."""
        watch, reason = self.follow(
            [trace(), self.polled(1), self.marked(2)] + [self.marked(2)] * 6,
            done=job.job_is_done(quiet=0.0),
        )
        self.assertEqual(reason, "exhausted")
        self.assertTrue(watch.inside_window)
        self.assertIsNone(watch.job_finished)
        self.assertEqual(watch.polls, 1)

    def test_a_sleep_is_an_opening_mark_followed_by_silence(self):
        watch, reason = self.follow(
            [trace(), self.marked(1), self.marked(1)],
            done=job.target_is_asleep(quiet=0.0),
        )
        self.assertEqual(reason, "asleep")
        self.assertLess(watch.marks[0]["elapsed"], 1.0)

    def test_the_first_valid_command_is_when_the_target_first_spoke(self):
        watch, _ = self.follow([trace(), trace(valid=1), trace(valid=9)])
        self.assertIsNotNone(watch.first_command)


class ReportTests(unittest.TestCase):
    def test_the_one_line_summary_names_the_state_and_the_current(self):
        watch = job.Watch(windows=[{"start": 10.0, "end": 45.0}])
        sampler = job.PsuSampler("cli", "psu2", zero=0.0, status=lambda c, n: ONLINE)
        sampler.samples = samples(
            [(14.0, 0.021), (20.0, 0.022), (30.0, 0.020), (44.0, 0.021)]
        )
        windows = job.measured_windows(watch, sampler, ["asleep"])
        line = job.one_line("sleep-proof", {"status": "done", "exit": 0}, windows)
        self.assertIn("done exit=0", line)
        self.assertIn("asleep 21 mA", line)
        self.assertNotIn("UNSOUND", line)

    def test_a_run_with_no_result_says_so_rather_than_printing_nothing(self):
        self.assertIn("NO RESULT", job.one_line("x", None, []))


class WindowLabellingTests(unittest.TestCase):
    """Six sleeps and six labels, but the md5 check between them opens windows
    of its own, so without a dwell rule the labels slide onto the wrong arms."""

    SLEEPS_AND_GAPS = [
        {"start": 10.0, "end": 51.0},    # a sleep
        {"start": 52.0, "end": 61.7},    # the probe's md5, awake
        {"start": 62.0, "end": 103.0},   # a sleep
    ]

    def windows(self, **extra):
        watch = job.Watch(windows=list(self.SLEEPS_AND_GAPS))
        return job.measured_windows(watch, None, ["A1", "B1"], **extra)

    def test_without_a_rule_the_gap_takes_a_label(self):
        self.assertEqual([w["label"] for w in self.windows()],
                         ["A1", "B1", "window-3"])

    def test_a_short_window_keeps_its_place_but_not_its_label(self):
        labelled = self.windows(min_seconds=30.0)
        self.assertEqual([w["label"] for w in labelled],
                         ["A1", "short-1", "B1"])
        self.assertEqual([w["start"] for w in labelled],
                         [w["start"] for w in self.SLEEPS_AND_GAPS])

    def test_more_windows_than_labels_still_get_names(self):
        watch = job.Watch(windows=[{"start": 0.0, "end": 40.0},
                                   {"start": 41.0, "end": 81.0}])
        self.assertEqual(
            [w["label"] for w in job.measured_windows(watch, None, ["only"], 30.0)],
            ["only", "window-2"],
        )

    def test_the_default_is_what_every_earlier_run_was_read_with(self):
        watch = job.Watch(windows=list(self.SLEEPS_AND_GAPS))
        self.assertEqual(job.measured_windows(watch, None, ["A1", "B1"]),
                         job.measured_windows(watch, None, ["A1", "B1"], 0.0))


if __name__ == "__main__":
    unittest.main()

import time
import unittest

from rg35xx import job
from rg35xx.debug_partition import JOB_SECTOR
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


class FakeClient:
    """A card that remembers the sectors written to it and replays a trace."""

    def __init__(self, traces=()):
        self.sectors: dict[int, bytes] = {}
        self.traces = list(traces)
        self.commands: list[str] = []

    def command(self, opcode, lba=0, count=0, data=b""):
        self.commands.append(opcode.name)
        if opcode == images.Opcode.WRITE:
            self.sectors[lba] = data
        if opcode == images.Opcode.READ:
            return self.sectors.get(lba, bytes(SECTOR_SIZE))
        return b""

    def download(self, blocks, start=0):
        return b"".join(
            self.sectors.get(lba, bytes(SECTOR_SIZE))
            for lba in range(start, start + blocks)
        )

    def trace(self):
        return self.traces.pop(0) if self.traces else self.traces


def trace(writes=0, valid=0, argument=0, command=0, frames=0, reads=0, edges=0):
    return {
        "command_frames": frames,
        "valid_commands": valid,
        "invalid_frames": 0,
        "writes": writes,
        "read_requests": reads,
        "clock_edges": edges,
        "last_command": command,
        "last_argument": argument,
        "protocol_status": {"card_state": 4},
    }


class ExchangeTests(unittest.TestCase):
    def test_submitting_a_job_numbers_it_past_the_result_on_the_card(self):
        client = FakeClient()
        region = encode_result({"sequence": "4", "status": "done"}, "earlier")
        for index in range(0, len(region), SECTOR_SIZE):
            client.sectors[DEBUG_START + RESULT_SECTOR + index // SECTOR_SIZE] = (
                region[index : index + SECTOR_SIZE]
            )
        submitted = job.submit(client, DEBUG_START, "echo hi\n", "phase0")
        self.assertEqual(submitted["sequence"], 5)
        self.assertEqual(submitted["previous"]["output"], "earlier")
        written = b"".join(
            client.sectors[DEBUG_START + JOB_SECTOR + index] for index in range(2)
        )
        self.assertEqual(decode_job(written)["script"], "echo hi\n")

    def test_the_previous_result_is_cleared_when_the_next_job_is_written(self):
        """A target that never started would otherwise leave the last run's
        result in place, and the next run would report it as its own."""
        client = FakeClient()
        region = encode_result({"sequence": "4", "status": "done"}, "earlier")
        client.sectors[DEBUG_START + RESULT_SECTOR] = region[:SECTOR_SIZE]
        job.submit(client, DEBUG_START, "echo hi\n", "phase0")
        self.assertIsNone(job.fetch(client, DEBUG_START))

    def test_a_card_with_no_result_numbers_the_first_job_one(self):
        self.assertEqual(job.next_sequence(None), 1)
        self.assertEqual(job.next_sequence({}), 1)
        self.assertEqual(job.next_sequence({"sequence": "nonsense"}), 1)


class WatchTests(unittest.TestCase):
    """What the host knows about a live target is the trace and nothing else."""

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

    def test_a_write_to_the_mark_sector_opens_and_closes_a_window(self):
        mark = DEBUG_START + SLEEP_MARK_SECTOR
        watch, _ = self.follow(
            [
                trace(),
                trace(writes=1, argument=mark),
                trace(writes=2, argument=DEBUG_START + RESULT_SECTOR),
                trace(writes=3, argument=mark),
                trace(writes=3, argument=mark),
            ]
        )
        self.assertEqual(len(watch.marks), 2)
        self.assertEqual(watch.results_written, 1)
        self.assertFalse(watch.inside_window)
        self.assertEqual(len(watch.windows), 1)

    def test_a_job_is_not_finished_while_the_target_is_inside_a_window(self):
        """Quiet is what a suspended target looks like, and cutting its power
        for being quiet is the one mistake this check exists to prevent."""
        mark = DEBUG_START + SLEEP_MARK_SECTOR
        watch, reason = self.follow(
            [
                trace(writes=1, argument=DEBUG_START + RESULT_SECTOR),
                trace(writes=2, argument=mark),
            ]
            + [trace(writes=2, argument=mark)] * 6,
            done=job.job_is_done(quiet=0.0),
        )
        self.assertEqual(reason, "exhausted")
        self.assertTrue(watch.inside_window)

    def test_a_job_that_wrote_a_result_and_went_quiet_is_finished(self):
        watch, reason = self.follow(
            [
                trace(),
                trace(writes=1, argument=DEBUG_START + RESULT_SECTOR),
                trace(writes=1, argument=DEBUG_START + RESULT_SECTOR),
            ],
            done=job.job_is_done(quiet=0.0),
        )
        self.assertEqual(reason, "job-done")

    def test_a_sleep_is_an_opening_mark_followed_by_silence(self):
        mark = DEBUG_START + SLEEP_MARK_SECTOR
        watch, reason = self.follow(
            [trace(), trace(writes=1, argument=mark), trace(writes=1, argument=mark)],
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


if __name__ == "__main__":
    unittest.main()

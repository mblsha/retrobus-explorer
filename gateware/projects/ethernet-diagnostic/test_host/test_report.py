import json
import tempfile
import unittest
from pathlib import Path

from rg35xx import trial
from rg35xx.report import format_summary
from rg35xx.report import load
from rg35xx.report import summarize
from rg35xx.report import userspace_time
from test_host.test_trial import trace


def row(elapsed, command=18, writes=0):
    """One timeline row, with the fields the metric reads."""
    return {"elapsed": elapsed, "last_command": command, "writes": writes}


def run(rows, sound=True):
    return {"zero_is_sound": sound, "timeline": rows}


class UserspaceTimeTests(unittest.TestCase):
    """Reaching userspace is observed as a write and nothing else, so what
    counts as that write is the whole measurement."""

    def test_a_multiblock_write_is_the_milestone(self):
        """U-Boot writes one sector at a time; the first multi-block write can
        only be Linux, whose every write is at least a page."""
        timeline = [row(0.0), row(1.5, writes=3), row(4.2, command=25, writes=3)]
        self.assertEqual(userspace_time(run(timeline)), 4.2)

    def test_a_write_counter_that_jumped_by_a_page_is_the_milestone(self):
        """The poll can easily miss the command itself; by the time it lands
        the sector counter has already moved by a page, which says the same
        thing."""
        timeline = [row(0.0, writes=3), row(2.0, writes=5), row(5.4, writes=11)]
        self.assertEqual(userspace_time(run(timeline)), 5.4)

    def test_u_boots_own_milestones_are_not_mistaken_for_userspace(self):
        """Three single-sector writes are exactly what the boot script does."""
        timeline = [row(0.0), row(1.0, writes=1), row(2.0, writes=2), row(3.0, writes=3)]
        self.assertIsNone(userspace_time(run(timeline)))

    def test_the_baseline_row_cannot_be_the_milestone(self):
        """The first row sits at or before the zero and carries the counters
        the run started from, so a run whose card was already busy would
        otherwise report a time of zero."""
        timeline = [row(0.0, command=25, writes=40), row(6.0, writes=40)]
        self.assertIsNone(userspace_time(run(timeline)))

    def test_a_run_without_a_sound_zero_is_skipped(self):
        """If no poll saw the card quiet, the run's clock started at an unknown
        point and its total is not comparable with anything."""
        timeline = [row(0.0), row(5.0, command=25)]
        self.assertEqual(userspace_time(run(timeline)), 5.0)
        self.assertIsNone(userspace_time(run(timeline, sound=False)))

    def test_a_run_with_no_timeline_has_no_time(self):
        self.assertIsNone(userspace_time(run([])))

    def test_a_recorded_trial_timeline_is_read_as_it_was_written(self):
        """The rows come from the trial's own collapse, so the metric is tested
        against the shape that is actually recorded."""
        samples = [
            (0.0, trace(frames=1, command=18, writes=2)),
            (2.0, trace(frames=2, command=24, writes=3)),
            (5.5, trace(frames=3, command=25, writes=3)),
        ]
        timeline = trial.transitions(samples)
        self.assertEqual(userspace_time(run(timeline)), 5.5)


class SummaryTests(unittest.TestCase):
    """The spread is the finding: two boots of the same image differ by
    seconds, so a median with no dispersion beside it invites a comparison
    the data does not support."""

    def runs(self, times):
        return [run([row(0.0), row(seconds, command=25)]) for seconds in times]

    def test_the_summary_describes_the_distribution(self):
        summary = summarize(self.runs([5.4, 5.3, 6.7, 5.35, 5.5]))
        self.assertEqual(summary["n"], 5)
        self.assertEqual(summary["runs"], 5)
        self.assertEqual(summary["min"], 5.3)
        self.assertEqual(summary["max"], 6.7)
        self.assertEqual(summary["median"], 5.4)
        self.assertEqual(summary["values"], [5.3, 5.35, 5.4, 5.5, 6.7])
        self.assertGreater(summary["stdev"], 0)
        self.assertGreater(summary["iqr"], 0)
        self.assertLess(summary["iqr"], summary["max"] - summary["min"])

    def test_runs_without_a_milestone_are_counted_but_not_averaged(self):
        """A run that never reached userspace still says something about how
        often this image boots, so the count it was drawn from is kept."""
        summary = summarize(self.runs([5.4, 5.5]) + [run([row(0.0), row(3.0)])])
        self.assertEqual((summary["n"], summary["runs"]), (2, 3))
        self.assertEqual(summary["values"], [5.4, 5.5])

    def test_a_set_with_no_sound_runs_reports_nothing_rather_than_zero(self):
        summary = summarize([run([row(0.0), row(5.0, command=25)], sound=False)])
        self.assertEqual((summary["n"], summary["runs"]), (0, 1))
        self.assertIsNone(summary["median"])
        self.assertEqual(format_summary("nothing", summary), ["nothing".ljust(30) + " no sound runs"])

    def test_a_single_run_has_no_deviation(self):
        summary = summarize(self.runs([5.4]))
        self.assertEqual(summary["median"], 5.4)
        self.assertIsNone(summary["stdev"])
        self.assertIn("median  5.40", format_summary("one", summary)[0])

    def test_the_line_carries_the_spread_and_the_values(self):
        lines = format_summary("erofs", summarize(self.runs([5.4, 5.3, 6.7, 5.35])))
        self.assertIn("n= 4/4 ", lines[0])
        self.assertIn("stdev", lines[0])
        self.assertIn("IQR", lines[0])
        self.assertIn("[5.3, 5.35, 5.4, 6.7]", lines[1])


class LoadTests(unittest.TestCase):
    def test_trials_are_read_in_a_stable_order(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, seconds in enumerate((5.4, 6.1), start=1):
                Path(directory, f"t-{index}.json").write_text(
                    json.dumps(run([row(0.0), row(seconds, command=25)]))
                )
            runs = load(f"{directory}/t-*.json")
        self.assertEqual([userspace_time(entry) for entry in runs], [5.4, 6.1])

    def test_a_trial_from_before_the_current_format_is_refused(self):
        """Those runs recorded a timeline alone, with nothing to say whether
        the zero was sound, so a number taken from one is not this figure."""
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "old.json").write_text(json.dumps([row(0.0)]))
            with self.assertRaisesRegex(ValueError, "predates the trial format"):
                load(f"{directory}/old.json")


if __name__ == "__main__":
    unittest.main()

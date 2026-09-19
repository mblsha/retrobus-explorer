import unittest

from rg35xx import trial


def trace(frames=0, command=0, argument=0, reads=0, lba=0, writes=0, multiblock=(),
          clock_edges=0):
    return {
        "command_frames": frames,
        "valid_commands": frames,
        "invalid_frames": 0,
        "last_command": command,
        "last_argument": argument,
        "read_requests": reads,
        "last_read_lba": lba,
        "writes": writes,
        "clock_edges": clock_edges,
        "recent_multiblock_reads": [
            {"lba": entry[0], "blocks": entry[1]} for entry in multiblock
        ],
        "protocol_status": {
            "card_state": 4,
            "wide_bus": False,
            "idle_data_high": False,
        },
    }


class TrialTimelineTests(unittest.TestCase):
    def test_a_streaming_transfer_is_one_transition(self):
        """Read counters advance on every poll while a transfer streams. Only a
        new command ends the stage, so the stream must not flood the timeline."""
        samples = [
            (0.0, trace(frames=1, command=18, reads=0)),
            (0.1, trace(frames=1, command=18, reads=400)),
            (0.2, trace(frames=1, command=18, reads=900)),
            (0.3, trace(frames=2, command=12, reads=1000)),
        ]
        timeline = trial.transitions(samples)
        self.assertEqual([entry["elapsed"] for entry in timeline], [0.0, 0.3])
        self.assertEqual([entry["last_command"] for entry in timeline], [18, 12])

    def test_sectors_since_measures_the_previous_stage(self):
        samples = [
            (0.0, trace(frames=1, command=18, reads=0)),
            (0.5, trace(frames=2, command=12, reads=1134)),
            (0.9, trace(frames=3, command=17, reads=1140)),
        ]
        timeline = trial.transitions(samples)
        self.assertEqual(
            [entry["sectors_since"] for entry in timeline], [None, 1134, 6]
        )

    def test_a_write_and_a_completed_multiblock_each_mark_a_stage(self):
        samples = [
            (0.0, trace(frames=5, command=18, multiblock=((96, 1134),))),
            (0.1, trace(frames=5, command=18, multiblock=((96, 1134),))),
            (0.2, trace(frames=5, command=18, writes=1, multiblock=((96, 1134),))),
            (0.3, trace(frames=5, command=18, writes=1,
                        multiblock=((96, 1134), (32989, 5)))),
        ]
        timeline = trial.transitions(samples)
        self.assertEqual([entry["elapsed"] for entry in timeline], [0.0, 0.2, 0.3])
        self.assertEqual([entry["writes"] for entry in timeline], [0, 1, 1])

    def test_a_long_stream_still_reports_progress_and_its_end(self):
        """A single transfer can run for tens of seconds without a new command,
        which is the failure worth studying, so the collapse must not hide it."""
        samples = [
            (0.0, trace(frames=1, command=18, reads=0, lba=100)),
            (1.0, trace(frames=1, command=18, reads=5000, lba=5100)),
            (2.0, trace(frames=1, command=18, reads=10000, lba=10100)),
            (3.0, trace(frames=1, command=18, reads=12000, lba=12100)),
        ]
        timeline = trial.transitions(samples, progress=8192)
        self.assertEqual([entry["elapsed"] for entry in timeline], [0.0, 2.0, 3.0])
        self.assertEqual(
            [entry["streaming"] for entry in timeline], [False, True, False]
        )
        # The final sample is always kept, so an unbounded stream still reports
        # the position it reached.
        self.assertEqual(timeline[-1]["read_lba"], 12100)

    def test_progress_rows_can_be_disabled(self):
        samples = [
            (0.0, trace(frames=1, command=18, reads=0)),
            (1.0, trace(frames=1, command=18, reads=100000)),
        ]
        timeline = trial.transitions(samples, progress=0)
        self.assertEqual(len(timeline), 2)  # first and the always-kept last
        self.assertFalse(timeline[-1]["streaming"])

    def test_repeated_identical_commands_are_distinguished_by_frame_count(self):
        """Two reads of the same sector are separate stages, not one."""
        samples = [
            (0.0, trace(frames=1, command=17, argument=0)),
            (0.1, trace(frames=2, command=17, argument=0)),
        ]
        self.assertEqual(len(trial.transitions(samples)), 2)


if __name__ == "__main__":
    unittest.main()


class TrialZeroTests(unittest.TestCase):
    """Where the clock starts decides every figure this bench reports."""

    def test_a_floating_clock_pin_does_not_start_the_clock(self):
        """With the target unpowered the card's clock pin floats and the edge
        counter still advances, measured on this bench at about fifty edges a
        second. Anchoring on it puts the zero at the first poll of every run,
        so each run silently loses however long the power supply took to
        respond and the fastest-looking runs are the ones measured worst."""
        baseline = trace(frames=100, clock_edges=1000)
        samples = [(0.0, baseline)]
        for index in range(1, 6):
            samples.append((index * 0.1, trace(frames=100, clock_edges=1000 + 50 * index)))
        samples.append((0.6, trace(frames=101, clock_edges=1300, reads=12)))
        self.assertEqual(trial.first_command_index(samples, baseline), 6)

    def test_reads_already_under_way_do_not_move_the_zero(self):
        """The host's first command is followed within milliseconds by its
        first read, so a poll that catches the command will usually show reads
        too. That is not evidence of having joined late."""
        baseline = trace(frames=7, reads=500)
        samples = [
            (0.0, baseline),
            (0.1, trace(frames=7, reads=500, clock_edges=50)),
            (0.2, trace(frames=9, reads=830, clock_edges=100)),
        ]
        self.assertEqual(trial.first_command_index(samples, baseline), 2)

    def test_a_target_that_never_starts_has_no_zero(self):
        baseline = trace(frames=4, clock_edges=10)
        samples = [(index * 0.1, trace(frames=4, clock_edges=10 + index)) for index in range(6)]
        self.assertIsNone(trial.first_command_index(samples, baseline))

    def test_the_first_poll_is_not_a_sound_zero(self):
        """If the very first poll already shows a command, no poll saw the card
        quiet, so the run may have been joined after the host had begun and its
        total cannot be trusted."""
        baseline = trace(frames=2)
        samples = [(0.0, baseline), (0.05, trace(frames=3, reads=40))]
        self.assertEqual(trial.first_command_index(samples, baseline), 1)


class InterfaceRateTests(unittest.TestCase):
    """The card rate decides the kernel read, which is half the boot, so it is
    derived from the FPGA's own timestamps rather than from the CSD or from
    anything the host reports."""

    def test_the_rate_follows_from_edges_and_fabric_ticks(self):
        # 1041 edges across a 512-byte block in 11103 ticks of a 64 MHz clock
        # is the measurement this bench has been reporting as 6 MHz.
        rate = trial.interface_rate(
            {
                "data_start": 1000,
                "first_block_end": 1000 + 11103,
                "data_start_edge": 125,
                "first_block_end_edge": 1166,
            },
            64e6,
        )
        self.assertAlmostEqual(rate["card_clock_hz"] / 1e6, 6.00, places=2)
        self.assertAlmostEqual(
            rate["throughput_bytes_per_second"] / 1e6, 2.95, places=2
        )

    def test_the_rate_scales_with_the_fabric_clock_it_is_counted_in(self):
        """The timestamps are counted in the bitstream's SD fabric clock, so a
        build at a different clock must be told, or every rate is wrong by the
        ratio between them."""
        timing = {
            "data_start": 0, "first_block_end": 11103,
            "data_start_edge": 125, "first_block_end_edge": 1166,
        }
        slow = trial.interface_rate(timing, 64e6)["card_clock_hz"]
        fast = trial.interface_rate(timing, 128e6)["card_clock_hz"]
        self.assertAlmostEqual(fast / slow, 2.0, places=6)

    def test_a_capture_that_never_completed_has_no_rate(self):
        self.assertIsNone(trial.interface_rate({}, 64e6))
        self.assertIsNone(
            trial.interface_rate(
                {"data_start": 10, "first_block_end": 10,
                 "data_start_edge": 0, "first_block_end_edge": 5},
                64e6,
            )
        )


class UserspaceReportTests(unittest.TestCase):
    """The number a run prints and the number a later summary prints have to
    be the same number, so the run line is rendered from the shared metric
    rather than read off the timeline by eye."""

    def run_of(self, samples, sound=True):
        return {"zero_is_sound": sound, "timeline": trial.transitions(samples)}

    def test_a_run_that_reached_userspace_says_when(self):
        samples = [
            (0.0, trace(frames=1, command=18, writes=2)),
            (3.0, trace(frames=2, command=24, writes=3)),
            (5.37, trace(frames=3, command=25, writes=3)),
        ]
        self.assertEqual(
            trial.userspace_report(self.run_of(samples)),
            "userspace milestone at 5.37s",
        )

    def test_a_run_that_stopped_in_u_boot_says_so(self):
        samples = [
            (0.0, trace(frames=1, command=18, writes=2)),
            (2.0, trace(frames=2, command=24, writes=3)),
            (9.0, trace(frames=3, command=24, writes=4)),
        ]
        self.assertEqual(
            trial.userspace_report(self.run_of(samples)),
            "no userspace milestone observed",
        )

    def test_a_run_whose_zero_is_unsound_reports_no_milestone(self):
        samples = [
            (0.0, trace(frames=1, command=18, writes=2)),
            (5.0, trace(frames=2, command=25, writes=3)),
        ]
        self.assertEqual(
            trial.userspace_report(self.run_of(samples, sound=False)),
            "no userspace milestone observed",
        )


class SupplyGateTests(unittest.TestCase):
    """A trial that powers nothing reports a target that did not start."""

    def run_main(self, status, *extra):
        from unittest.mock import patch

        with (
            patch.object(trial, "psu_status", return_value=status) as asked,
            patch.object(trial.images, "Images") as client,
            self.assertRaises(SystemExit) as stopped,
        ):
            trial.main(["--state", "/nonexistent", "--psu-cli", "/cli", *extra])
        return asked, client, stopped.exception

    def test_an_offline_supply_stops_the_trial_before_the_card_is_touched(self):
        offline = "psu2 (P906) channel 1:\n  Online: NO\n  Output: OFF\n"
        asked, client, stopped = self.run_main(offline)
        self.assertIn("offline", str(stopped))
        client.assert_not_called()

    def test_the_other_bench_channel_is_refused_before_anything_runs(self):
        """psu1 powers a different machine; until now only deploy refused it."""
        from unittest.mock import patch

        with (
            patch("rg35xx.deploy.subprocess.run") as run,
            patch.object(trial.images, "Images") as client,
            self.assertRaises((SystemExit, ValueError)),
        ):
            trial.main(["--state", "/nonexistent", "--psu-cli", "/cli", "--channel", "psu1"])
        run.assert_not_called()
        client.assert_not_called()

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/rg35xx_trial.py"
SPEC = importlib.util.spec_from_file_location("rg35xx_trial", SCRIPT)
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)


def trace(frames=0, command=0, argument=0, reads=0, lba=0, writes=0, multiblock=()):
    return {
        "command_frames": frames,
        "valid_commands": frames,
        "invalid_frames": 0,
        "last_command": command,
        "last_argument": argument,
        "read_requests": reads,
        "last_read_lba": lba,
        "writes": writes,
        "clock_edges": 0,
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

    def test_repeated_identical_commands_are_distinguished_by_frame_count(self):
        """Two reads of the same sector are separate stages, not one."""
        samples = [
            (0.0, trace(frames=1, command=17, argument=0)),
            (0.1, trace(frames=2, command=17, argument=0)),
        ]
        self.assertEqual(len(trial.transitions(samples)), 2)


if __name__ == "__main__":
    unittest.main()

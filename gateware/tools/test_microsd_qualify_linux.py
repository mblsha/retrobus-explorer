import copy
import unittest
import io
import json
from contextlib import redirect_stderr
from unittest.mock import patch
from types import SimpleNamespace
from microsd_qualify_linux import qualification
from microsd_qualify_linux import validate


class QualificationEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.state = {
            "ios": "clock: 15000000 Hz\nactual clock: 14850000 Hz\nbus width: 2 (4 bits)\n",
            "errors": "# Data CRC Errors: 0\n",
            "dmesg": ["[1.0] baseline"],
        }

    def test_clean_actual_divider(self):
        self.assertEqual(validate(self.state, self.state, 14850000, 4), ([], []))

    def test_recovery_with_cleared_counters(self):
        after = copy.deepcopy(self.state)
        after["dmesg"].append("[2.0] mmc1: new SD card")
        self.assertTrue(validate(self.state, after, 14850000, 4)[0])

    def test_clock_fallback(self):
        after = copy.deepcopy(self.state)
        after["ios"] = after["ios"].replace("14850000", "12000000")
        self.assertTrue(validate(self.state, after, 14850000, 4)[0])

    def test_crc_counter(self):
        after = copy.deepcopy(self.state)
        after["errors"] = "# Data CRC Errors: 1\n"
        self.assertTrue(validate(self.state, after, 14850000, 4)[0])

    def test_filesystem_notices_are_explicitly_allowed(self):
        after = copy.deepcopy(self.state)
        after["dmesg"].extend(
            [
                "[2.0]  mmcblk1: p1",
                "[2.1] FAT-fs (mmcblk1): utf8 is not a recommended IO charset for FAT filesystems, filesystem will be case sensitive!",
            ]
        )
        self.assertTrue(validate(self.state, after, 14850000, 4)[0])
        self.assertFalse(validate(self.state, after, 14850000, 4, True)[0])
        after["dmesg"].append("[2.2] mmc1: new SD card")
        self.assertTrue(validate(self.state, after, 14850000, 4, True)[0])

    def test_disappearing_card_fails_and_preserves_evidence(self):
        output = io.StringIO()
        args = SimpleNamespace(actual_clock_hz=14850000, clock_hz=15000000, bus_width=4)
        with (
            patch(
                "microsd_qualify_linux.snapshot",
                side_effect=[self.state, FileNotFoundError("card removed")],
            ),
            redirect_stderr(output),
        ):
            with self.assertRaises(RuntimeError):
                with qualification(args):
                    pass
        record = json.loads(output.getvalue())
        self.assertFalse(record["qualification_passed"])
        self.assertIn("card removed", record["problems"][0])

    def test_transfer_failure_still_collects_evidence(self):
        output = io.StringIO()
        args = SimpleNamespace(actual_clock_hz=14850000, clock_hz=15000000, bus_width=4)
        with (
            patch(
                "microsd_qualify_linux.snapshot", side_effect=[self.state, self.state]
            ) as capture,
            redirect_stderr(output),
        ):
            with self.assertRaisesRegex(ValueError, "data mismatch"):
                with qualification(args):
                    raise ValueError("data mismatch")
        self.assertEqual(capture.call_count, 2)
        self.assertFalse(json.loads(output.getvalue())["qualification_passed"])

    def test_hidden_recovery_fails_normal_test(self):
        output = io.StringIO()
        after = copy.deepcopy(self.state)
        after["dmesg"].append("[2.0] mmc1: new SD card")
        args = SimpleNamespace(actual_clock_hz=14850000, clock_hz=15000000, bus_width=4)
        with (
            patch("microsd_qualify_linux.snapshot", side_effect=[self.state, after]),
            redirect_stderr(output),
        ):
            with self.assertRaises(RuntimeError):
                with qualification(args):
                    pass
        self.assertIn("external MMC", json.loads(output.getvalue())["problems"][0])

    def test_log_loss(self):
        after = copy.deepcopy(self.state)
        after["dmesg"] = ["[3.0] ring buffer wrapped"]
        self.assertTrue(validate(self.state, after, 14850000, 4)[0])


if __name__ == "__main__":
    unittest.main()

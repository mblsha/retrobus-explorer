import copy
import unittest
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch
from subprocess import CompletedProcess
from microsd_qualify_linux import main
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

    def test_disappearing_card_preserves_test_output_and_fails(self):
        output = io.StringIO()
        with (
            patch(
                "sys.argv",
                [
                    "qualify",
                    "--actual-clock-hz",
                    "14850000",
                    "--bus-width",
                    "4",
                    "--",
                    "test-helper",
                ],
            ),
            patch(
                "microsd_qualify_linux.snapshot",
                side_effect=[self.state, FileNotFoundError("card removed")],
            ),
            patch(
                "microsd_qualify_linux.subprocess.run",
                return_value=CompletedProcess(
                    ["test-helper"], 0, "data checked", "diagnostic"
                ),
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as exit_result:
                main()
        self.assertEqual(exit_result.exception.code, 1)
        record = json.loads(output.getvalue())
        self.assertFalse(record["passed"])
        self.assertEqual(record["stdout"], "data checked")
        self.assertIn("card removed", record["problems"][0])

    def test_log_loss(self):
        after = copy.deepcopy(self.state)
        after["dmesg"] = ["[3.0] ring buffer wrapped"]
        self.assertTrue(validate(self.state, after, 14850000, 4)[0])


if __name__ == "__main__":
    unittest.main()

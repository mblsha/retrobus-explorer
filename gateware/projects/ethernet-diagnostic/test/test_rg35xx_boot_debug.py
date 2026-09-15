import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/rg35xx_boot_debug.py"
SPEC = importlib.util.spec_from_file_location("rg35xx_boot_debug", SCRIPT)
debug = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(debug)


class BootDebugTests(unittest.TestCase):
    def test_command_is_one_host_to_target_sector(self):
        encoded = debug.encode_command("continue")
        self.assertEqual(len(encoded), debug.SECTOR_SIZE)
        self.assertEqual(
            debug.decode_records(encoded),
            [{
                "sector": "0",
                "direction": "host-to-target",
                "command": "continue",
            }],
        )

    def test_decoder_keeps_sector_numbers_and_skips_unmarked_sectors(self):
        record = (
            b"RG35DBG1\ndirection=target-to-host\nmilestone=kernel-entry\n"
        ).ljust(debug.SECTOR_SIZE, b"\0")
        data = bytes(debug.SECTOR_SIZE) + record
        self.assertEqual(
            debug.decode_records(data),
            [{
                "sector": "1",
                "direction": "target-to-host",
                "milestone": "kernel-entry",
            }],
        )

    def test_decoder_rejects_partial_sector(self):
        with self.assertRaisesRegex(ValueError, "whole 512-byte sectors"):
            debug.decode_records(b"partial")

    def test_encoder_rejects_oversize_command(self):
        with self.assertRaisesRegex(ValueError, "does not fit"):
            debug.encode_command("x" * debug.SECTOR_SIZE)


if __name__ == "__main__":
    unittest.main()

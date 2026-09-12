"""Keep build metadata tied to every supported Spade CSD mode."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/openxc7-macos"))
from build_ddr_bios import frontend_csd  # noqa: E402


class FrontendCSDTest(unittest.TestCase):
    def test_current_modes(self):
        source = (ROOT / "projects/microsd-emulator/src/main.spade").read_text()
        for writable, fast, expected in [
            (False, False, 0x260009105903FFC000000002402033),
            (False, True, 0x260009105903FFC000000002402033),
            (True, False, 0x00260012115903FFC0028000024000D5),
            (True, True, 0x0026001A115903FFC002800002400023),
        ]:
            with self.subTest(writable=writable, fast=fast):
                self.assertEqual(frontend_csd(source, writable, fast), expected)

    def test_missing_or_ambiguous_choice_is_rejected(self):
        source = (ROOT / "projects/microsd-emulator/src/main.spade").read_text()
        for invalid in ("", source + source):
            with self.assertRaises(AssertionError):
                frontend_csd(invalid, True, True)

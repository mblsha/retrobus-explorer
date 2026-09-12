"""Build metadata describes the supported card; CMD9 is checked in test_sd.py."""

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "experiments/openxc7-macos")
)
from build_ddr import sd_properties


class CardMetadataTest(unittest.TestCase):
    def test_capacity_and_advertised_clock(self):
        properties = sd_properties()
        self.assertEqual(properties["sd_capacity_bytes"], 256 * 1024 * 1024)
        self.assertEqual(properties["sd_max_clock_hz"], 13_000_000)

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parent / "search_placement_seeds.py"
SPEC = importlib.util.spec_from_file_location("search_placement_seeds", SCRIPT)
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


ESTIMATE_THEN_ROUTED = """
Info: Max frequency for clock 'dclk': 61.00 MHz (FAIL at 80.00 MHz)
Info: Max frequency for clock 'fclk': 59.00 MHz (FAIL at 64.00 MHz)
Info: Routing...
Info: Max frequency for clock 'dclk': 81.57 MHz (PASS at 80.00 MHz)
Info: Max frequency for clock 'fclk': 80.50 MHz (PASS at 64.00 MHz)
"""


class SearchPlacementSeedsTests(unittest.TestCase):
    def test_last_report_per_clock_wins(self):
        """nextpnr prints a pre-routing estimate first; only the final result
        describes the placement, and build_ddr.py reads it the same way."""
        clocks = search.parse_clocks(ESTIMATE_THEN_ROUTED)
        self.assertEqual(clocks["dclk"], (81.57, "PASS", 80.0))
        self.assertEqual(clocks["fclk"], (80.50, "PASS", 64.0))
        self.assertEqual(search.failing_clocks(clocks), [])

    def test_failing_clocks_are_reported_sorted(self):
        clocks = search.parse_clocks(
            "Info: Max frequency for clock 'fclk': 59.00 MHz (FAIL at 64.00 MHz)\n"
            "Info: Max frequency for clock 'dclk': 61.00 MHz (FAIL at 80.00 MHz)\n"
            "Info: Max frequency for clock 'core.clk': 900.00 MHz (PASS at 100.00 MHz)\n"
        )
        self.assertEqual(search.failing_clocks(clocks), ["dclk", "fclk"])

    def test_a_log_without_timing_results_has_no_clocks(self):
        self.assertEqual(search.parse_clocks("ERROR: unable to place"), {})


if __name__ == "__main__":
    unittest.main()

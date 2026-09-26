import importlib.util
import json
import tempfile
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


class EvaluateTests(unittest.TestCase):
    """A seed the search calls usable has to be one build_ddr.py accepts."""

    SEED = 6

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name)
        (self.output / f"route-seed-{self.SEED}.log").write_text(
            "Info: Max frequency for clock 'fclk': 76.92 MHz (PASS at 64.00 MHz)\n"
        )
        self.cells = {}
        lines = ["(TIMESCALE 1ps)"]
        for pin in (0, 1, 2, 3, 7):
            source, target = f"ff{pin}", f"board.pmod[{pin}]$OBUFT"
            self.cells[source] = {
                "type": "SLICE_FFX",
                "parameters": {"IS_CLK_INVERTED": "1"},
                "connections": {"CK": [1], "Q": [100 + pin]},
                "port_directions": {"CK": "input", "Q": "output"},
            }
            self.cells[target] = {
                "type": "IOB33_OUTBUF",
                "connections": {"IN": [100 + pin]},
                "port_directions": {"IN": "input"},
            }
            lines.append(f"(INTERCONNECT {source}/Q {target}/IN (2500) (2500))")
        (self.output / f"routed-seed-{self.SEED}.sdf").write_text("\n".join(lines))

    def evaluate(self, **profile):
        module = {"netnames": {"fclk": {"bits": [1]}}, "cells": self.cells}
        (self.output / f"routed-seed-{self.SEED}.json").write_text(
            json.dumps({"modules": {"board": module}})
        )
        return search.evaluate(self.output, self.SEED, **profile)

    def test_the_fast_profile_rejects_a_rising_edge_data_register(self):
        self.cells["ff3"]["parameters"]["IS_CLK_INVERTED"] = "0"
        result = self.evaluate(slow_mmc=False)
        self.assertFalse(result["usable"])
        self.assertIn("output delay", result["reason"])

    def test_the_fast_profile_accepts_falling_edge_outputs(self):
        result = self.evaluate(slow_mmc=False)
        self.assertTrue(result["usable"])
        self.assertEqual(len(result["outputs_ps"]), 5)

    def test_the_slow_profile_wants_a_rising_edge_command(self):
        self.cells["ff2"]["parameters"]["IS_CLK_INVERTED"] = "0"
        self.assertTrue(self.evaluate(slow_mmc=True)["usable"])


if __name__ == "__main__":
    unittest.main()

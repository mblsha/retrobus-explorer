"""Reject output muxes, wrong clock edges and excessive pad-route delay."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "experiments/openxc7-macos")
)
from ddr_output_timing import (
    profile_output_checks,
    verify_direct_sd_outputs,
    verify_profile_outputs,
)


class SDOutputTimingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.routed = Path(self.temp.name) / "routed.json"
        self.sdf = Path(self.temp.name) / "routed.sdf"
        self.module = {"netnames": {"fclk": {"bits": [1]}}, "cells": {}}
        lines = ["(TIMESCALE 1ps)"]
        for pin in (0, 1, 2, 3, 7):
            source, target = f"ff{pin}", f"board.pmod[{pin}]$OBUFT"
            self.module["cells"][source] = {
                "type": "SLICE_FFX",
                "parameters": {"IS_CLK_INVERTED": "1"},
                "connections": {"CK": [1], "Q": [100 + pin]},
                "port_directions": {"CK": "input", "Q": "output"},
            }
            self.module["cells"][target] = {
                "type": "IOB33_OUTBUF",
                "connections": {"IN": [100 + pin]},
                "port_directions": {"IN": "input"},
            }
            lines.append(
                f"(INTERCONNECT {source}/Q {target}/IN (2500:2500:2500) (2500:2500:2500))"
            )
        self.sdf.write_text("\n".join(lines))

    def check(self):
        self.routed.write_text(json.dumps({"modules": {"board": self.module}}))
        return verify_direct_sd_outputs(self.routed, self.sdf)

    def test_direct_registers_pass(self):
        self.assertEqual(len(self.check()), 5)

    def test_output_mux_fails(self):
        self.module["cells"]["ff0"]["type"] = "SLICE_LUTX"
        with self.assertRaises(RuntimeError):
            self.check()

    def test_positive_edge_fails(self):
        self.module["cells"]["ff0"]["parameters"]["IS_CLK_INVERTED"] = "0"
        with self.assertRaises(RuntimeError):
            self.check()

    def test_slow_profile_requires_registered_positive_edge_command(self):
        self.module["cells"]["ff2"]["parameters"]["IS_CLK_INVERTED"] = "0"
        self.routed.write_text(json.dumps({"modules": {"board": self.module}}))
        self.assertEqual(
            len(
                verify_direct_sd_outputs(
                    self.routed,
                    self.sdf,
                    pins=frozenset({2}),
                    inverted=False,
                )
            ),
            1,
        )

    def test_missing_pin_fails(self):
        del self.module["cells"]["board.pmod[7]$OBUFT"]
        with self.assertRaises(RuntimeError):
            self.check()

    def test_long_route_fails(self):
        self.sdf.write_text(self.sdf.read_text().replace("2500", "4000", 1))
        with self.assertRaises(RuntimeError):
            self.check()

    def test_each_profile_names_its_pins_and_edges(self):
        data = frozenset({0, 1, 3, 7})
        self.assertEqual(
            profile_output_checks(slow_mmc=False),
            [(frozenset({0, 1, 2, 3, 7}), True)],
        )
        self.assertEqual(
            profile_output_checks(slow_mmc=True), [(frozenset({2}), False)]
        )
        for legacy in ({"h700_mmc": True}, {"mmc_only": True}):
            with self.subTest(**legacy):
                self.assertEqual(
                    profile_output_checks(slow_mmc=True, **legacy),
                    [(frozenset({2}), False), (data, True)],
                )

    def test_the_fast_profile_holds_the_data_pins_too(self):
        """A rising-edge DAT register is wrong for the fast profile even when
        CMD is right, so checking CMD alone would pass a placement the build
        rejects."""
        self.module["cells"]["ff3"]["parameters"]["IS_CLK_INVERTED"] = "0"
        self.routed.write_text(json.dumps({"modules": {"board": self.module}}))
        with self.assertRaises(RuntimeError):
            verify_profile_outputs(self.routed, self.sdf, slow_mmc=False)

    def test_the_h700_profile_launches_command_on_the_rising_edge(self):
        self.module["cells"]["ff2"]["parameters"]["IS_CLK_INVERTED"] = "0"
        self.routed.write_text(json.dumps({"modules": {"board": self.module}}))
        paths = verify_profile_outputs(
            self.routed, self.sdf, slow_mmc=True, h700_mmc=True
        )
        self.assertEqual(sorted(p["signal"] for p in paths),
                         ["CMD", "DAT0", "DAT1", "DAT2", "DAT3"])

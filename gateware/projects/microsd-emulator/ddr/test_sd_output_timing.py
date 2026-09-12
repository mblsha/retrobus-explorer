"""Reject output muxes, wrong clock edges and excessive pad-route delay."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "experiments/openxc7-macos")
)
from ddr_output_timing import verify_direct_sd_outputs


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

    def test_missing_pin_fails(self):
        del self.module["cells"]["board.pmod[7]$OBUFT"]
        with self.assertRaises(RuntimeError):
            self.check()

    def test_long_route_fails(self):
        self.sdf.write_text(self.sdf.read_text().replace("2500", "4000", 1))
        with self.assertRaises(RuntimeError):
            self.check()

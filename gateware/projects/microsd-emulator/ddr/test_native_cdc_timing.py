"""The routed CDC guard must fail closed for missing paths and excessive delay."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "experiments/openxc7-macos")
)
from ddr_cdc_timing import verify_native_cdc


class NativeCDCTimingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.routed = Path(self.temp.name) / "routed.json"
        self.sdf = Path(self.temp.name) / "route.sdf"
        self.module = {
            "netnames": {"fclk": {"bits": [1]}, "dclk": {"bits": [2]}},
            "cells": {},
        }
        lines = ["(TIMESCALE 1ps)"]
        for fifo in range(3):
            for group in ("gwsync", "grsync"):
                for lane in range(1):
                    bit = 100 + len(self.module["cells"])
                    name = f"sd_memory_crossing.async_fifo_{fifo}.async_fifo_v_0.{group}[{lane}]"
                    self.module["netnames"][name] = {"bits": [bit]}
                    self.module["cells"][f"src{bit}"] = {
                        "type": "SLICE_FFX",
                        "connections": {"CK": [1], "Q": [bit]},
                    }
                    self.module["cells"][f"dst{bit}"] = {
                        "type": "SLICE_FFX",
                        "connections": {"CK": [2], "D": [bit]},
                    }
                    lines.append(
                        f"(INTERCONNECT src{bit}/Q dst{bit}/D (1000:1000:1000) (1000:1000:1000))"
                    )
        self.sdf.write_text("\n".join(lines))

    def check(self, **options):
        self.routed.write_text(json.dumps({"modules": {"top": self.module}}))
        return verify_native_cdc(self.routed, self.sdf, **options)

    def test_all_paths_are_checked(self):
        self.assertEqual(len(self.check()), 6)

    def test_excessive_pointer_delay_is_rejected(self):
        self.sdf.write_text(
            self.sdf.read_text().replace("1000:1000:1000", "9000:9000:9000", 1)
        )
        with self.assertRaises(RuntimeError):
            self.check()

    def test_missing_pointer_is_rejected(self):
        self.module["netnames"].pop(
            next(n for n in self.module["netnames"] if "gwsync" in n)
        )
        with self.assertRaises(RuntimeError):
            self.check()

    def test_wrong_destination_clock_is_rejected(self):
        self.module["cells"]["dst100"]["connections"]["CK"] = [1]
        with self.assertRaises(RuntimeError):
            self.check()


class EthernetCDCTimingTest(NativeCDCTimingTest):
    def setUp(self):
        super().setUp()
        nets = self.module["netnames"]
        nets.update(eth_rx_global={"bits": [3]}, eth_tx_global={"bits": [4]})
        lines = []
        for entity, width, clock in (("receiver", 4, 3), ("transmitter", 2, 4)):
            for group in ("published", "consumed"):
                for lane in range(width):
                    bit = 200 + len(self.module["cells"])
                    name = (
                        f"sd.network_frontend_0.frame_{entity}_0.{group}_gray[{lane}]"
                    )
                    nets[name] = {"bits": [bit]}
                    source_clock, target_clock = (
                        (1, clock) if group == "consumed" else (clock, 1)
                    )
                    self.module["cells"][f"src{bit}"] = {
                        "type": "SLICE_FFX",
                        "connections": {"CK": [source_clock], "Q": [bit]},
                    }
                    self.module["cells"][f"dst{bit}"] = {
                        "type": "SLICE_FFX",
                        "connections": {"CK": [target_clock], "D": [bit]},
                    }
                    lines.append(
                        f"(INTERCONNECT src{bit}/Q dst{bit}/D (1000:1000:1000) (1000:1000:1000))"
                    )
        self.sdf.write_text(self.sdf.read_text() + "\n" + "\n".join(lines))

    def check(self, **options):
        return super().check(ethernet=True)

    def test_all_paths_are_checked(self):
        self.assertEqual(len(self.check()), 18)

    def test_missing_ethernet_pointer_is_rejected(self):
        self.module["netnames"].pop(
            next(n for n in self.module["netnames"] if "published_gray" in n)
        )
        with self.assertRaisesRegex(RuntimeError, "twelve"):
            self.check()

    def test_excessive_ethernet_delay_is_rejected(self):
        self.sdf.write_text(
            self.sdf.read_text().replace(
                "src212/Q dst212/D (1000:1000:1000)",
                "src212/Q dst212/D (40000:40000:40000)",
            )
        )
        with self.assertRaises(RuntimeError):
            self.check()

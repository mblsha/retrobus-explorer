"""Reject wrong clock ownership, broken synchronizers, and excessive routed delay."""

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
        self.crossings = {}
        self.sdf.write_text("(TIMESCALE 1ps)\n")
        for fifo in range(3):
            write_clock, read_clock = (2, 1) if fifo == 2 else (1, 2)
            for group, source, target in (
                ("gwsync", write_clock, read_clock),
                ("grsync", read_clock, write_clock),
            ):
                self.add_crossing(
                    f"sd_memory_crossing.async_fifo_{fifo}.async_fifo_v_0.{group}[0]",
                    source,
                    target,
                )

    def add_crossing(
        self, name, source, target, source_falling=False, target_falling=False
    ):
        bit = 100 + 3 * len(self.crossings)
        source_name, first, second = f"src{bit}", f"dst{bit}", f"sync{bit}"
        self.module["netnames"][name] = {"bits": [bit]}
        for cell_name, clock, falling, ports in (
            (source_name, source, source_falling, {"Q": [bit]}),
            (first, target, target_falling, {"D": [bit], "Q": [bit + 1]}),
            (second, target, target_falling, {"D": [bit + 1], "Q": [bit + 2]}),
        ):
            self.module["cells"][cell_name] = {
                "type": "SLICE_FFX",
                "parameters": {"IS_CLK_INVERTED": str(int(falling))},
                "connections": {"CK": [clock], **ports},
            }
        self.crossings[name] = (source_name, first, second)
        with self.sdf.open("a") as sdf:
            sdf.write(
                f"(INTERCONNECT {source_name}/Q {first}/D (1000:1000:1000) (1000:1000:1000))\n"
            )

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
        self.module["netnames"].pop(next(iter(self.crossings)))
        with self.assertRaises(RuntimeError):
            self.check()

    def test_wrong_destination_clock_is_rejected(self):
        self.module["cells"]["dst100"]["connections"]["CK"] = [1]
        with self.assertRaises(RuntimeError):
            self.check()

    def test_missing_second_stage_is_rejected(self):
        del self.module["cells"]["sync100"]
        with self.assertRaisesRegex(RuntimeError, "fanout"):
            self.check()

    def test_first_stage_cannot_drive_functional_logic(self):
        self.module["cells"]["unsafe"] = {
            "type": "LUT1",
            "connections": {"I": [101], "O": [999]},
        }
        with self.assertRaisesRegex(RuntimeError, "fanout"):
            self.check()

    def test_second_stage_must_use_same_clock(self):
        self.module["cells"]["sync100"]["connections"]["CK"] = [1]
        with self.assertRaisesRegex(RuntimeError, "second synchronizer"):
            self.check()


class EthernetCDCTimingTest(NativeCDCTimingTest):
    def setUp(self):
        super().setUp()
        self.module["netnames"].update(
            eth_rx_global={"bits": [3]}, eth_tx_global={"bits": [4]}
        )
        # Independent fixture contract: TX producer is fabric, TX consumer is falling edge.
        for queue, pointer, width, source, target, sf, tf in (
            ("receiver", "published", 4, 3, 1, False, False),
            ("receiver", "consumed", 4, 1, 3, False, False),
            ("transmitter", "published", 2, 1, 4, False, True),
            ("transmitter", "consumed", 2, 4, 1, True, False),
        ):
            for lane in range(width):
                self.add_crossing(
                    f"sd.network_frontend_0.frame_{queue}_0.{pointer}_gray[{lane}]",
                    source,
                    target,
                    sf,
                    tf,
                )

    def check(self, **options):
        return super().check(ethernet=True)

    def tx_published(self):
        name = next(n for n in self.crossings if "transmitter_0.published" in n)
        return self.crossings[name]

    def test_all_paths_are_checked(self):
        self.assertEqual(len(self.check()), 18)

    def test_missing_ethernet_pointer_is_rejected(self):
        self.module["netnames"].pop(
            next(n for n in self.crossings if "published_gray" in n)
        )
        with self.assertRaisesRegex(RuntimeError, "pointer bits"):
            self.check()

    def test_excessive_ethernet_delay_is_rejected(self):
        src, dst, _ = self.tx_published()
        self.sdf.write_text(
            self.sdf.read_text().replace(
                f"{src}/Q {dst}/D (1000:1000:1000)",
                f"{src}/Q {dst}/D (40000:40000:40000)",
            )
        )
        with self.assertRaises(RuntimeError):
            self.check()

    def test_reversed_transmitter_domains_are_rejected(self):
        for name, (src, dst, second) in self.crossings.items():
            if "transmitter" not in name:
                continue
            cells = self.module["cells"]
            source_clock = cells[src]["connections"]["CK"]
            target_clock = cells[dst]["connections"]["CK"]
            cells[src]["connections"]["CK"] = target_clock
            cells[dst]["connections"]["CK"] = source_clock
            cells[second]["connections"]["CK"] = source_clock
        with self.assertRaisesRegex(RuntimeError, "clock/edge"):
            self.check()

    def test_other_recognized_clocks_are_rejected(self):
        for position in (0, 1):
            with self.subTest(position=position):
                cell = self.module["cells"][self.tx_published()[position]]
                original = cell["connections"]["CK"]
                cell["connections"]["CK"] = [3]
                with self.assertRaisesRegex(RuntimeError, "clock/edge"):
                    self.check()
                cell["connections"]["CK"] = original

    def test_transmitter_requires_falling_edge(self):
        self.module["cells"][self.tx_published()[1]]["parameters"][
            "IS_CLK_INVERTED"
        ] = "0"
        with self.assertRaisesRegex(RuntimeError, "clock/edge"):
            self.check()

    def test_aggregate_count_cannot_hide_wrong_group_width(self):
        name = next(n for n in self.crossings if "receiver_0.published_gray[3]" in n)
        net = self.module["netnames"].pop(name)
        self.module["netnames"][
            name.replace(
                "receiver_0.published_gray[3]", "transmitter_0.published_gray[2]"
            )
        ] = net
        with self.assertRaisesRegex(RuntimeError, "pointer bits"):
            self.check()

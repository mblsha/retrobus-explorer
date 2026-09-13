from __future__ import annotations

import unittest

from jitx._instantiation import instantiation

from src.main import FT_PINS, ORDERED_PINS, SAFE_BY_PREFIX, SAFE_ORDERED_PINS, AlchitryElementBottom

FT_V1_PINS = {
    "A17",
    "A18",
    "A20",
    "A21",
    "A27",
    "A28",
    "A30",
    "A31",
    "B14",
    "B15",
    "B17",
    "B18",
    "B20",
    "B21",
    "B23",
    "B24",
    "B27",
    "B28",
    "B30",
    "B31",
    "B33",
    "B34",
    "B36",
    "B37",
}


class FtV1ExclusionTests(unittest.TestCase):
    def test_exclusion_set_matches_authoritative_ft_v1_acf(self) -> None:
        self.assertEqual(FT_PINS, FT_V1_PINS)

    def test_safe_pin_lists_exclude_every_ft_pin(self) -> None:
        self.assertEqual(len(ORDERED_PINS), len(set(ORDERED_PINS)))
        self.assertTrue(FT_PINS.issubset(ORDERED_PINS))
        self.assertTrue(FT_PINS.isdisjoint(SAFE_ORDERED_PINS))
        self.assertEqual(SAFE_ORDERED_PINS, [pin for pin in ORDERED_PINS if pin not in FT_PINS])

    def test_safe_pin_counts_match_au1_contract(self) -> None:
        expected_counts = {"A": 24, "B": 16, "C": 32, "D": 6}
        self.assertEqual(len(SAFE_ORDERED_PINS), 78)
        self.assertEqual({prefix: len(pins) for prefix, pins in SAFE_BY_PREFIX.items()}, expected_counts)

    def test_exposed_ports_match_safe_pin_counts(self) -> None:
        with instantiation.activate():
            component = AlchitryElementBottom()
        self.assertEqual(len(component.data), len(SAFE_ORDERED_PINS))
        for prefix, pins in SAFE_BY_PREFIX.items():
            with self.subTest(connector=prefix):
                self.assertEqual(len(getattr(component, f"data_{prefix.lower()}")), len(pins))


if __name__ == "__main__":
    unittest.main()

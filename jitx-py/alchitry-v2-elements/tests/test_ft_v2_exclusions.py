from __future__ import annotations

import inspect
import unittest

from shared_components.alchitry_v2 import FT_PROFILE

from alchitry_v2_elements.components import (
    AlchitryFtV2BothElement,
    AlchitryFtV2BottomElement,
    AlchitryFtV2TopElement,
    AlchitryV2BothElement,
    AlchitryV2BottomElement,
    AlchitryV2TopElement,
)

FT_V2_BANK_A_PINS = {
    3,
    4,
    5,
    6,
    9,
    10,
    11,
    12,
    15,
    16,
    17,
    18,
    21,
    22,
    23,
    24,
    27,
    28,
    29,
    30,
    33,
    34,
    35,
    36,
    39,
    41,
}


class FtV2ExclusionTests(unittest.TestCase):
    def test_profile_matches_authoritative_ft_v2_acf_pin_set(self) -> None:
        self.assertEqual(
            set(FT_PROFILE.connector_profile("A").reserved_signal_pins()),
            FT_V2_BANK_A_PINS,
        )
        self.assertEqual(FT_PROFILE.connector_profile("B").reserved_signal_pins(), ())

    def test_ft_templates_exclude_every_reserved_signal(self) -> None:
        expected = {f"A{pin}" for pin in FT_V2_BANK_A_PINS}
        for component_class in (
            AlchitryFtV2TopElement,
            AlchitryFtV2BottomElement,
            AlchitryFtV2BothElement,
        ):
            with self.subTest(component=component_class.__name__):
                metadata = vars(component_class)
                excluded = metadata["excluded_signal_names"]
                signals = metadata["source_signal_names"]
                self.assertEqual(set(excluded), expected)
                self.assertTrue(expected.isdisjoint(signals))
                self.assertTrue(expected.isdisjoint(metadata))
                self.assertEqual(metadata["profile_name"], "ft")

    def test_generic_templates_remain_unrestricted(self) -> None:
        expected = {f"A{pin}" for pin in FT_V2_BANK_A_PINS}
        for component_class in (
            AlchitryV2TopElement,
            AlchitryV2BottomElement,
            AlchitryV2BothElement,
        ):
            with self.subTest(component=component_class.__name__):
                metadata = vars(component_class)
                excluded = metadata["excluded_signal_names"]
                signals = metadata["source_signal_names"]
                self.assertEqual(excluded, ())
                self.assertTrue(expected.issubset(signals))
                self.assertIsNone(metadata["profile_name"])

    def test_unoccupied_and_bank_b_signals_remain_available(self) -> None:
        for component_class in (
            AlchitryFtV2TopElement,
            AlchitryFtV2BottomElement,
            AlchitryFtV2BothElement,
        ):
            with self.subTest(component=component_class.__name__):
                signals = vars(component_class)["source_signal_names"]
                self.assertIn("A40", signals)
                self.assertIn("A42", signals)
                self.assertIn("B3", signals)
                self.assertIn("A40", vars(component_class))
                self.assertIn("A42", vars(component_class))
                self.assertIn("B3", vars(component_class))

    def test_reference_elements_allow_holes_to_be_replaced(self) -> None:
        include_holes = inspect.signature(AlchitryFtV2BottomElement).parameters["include_holes"]
        self.assertIs(include_holes.default, True)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from shared_components.rpi_pico import (
    PICO_BOARD_LENGTH,
    PICO_BOARD_WIDTH,
    PICO_PIN_COUNT,
    PICO_PIN_PITCH,
    PICO_PINS_PER_ROW,
    PICO_ROW_SPACING,
    pico_physical_pin_index,
)


class PicoFootprintTests(unittest.TestCase):
    def test_standard_pico_geometry(self) -> None:
        self.assertEqual(PICO_PIN_COUNT, 40)
        self.assertEqual(PICO_PINS_PER_ROW, 20)
        self.assertAlmostEqual(PICO_PIN_PITCH, 2.54)
        self.assertAlmostEqual(PICO_ROW_SPACING, 17.78)
        self.assertAlmostEqual(PICO_BOARD_LENGTH, 51.0)
        self.assertAlmostEqual(PICO_BOARD_WIDTH, 21.0)

    def test_physical_pin_validation(self) -> None:
        self.assertEqual(pico_physical_pin_index(1), 0)
        self.assertEqual(pico_physical_pin_index(40), 39)
        with self.assertRaises(ValueError):
            pico_physical_pin_index(0)
        with self.assertRaises(ValueError):
            pico_physical_pin_index(41)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import inspect
import unittest

from shared_components.pmod import (
    PMOD_DATA_PINS,
    PMOD_GROUND_PINS,
    PMOD_INTERFACE_SPEC_URL,
    PMOD_IO_TO_PIN,
    PMOD_PAD_CENTERS,
    PMOD_PIN_NAMES,
    PMOD_PIN_ROLES,
    PMOD_POWER_PINS,
    PMOD_VCC_PINS,
    PmodHeader2x6,
)


class PmodHeaderTests(unittest.TestCase):
    def test_canonical_type_2a_pinout_is_protocol_neutral(self) -> None:
        self.assertEqual(
            PMOD_PIN_NAMES,
            {
                1: "IO1",
                2: "IO2",
                3: "IO3",
                4: "IO4",
                5: "GND",
                6: "VCC",
                7: "IO5",
                8: "IO6",
                9: "IO7",
                10: "IO8",
                11: "GND",
                12: "VCC",
            },
        )
        self.assertEqual(PMOD_DATA_PINS, (1, 2, 3, 4, 7, 8, 9, 10))
        self.assertEqual(PMOD_GROUND_PINS, (5, 11))
        self.assertEqual(PMOD_VCC_PINS, (6, 12))
        self.assertEqual(PMOD_POWER_PINS, (5, 6, 11, 12))
        self.assertEqual(PMOD_IO_TO_PIN, {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10})
        self.assertEqual(set(PMOD_PIN_ROLES.values()), {"data", "ground", "power"})
        self.assertIn("pmod-interface-specification", PMOD_INTERFACE_SPEC_URL)

    def test_standard_two_by_six_geometry(self) -> None:
        self.assertEqual(len(PMOD_PAD_CENTERS), 12)
        self.assertEqual({x for x, _y in PMOD_PAD_CENTERS.values()}, {-1.27, 1.27})
        self.assertEqual(
            sorted({y for _x, y in PMOD_PAD_CENTERS.values()}),
            [-6.35, -3.81, -1.27, 1.27, 3.81, 6.35],
        )
        self.assertIn("straight or right-angle", PmodHeader2x6.description)

    def test_physical_and_gpio_accessors_share_the_canonical_ports(self) -> None:
        connector = PmodHeader2x6()
        pin_accessor = vars(PmodHeader2x6)["pin"]
        gpio_accessor = vars(PmodHeader2x6)["gpio"]
        self.assertIn("return self.p[number - 1]", inspect.getsource(pin_accessor))
        self.assertIn("return self.pin(PMOD_IO_TO_PIN[number])", inspect.getsource(gpio_accessor))
        with self.assertRaises(ValueError):
            pin_accessor(connector, 0)
        with self.assertRaises(ValueError):
            pin_accessor(connector, 13)
        with self.assertRaises(ValueError):
            gpio_accessor(connector, 0)
        with self.assertRaises(ValueError):
            gpio_accessor(connector, 9)


if __name__ == "__main__":
    unittest.main()

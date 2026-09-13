from __future__ import annotations

import unittest

from alchitry_v2_elements import AlchitryFtV2BottomElement
from alchitry_v2_elements.components import ELEMENT_LAYOUTS
from alchitry_v2_elements.generated_data import V2_BOTTOM_SIGNAL_MAP
from jitx.layerindex import Side
from shared_components.alchitry_v2 import FT_PROFILE

from src.pinmap import DATA_CONNECTIONS
from src.main import (
    AU2_CENTER_X,
    AU2_CONNECTOR_ELEMENT,
    BANK_A_SIGNAL_PINS,
    BANK_B_SIGNAL_PINS,
    BOARD_EXTENSION,
    BOARD_HEIGHT,
    BOARD_WIDTH,
    DATA_PIN_NAMES,
    FFC_PARENT_PLACEMENTS,
    GROUND_HOLE_DIAMETER,
    GROUND_PAD_ARRAY_HEIGHT,
    GROUND_PAD_ARRAY_WIDTH,
    GROUND_PAD_DIAMETER,
    GROUNDED_CORNERS_ORIGIN,
    LOWER_GPIO_LABELS,
    REFERENCE_MOUNTING_HOLE_X,
    REFERENCE_MOUNTING_HOLE_Y,
    SAFE_PIN_INDEX,
    SAFE_PIN_NAMES,
    SALEAE_PARENT_PLACEMENT,
    SALEAE_PIN_NAMES,
    SHIFTER_PARENT_PLACEMENTS,
    SUPPLY_BUS_LABEL,
    SUPPLY_SELECT_LABELS,
    SUPPLY_SELECT_PARENT_PLACEMENT,
    UPPER_GPIO_LABELS,
    V2_BOTTOM_ELEMENT_ORIGIN,
)


def _specs_by_name(specs):
    return {spec.name: spec for spec in specs}


def _reference_pad_xy(prefix: str, pin: int) -> tuple[float, float]:
    layout = {signal_prefix: (specs, x, y) for specs, x, y, signal_prefix, _ in ELEMENT_LAYOUTS["V2_BOTTOM"]}
    specs, connector_x, connector_y = layout[prefix]
    spec = _specs_by_name(specs)[str(pin)]
    return (
        round(V2_BOTTOM_ELEMENT_ORIGIN[0] + connector_x + spec.x, 6),
        round(V2_BOTTOM_ELEMENT_ORIGIN[1] + connector_y + spec.y, 6),
    )


class Au2MappingTests(unittest.TestCase):
    def test_ft_safe_signal_counts(self) -> None:
        self.assertEqual(len(BANK_A_SIGNAL_PINS), 26)
        self.assertEqual(len(BANK_B_SIGNAL_PINS), 52)
        self.assertEqual(len(SAFE_PIN_NAMES), 78)
        self.assertEqual(len(SAFE_PIN_INDEX), 78)

    def test_reserved_and_ground_pins_are_not_exposed_as_signals(self) -> None:
        claims = {
            f"{connector}{claim.pin}"
            for connector in ("A", "B")
            for claim in FT_PROFILE.connector_profile(connector).claims
        }
        self.assertTrue(claims.isdisjoint(SAFE_PIN_NAMES))

    def test_data_and_saleae_allocations_are_unique_and_safe(self) -> None:
        self.assertEqual(len(DATA_PIN_NAMES), 48)
        self.assertEqual(len(SALEAE_PIN_NAMES), 8)
        self.assertEqual(len(set(DATA_PIN_NAMES)), 48)
        self.assertEqual(len(set(SALEAE_PIN_NAMES)), 8)
        self.assertTrue(set(DATA_PIN_NAMES).isdisjoint(SALEAE_PIN_NAMES))
        self.assertTrue((set(DATA_PIN_NAMES) | set(SALEAE_PIN_NAMES)).issubset(SAFE_PIN_NAMES))
        self.assertEqual(DATA_PIN_NAMES, tuple(route.fpga_pin for route in DATA_CONNECTIONS))
        self.assertEqual(SALEAE_PIN_NAMES, ("B15", "B21", "B27", "B39", "B3", "B5", "B9", "B11"))

    def test_approved_layout_placements_are_stable(self) -> None:
        self.assertEqual(BOARD_WIDTH, 59.5)
        self.assertEqual(BOARD_HEIGHT, 45.0)
        self.assertEqual(BOARD_EXTENSION, 4.5)
        self.assertEqual(AU2_CENTER_X, -2.25)
        self.assertEqual(V2_BOTTOM_ELEMENT_ORIGIN, (-29.75, 22.5))
        self.assertEqual(GROUNDED_CORNERS_ORIGIN, (-2.25, 0.0))
        self.assertEqual(
            SHIFTER_PARENT_PLACEMENTS,
            (
                ((-2.736, 9.468), 90.0),
                ((6.492, 9.468), 90.0),
                ((11.257, -9.468), 270.0),
                ((20.259, -9.468), 270.0),
                ((2.249, -9.468), 270.0),
                ((15.543, 9.468), 90.0),
            ),
        )
        self.assertEqual(FFC_PARENT_PLACEMENTS, (((8.468, -8.25), 180.0), ((8.468, 8.25), 180.0)))
        self.assertEqual(SALEAE_PARENT_PLACEMENT, ((-15.25, -10.0), 0.0))
        self.assertEqual(SUPPLY_SELECT_PARENT_PLACEMENT, ((-23.25, 13.5), 180.0))

    def test_gpio_labels_match_au1_header_order(self) -> None:
        self.assertEqual(UPPER_GPIO_LABELS, (7, 6, 5, 4))
        self.assertEqual(LOWER_GPIO_LABELS, (3, 2, 1, 0))

    def test_supply_labels_match_au1_style_with_au2_voltage_name(self) -> None:
        self.assertEqual(SUPPLY_SELECT_LABELS, ("NC", "VDD", "3V3"))
        self.assertEqual(SUPPLY_BUS_LABEL, "VBus")

    def test_interface_uses_canonical_ft_safe_v2_bottom_element(self) -> None:
        self.assertIs(AU2_CONNECTOR_ELEMENT, AlchitryFtV2BottomElement)
        self.assertEqual(AU2_CONNECTOR_ELEMENT.mpn, "V2_BOTTOM")
        self.assertEqual(vars(AU2_CONNECTOR_ELEMENT)["profile_name"], "ft")
        self.assertTrue(
            all(spec.side == Side.Bottom for specs, _, _, _, _ in ELEMENT_LAYOUTS["V2_BOTTOM"] for spec in specs)
        )

    def test_reference_bottom_signal_map_is_used_verbatim(self) -> None:
        signal_map = dict(V2_BOTTOM_SIGNAL_MAP)
        self.assertIn("C30", signal_map["GND"])
        self.assertNotIn("L4", signal_map)

    def test_grounded_corners_preserve_reference_hole_centers(self) -> None:
        self.assertEqual(GROUND_HOLE_DIAMETER, 2.2)
        self.assertGreater(GROUND_PAD_DIAMETER, GROUND_HOLE_DIAMETER)
        self.assertEqual(GROUND_PAD_ARRAY_WIDTH / 2.0 - GROUND_PAD_DIAMETER, REFERENCE_MOUNTING_HOLE_X)
        self.assertEqual(GROUND_PAD_ARRAY_HEIGHT / 2.0 - GROUND_PAD_DIAMETER, REFERENCE_MOUNTING_HOLE_Y)
        self.assertEqual(
            (
                GROUNDED_CORNERS_ORIGIN[0] - REFERENCE_MOUNTING_HOLE_X,
                GROUNDED_CORNERS_ORIGIN[0] + REFERENCE_MOUNTING_HOLE_X,
            ),
            (-27.25, 22.75),
        )

    def test_bottom_connector_pin_positions_match_published_kicad_reference(self) -> None:
        # Corner signal-pad positions from Alchitry's published V2_BOTTOM
        # footprint, translated by (-29.75, +22.5) so the 55 mm official Au2
        # outline stays aligned with the adapter's negative-X edge.
        # These checks deliberately use pin names as keys so a geometric mirror
        # cannot silently exchange the connector's electrical pin identities.
        expected = {
            "C1": (-18.05, -17.145),
            "C2": (-18.05, -19.855),
            "C49": (-8.45, -17.145),
            "C50": (-8.45, -19.855),
            "A1": (0.45, -17.145),
            "A2": (0.45, -19.855),
            "A79": (16.05, -17.145),
            "A80": (16.05, -19.855),
            "B1": (0.45, 19.855),
            "B2": (0.45, 17.145),
            "B79": (16.05, 19.855),
            "B80": (16.05, 17.145),
        }
        actual = {
            **{f"C{pin}": _reference_pad_xy("C", pin) for pin in (1, 2, 49, 50)},
            **{f"A{pin}": _reference_pad_xy("A", pin) for pin in (1, 2, 79, 80)},
            **{f"B{pin}": _reference_pad_xy("B", pin) for pin in (1, 2, 79, 80)},
        }
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()

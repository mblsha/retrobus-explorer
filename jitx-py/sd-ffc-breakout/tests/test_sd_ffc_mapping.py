from __future__ import annotations

import unittest

from jitx.placement import Side
from jitx.shapes.primitive import Arc
from shared_components.ffc import DEFAULT_RETROBUS_GND_PINS
from shared_components.full_size_sd import SD_EDGE_PAD_SPECS

from src.main import (
    BOARD_BOTTOM_Y,
    BOARD_OUTLINE,
    BOARD_REAR_CORNER_RADIUS,
    BOARD_REAR_X,
    BOARD_TOP_Y,
    BOTTOM_GROUND_POUR_AREA,
    CARD_FRONT_X,
    CARD_PAD_CENTERS,
    CARD_SHOULDER_X,
    FFC_GROUND_PINS,
    FFC_GROUND_VIA_CENTERS,
    FFC_ROTATION,
    FFC_SIDE,
    FFC_TAIL_DEPTH,
    REFERENCE_FFC_TAIL_DEPTH,
    SD_CONTACT_LABEL_X,
    SD_CONTACT_LABELS,
    SD_EDGE_ORIGIN,
    SD_GROUND_VIA_CENTERS,
    SD_GROUND_VIA_X,
    SD_TO_FFC_PIN,
    SD_VDD_FFC_PIN,
    SIGNAL_AREA,
    TAIL_START_X,
    TOP_GROUND_POUR_AREA,
    ffc_pad_center,
)


class FullSizeSdFfcBreakoutTests(unittest.TestCase):
    def test_all_nine_sd_contacts_are_present(self) -> None:
        self.assertEqual(set(SD_EDGE_PAD_SPECS), set(range(1, 10)))

    def test_all_sd_contacts_have_meaning_labels(self) -> None:
        self.assertEqual({pin for pin, _label, _y in SD_CONTACT_LABELS}, set(range(1, 10)))
        self.assertTrue(all(str(pin) in label for pin, label, _y in SD_CONTACT_LABELS))
        self.assertEqual(SD_CONTACT_LABEL_X, 15.0)

    def test_sparkfun_reference_finger_centers_are_preserved(self) -> None:
        # Global centers from SparkFun SD_Sniffer after its MR270 placement.
        expected_global_centers = {
            1: (3.0666, 23.2546),
            2: (3.0770, 20.7050),
            3: (3.0770, 18.1100),
            4: (3.0770, 15.5800),
            5: (3.0770, 13.0450),
            6: (3.0770, 10.4800),
            7: (3.0770, 8.0800),
            8: (3.0770, 6.0800),
            9: (5.7500, 26.0400),
        }
        for number, (x, y, _width, _length) in SD_EDGE_PAD_SPECS.items():
            # Eagle MR270/JITX bottom-270 transform used by the design.
            transformed = (SD_EDGE_ORIGIN[0] - y, SD_EDGE_ORIGIN[1] - x)
            self.assertAlmostEqual(transformed[0], expected_global_centers[number][0], places=4)
            self.assertAlmostEqual(transformed[1], expected_global_centers[number][1], places=4)
        self.assertEqual(SD_EDGE_PAD_SPECS[9][2:], (2.0, 5.0))
        self.assertEqual(SD_EDGE_PAD_SPECS[8][2:], (1.25, 6.0))

    def test_sd_signals_are_evenly_spread_across_ffc(self) -> None:
        self.assertEqual(
            SD_TO_FFC_PIN,
            {"DAT2": 4, "DAT3": 14, "CMD": 24, "CLK": 36, "DAT0": 46, "DAT1": 56},
        )
        signal_pins = sorted(SD_TO_FFC_PIN.values())
        gaps = [signal_pins[index + 1] - signal_pins[index] for index in range(len(signal_pins) - 1)]
        self.assertLessEqual(max(gaps) - min(gaps), 2)

    def test_each_sd_data_wire_borders_a_dedicated_ground(self) -> None:
        for name in ("DAT0", "DAT1", "DAT2", "DAT3"):
            pin = SD_TO_FFC_PIN[name]
            self.assertTrue(any(abs(pin - ground_pin) == 1 for ground_pin in DEFAULT_RETROBUS_GND_PINS))

    def test_every_unused_ffc_wire_is_ground(self) -> None:
        non_ground_pins = {SD_VDD_FFC_PIN, *SD_TO_FFC_PIN.values()}
        self.assertEqual(set(FFC_GROUND_PINS), set(range(1, 61)) - non_ground_pins)
        self.assertTrue(set(DEFAULT_RETROBUS_GND_PINS).issubset(FFC_GROUND_PINS))

    def test_sd_vdd_uses_retrobus_vcc5v_position(self) -> None:
        self.assertEqual(SD_VDD_FFC_PIN, 1)

    def test_ffc_is_rotated_on_sd_contact_side(self) -> None:
        self.assertEqual(FFC_ROTATION, 270.0)
        self.assertIs(FFC_SIDE, Side.Bottom)
        pin_one = ffc_pad_center(1)
        self.assertAlmostEqual(pin_one[0], 41.904, places=4)
        self.assertAlmostEqual(pin_one[1], 30.879, places=4)

    def test_each_ffc_ground_pin_has_a_plane_via(self) -> None:
        self.assertEqual(len(FFC_GROUND_VIA_CENTERS), len(FFC_GROUND_PINS))
        expected_y = {ffc_pad_center(pin)[1] for pin in FFC_GROUND_PINS}
        self.assertEqual({center[1] for center in FFC_GROUND_VIA_CENTERS}, expected_y)

    def test_sd_ground_vias_are_close_to_the_fingers(self) -> None:
        self.assertEqual(SD_GROUND_VIA_X, 8.0)
        self.assertEqual(
            SD_GROUND_VIA_CENTERS,
            ((8.0, CARD_PAD_CENTERS["VSS1"][1]), (8.0, CARD_PAD_CENTERS["VSS2"][1])),
        )
        self.assertLess(SD_GROUND_VIA_X - CARD_PAD_CENTERS["VSS1"][0], 5.0)

    def test_both_sides_have_full_board_ground_pours(self) -> None:
        self.assertIs(TOP_GROUND_POUR_AREA, SIGNAL_AREA)
        self.assertIs(BOTTOM_GROUND_POUR_AREA, SIGNAL_AREA)

    def test_inserted_outline_matches_reference_before_widening(self) -> None:
        self.assertEqual(CARD_FRONT_X, 0.0)
        self.assertEqual(CARD_SHOULDER_X, 34.29)
        self.assertIn((0.0, 3.81), BOARD_OUTLINE)
        self.assertIn((0.0, 24.13), BOARD_OUTLINE)
        self.assertIn((3.81, 27.94), BOARD_OUTLINE)
        self.assertGreater(BOARD_REAR_X, CARD_SHOULDER_X)
        self.assertEqual(FFC_TAIL_DEPTH, REFERENCE_FFC_TAIL_DEPTH / 3.0)
        self.assertEqual(BOARD_REAR_X, TAIL_START_X + FFC_TAIL_DEPTH)
        self.assertEqual(BOARD_TOP_Y - BOARD_BOTTOM_Y, 40.0)
        rear_arcs = [element for element in BOARD_OUTLINE if isinstance(element, Arc)]
        self.assertEqual(len(rear_arcs), 2)
        self.assertTrue(all(arc.radius == BOARD_REAR_CORNER_RADIUS for arc in rear_arcs))


if __name__ == "__main__":
    unittest.main()

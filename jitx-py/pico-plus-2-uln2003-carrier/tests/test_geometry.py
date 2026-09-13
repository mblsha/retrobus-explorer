from __future__ import annotations

import math
import unittest

from src.geometry import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    DRIVER_GPIO_PINS,
    DRIVER_GROUND_PHYSICAL_PINS,
    DRIVER_H1_POSITIONS,
    DRIVER_ROTATIONS,
    DRIVER_SIGNAL_PHYSICAL_PINS,
    GROUND_POUR_LAYERS,
    GROUND_STITCH_VIA_CENTERS,
    GROUND_STITCH_VIA_DIAMETER,
    GROUND_STITCH_VIA_HOLE_DIAMETER,
    PICO_CENTER,
    PICO_ROW_OFFSET,
    PICO_USED_PIN_LABELS,
    PICO_VBUS_PHYSICAL_PIN,
    ULN_BOARD_BOUNDS,
    ULN_COMPONENT_CUTOUT_BOUNDS,
    ULN_CONNECTOR_ARM_WIDTH,
    ULN_CUTOUT_TOP_EXPANSION,
    ULN_H_POSITIONS,
    ULN_HOLE_DIAMETER,
    ULN_OUTER_RIM_WIDTH,
    ULN_V_POSITIONS,
    pico_pin_label_position,
    pico_pin_position,
)


class CarrierGeometryTests(unittest.TestCase):
    def test_requested_gpio_mapping(self) -> None:
        self.assertEqual(DRIVER_GPIO_PINS, ((0, 1, 2, 3), (10, 11, 12, 13), (20, 21, 22, 26)))
        self.assertEqual(DRIVER_SIGNAL_PHYSICAL_PINS, ((1, 2, 4, 5), (14, 15, 16, 17), (26, 27, 29, 31)))
        self.assertEqual(DRIVER_GROUND_PHYSICAL_PINS, (13, 18, 23))
        self.assertEqual(PICO_VBUS_PHYSICAL_PIN, 40)

    def test_used_pico_pin_labels_are_derived_from_the_mapping(self) -> None:
        labels = dict(PICO_USED_PIN_LABELS)
        self.assertEqual(len(labels), 16)
        for gpios, physical_pins in zip(
            DRIVER_GPIO_PINS,
            DRIVER_SIGNAL_PHYSICAL_PINS,
            strict=True,
        ):
            for gpio, physical_pin in zip(gpios, physical_pins, strict=True):
                self.assertEqual(labels[physical_pin], f"GP{gpio}")
        for physical_pin in DRIVER_GROUND_PHYSICAL_PINS:
            self.assertEqual(labels[physical_pin], "GND")
        self.assertEqual(labels[PICO_VBUS_PHYSICAL_PIN], "5V")

    def test_used_pico_labels_are_inset_between_the_header_rows(self) -> None:
        for physical_pin, _label in PICO_USED_PIN_LABELS:
            pin_x, pin_y = pico_pin_position(physical_pin)
            label_x, label_y = pico_pin_label_position(physical_pin)
            self.assertAlmostEqual(pin_x, label_x)
            self.assertLess(abs(label_y), abs(pin_y))
            self.assertLess(abs(label_y), PICO_ROW_OFFSET)

    def test_calibrated_l_connector_geometry(self) -> None:
        self.assertEqual(ULN_H_POSITIONS, ((0.0, 0.0), (-2.54, 0.0), (-5.08, 0.0), (-7.62, 0.0)))
        self.assertAlmostEqual(ULN_H_POSITIONS[0][0] - ULN_V_POSITIONS[0][0], 10.7045)
        self.assertAlmostEqual(ULN_V_POSITIONS[0][1] - ULN_H_POSITIONS[0][1], 19.4094)
        for upper, lower in zip(ULN_V_POSITIONS, ULN_V_POSITIONS[1:], strict=False):
            self.assertAlmostEqual(upper[1] - lower[1], 2.54)

    def test_rotated_gpio_banks_stay_near_aligned_for_mostly_direct_routes(self) -> None:
        offsets = []
        for h1, rotation, physical_pins in zip(
            DRIVER_H1_POSITIONS,
            DRIVER_ROTATIONS,
            DRIVER_SIGNAL_PHYSICAL_PINS,
            strict=True,
        ):
            angle = math.radians(rotation)
            for local_position, physical_pin in zip(ULN_V_POSITIONS, physical_pins, strict=True):
                module_x = h1[0] + local_position[0] * math.cos(angle) - local_position[1] * math.sin(angle)
                if physical_pin <= 20:
                    pico_local_y = -24.13 + (physical_pin - 1) * 2.54
                else:
                    pico_local_y = 24.13 - (physical_pin - 21) * 2.54
                pico_x = PICO_CENTER[0] - pico_local_y
                offsets.append(abs(module_x - pico_x))
        self.assertLessEqual(max(offsets), 5.5)
        self.assertGreaterEqual(sum(offset <= 3.0 for offset in offsets), 8)

    def test_component_cutout_retains_connector_material_and_outer_rim(self) -> None:
        left, bottom, right, top = ULN_COMPONENT_CUTOUT_BOUNDS
        pad_radius = 1.0

        self.assertAlmostEqual(bottom, ULN_CONNECTOR_ARM_WIDTH / 2.0)
        self.assertAlmostEqual(left, ULN_V_POSITIONS[0][0] + ULN_CONNECTOR_ARM_WIDTH / 2.0)
        self.assertAlmostEqual(right, ULN_BOARD_BOUNDS[2] - ULN_OUTER_RIM_WIDTH)
        self.assertAlmostEqual(
            top,
            ULN_BOARD_BOUNDS[3] - ULN_OUTER_RIM_WIDTH + ULN_CUTOUT_TOP_EXPANSION,
        )
        self.assertGreater(bottom - pad_radius, 0.0)
        self.assertGreater(left - (ULN_V_POSITIONS[0][0] + pad_radius), 0.0)
        self.assertGreater(bottom, ULN_HOLE_DIAMETER / 2.0)
        self.assertGreater(right - left, 25.0)
        self.assertGreater(top - bottom, 23.0)

    def test_ground_pours_cover_both_copper_layers(self) -> None:
        self.assertEqual(GROUND_POUR_LAYERS, (0, 1))

    def test_ground_stitching_vias_are_unique_and_inside_the_board(self) -> None:
        self.assertEqual(len(GROUND_STITCH_VIA_CENTERS), 23)
        self.assertEqual(len(set(GROUND_STITCH_VIA_CENTERS)), len(GROUND_STITCH_VIA_CENTERS))
        edge_margin = GROUND_STITCH_VIA_DIAMETER / 2.0 + 0.5
        self.assertTrue(all(abs(x) <= BOARD_WIDTH / 2.0 - edge_margin for x, _y in GROUND_STITCH_VIA_CENTERS))
        self.assertTrue(all(abs(y) <= BOARD_HEIGHT / 2.0 - edge_margin for _x, y in GROUND_STITCH_VIA_CENTERS))
        self.assertGreater(GROUND_STITCH_VIA_DIAMETER, GROUND_STITCH_VIA_HOLE_DIAMETER)
        self.assertGreaterEqual(GROUND_STITCH_VIA_HOLE_DIAMETER, 0.8)


if __name__ == "__main__":
    unittest.main()


def test_numerical_geometry_import_has_no_pcb_or_process_dependency():
    import subprocess
    import sys

    code = """
import sys
import subprocess

def forbidden(*args, **kwargs):
    raise RuntimeError('geometry import launched a process')
subprocess.Popen = forbidden
import src.geometry
if any(name == 'jitx' or name.startswith('jitx.') for name in sys.modules):
    raise RuntimeError('numerical geometry imported JITX')
if 'src.main' in sys.modules:
    raise RuntimeError('numerical geometry imported board entry point')
"""
    subprocess.run([sys.executable, "-c", code], check=True)

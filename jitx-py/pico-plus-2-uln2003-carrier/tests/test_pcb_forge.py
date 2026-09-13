from __future__ import annotations

import unittest

from shapely.geometry import Point

from mechanical.layout import (
    ForgeParameters,
    build_layout,
    clearance_estimates,
    driver_point,
    mirror_holes_for_press,
    pico_pin_position,
    signal_net_name,
)
from src.geometry import (
    DRIVER_SIGNAL_PHYSICAL_PINS,
    GROUND_STITCH_VIA_CENTERS,
    GROUND_STITCH_VIA_HOLE_DIAMETER,
    ULN_V_POSITIONS,
    VBUS_TOP_PATHS,
)


class PcbForgeGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.layout = build_layout()

    def test_complete_board_geometry_is_present(self) -> None:
        self.assertEqual(len(self.layout.holes), 64 + len(GROUND_STITCH_VIA_CENTERS))
        self.assertEqual(len(self.layout.base_profile.interiors), 3)
        self.assertEqual(len(self.layout.top_nets), 41)
        self.assertGreater(self.layout.top_copper.area, 900.0)

    def test_signal_channels_join_the_matching_pico_and_driver_pads(self) -> None:
        for driver_index, physical_pins in enumerate(DRIVER_SIGNAL_PHYSICAL_PINS):
            for input_index, (physical_pin, local_position) in enumerate(
                zip(physical_pins, ULN_V_POSITIONS, strict=True)
            ):
                copper = self.layout.top_nets[signal_net_name(driver_index, input_index)]
                self.assertTrue(copper.covers(Point(pico_pin_position(physical_pin))))
                self.assertTrue(copper.covers(Point(driver_point(driver_index, local_position))))

    def test_vbus_wrap_reaches_every_path_endpoint(self) -> None:
        vbus = self.layout.top_nets["VBUS_5V"]
        for path in VBUS_TOP_PATHS:
            self.assertTrue(vbus.covers(Point(path[0])))
            self.assertTrue(vbus.covers(Point(path[-1])))

    def test_bottom_ground_mask_keeps_antipads_around_non_ground_holes(self) -> None:
        for hole in self.layout.holes:
            center = Point(hole.center)
            if hole.net == "GND":
                self.assertTrue(self.layout.bottom_ground.covers(center))
            else:
                self.assertFalse(self.layout.bottom_ground.covers(center))
            self.assertFalse(self.layout.ground_foil.covers(center))

    def test_front_ground_mask_clears_signals_and_includes_stitching_vias(self) -> None:
        signal = self.layout.top_nets[signal_net_name(0, 0)]
        self.assertFalse(self.layout.front_ground.intersects(signal))
        via_holes = [hole for hole in self.layout.holes if hole.diameter == GROUND_STITCH_VIA_HOLE_DIAMETER]
        self.assertEqual(len(via_holes), len(GROUND_STITCH_VIA_CENTERS))
        for hole in via_holes:
            center = Point(hole.center)
            self.assertTrue(self.layout.front_ground.covers(center))
            self.assertTrue(self.layout.bottom_ground.covers(center))
            self.assertFalse(self.layout.front_ground_foil.covers(center))

    def test_default_press_parameters_fit_the_trace_channels_and_holes(self) -> None:
        parameters = ForgeParameters()
        parameters.validate()
        self.assertLessEqual(parameters.ridge_height, parameters.trace_depth)
        self.assertLess(parameters.spike_clearance, min(hole.diameter for hole in self.layout.holes))
        mirrored_holes = mirror_holes_for_press(self.layout.holes)
        for source, mirrored in zip(self.layout.holes, mirrored_holes, strict=True):
            self.assertAlmostEqual(mirrored.center[0], -source.center[0])
            self.assertAlmostEqual(mirrored.center[1], source.center[1])
        summary = clearance_estimates(parameters)
        self.assertGreaterEqual(summary["vertical_bottoming_clearance_mm"], 0.0)
        self.assertGreater(summary["minimum_spike_radial_clearance_mm"], 0.0)


if __name__ == "__main__":
    unittest.main()

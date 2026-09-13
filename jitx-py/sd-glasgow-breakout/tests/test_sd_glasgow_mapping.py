from __future__ import annotations

import unittest
from itertools import permutations
from math import hypot

from jitx.placement import Side
from shared_components.full_size_sd import (
    SD_CARD_OUTLINE_LEADING,
    SD_CARD_OUTLINE_TRAILING,
    SD_CARD_PAD_CENTERS,
)
from shared_components.glasgow import (
    GLASGOW_GROUND_PINS,
    GLASGOW_PORT_PINOUT,
    HCTL_PM254_BODY_SIZE,
    HCTL_PM254_OPPOSITE_SIDE_MATING_PIN,
    HCTL_PM254_PAD_CENTERS,
    HCTL_PM254_SOLDERMASK_DIAMETER,
    GlasgowPortConnector,
    hctl_pm254_soldermask_openings,
)

from src.main import (
    AUTOROUTED_SIGNAL_PATHS,
    BOARD_BOTTOM_Y,
    BOARD_OUTLINE,
    BOARD_REAR_X,
    BOARD_TOP_Y,
    BOTTOM_GROUND_POUR_AREA,
    GLASGOW_IO_TO_SD,
    GLASGOW_ORIGIN,
    GLASGOW_PIN_LABEL_RIGHT_X,
    GLASGOW_ROTATION,
    GLASGOW_ROW_LABELS,
    GLASGOW_SIDE,
    GLASGOW_SWAP_ROWS_FOR_MATING,
    GLASGOW_UNUSED_IO,
    GLASGOW_VIO_CONNECTED,
    SD_CARD_BOTTOM_Y,
    SD_CARD_TOP_Y,
    SD_GROUND_VIA_CENTERS,
    SD_TO_GLASGOW_IO,
    SD_VDD_GLASGOW_PIN,
    SENSE_CENTER,
    SENSE_ROUTE_AROUND_Y,
    SENSE_ROUTE_BEHIND_X,
    SENSE_ROUTE_ENTRY_Y,
    SENSE_ROUTE_LAYER,
    SENSE_ROUTE_POINTS,
    SIGNAL_AREA,
    TAIL_CHAMFER_X,
    TOP_GROUND_POUR_AREA,
    glasgow_logical_pad_center,
)


class SdGlasgowBreakoutTests(unittest.TestCase):
    def test_board_is_47mm_long_with_connector_shifted_into_the_extension(self) -> None:
        self.assertEqual(BOARD_REAR_X, 47.0)
        self.assertEqual(GLASGOW_ORIGIN[0], 43.0)
        self.assertEqual(BOARD_REAR_X - GLASGOW_ORIGIN[0], 4.0)

    def test_reuses_complete_sd_card_outline(self) -> None:
        self.assertEqual(BOARD_OUTLINE[: len(SD_CARD_OUTLINE_LEADING)], list(SD_CARD_OUTLINE_LEADING))
        self.assertEqual(BOARD_OUTLINE[-len(SD_CARD_OUTLINE_TRAILING) :], list(SD_CARD_OUTLINE_TRAILING))

    def test_tail_outline_is_centered_on_the_glasgow_rows(self) -> None:
        self.assertAlmostEqual((BOARD_TOP_Y + BOARD_BOTTOM_Y) / 2.0, GLASGOW_ORIGIN[1])
        self.assertAlmostEqual(BOARD_TOP_Y - GLASGOW_ORIGIN[1], GLASGOW_ORIGIN[1] - BOARD_BOTTOM_Y)

    def test_tail_shoulders_are_45_degree_chamfers(self) -> None:
        leading_length = len(SD_CARD_OUTLINE_LEADING)
        self.assertEqual(
            BOARD_OUTLINE[leading_length - 1 : leading_length + 2],
            [(34.29, 29.21), (TAIL_CHAMFER_X, BOARD_TOP_Y), (37.0, BOARD_TOP_Y)],
        )
        top_dx = TAIL_CHAMFER_X - 34.29
        top_dy = BOARD_TOP_Y - 29.21
        self.assertAlmostEqual(top_dx, top_dy)
        trailing_start = len(BOARD_OUTLINE) - len(SD_CARD_OUTLINE_TRAILING)
        self.assertEqual(
            BOARD_OUTLINE[trailing_start - 2 : trailing_start + 1],
            [(37.0, BOARD_BOTTOM_Y), (TAIL_CHAMFER_X, BOARD_BOTTOM_Y), (34.29, 2.54)],
        )
        bottom_dx = TAIL_CHAMFER_X - 34.29
        bottom_dy = 2.54 - BOARD_BOTTOM_Y
        self.assertAlmostEqual(bottom_dx, bottom_dy)

    def test_glasgow_rows_are_centered_within_the_sd_card_height(self) -> None:
        bottom_row_y = glasgow_logical_pad_center(1)[1]
        top_row_y = glasgow_logical_pad_center(19)[1]
        self.assertAlmostEqual(GLASGOW_ORIGIN[1], (SD_CARD_BOTTOM_Y + SD_CARD_TOP_Y) / 2.0)
        self.assertAlmostEqual(bottom_row_y - SD_CARD_BOTTOM_Y, SD_CARD_TOP_Y - top_row_y)
        self.assertAlmostEqual(bottom_row_y - SD_CARD_BOTTOM_Y, 0.635)

    def test_hctl_connector_metadata_and_geometry(self) -> None:
        self.assertEqual(GlasgowPortConnector.mpn, "PM254-2-10-Z-8.5")
        self.assertEqual(GlasgowPortConnector.lcsc_part_number, "C2897411")
        self.assertEqual(HCTL_PM254_BODY_SIZE, (5.0, 25.8))
        self.assertEqual(len(HCTL_PM254_PAD_CENTERS), 20)

    def test_hctl_through_hole_pads_have_mask_openings_on_both_sides(self) -> None:
        top_opening, bottom_opening = hctl_pm254_soldermask_openings()

        self.assertEqual(HCTL_PM254_SOLDERMASK_DIAMETER, 1.8)
        self.assertIs(top_opening.side, Side.Top)
        self.assertIs(bottom_opening.side, Side.Bottom)

    def test_glasgow_port_pinout_matches_official_documentation(self) -> None:
        self.assertEqual(GLASGOW_PORT_PINOUT[1], "SENSE")
        self.assertEqual(GLASGOW_PORT_PINOUT[2], "VIO")
        for index in range(8):
            self.assertEqual(GLASGOW_PORT_PINOUT[3 + 2 * index], f"IO{index}")
            self.assertEqual(GLASGOW_PORT_PINOUT[4 + 2 * index], "GND")
        self.assertEqual(GLASGOW_GROUND_PINS, (4, 6, 8, 10, 12, 14, 16, 18))

    def test_dat2_is_on_io7_and_other_signals_use_the_shortest_assignment(self) -> None:
        self.assertEqual(
            SD_TO_GLASGOW_IO,
            {"DAT1": 0, "DAT0": 1, "CLK": 2, "CMD": 5, "DAT3": 6, "DAT2": 7},
        )
        self.assertEqual(SD_TO_GLASGOW_IO["DAT2"], 7)

        remaining_signals = ("DAT1", "DAT0", "CLK", "CMD", "DAT3")

        def assignment_length(assignment: dict[str, int]) -> float:
            return sum(
                hypot(
                    SD_CARD_PAD_CENTERS[name][0] - glasgow_logical_pad_center(3 + 2 * io)[0],
                    SD_CARD_PAD_CENTERS[name][1] - glasgow_logical_pad_center(3 + 2 * io)[1],
                )
                for name, io in assignment.items()
            )

        actual = {name: SD_TO_GLASGOW_IO[name] for name in remaining_signals}
        shortest = min(
            assignment_length(dict(zip(remaining_signals, io_assignment, strict=True)))
            for io_assignment in permutations(range(7), len(remaining_signals))
        )
        self.assertAlmostEqual(assignment_length(actual), shortest)

    def test_spi_mapping_is_cs_a6_sck_a2_copi_a5_cipo_a1(self) -> None:
        self.assertEqual(SD_TO_GLASGOW_IO["DAT3"], 6)
        self.assertEqual(SD_TO_GLASGOW_IO["CLK"], 2)
        self.assertEqual(SD_TO_GLASGOW_IO["CMD"], 5)
        self.assertEqual(SD_TO_GLASGOW_IO["DAT0"], 1)

    def test_captured_autoroutes_join_the_mapped_pad_centers(self) -> None:
        self.assertEqual(set(AUTOROUTED_SIGNAL_PATHS), set(SD_TO_GLASGOW_IO))
        for name, io_index in SD_TO_GLASGOW_IO.items():
            self.assertEqual(AUTOROUTED_SIGNAL_PATHS[name][0], SD_CARD_PAD_CENTERS[name])
            self.assertEqual(
                AUTOROUTED_SIGNAL_PATHS[name][-1],
                glasgow_logical_pad_center(3 + 2 * io_index),
            )

    def test_sd_vdd_is_sensed_without_tying_glasgow_vio(self) -> None:
        self.assertEqual(SD_VDD_GLASGOW_PIN, 1)
        self.assertFalse(GLASGOW_VIO_CONNECTED)

    def test_sense_route_runs_through_the_row_gap_then_behind_the_connector(self) -> None:
        self.assertEqual(SENSE_ROUTE_LAYER, 1)
        gnd_column_x = glasgow_logical_pad_center(4)[0]
        io_column_x = glasgow_logical_pad_center(3)[0]
        self.assertGreater(SENSE_ROUTE_BEHIND_X, max(gnd_column_x, io_column_x))
        self.assertEqual(SENSE_ROUTE_POINTS[0], SD_CARD_PAD_CENTERS["VDD"])
        self.assertEqual(
            SENSE_ROUTE_POINTS[1],
            (SD_CARD_PAD_CENTERS["VDD"][0], SENSE_ROUTE_ENTRY_Y),
        )
        self.assertEqual(
            SENSE_ROUTE_POINTS[2],
            (SENSE_ROUTE_BEHIND_X, SENSE_ROUTE_ENTRY_Y),
        )
        self.assertEqual(
            SENSE_ROUTE_POINTS[3],
            (SENSE_ROUTE_BEHIND_X, SENSE_ROUTE_AROUND_Y),
        )
        self.assertEqual(SENSE_ROUTE_POINTS[4], (SENSE_CENTER[0], SENSE_ROUTE_AROUND_Y))
        self.assertEqual(SENSE_ROUTE_POINTS[-1], SENSE_CENTER)

    def test_connector_faces_down_and_ground_row_faces_the_card(self) -> None:
        self.assertEqual(GLASGOW_ROTATION, 180.0)
        self.assertIs(GLASGOW_SIDE, Side.Bottom)
        self.assertTrue(GLASGOW_SWAP_ROWS_FOR_MATING)
        self.assertEqual(HCTL_PM254_OPPOSITE_SIDE_MATING_PIN[3], 4)
        self.assertEqual(HCTL_PM254_OPPOSITE_SIDE_MATING_PIN[4], 3)
        self.assertLess(glasgow_logical_pad_center(4)[0], glasgow_logical_pad_center(3)[0])
        self.assertEqual(GLASGOW_UNUSED_IO, (3, 4))

    def test_glasgow_row_labels_are_compact_right_aligned_and_show_sd_mapping(self) -> None:
        self.assertEqual(
            GLASGOW_IO_TO_SD,
            {0: "DAT1", 1: "DAT0", 2: "CLK", 5: "CMD", 6: "DAT3", 7: "DAT2"},
        )
        self.assertEqual(
            {pins: label for pins, label, _x, _y in GLASGOW_ROW_LABELS},
            {
                (1, 2): "VDD VS",
                (3, 4): "DAT1 G0",
                (5, 6): "DAT0 G1",
                (7, 8): "CLK G2",
                (9, 10): "G3",
                (11, 12): "G4",
                (13, 14): "CMD G5",
                (15, 16): "DAT3 G6",
                (17, 18): "DAT2 G7",
                (19, 20): "··",
            },
        )
        self.assertEqual(
            {pin for pins, _label, _x, _y in GLASGOW_ROW_LABELS for pin in pins},
            set(range(1, 21)),
        )
        for pins, label, x, y in GLASGOW_ROW_LABELS:
            self.assertEqual(x, GLASGOW_PIN_LABEL_RIGHT_X)
            self.assertNotIn("G ", label)
            pad_x, pad_y = glasgow_logical_pad_center(pins[0])
            self.assertLess(x, pad_x)
            self.assertLessEqual(abs(y - pad_y), 0.81)

    def test_both_layers_are_ground_poured_and_vss_vias_are_close(self) -> None:
        self.assertIs(TOP_GROUND_POUR_AREA, SIGNAL_AREA)
        self.assertIs(BOTTOM_GROUND_POUR_AREA, SIGNAL_AREA)
        for center, name in zip(SD_GROUND_VIA_CENTERS, ("VSS1", "VSS2"), strict=True):
            self.assertLess(center[0] - SD_CARD_PAD_CENTERS[name][0], 5.0)


if __name__ == "__main__":
    unittest.main()

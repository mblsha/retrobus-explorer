from pathlib import Path

from pytest import approx
from shared_components.pmod import (
    PMOD_BODY_SIZE,
    PMOD_DATA_PINS,
    PMOD_GROUND_PINS,
    PMOD_PAD_CENTERS,
    PMOD_PAD_DIAMETER,
    PMOD_PIN_NAMES,
    PMOD_POWER_PINS,
    PMOD_ROW_SPACING,
    PMOD_VCC_PINS,
)

from src.main import (
    BOARD_REAR_X,
    PMOD_CONNECTED_GROUND_PINS,
    PMOD_CONNECTED_VCC_PINS,
    PMOD_EDGE_COPPER_CLEARANCE,
    PMOD_INBOARD_ROW_LABEL_X,
    PMOD_MAPPING_SHA256,
    PMOD_ORIGIN_X,
    PMOD_OUTBOARD_ROW_LABEL_X,
    PMOD_PIN_TO_SD_SIGNAL,
    PMOD_UNUSED_PINS,
    SD_TO_PMOD_PIN,
    pmod_pin_label_x,
    pmod_pin_labels,
)


def test_sd_signals_use_exhaustively_optimized_fungible_data_positions() -> None:
    assert SD_TO_PMOD_PIN == {
        "DAT3": 7,
        "CMD": 2,
        "CLK": 8,
        "DAT0": 9,
        "DAT1": 10,
        "DAT2": 1,
    }
    assert PMOD_MAPPING_SHA256 == "28d19e5d15e0e4139128fb9cacba5f93e987345144f5b500e82ef2622f33248c"


def test_every_signal_has_a_unique_pmod_pin() -> None:
    assert len(set(SD_TO_PMOD_PIN.values())) == len(SD_TO_PMOD_PIN)
    assert set(SD_TO_PMOD_PIN.values()) <= set(PMOD_DATA_PINS)
    assert set(SD_TO_PMOD_PIN.values()).isdisjoint(PMOD_GROUND_PINS + PMOD_VCC_PINS)


def test_power_isolation_is_an_explicit_invariant() -> None:
    assert PMOD_GROUND_PINS == (5, 11)
    assert PMOD_VCC_PINS == (6, 12)
    assert PMOD_POWER_PINS == (5, 6, 11, 12)
    assert PMOD_CONNECTED_GROUND_PINS == ()
    assert PMOD_CONNECTED_VCC_PINS == ()
    assert PMOD_UNUSED_PINS == (3, 4)


def test_canonical_pmod_pin_names_cover_all_physical_positions() -> None:
    assert PMOD_PIN_NAMES == {
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
    }


def test_header_is_two_rows_of_six_on_254_mm_pitch() -> None:
    assert len(PMOD_PAD_CENTERS) == 12
    assert {x for x, _y in PMOD_PAD_CENTERS.values()} == {-1.27, 1.27}
    assert sorted({y for _x, y in PMOD_PAD_CENTERS.values()}) == [-6.35, -3.81, -1.27, 1.27, 3.81, 6.35]


def test_board_edge_clears_the_header_without_blocking_right_angle_mating() -> None:
    outboard_pad_center_x = PMOD_ORIGIN_X + PMOD_ROW_SPACING / 2.0
    outboard_copper_edge_x = outboard_pad_center_x + PMOD_PAD_DIAMETER / 2.0
    nominal_body_edge_x = PMOD_ORIGIN_X + PMOD_BODY_SIZE[0] / 2.0

    assert BOARD_REAR_X == approx(45.67)
    assert BOARD_REAR_X - outboard_pad_center_x == approx(1.4)
    assert BOARD_REAR_X - outboard_copper_edge_x == approx(PMOD_EDGE_COPPER_CLEARANCE)
    assert BOARD_REAR_X - nominal_body_edge_x == approx(0.17)
    assert BOARD_REAR_X < 46.0


def test_both_sides_receive_every_canonical_pmod_label() -> None:
    source = (Path(__file__).parents[1] / "src" / "main.py").read_text()
    assert source.count("labels = pmod_pin_labels(pin)") == 1
    assert "side=FeatureSide.Top" in source
    assert "side=FeatureSide.Bottom" in source


def test_connected_pmod_labels_include_their_sd_signal_alias() -> None:
    assert PMOD_PIN_TO_SD_SIGNAL == {
        1: "DAT2",
        2: "CMD",
        7: "DAT3",
        8: "CLK",
        9: "DAT0",
        10: "DAT1",
    }
    assert pmod_pin_labels(1) == ("1 IO1", "SD DAT2")
    assert pmod_pin_labels(10) == ("10 IO8", "SD DAT1")


def test_both_label_columns_stay_inboard_of_the_right_angle_header() -> None:
    assert pmod_pin_label_x(1) == PMOD_OUTBOARD_ROW_LABEL_X
    assert pmod_pin_label_x(7) == PMOD_INBOARD_ROW_LABEL_X
    assert PMOD_OUTBOARD_ROW_LABEL_X < PMOD_INBOARD_ROW_LABEL_X < PMOD_ORIGIN_X


def test_unconnected_pmod_labels_do_not_claim_an_sd_signal() -> None:
    assert pmod_pin_labels(3) == ("3 IO3",)
    assert pmod_pin_labels(5) == ("5 GND",)
    assert pmod_pin_labels(12) == ("12 VCC",)


def test_source_contains_no_captured_or_hand_authored_signal_routes() -> None:
    source = (Path(__file__).parents[1] / "src" / "main.py").read_text()
    assert "AUTOROUTED_SIGNAL_PATHS" not in source
    assert "Polyline" not in source
    assert "Copper(" not in source

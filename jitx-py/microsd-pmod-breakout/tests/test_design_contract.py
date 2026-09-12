from pathlib import Path

from jitx.placement import Side
from pytest import approx
from shared_components.micro_sd import MICRO_SD_DATA_PORTS, MICRO_SD_EDGE_PAD_CENTERS
from shared_components.pmod import PMOD_DATA_PINS, PMOD_GROUND_PINS, PMOD_VCC_PINS

from src.main import (
    BOARD_HEIGHT,
    BOARD_REAR_X,
    BOARD_THICKNESS_MM,
    BOARD_WIDTH,
    BOTTOM_HEADER_MAPPING_SHA256,
    BOTTOM_HEADER_ROTATION,
    BOTTOM_HEADER_SD_TO_PMOD_PIN,
    MICRO_SD_CARD_SHOULDER_X,
    PMOD_CONNECTED_GROUND_PINS,
    PMOD_CONNECTED_VCC_PINS,
    PMOD_EDGE_COPPER_CLEARANCE,
    PMOD_ORIGIN,
    PMOD_OUTBOARD_PAD_CENTER_X,
    TOP_HEADER_MAPPING_SHA256,
    TOP_HEADER_ROTATION,
    TOP_HEADER_SD_TO_PMOD_PIN,
    micro_sd_pad_center,
    pmod_pad_center,
)


def test_both_variants_map_all_six_data_signals_to_unique_pmod_gpio() -> None:
    for mapping in (BOTTOM_HEADER_SD_TO_PMOD_PIN, TOP_HEADER_SD_TO_PMOD_PIN):
        assert set(mapping) == set(MICRO_SD_DATA_PORTS)
        assert len(set(mapping.values())) == 6
        assert set(mapping.values()) <= set(PMOD_DATA_PINS)

    assert BOTTOM_HEADER_SD_TO_PMOD_PIN == {
        "DAT2": 7,
        "DAT3": 8,
        "CMD": 9,
        "CLK": 3,
        "DAT0": 10,
        "DAT1": 4,
    }
    assert TOP_HEADER_SD_TO_PMOD_PIN == {
        "DAT2": 4,
        "DAT3": 10,
        "CMD": 3,
        "CLK": 9,
        "DAT0": 8,
        "DAT1": 7,
    }
    assert BOTTOM_HEADER_MAPPING_SHA256 == "165ca88c1986bf63e14639bda5ad679d3f64fa23510b492b782cab3410027ee7"
    assert TOP_HEADER_MAPPING_SHA256 == "3c9dcf15a74e1d2dd39a2259fb427a3ec857f8f7ad2a3092657fe4a7256f2151"


def test_emulator_preserves_the_full_size_host_to_host_power_isolation() -> None:
    assert PMOD_CONNECTED_GROUND_PINS == ()
    assert PMOD_CONNECTED_VCC_PINS == ()
    assert PMOD_GROUND_PINS == (5, 11)
    assert PMOD_VCC_PINS == (6, 12)


def test_board_uses_a_thin_micro_sd_nose_and_right_angle_header_clearance() -> None:
    assert BOARD_THICKNESS_MM == approx(0.8)
    assert MICRO_SD_CARD_SHOULDER_X == approx(15.0)
    assert BOARD_WIDTH == approx(BOARD_REAR_X)
    assert BOARD_REAR_X - (PMOD_OUTBOARD_PAD_CENTER_X + 0.8) == approx(PMOD_EDGE_COPPER_CLEARANCE)
    assert BOARD_HEIGHT == approx(18.5)


def test_micro_sd_contacts_are_card_edge_fingers_not_socket_pads() -> None:
    centers = {name: micro_sd_pad_center(name) for name in MICRO_SD_DATA_PORTS}
    assert centers == {name: MICRO_SD_EDGE_PAD_CENTERS[name] for name in MICRO_SD_DATA_PORTS}
    assert all(x == approx(2.30) for x, _y in centers.values())
    assert centers["DAT2"][1] > centers["DAT3"][1] > centers["CMD"][1]
    assert centers["CMD"][1] > centers["CLK"][1] > centers["DAT0"][1] > centers["DAT1"][1]


def test_top_variant_rotates_the_same_pmod_landpattern_without_mirroring_it() -> None:
    for pin in range(1, 13):
        bottom_x, bottom_y = pmod_pad_center(pin, Side.Bottom, BOTTOM_HEADER_ROTATION)
        top_x, top_y = pmod_pad_center(pin, Side.Top, TOP_HEADER_ROTATION)
        assert top_x == approx(bottom_x)
        assert top_y + bottom_y == approx(2.0 * PMOD_ORIGIN[1])

    top_power_y = {
        pmod_pad_center(pin, Side.Top, TOP_HEADER_ROTATION)[1]
        for pin in (*PMOD_GROUND_PINS, *PMOD_VCC_PINS)
    }
    top_data_y = {
        pmod_pad_center(pin, Side.Top, TOP_HEADER_ROTATION)[1]
        for pin in PMOD_DATA_PINS
    }
    assert min(top_power_y) > max(top_data_y)


def test_signal_copper_is_owned_only_by_jitx_route_plans() -> None:
    source = (Path(__file__).parents[1] / "src" / "main.py").read_text()
    assert "Polyline" not in source
    assert "Copper(" not in source
    assert "Molex1040310811MicroSdSocket" not in source


def test_source_exposes_explicit_top_and_bottom_emulator_designs() -> None:
    source = (Path(__file__).parents[1] / "src" / "main.py").read_text()
    assert "class MicroSdPmodEmulatorDesign" + "(Design):" in source
    assert "class MicroSdPmodEmulatorTopHeaderDesign" + "(Design):" in source
    assert "pmod_side=Side.Bottom" in source
    assert "pmod_side=Side.Top" in source

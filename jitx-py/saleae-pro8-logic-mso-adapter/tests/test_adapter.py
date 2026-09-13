from __future__ import annotations

import pytest
from jitx.layerindex import Side as FeatureSide
from shared_components.saleae import (
    LOGIC_MSO_GROUND_PAD_NUMBERS,
    LOGIC_MSO_HEADER_BODY_SIZE,
    LOGIC_MSO_HEADER_COURTYARD_SIZE,
    LOGIC_MSO_HEADER_INNER_SIZE,
    LOGIC_MSO_HEADER_PAD_CENTERS,
    LOGIC_MSO_HEADER_PINOUT,
    LOGIC_MSO_HEADER_SOLDERMASK_DIAMETER,
    LOGIC_MSO_SIGNAL_PAD_NUMBERS,
    SALEAE8_HEADER_CENTER_SPACING,
    SALEAE_HEADER_PAD_CENTERS,
    SALEAE_HEADER_PITCH,
    SALEAE_HEADER_SOLDERMASK_DIAMETER,
    LogicMsoDigitalHeader2x5,
    Saleae8,
    SaleaeMaleHeader2x4,
    pth_soldermask_openings,
)

from src.main import (
    AUTOROUTED_SIGNAL_PATHS,
    BANK_CENTER_SPACING,
    BOARD_HEIGHT,
    BOARD_WIDTH,
    CHANNEL_GROUPS,
    GROUND_POUR_LAYERS,
    GROUND_STITCH_VIA_CENTERS,
    LOGIC_MSO_BANK_Y,
    LOGIC_MSO_CENTER_SPACING,
    LOGIC_MSO_PIN_LABELS,
    MIN_SILKSCREEN_TEXT_HEIGHT,
    PIN_LABELS,
    PRO8_ASSEMBLY_CENTER,
    PRO8_HEADER_CENTERS,
    PRO8_HEADER_COMPONENT,
    PRO8_PIN_LABELS,
    PRO8_ROTATION,
    SaleaePro8LogicMsoAdapterSubstrate,
)


def test_logic_mso_pinout_matches_saleae_digital_probe() -> None:
    assert LOGIC_MSO_HEADER_PINOUT == {
        1: "GND",
        2: "D0",
        3: "GND",
        4: "D1",
        5: "GND",
        6: "D2",
        7: "GND",
        8: "D3",
        9: "DNC",
        10: "DNC",
    }


def test_logic_mso_pad_grid_is_2x5_at_254_pitch() -> None:
    assert LOGIC_MSO_HEADER_PAD_CENTERS[1] == pytest.approx((-5.08, 1.27))
    assert LOGIC_MSO_HEADER_PAD_CENTERS[2] == pytest.approx((-5.08, -1.27))
    assert LOGIC_MSO_HEADER_PAD_CENTERS[9] == pytest.approx((5.08, 1.27))
    assert LOGIC_MSO_HEADER_PAD_CENTERS[10] == pytest.approx((5.08, -1.27))


def test_logic_mso_shared_component_uses_the_mating_row_order_by_default() -> None:
    assert LOGIC_MSO_GROUND_PAD_NUMBERS == (1, 3, 5, 7)
    assert LOGIC_MSO_SIGNAL_PAD_NUMBERS == (2, 4, 6, 8)
    assert tuple(pin for pin, role in LOGIC_MSO_HEADER_PINOUT.items() if role == "GND") == (
        1,
        3,
        5,
        7,
    )
    assert tuple(pin for pin, role in LOGIC_MSO_HEADER_PINOUT.items() if role in {"D0", "D1", "D2", "D3"}) == (
        2,
        4,
        6,
        8,
    )


@pytest.mark.parametrize(
    "diameter",
    (SALEAE_HEADER_SOLDERMASK_DIAMETER, LOGIC_MSO_HEADER_SOLDERMASK_DIAMETER),
)
def test_gpio_through_hole_pads_have_mask_openings_on_both_faces(diameter: float) -> None:
    top_opening, bottom_opening = pth_soldermask_openings(diameter)
    assert top_opening.side is FeatureSide.Top
    assert bottom_opening.side is FeatureSide.Bottom


def test_c93713_clearance_uses_full_shroud() -> None:
    assert LOGIC_MSO_HEADER_BODY_SIZE == pytest.approx((20.3, 9.0))
    assert LOGIC_MSO_HEADER_INNER_SIZE[0] >= 17.3
    assert LOGIC_MSO_HEADER_INNER_SIZE[1] >= 6.0
    assert LOGIC_MSO_HEADER_COURTYARD_SIZE[0] > LOGIC_MSO_HEADER_BODY_SIZE[0]
    assert LOGIC_MSO_HEADER_COURTYARD_SIZE[1] > LOGIC_MSO_HEADER_BODY_SIZE[1]


def test_board_clears_both_c93713_courtyards() -> None:
    half_courtyard_width = LOGIC_MSO_HEADER_COURTYARD_SIZE[0] / 2.0
    half_courtyard_height = LOGIC_MSO_HEADER_COURTYARD_SIZE[1] / 2.0
    assert LOGIC_MSO_CENTER_SPACING / 2.0 + half_courtyard_width < BOARD_WIDTH / 2.0
    assert abs(LOGIC_MSO_BANK_Y) + half_courtyard_height < BOARD_HEIGHT / 2.0
    assert LOGIC_MSO_CENTER_SPACING > LOGIC_MSO_HEADER_COURTYARD_SIZE[0]


def test_channel_banks_map_straight_through() -> None:
    assert CHANNEL_GROUPS == ((0, 1, 2, 3), (4, 5, 6, 7))


def test_ground_pours_cover_both_copper_layers() -> None:
    assert GROUND_POUR_LAYERS == (0, 1)


def test_ground_stitching_vias_cover_the_board_perimeter() -> None:
    assert len(GROUND_STITCH_VIA_CENTERS) == 26
    assert len(set(GROUND_STITCH_VIA_CENTERS)) == len(GROUND_STITCH_VIA_CENTERS)
    assert all(abs(x) <= BOARD_WIDTH / 2.0 - 0.8 for x, _y in GROUND_STITCH_VIA_CENTERS)
    assert all(abs(y) <= BOARD_HEIGHT / 2.0 - 0.8 for _x, y in GROUND_STITCH_VIA_CENTERS)


def test_every_connector_pad_has_a_short_label() -> None:
    assert len(PRO8_PIN_LABELS) == 16
    assert len(LOGIC_MSO_PIN_LABELS) == 20
    assert len(PIN_LABELS) == 36
    labels = [label for label, _x, _y in PIN_LABELS]
    assert labels.count("G") == 16
    assert labels.count("·") == 4
    assert all(labels.count(str(channel)) == 2 for channel in range(8))
    assert [label for label, _x, _y in LOGIC_MSO_PIN_LABELS[:5]] == ["G", "G", "G", "G", "·"]
    assert [label for label, _x, _y in LOGIC_MSO_PIN_LABELS[5:10]] == ["0", "1", "2", "3", "·"]
    assert [label for label, _x, _y in LOGIC_MSO_PIN_LABELS[10:15]] == ["G", "G", "G", "G", "·"]
    assert [label for label, _x, _y in LOGIC_MSO_PIN_LABELS[15:]] == ["4", "5", "6", "7", "·"]


def test_short_pro8_labels_meet_the_project_silkscreen_rule() -> None:
    assert MIN_SILKSCREEN_TEXT_HEIGHT == pytest.approx(0.8)
    assert SaleaePro8LogicMsoAdapterSubstrate.constraints.min_silkscreen_text_height == pytest.approx(0.8)


def test_pro8_uses_shared_saleae8_assembly_and_grid() -> None:
    assert PRO8_HEADER_COMPONENT is Saleae8
    assert BANK_CENTER_SPACING == pytest.approx(SALEAE8_HEADER_CENTER_SPACING)
    assert SALEAE8_HEADER_CENTER_SPACING == pytest.approx(13.462)
    assert SALEAE_HEADER_PITCH == pytest.approx(2.54)
    assert SALEAE_HEADER_PAD_CENTERS[1] == pytest.approx((-1.27, 3.81))
    assert SALEAE_HEADER_PAD_CENTERS[8] == pytest.approx((1.27, -3.81))
    assert SaleaeMaleHeader2x4.__mro__[1].__name__ == "SignalGroundHeader2x4"


def test_entire_saleae8_centerline_is_quarter_turned() -> None:
    assert PRO8_ROTATION == pytest.approx(270.0)
    assert PRO8_HEADER_CENTERS[0][1] == pytest.approx(PRO8_HEADER_CENTERS[1][1])
    assert PRO8_HEADER_CENTERS[0][1] == pytest.approx(PRO8_ASSEMBLY_CENTER[1])
    assert PRO8_HEADER_CENTERS[1][0] - PRO8_HEADER_CENTERS[0][0] == pytest.approx(BANK_CENTER_SPACING)


def test_pro8_is_tucked_against_the_logic_mso_courtyard() -> None:
    logic_mso_courtyard_top = LOGIC_MSO_BANK_Y + LOGIC_MSO_HEADER_COURTYARD_SIZE[1] / 2.0
    pro8_body_bottom = PRO8_ASSEMBLY_CENTER[1] - SALEAE_HEADER_PITCH
    assert pro8_body_bottom - logic_mso_courtyard_top == pytest.approx(0.26)


def test_all_channels_keep_the_reviewed_autorouter_paths() -> None:
    assert set(AUTOROUTED_SIGNAL_PATHS) == set(range(8))
    assert all(len(path) == 2 for path in AUTOROUTED_SIGNAL_PATHS.values())
    assert all(path[-1][1] == pytest.approx(-5.77) for path in AUTOROUTED_SIGNAL_PATHS.values())


def test_connector_metadata_is_explicit() -> None:
    assert LogicMsoDigitalHeader2x5.lcsc_part_number == "C93713"
    assert LogicMsoDigitalHeader2x5.mpn == "Z-231011810106"
    assert "male" in SaleaeMaleHeader2x4.value.lower()

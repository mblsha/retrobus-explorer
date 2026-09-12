from shared_components.micro_sd import (
    MICRO_SD_CARD_OUTLINE_LEADING,
    MICRO_SD_CARD_OUTLINE_TRAILING,
    MICRO_SD_DATA_PORTS,
    MICRO_SD_EDGE_ORIGIN,
    MICRO_SD_EDGE_PAD_CENTERS,
    MICRO_SD_EDGE_PAD_SPECS,
    MICRO_SD_EDGE_ROTATION,
    MICRO_SD_PIN_NUMBER_BY_PORT,
    MICRO_SD_PINOUT,
)


def test_micro_sd_pinout_matches_the_industry_contact_order() -> None:
    assert MICRO_SD_PIN_NUMBER_BY_PORT == {
        "DAT2": 1,
        "DAT3": 2,
        "CMD": 3,
        "VDD": 4,
        "CLK": 5,
        "VSS": 6,
        "DAT0": 7,
        "DAT1": 8,
    }
    assert MICRO_SD_PINOUT[2].spi_role == "CS"
    assert MICRO_SD_PINOUT[3].spi_role == "MOSI"
    assert MICRO_SD_PINOUT[5].spi_role == "SCK"
    assert MICRO_SD_PINOUT[7].spi_role == "MISO"
    assert MICRO_SD_DATA_PORTS == ("DAT2", "DAT3", "CMD", "CLK", "DAT0", "DAT1")


def test_micro_sd_card_edge_matches_the_proven_sniffer_geometry() -> None:
    assert MICRO_SD_EDGE_ORIGIN == (0.0, 10.16)
    assert MICRO_SD_EDGE_ROTATION == 270.0
    assert MICRO_SD_EDGE_PAD_SPECS[1] == (1.46, 2.30, 0.85, 3.25)
    assert MICRO_SD_EDGE_PAD_SPECS[4] == (4.76, 2.10, 0.85, 3.75)
    assert MICRO_SD_EDGE_PAD_SPECS[6] == (6.96, 2.10, 0.85, 3.75)
    assert MICRO_SD_EDGE_PAD_CENTERS == {
        "DAT2": (2.30, 8.70),
        "DAT3": (2.30, 7.60),
        "CMD": (2.30, 6.50),
        "VDD": (2.10, 5.40),
        "CLK": (2.30, 4.30),
        "VSS": (2.10, 3.20),
        "DAT0": (2.30, 2.10),
        "DAT1": (2.30, 1.00),
    }
    assert MICRO_SD_CARD_OUTLINE_LEADING == ((0.0, 0.0), (15.0, 0.0))
    assert MICRO_SD_CARD_OUTLINE_TRAILING[0] == (15.0, 11.0)
    assert MICRO_SD_CARD_OUTLINE_TRAILING[-1] == (0.0, 10.0)

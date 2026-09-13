import pytest
from jitx._instantiation import instantiation
from jitx.inspect import extract
from jitx.net import Net, Port
from jitx.placement import Side
from pytest import approx
from shared_components.micro_sd import MICRO_SD_DATA_PORTS, MICRO_SD_EDGE_PAD_CENTERS
from shared_components.pmod import PMOD_DATA_PINS, PMOD_GROUND_PINS, PMOD_VCC_PINS

from src.main import (
    BOARD_HEIGHT,
    BOARD_REAR_X,
    BOARD_THICKNESS_MM,
    BOARD_WIDTH,
    BOTTOM_HEADER_ROTATION,
    BOTTOM_HEADER_SD_TO_PMOD_PIN,
    MICRO_SD_CARD_SHOULDER_X,
    PMOD_EDGE_COPPER_CLEARANCE,
    PMOD_ORIGIN,
    PMOD_OUTBOARD_PAD_CENTER_X,
    TOP_HEADER_ROTATION,
    TOP_HEADER_SD_TO_PMOD_PIN,
    MicroSdPmodEmulatorCircuit,
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


@pytest.mark.parametrize("top", [False, True])
def test_constructed_circuit_connections_and_power_isolation(top: bool) -> None:
    mapping = TOP_HEADER_SD_TO_PMOD_PIN if top else BOTTOM_HEADER_SD_TO_PMOD_PIN
    with instantiation.activate():
        circuit = MicroSdPmodEmulatorCircuit(
            pmod_side=Side.Top if top else Side.Bottom,
            pmod_rotation=TOP_HEADER_ROTATION if top else BOTTOM_HEADER_ROTATION,
            sd_to_pmod_pin=mapping,
            header_side_name="top" if top else "bottom",
        )
    # Traverse the constructed circuit, including nets added outside self.nets.
    nets = [{id(port) for port in net if isinstance(port, Port)} for net in extract(circuit, Net, refs=True)]
    assert len(nets) == 7
    expected = [{id(circuit.gnd), id(circuit.card.VSS)}] + [
        {id(getattr(circuit.card, signal)), id(circuit.pmod.pin(pin))}
        for signal, pin in mapping.items()
    ]
    assert {frozenset(net) for net in nets} == {frozenset(net) for net in expected}
    connected = set().union(*nets)
    for pin in (1, 2, 5, 6, 11, 12):
        assert id(circuit.pmod.pin(pin)) not in connected
    assert id(circuit.card.VDD) not in connected


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
        pmod_pad_center(pin, Side.Top, TOP_HEADER_ROTATION)[1] for pin in (*PMOD_GROUND_PINS, *PMOD_VCC_PINS)
    }
    top_data_y = {pmod_pad_center(pin, Side.Top, TOP_HEADER_ROTATION)[1] for pin in PMOD_DATA_PINS}
    assert min(top_power_y) > max(top_data_y)

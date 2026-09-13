from alchitry_v2_elements import AlchitryV2BottomElement

from src.physical import (
    AU2_BANK_CENTER,
    BOARD_CENTER_X,
    BOARD_HEIGHT,
    BOARD_WIDTH,
    CPU_PLACEMENT,
    LVC_TRANSLATOR_PLACEMENTS,
    MOUNTING_HOLE_CENTERS,
    MOUNTING_HOLE_DIAMETER,
    MOUNTING_HOLE_EDGE_INSET,
    MOUNTING_HOLE_PAD_DIAMETER,
    SOUTH_TRANSLATOR_PLACEMENTS,
    TOP_ASSEMBLY_SHIFT_X,
    TXS_TRANSLATOR_PLACEMENTS,
)
from src.pinmap import (
    ACTIVE_LOW_ENABLE_CONTROL_NAMES,
    AU2_CORRIDOR_SIGNALS,
    AU2_GPIO_NAMES,
    AU2_PIN_BY_LOGICAL_SIGNAL,
    AUTO_BIDIRECTIONAL_BANKS,
    BANKS,
    CLOCK_CAPABLE_AU2_PINS,
    CLOCK_SIGNAL_NAMES,
    CONTROL_AU2_PINS,
    CONTROL_SIGNAL_NAMES,
    CPU_PIN_NAMES_BY_NUMBER,
    DIGITAL_CPU_SIGNAL_NAMES,
    E_OE_AU2_PIN,
    E_PORT_BANKS,
    ENABLE_CONTROL_SIGNAL_NAMES,
    FT2_RESERVED_AU2_GPIO_NAMES,
    NON_3V3_TOLERANT_AU2_PINS,
    POWER_PIN_NAMES,
    SOUTH_AUTO_BANKS,
    UNUSED_AU2_GPIO_NAMES,
    WEST_AUTO_BANK,
)



def test_cpu_has_complete_unique_pinout() -> None:
    assert len(CPU_PIN_NAMES_BY_NUMBER) == 100
    assert len(set(CPU_PIN_NAMES_BY_NUMBER)) == 100
    assert set(CPU_PIN_NAMES_BY_NUMBER) == set(DIGITAL_CPU_SIGNAL_NAMES) | set(POWER_PIN_NAMES)
    assert CPU_PIN_NAMES_BY_NUMBER[84:] == tuple(f"E{index}" for index in range(15, -1, -1))


def test_translator_plan_covers_every_non_power_pin() -> None:
    assert len(BANKS) == 10
    assert len(E_PORT_BANKS) == 2
    assert len(AUTO_BIDIRECTIONAL_BANKS) == 5
    assert len(DIGITAL_CPU_SIGNAL_NAMES) == 98
    assert len(set(DIGITAL_CPU_SIGNAL_NAMES)) == 98


def test_au2_mapping_avoids_only_the_non_tolerant_gpios() -> None:
    assert len(AU2_GPIO_NAMES) == 104
    assert len(CONTROL_SIGNAL_NAMES) == 5
    assert len(AU2_PIN_BY_LOGICAL_SIGNAL) == 103
    assert len(set(AU2_PIN_BY_LOGICAL_SIGNAL.values())) == 103
    gpio_pins = set(AU2_PIN_BY_LOGICAL_SIGNAL.values()) - {E_OE_AU2_PIN}
    assert len(gpio_pins) == 102
    assert gpio_pins < set(AU2_GPIO_NAMES)
    # The Alchitry pinout legend: the 1.35 V pins are not 3.3 V tolerant.
    assert UNUSED_AU2_GPIO_NAMES == NON_3V3_TOLERANT_AU2_PINS == ("B46", "B48")


def test_e_oe_terminates_on_the_control_connector_led_pin() -> None:
    assert AU2_PIN_BY_LOGICAL_SIGNAL["E_OE"] == E_OE_AU2_PIN == "L0"
    assert E_OE_AU2_PIN not in AU2_GPIO_NAMES


def test_au2_gpio_pool_is_derived_from_the_canonical_generic_element() -> None:
    canonical = {
        name
        for name in vars(AlchitryV2BottomElement)["source_signal_names"]
        if name[:1] in {"A", "B"} and name[1:].isdigit()
    }
    assert set(AU2_GPIO_NAMES) == canonical
    assert vars(AlchitryV2BottomElement)["excluded_signal_names"] == ()


def test_ft2_stacking_is_intentionally_impossible_for_the_full_pin_tester() -> None:
    ft2_available = set(AU2_GPIO_NAMES) - set(FT2_RESERVED_AU2_GPIO_NAMES)
    assert len(FT2_RESERVED_AU2_GPIO_NAMES) == 26
    assert len(ft2_available) == 78
    assert len(AU2_PIN_BY_LOGICAL_SIGNAL) > len(ft2_available)


def test_clock_signals_use_clock_capable_p_pins() -> None:
    # Single-ended clocks must use the P member of an MRCC/SRCC pair.
    assert CLOCK_CAPABLE_AU2_PINS == ("A41", "A42", "A47", "A48", "B41", "B42", "B47")
    clock_pins = [AU2_PIN_BY_LOGICAL_SIGNAL[signal] for signal in CLOCK_SIGNAL_NAMES]
    assert len(clock_pins) == len(set(clock_pins))
    assert set(clock_pins) <= set(CLOCK_CAPABLE_AU2_PINS)


def test_au2_connector_rows_cover_the_selected_gpio_assignments() -> None:
    assert {corridor: len(signals) for corridor, signals in AU2_CORRIDOR_SIGNALS.items()} == {
        ("A", 0): 26,
        ("A", 1): 26,
        ("B", 0): 24,
        ("B", 1): 26,
    }
    for (connector, parity), signals in AU2_CORRIDOR_SIGNALS.items():
        for signal in signals:
            pin = AU2_PIN_BY_LOGICAL_SIGNAL[signal]
            assert pin[0] == connector
            assert int(pin[1:]) % 2 == parity


def test_cpu_is_centered_against_both_data_bearing_au2_connectors() -> None:
    assert TOP_ASSEMBLY_SHIFT_X == 22.5
    assert CPU_PLACEMENT.x == AU2_BANK_CENTER["A"][0] == AU2_BANK_CENTER["B"][0]


def test_mounting_holes_follow_the_adapter_board_corners() -> None:
    assert MOUNTING_HOLE_DIAMETER == 2.2
    assert MOUNTING_HOLE_PAD_DIAMETER == 3.6
    assert MOUNTING_HOLE_EDGE_INSET == 5.0
    assert set(MOUNTING_HOLE_CENTERS) == {
        (BOARD_CENTER_X - BOARD_WIDTH / 2 + MOUNTING_HOLE_EDGE_INSET, -BOARD_HEIGHT / 2 + MOUNTING_HOLE_EDGE_INSET),
        (BOARD_CENTER_X + BOARD_WIDTH / 2 - MOUNTING_HOLE_EDGE_INSET, -BOARD_HEIGHT / 2 + MOUNTING_HOLE_EDGE_INSET),
        (BOARD_CENTER_X - BOARD_WIDTH / 2 + MOUNTING_HOLE_EDGE_INSET, BOARD_HEIGHT / 2 - MOUNTING_HOLE_EDGE_INSET),
        (BOARD_CENTER_X + BOARD_WIDTH / 2 - MOUNTING_HOLE_EDGE_INSET, BOARD_HEIGHT / 2 - MOUNTING_HOLE_EDGE_INSET),
    }


def test_every_output_enable_has_a_control_name() -> None:
    assert {bank.oe_control for bank in BANKS if bank.oe_control is not None} <= set(CONTROL_SIGNAL_NAMES)
    assert {bank.dir_control for bank in BANKS if bank.dir_control is not None} <= set(CONTROL_SIGNAL_NAMES)
    assert {bank.enable_control for bank in AUTO_BIDIRECTIONAL_BANKS if bank.enable_control is not None} <= set(
        CONTROL_SIGNAL_NAMES
    )
    assert set(ENABLE_CONTROL_SIGNAL_NAMES) <= set(CONTROL_SIGNAL_NAMES)
    assert set(ACTIVE_LOW_ENABLE_CONTROL_NAMES) < set(ENABLE_CONTROL_SIGNAL_NAMES)


def test_control_au2_pins_match_the_optimized_fixture() -> None:
    assert CONTROL_AU2_PINS == {
        "CTRL_OE_N": "A30",
        "KEY_OE_N": "A10",
        "D_OE_N": "A42",
        "D_DIR": "A58",
        "E_OE": "L0",
    }


def test_reserved_direction_controlled_input_bank_is_empty() -> None:
    control_banks = [bank for bank in BANKS if bank.oe_control == "CTRL_OE_N"]
    assert len(control_banks) == 1
    assert {signal for signal in control_banks[0].signals if signal is not None} == set()


def test_south_auto_banks_follow_the_cpu_edge_without_crossings() -> None:
    assert set(signal for bank in SOUTH_AUTO_BANKS for signal in bank.signals if signal is not None) == {
        "X1", "X2", "X3", "X4", "VDD", "IRQ", "RESET", "TEST", "CI", "CO", "ON", "WR", "MRQ"
    }
    assert [placement.position for placement in SOUTH_TRANSLATOR_PLACEMENTS] == [(1.5, -17.5), (9.2, -17.5)]
    assert all(placement.rotation == 90 for placement in SOUTH_TRANSLATOR_PLACEMENTS)


def test_south_lvc_has_the_expanded_cpu_fanout_corridor() -> None:
    assert LVC_TRANSLATOR_PLACEMENTS[-1].position == (20.0, -18.5)
    assert LVC_TRANSLATOR_PLACEMENTS[-1].rotation == 270


def test_u3_has_the_north_bottom_copper_and_decoupling_corridor() -> None:
    assert LVC_TRANSLATOR_PLACEMENTS[1].position == (20.0, 27.0)
    assert LVC_TRANSLATOR_PLACEMENTS[1].rotation == 90


def test_west_auto_bank_follows_the_cpu_perimeter_without_crossing() -> None:
    assert set(WEST_AUTO_BANK.signals) == {"KO0", "KO1", "KO2", "KO3", "KO4", "KO5", "RXD", "TXD"}
    assert WEST_AUTO_BANK.enable_control is None
    assert AUTO_BIDIRECTIONAL_BANKS[1] is WEST_AUTO_BANK
    assert [placement.position for placement in TXS_TRANSLATOR_PLACEMENTS] == [
        (1.5, -17.5),
        (-8.5, 7.8),
        (9.2, -17.5),
        (-8.5, 0.0),
        (-8.5, -7.7),
    ]
    assert [placement.rotation for placement in TXS_TRANSLATOR_PLACEMENTS] == [90, 0, 90, 0, 0]


def test_binja_esr_e_port_is_per_channel_bidirectional() -> None:
    assert {signal for bank in E_PORT_BANKS for signal in bank.signals} == {f"E{index}" for index in range(16)}
    assert {bank.enable_control for bank in E_PORT_BANKS} == {"E_OE"}


def test_fixed_and_data_bus_directions_are_reflected_in_bank_plan() -> None:
    mode_by_signal = {signal: bank.mode for bank in BANKS for signal in bank.signals if signal is not None}
    for signal in ("OUT", "DIS", "HA"):
        assert mode_by_signal[signal] == "cpu_to_fpga"
    assert "IRQ" not in mode_by_signal
    assert SOUTH_AUTO_BANKS[0].signals[7] == "IRQ"
    for signal in (f"D{index}" for index in range(8)):
        assert mode_by_signal[signal] == "dynamic"
    assert {
        signal for bank in SOUTH_AUTO_BANKS for signal in bank.signals if signal is not None
    } == {"X1", "X2", "X3", "X4", "VDD", "IRQ", "RESET", "TEST", "CI", "CO", "ON", "WR", "MRQ"}

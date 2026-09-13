from src.assignment import (
    CONNECTION_BY_CHANNEL,
    CONNECTION_BY_SIGNAL,
    CONNECTIONS,
)
from src.pinmap import (
    ASSIGNABLE_AU2_GPIO_NAMES,
    AU2_PIN_BY_LOGICAL_SIGNAL,
    DIGITAL_CPU_SIGNAL_NAMES,
    NON_3V3_TOLERANT_AU2_PINS,
)
from src.via_policy import (
    SIGNAL_VIA_ANNULAR_RING_MM,
    SIGNAL_VIA_DIAMETER_MM,
    SIGNAL_VIA_DRILL_MM,
)


def test_assignment_snapshot_is_a_complete_channel_bijection() -> None:
    assert len(CONNECTIONS) == 98
    assert len(CONNECTION_BY_SIGNAL) == 98
    assert len(CONNECTION_BY_CHANNEL) == 98
    assert len(CONNECTION_BY_CHANNEL) == 98
    assert set(CONNECTION_BY_SIGNAL) == set(DIGITAL_CPU_SIGNAL_NAMES)


def test_assignment_uses_only_safe_unique_au2_data_pins() -> None:
    pins = [row.au2_pin for row in CONNECTIONS]
    assert len(pins) == len(set(pins)) == len(ASSIGNABLE_AU2_GPIO_NAMES)
    assert set(pins) == set(ASSIGNABLE_AU2_GPIO_NAMES)
    assert not set(pins) & set(NON_3V3_TOLERANT_AU2_PINS)
    assert {
        signal: AU2_PIN_BY_LOGICAL_SIGNAL[signal]
        for signal in DIGITAL_CPU_SIGNAL_NAMES
    } == {signal: row.au2_pin for signal, row in CONNECTION_BY_SIGNAL.items()}


def test_signal_via_policy_is_manufacturable() -> None:
    assert (SIGNAL_VIA_DIAMETER_MM, SIGNAL_VIA_DRILL_MM) == (0.60, 0.30)
    assert SIGNAL_VIA_ANNULAR_RING_MM == 0.15


def test_final_assignment_rejects_clock_on_an_ordinary_gpio(monkeypatch):
    from dataclasses import replace

    import pytest

    from src import pinmap

    assignments = dict(CONNECTION_BY_SIGNAL)
    clock = assignments["DCLK"]
    ordinary = next(c for c in CONNECTIONS if c.au2_pin not in pinmap.CLOCK_CAPABLE_AU2_PINS)
    assignments[clock.signal] = replace(clock, au2_pin=ordinary.au2_pin)
    assignments[ordinary.signal] = replace(ordinary, au2_pin=clock.au2_pin)
    monkeypatch.setattr(pinmap, "CONNECTION_BY_SIGNAL", assignments)
    with pytest.raises(ValueError, match="clock signals"):
        pinmap._load_assigned_au2_pins()

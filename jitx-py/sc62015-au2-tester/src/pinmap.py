from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from alchitry_v2_elements import AlchitryV2BottomElement
from shared_components.alchitry_v2 import FT_PROFILE

from src.assignment import CONNECTION_BY_SIGNAL


def _numbered(prefix: str, first: int, last: int, *, descending: bool = False) -> tuple[str, ...]:
    values = range(first, last + 1)
    if descending:
        values = reversed(tuple(values))
    return tuple(f"{prefix}{index}" for index in values)


CPU_PIN_NAMES_BY_NUMBER = (
    "X1",
    "X2",
    "X3",
    "X4",
    "VDD",
    "VCC",
    "RESET",
    "GND",
    "TEST",
    "CI",
    "CO",
    "ON",
    "WR",
    "MRQ",
    *_numbered("K", 10, 17),
    *_numbered("D", 0, 7),
    *_numbered("A", 0, 18),
    "VDISP",
    "VA",
    "DCLK",
    *_numbered("KO", 10, 15, descending=True),
    "IRQ",
    "OUT",
    *_numbered("CE", 0, 7, descending=True),
    "ACLK",
    "DIS",
    "HA",
    "RD",
    *_numbered("KO", 0, 9, descending=True),
    "RXD",
    "TXD",
    *_numbered("E", 0, 15, descending=True),
)

# The PC-E500 service manual identifies only VCC and GND as power pins. VDD is
# a display-converter control output; VDISP and VA are reserved on that model.
POWER_PIN_NAMES = ("VCC", "GND")

# Semantic bank membership and the physical half-bank hosting each group are
# fixed board-design inputs.
CONTROL_INPUT_SIGNAL_NAMES = ("IRQ", "ON", "CI", "TEST", "RESET", "X4", "RXD", "X2")
KEY_INPUT_SIGNAL_NAMES = _numbered("K", 10, 17)
DATA_BUS_SIGNAL_NAMES = _numbered("D", 0, 7)
E_PORT_SIGNAL_NAMES = _numbered("E", 0, 15)
SENSE_SIGNAL_NAMES = tuple(
    sorted(
        set(CPU_PIN_NAMES_BY_NUMBER)
        - set(POWER_PIN_NAMES)
        - set(CONTROL_INPUT_SIGNAL_NAMES)
        - set(KEY_INPUT_SIGNAL_NAMES)
        - set(DATA_BUS_SIGNAL_NAMES)
        - set(E_PORT_SIGNAL_NAMES)
    )
)


@dataclass(frozen=True)
class TranslatorBank:
    name: str
    mode: Literal["cpu_to_fpga", "fpga_to_cpu", "dynamic"]
    signals: tuple[str | None, ...]
    oe_control: str | None
    dir_control: str | None = None

    def __post_init__(self) -> None:
        if len(self.signals) != 8:
            raise ValueError(f"{self.name} must contain exactly eight channels")
        if self.mode == "dynamic" and self.dir_control is None:
            raise ValueError(f"{self.name} requires a direction control")


@dataclass(frozen=True)
class AutoBidirectionalBank:
    name: str
    signals: tuple[str | None, ...]
    enable_control: str | None

    def __post_init__(self) -> None:
        if len(self.signals) != 8:
            raise ValueError(f"{self.name} must contain exactly eight channels")


# Bank index maps to hardware as translator = index // 2, half = index % 2.
# RXD and the seven adjacent CPU-perimeter signals use the compact west
# auto-direction bank.  The south-edge signals and IRQ use two more TXS0108E
# banks. IRQ takes U9's otherwise-free channel 7 and reaches it directly on
# B.Cu beneath the SMD CPU body. Five 16-bit LVC translators cover the other
# 61 pins.
LVC_BANK_ROLES = (
    "sense",
    "sense",
    "sense",
    "sense",
    "control",
    "sense",
    "sense",
    "sense",
    "data",
    "key",
)
LVC_BANK_SIGNALS = (
    (None, None, None, None, "KO6", "KO7", "KO8", "KO9"),
    ("RD", "HA", "DIS", "CE0", "CE1", "CE2", "CE3", "CE4"),
    ("CE5", "ACLK", "CE6", "DCLK", "CE7", "OUT", "KO10", "KO11"),
    ("KO12", "KO13", "KO14", "KO15", "VA", "VDISP", None, None),
    (None, None, None, None, None, None, None, None),
    ("A18", "A17", "A16", "A15", "A14", "A13", "A12", "A11"),
    ("A10", "A9", "A8", "A7", "A6", "A5", "A4", "A3"),
    ("A2", "A1", "A0", None, None, None, None, None),
    ("D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0"),
    ("K17", "K16", "K15", "K14", "K13", "K12", "K11", "K10"),
)


def _lvc_bank(index: int, role: str, signals: tuple[str | None, ...]) -> TranslatorBank:
    if role == "control":
        return TranslatorBank(f"control_inputs_{index}", "fpga_to_cpu", signals, "CTRL_OE_N")
    if role == "key":
        return TranslatorBank("key_inputs", "fpga_to_cpu", signals, "KEY_OE_N")
    if role == "data":
        return TranslatorBank("data_bus", "dynamic", signals, "D_OE_N", "D_DIR")
    return TranslatorBank(f"sense_{index}", "cpu_to_fpga", signals, None)


BANKS = tuple(
    _lvc_bank(index, role, signals)
    for index, (role, signals) in enumerate(zip(LVC_BANK_ROLES, LVC_BANK_SIGNALS, strict=True))
)

# The bottom pair follows the SC62015 south-edge pins from left to right. U9
# uses the continuous channel-1..5 run for X1..VDD and its rightmost channel
# for the B.Cu IRQ run beneath the package. U12 uses the package's wider
# channel-0..1 pitch for the RESET-to-TEST gap caused by the intervening GND
# pin, then continues monotonically through MRQ.  The two rotated packages
# can therefore fan out without a same-layer crossing despite the mixed
# electrical directions.
SOUTH_AUTO_BANKS = (
    AutoBidirectionalBank(
        "south_oscillator",
        (None, "X2", "X4", "VDD", "RESET", "TEST", None, "IRQ"),
        None,
    ),
    AutoBidirectionalBank(
        "south_control",
        ("CI", "CO", "ON", "WR", "MRQ", "X1", "X3", None),
        None,
    ),
)

# binja-esr identifies EOL/EOH (F3h/F4h) as output buffers and EIL/EIH
# (F5h/F6h) as input buffers for the complete E0-E15 port.  The SC62015 ISA
# can update individual output-latch bits with ordinary internal-memory
# logical operations, so neither byte can safely share one external DIR pin.
WEST_AUTO_BANK = AutoBidirectionalBank(
    "west_corner",
    ("KO5", "KO4", "KO2", "KO3", "KO1", "KO0", "RXD", "TXD"),
    None,
)
E_PORT_BANKS = (
    AutoBidirectionalBank("e_port_a", _numbered("E", 8, 15, descending=True), "E_OE"),
    AutoBidirectionalBank("e_port_b", _numbered("E", 0, 7, descending=True), "E_OE"),
)
AUTO_BIDIRECTIONAL_BANKS = (
    SOUTH_AUTO_BANKS[0],
    WEST_AUTO_BANK,
    SOUTH_AUTO_BANKS[1],
    *E_PORT_BANKS,
)

CONTROL_SIGNAL_NAMES = (
    "CTRL_OE_N",
    "KEY_OE_N",
    "D_OE_N",
    "D_DIR",
    "E_OE",
)

# FPGA-driven target-side signals use the bottom copper guide. This lets IRQ
# reach U9 directly beneath the SMD CPU while the CPU-sourced south fan remains
# on F.Cu.
TARGET_BCU_SIGNAL_NAMES = ("IRQ", *KEY_INPUT_SIGNAL_NAMES)

ACTIVE_LOW_ENABLE_CONTROL_NAMES = ("CTRL_OE_N", "KEY_OE_N", "D_OE_N")
ENABLE_CONTROL_SIGNAL_NAMES = (*ACTIVE_LOW_ENABLE_CONTROL_NAMES, "E_OE")

DIGITAL_CPU_SIGNAL_NAMES = (
    *(signal for bank in BANKS for signal in bank.signals if signal is not None),
    *(signal for bank in AUTO_BIDIRECTIONAL_BANKS for signal in bank.signals if signal is not None),
)


def _gpio_sort_key(name: str) -> tuple[str, int]:
    return (name[0], int(name[1:]))


# This tester deliberately uses the unrestricted Au2 element.  It needs 103
# GPIOs, while an Ft2-stacked design has only 78 available after applying the
# canonical Ft profile's 26 Bank-A exclusions.
AU2_GPIO_NAMES = tuple(
    sorted(
        (name for name in vars(AlchitryV2BottomElement)["source_signal_names"] if re.fullmatch(r"[AB][0-9]+", name)),
        key=_gpio_sort_key,
    )
)
FT2_RESERVED_AU2_GPIO_NAMES = tuple(
    sorted(
        (
            f"{connector}{pin}"
            for connector in ("A", "B")
            for pin in FT_PROFILE.connector_profile(connector).reserved_signal_pins()
        ),
        key=_gpio_sort_key,
    )
)

# The four CPU-sourced clocks must land on single-ended-clock-capable Au2
# pins. Per the Alchitry V2 pinout tables, those are the P members of the
# MRCC/SRCC pairs: "Single ended clocks must go to the P pin of the pair."
# FPGA-driven X2/X4 do not need clock-capable inputs.
CLOCK_SIGNAL_NAMES = ("DCLK", "ACLK", "X1", "X3")
CLOCK_CAPABLE_AU2_PINS = ("A41", "A42", "A47", "A48", "B41", "B42", "B47")

# Au2 element pins B46 and B48 are the DDR3L bank's D9_1V35/D10_1V35 nets.
# The Alchitry pinout legend states the 1.35 V pins are not 3.3 V tolerant,
# so the 3.3 V translator outputs must never use them.
NON_3V3_TOLERANT_AU2_PINS = ("B46", "B48")

# Excluding B46/B48 leaves 102 Bank A/B GPIOs for 103 nets, so E_OE moves to
# the control-connector LED0 pin (element signal L0, connector pin C29). The
# Au2 loads that FPGA pin with 330 ohm + LED to GND, which reinforces E_OE's
# safe-state pull-down and lights the LED whenever the E port is enabled.
# LED4 is unusable: the published element library ties C30 to GND.
E_OE_AU2_PIN = "L0"


CONTROL_AU2_PINS = {
    "CTRL_OE_N": "A30",
    "KEY_OE_N": "A10",
    "D_OE_N": "A42",
    "D_DIR": "A58",
    "E_OE": E_OE_AU2_PIN,
}

# These are the concrete Au2 GPIO resources that may be assigned to translated
# SC62015 signals.  Controls remain fixed, and the DDR3L-bank pins that are not
# 3.3-V tolerant are never exposed to the assignment solver.  There are 98
# translated signals and 98 eligible pins, so the assignment is necessarily a
# bijection.  CLOCK_SIGNAL_NAMES is an additional policy constraint applied by
# the assignment-lock generator; JITX's assignment graph supplies physical
# feasibility, while the versioned policy remains the electrical authority.
ASSIGNABLE_AU2_GPIO_NAMES = tuple(
    pin
    for pin in AU2_GPIO_NAMES
    if pin not in set(CONTROL_AU2_PINS.values())
    and pin not in set(NON_3V3_TOLERANT_AU2_PINS)
)

if len(ASSIGNABLE_AU2_GPIO_NAMES) != 98:
    raise AssertionError("translated SC62015 signals require exactly 98 assignable Au2 GPIOs")


def _load_assigned_au2_pins() -> dict[str, str]:
    """Use the static electrical assignment as the selected Au2 pin map."""
    result = dict(CONTROL_AU2_PINS)
    assigned_pins = {signal: row.au2_pin for signal, row in CONNECTION_BY_SIGNAL.items()}
    expected = set(DIGITAL_CPU_SIGNAL_NAMES)
    if set(assigned_pins) != expected or len(assigned_pins) != len(set(assigned_pins.values())):
        raise AssertionError("assignment snapshot must be a unique translated-signal pin bijection")
    if set(assigned_pins.values()) != set(ASSIGNABLE_AU2_GPIO_NAMES):
        raise AssertionError("assignment snapshot must use the canonical safe Au2 GPIO pool")
    result.update(assigned_pins)
    if len(result) != 103 or len(set(result.values())) != 103:
        raise ValueError("all 103 final assignments must use distinct pins")
    if any(result[signal] not in CLOCK_CAPABLE_AU2_PINS for signal in CLOCK_SIGNAL_NAMES):
        raise ValueError("clock signals must use single-ended-clock-capable Au2 pins")
    return result


AU2_PIN_BY_LOGICAL_SIGNAL = _load_assigned_au2_pins()
AU2_CORRIDOR_SIGNALS = {
    corridor: tuple(
        signal for signal, pin in AU2_PIN_BY_LOGICAL_SIGNAL.items() if (pin[0], int(pin[1:]) % 2) == corridor
    )
    for corridor in (("A", 0), ("A", 1), ("B", 0), ("B", 1))
}
UNUSED_AU2_GPIO_NAMES = tuple(pin for pin in AU2_GPIO_NAMES if pin not in set(AU2_PIN_BY_LOGICAL_SIGNAL.values()))


def signal_to_net_name(signal: str) -> str:
    return signal.replace("_N", "n").replace("_", "-")

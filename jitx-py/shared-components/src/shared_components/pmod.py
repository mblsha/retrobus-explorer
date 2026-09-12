from __future__ import annotations

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

PMOD_PIN_COUNT = 12
PMOD_PITCH = 2.54
PMOD_ROW_SPACING = 2.54
PMOD_PAD_DIAMETER = 1.6
PMOD_HOLE_DIAMETER = 1.0
PMOD_SOLDERMASK_DIAMETER = 1.8
PMOD_BODY_SIZE = (5.0, 15.2)
PMOD_INTERFACE_SPEC_URL = (
    "https://digilent.com/reference/_media/reference/pmod/pmod-interface-specification-1_3_1.pdf"
)

# Canonical names for the generic 12-pin PMOD interface. Protocol-specific
# aliases belong to the selected cable mapping, not the connector itself.
PMOD_PIN_NAMES = {
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
PMOD_PIN_ROLES = {
    pin: "data" if name.startswith("IO") else "ground" if name == "GND" else "power"
    for pin, name in PMOD_PIN_NAMES.items()
}
PMOD_DATA_PINS = tuple(pin for pin, role in PMOD_PIN_ROLES.items() if role == "data")
PMOD_GROUND_PINS = tuple(pin for pin, role in PMOD_PIN_ROLES.items() if role == "ground")
PMOD_VCC_PINS = tuple(pin for pin, role in PMOD_PIN_ROLES.items() if role == "power")
PMOD_POWER_PINS = tuple(pin for pin, role in PMOD_PIN_ROLES.items() if role != "data")
PMOD_IO_TO_PIN = {io: pin for io, pin in enumerate(PMOD_DATA_PINS, start=1)}

# PMOD uses two rows of six pins. Looking down onto the connector footprint,
# pins 1..6 occupy the pin-1 row and pins 7..12 the second row.
PMOD_PAD_CENTERS = {
    pin: (
        -PMOD_ROW_SPACING / 2.0 if pin <= 6 else PMOD_ROW_SPACING / 2.0,
        (2.5 - ((pin - 1) % 6)) * PMOD_PITCH,
    )
    for pin in range(1, PMOD_PIN_COUNT + 1)
}


def pth_soldermask_openings() -> tuple[Soldermask, Soldermask]:
    return (
        Soldermask(Circle(diameter=PMOD_SOLDERMASK_DIAMETER), side=Side.Top),
        Soldermask(Circle(diameter=PMOD_SOLDERMASK_DIAMETER), side=Side.Bottom),
    )


class PmodPthPad(Pad):
    shape = Circle(diameter=PMOD_PAD_DIAMETER)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=PMOD_HOLE_DIAMETER))
        self.top_soldermask, self.bottom_soldermask = pth_soldermask_openings()


class PmodHeader2x6Landpattern(Landpattern):
    def __init__(self):
        for pin, position in PMOD_PAD_CENTERS.items():
            setattr(self, f"p{pin}", PmodPthPad().at(*position))

        half_width = PMOD_BODY_SIZE[0] / 2.0
        half_height = PMOD_BODY_SIZE[1] / 2.0
        self.outline = Silkscreen(
            Polyline(
                0.2,
                [
                    (-half_width, -half_height),
                    (-half_width, half_height),
                    (half_width, half_height),
                    (half_width, -half_height),
                    (-half_width, -half_height),
                ],
            )
        )
        pin_one_x, pin_one_y = PMOD_PAD_CENTERS[1]
        self.pin_one = Silkscreen(Circle(diameter=0.5).at(pin_one_x - 1.0, pin_one_y + 0.8))
        self.courtyard = Courtyard(rectangle(PMOD_BODY_SIZE[0] + 0.5, PMOD_BODY_SIZE[1] + 0.5))


class PmodHeader2x6(Component):
    """Protocol-neutral 2x6 through-hole header with canonical PMOD numbering."""

    p = [Port() for _ in range(PMOD_PIN_COUNT)]

    manufacturer = "Generic"
    mpn = "generic-male-2x6-2.54mm-th-pmod"
    description = (
        "Generic 2x6 2.54 mm through-hole straight or right-angle male header "
        "with canonical PMOD pin numbering"
    )
    reference_designator_prefix = "J"
    value = "PMOD 2x6"

    def __init__(self):
        self.landpattern = PmodHeader2x6Landpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.p[index]]), right=PinGroup([self.p[index + 6]]))
                for index in range(6)
            ],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping(
            {self.p[index]: getattr(self.landpattern, f"p{index + 1}") for index in range(PMOD_PIN_COUNT)}
        )

    def pin(self, number: int) -> Port:
        if not 1 <= number <= PMOD_PIN_COUNT:
            raise ValueError(f"PMOD pin must be 1..{PMOD_PIN_COUNT}, got {number}")
        return self.p[number - 1]

    def gpio(self, number: int) -> Port:
        if number not in PMOD_IO_TO_PIN:
            raise ValueError(f"PMOD GPIO must be IO1..IO8, got IO{number}")
        return self.pin(PMOD_IO_TO_PIN[number])

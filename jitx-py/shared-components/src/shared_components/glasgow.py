from __future__ import annotations

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

HCTL_PM254_PITCH = 2.54
HCTL_PM254_ROW_SPACING = 2.54
HCTL_PM254_BODY_SIZE = (5.0, 25.8)
HCTL_PM254_SOLDERMASK_DIAMETER = 1.8
HCTL_PM254_PAD_CENTERS = {
    pin: (
        -HCTL_PM254_ROW_SPACING / 2.0 if pin % 2 else HCTL_PM254_ROW_SPACING / 2.0,
        11.43 - HCTL_PM254_PITCH * ((pin - 1) // 2),
    )
    for pin in range(1, 21)
}
HCTL_PM254_OPPOSITE_SIDE_MATING_PIN = {
    pin: pin + 1 if pin % 2 else pin - 1 for pin in range(1, 21)
}

GLASGOW_PORT_PINOUT = {
    1: "SENSE",
    2: "VIO",
    3: "IO0",
    4: "GND",
    5: "IO1",
    6: "GND",
    7: "IO2",
    8: "GND",
    9: "IO3",
    10: "GND",
    11: "IO4",
    12: "GND",
    13: "IO5",
    14: "GND",
    15: "IO6",
    16: "GND",
    17: "IO7",
    18: "GND",
    19: "NC",
    20: "NC",
}
GLASGOW_GROUND_PINS = tuple(pin for pin, name in GLASGOW_PORT_PINOUT.items() if name == "GND")


def hctl_pm254_soldermask_openings() -> tuple[Soldermask, Soldermask]:
    """Return equal annular-ring openings for both connector surfaces."""

    return (
        Soldermask(
            Circle(diameter=HCTL_PM254_SOLDERMASK_DIAMETER),
            side=Side.Top,
        ),
        Soldermask(
            Circle(diameter=HCTL_PM254_SOLDERMASK_DIAMETER),
            side=Side.Bottom,
        ),
    )


class HctlPm254PthPad(Pad):
    shape = Circle(diameter=1.6)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        # A through-hole socket is soldered from the side opposite its body, so
        # its annular rings must be exposed on both board surfaces. Surface
        # features are one-sided in JITX and follow component placement; make
        # both relative sides explicit so bottom-mounted connectors still
        # export openings on F.Mask and B.Mask.
        self.top_soldermask, self.bottom_soldermask = hctl_pm254_soldermask_openings()


class HctlPm2542x10Z85Landpattern(Landpattern):
    def __init__(self):
        for pin, position in HCTL_PM254_PAD_CENTERS.items():
            setattr(self, f"p{pin}", HctlPm254PthPad().at(*position))

        half_width = HCTL_PM254_BODY_SIZE[0] / 2.0
        half_height = HCTL_PM254_BODY_SIZE[1] / 2.0
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
        self.pin_one = Silkscreen(Circle(diameter=0.5).at(-2.2, 12.2))
        self.courtyard = Courtyard(rectangle(5.5, 26.3))


class GlasgowPortConnector(Component):
    """Glasgow A/B port on the specified HCTL 2x10 female socket."""

    SENSE = Port()
    VIO = Port()
    IO = [Port() for _ in range(8)]
    GND = [Port() for _ in range(8)]
    NC = [Port() for _ in range(2)]

    manufacturer = "HCTL"
    mpn = "PM254-2-10-Z-8.5"
    lcsc_part_number = "C2897411"
    datasheet = "https://www.lcsc.com/product-detail/C2897411.html"
    description = "20-position 2.54 mm dual-row through-hole female socket for Glasgow ports A/B"
    reference_designator_prefix = "J"
    value = "PM254-2-10-Z-8.5"

    def __init__(self, *, swap_rows_for_mating: bool = False):
        self.landpattern = HctlPm2542x10Z85Landpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.SENSE]), right=PinGroup([self.VIO])),
                *[
                    Row(left=PinGroup([self.IO[index]]), right=PinGroup([self.GND[index]]))
                    for index in range(8)
                ],
                Row(left=PinGroup([self.NC[0]]), right=PinGroup([self.NC[1]])),
            ],
            config=BoxConfig(group_spacing=1),
        )

        ports_by_pin = {
            1: self.SENSE,
            2: self.VIO,
            **{3 + 2 * index: self.IO[index] for index in range(8)},
            **{4 + 2 * index: self.GND[index] for index in range(8)},
            19: self.NC[0],
            20: self.NC[1],
        }
        physical_pin_by_logical_pin = (
            HCTL_PM254_OPPOSITE_SIDE_MATING_PIN
            if swap_rows_for_mating
            else {pin: pin for pin in ports_by_pin}
        )
        self.pad_mapping = PadMapping(
            {
                port: getattr(self.landpattern, f"p{physical_pin_by_logical_pin[pin]}")
                for pin, port in ports_by_pin.items()
            }
        )

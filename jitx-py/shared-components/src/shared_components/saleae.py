from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jitx.circuit import Circuit
from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side as FeatureSide
from jitx.net import Net, Port
from jitx.placement import Placement, Side
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

SALEAE_HEADER_PITCH = 2.54
SALEAE8_HEADER_CENTER_SPACING = 13.462
SALEAE_HEADER_SOLDERMASK_DIAMETER = 1.5
SALEAE_HEADER_PAD_CENTERS = {
    pin: (
        -SALEAE_HEADER_PITCH / 2.0 if pin % 2 else SALEAE_HEADER_PITCH / 2.0,
        3.0 * SALEAE_HEADER_PITCH / 2.0 - ((pin - 1) // 2) * SALEAE_HEADER_PITCH,
    )
    for pin in range(1, 9)
}

LOGIC_MSO_SIGNAL_PAD_NUMBERS = (2, 4, 6, 8)
LOGIC_MSO_GROUND_PAD_NUMBERS = (1, 3, 5, 7)
LOGIC_MSO_HEADER_PINOUT = {
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
LOGIC_MSO_HEADER_PITCH = 2.54
LOGIC_MSO_HEADER_BODY_SIZE = (20.3, 9.0)
LOGIC_MSO_HEADER_INNER_SIZE = (18.0, 6.7)
LOGIC_MSO_HEADER_COURTYARD_SIZE = (21.3, 10.0)
LOGIC_MSO_HEADER_SOLDERMASK_DIAMETER = 1.8
LOGIC_MSO_HEADER_PAD_CENTERS = {
    pin: (
        -5.08 + LOGIC_MSO_HEADER_PITCH * ((pin - 1) // 2),
        LOGIC_MSO_HEADER_PITCH / 2.0 if pin % 2 else -LOGIC_MSO_HEADER_PITCH / 2.0,
    )
    for pin in range(1, 11)
}


def pth_soldermask_openings(diameter: float) -> tuple[Soldermask, Soldermask]:
    """Return equal soldermask openings for both faces of a through-hole pad."""

    return (
        Soldermask(Circle(diameter=diameter), side=FeatureSide.Top),
        Soldermask(Circle(diameter=diameter), side=FeatureSide.Bottom),
    )


class SaleaeProbePthPad(Pad):
    shape = Circle(diameter=1.4)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        self.top_soldermask, self.bottom_soldermask = pth_soldermask_openings(SALEAE_HEADER_SOLDERMASK_DIAMETER)


class SignalGroundHeader2x4(Component):
    GND = Port()
    p0 = Port()
    p1 = Port()
    p2 = Port()
    p3 = Port()

    reference_designator_prefix = "J"
    value = "~"

    def __init__(self, *, landpattern: Any, manufacturer: str, mpn: str, description: str, value: str):
        self.manufacturer = manufacturer
        self.mpn = mpn
        self.description = description
        self.value = value
        self.landpattern = landpattern
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.GND]), right=PinGroup([self.p3])),
                Row(right=PinGroup([self.p2])),
                Row(right=PinGroup([self.p1])),
                Row(right=PinGroup([self.p0])),
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping(
            {
                self.GND: (
                    self.landpattern.p1,
                    self.landpattern.p3,
                    self.landpattern.p5,
                    self.landpattern.p7,
                ),
                self.p0: self.landpattern.p8,
                self.p1: self.landpattern.p6,
                self.p2: self.landpattern.p4,
                self.p3: self.landpattern.p2,
            }
        )


class SaleaeProbeHeaderLandpattern(Landpattern):
    def __init__(self):
        for pin, position in SALEAE_HEADER_PAD_CENTERS.items():
            setattr(self, f"p{pin}", SaleaeProbePthPad().at(*position))
        half_w = SALEAE_HEADER_PITCH
        half_h = 2.0 * SALEAE_HEADER_PITCH
        self.outline = Silkscreen(
            Polyline(
                0.153,
                [
                    (-half_w, -half_h),
                    (-half_w, half_h),
                    (half_w, half_h),
                    (half_w, -half_h),
                    (-half_w, -half_h),
                ],
            )
        )


class SaleaeProbeHeader2x4(SignalGroundHeader2x4):
    def __init__(self):
        super().__init__(
            landpattern=SaleaeProbeHeaderLandpattern(),
            manufacturer="Generic",
            mpn="generic-2x4-2.54mm-th",
            description="Generic 2x4 2.54 mm Saleae-compatible probe header",
            value="8X2-pin-header",
        )


class SaleaeMaleHeader2x4(SignalGroundHeader2x4):
    """Male 2x4 header for the Saleae Logic/Logic Pro Gen 2 harness."""

    manufacturer = "Generic"
    mpn = "generic-male-2x4-2.54mm-th"
    description = "Male 2x4 2.54 mm header for Saleae Logic Pro 8 Gen 2 harness"
    value = "2x4 male Saleae header"

    def __init__(self):
        super().__init__(
            landpattern=SaleaeProbeHeaderLandpattern(),
            manufacturer=self.manufacturer,
            mpn=self.mpn,
            description=self.description,
            value=self.value,
        )


class Saleae8(Circuit):
    """Paired Saleae connector with the exact spacing used by the Au1 element."""

    gnd = Port()
    data = [Port() for _ in range(8)]

    def __init__(
        self,
        *,
        header_factory: Callable[[], SignalGroundHeader2x4] = SaleaeProbeHeader2x4,
        text_angle: float = 0.0,
        show_labels: bool = True,
    ):
        super().__init__()
        self.upper = header_factory()
        self.lower = header_factory()

        lower_ports = (self.lower.p0, self.lower.p1, self.lower.p2, self.lower.p3)
        upper_ports = (self.upper.p0, self.upper.p1, self.upper.p2, self.upper.p3)
        self.nets = [
            Net() + self.gnd + self.upper.GND + self.lower.GND,
            *(
                Net(name=f"SALEAE{channel}")
                + self.data[channel]
                + (lower_ports[channel] if channel < 4 else upper_ports[channel - 4])
                for channel in range(8)
            ),
        ]

        half_spacing = SALEAE8_HEADER_CENTER_SPACING / 2.0
        self.place(
            self.upper,
            Placement((0.0, half_spacing), on=Side.Top),
        )
        self.place(
            self.lower,
            Placement((0.0, -half_spacing), on=Side.Top),
        )

        if show_labels:
            for index in range(4):
                offset = SALEAE_HEADER_PITCH * index
                self += Silkscreen(
                    Text(str(7 - index), 1.5).at(3.5, half_spacing + 3.8 - offset, rotate=text_angle),
                    side=FeatureSide.Top,
                )
                self += Silkscreen(
                    Text(str(3 - index), 1.5).at(3.5, -half_spacing + 3.8 - offset, rotate=text_angle),
                    side=FeatureSide.Top,
                )


class LogicMsoHeaderPthPad(Pad):
    shape = Circle(diameter=1.6)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.1))
        self.top_soldermask, self.bottom_soldermask = pth_soldermask_openings(LOGIC_MSO_HEADER_SOLDERMASK_DIAMETER)


class LogicMsoHeaderLandpattern(Landpattern):
    p9: Pad
    p10: Pad

    """Nextron Z-231011810106 / LCSC C93713 keyed 2x5 header."""

    def __init__(self):
        for pin, position in LOGIC_MSO_HEADER_PAD_CENTERS.items():
            setattr(self, f"p{pin}", LogicMsoHeaderPthPad().at(*position))

        half_width = LOGIC_MSO_HEADER_BODY_SIZE[0] / 2.0
        half_height = LOGIC_MSO_HEADER_BODY_SIZE[1] / 2.0
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
        self.pin_one = Silkscreen(Circle(diameter=0.6).at(-8.9, 3.2))
        self.courtyard = Courtyard(rectangle(*LOGIC_MSO_HEADER_COURTYARD_SIZE))


class LogicMsoDigitalHeader2x5(Component):
    """Logic MSO single-ended Digital Probe mating header."""

    data = [Port() for _ in range(4)]
    GND = Port()
    DNC = [Port() for _ in range(2)]

    manufacturer = "Nextron"
    mpn = "Z-231011810106"
    lcsc_part_number = "C93713"
    datasheet = "https://www.lcsc.com/product-detail/C93713.html"
    description = "Keyed 10-position 2.54 mm through-hole IDC header for Logic MSO Digital Probe"
    reference_designator_prefix = "J"
    value = "Z-231011810106"

    def __init__(self):
        self.landpattern = LogicMsoHeaderLandpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.data[0]]), right=PinGroup([self.GND])),
                Row(left=PinGroup([self.data[1]])),
                Row(left=PinGroup([self.data[2]])),
                Row(left=PinGroup([self.data[3]])),
                Row(left=PinGroup([self.DNC[0]]), right=PinGroup([self.DNC[1]])),
            ],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping(
            {
                self.GND: tuple(getattr(self.landpattern, f"p{pin}") for pin in LOGIC_MSO_GROUND_PAD_NUMBERS),
                **{
                    self.data[index]: getattr(self.landpattern, f"p{pin}")
                    for index, pin in enumerate(LOGIC_MSO_SIGNAL_PAD_NUMBERS)
                },
                self.DNC[0]: self.landpattern.p9,
                self.DNC[1]: self.landpattern.p10,
            }
        )

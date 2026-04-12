from __future__ import annotations

from typing import Any

from jitx.component import Component
from jitx.feature import Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.primitive import Circle, Polyline
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class SaleaeProbePthPad(Pad):
    shape = Circle(diameter=1.4)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        self.soldermask = Soldermask(Circle(diameter=1.5))


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
        self.p1 = SaleaeProbePthPad().at(-1.27, 3.81)
        self.p2 = SaleaeProbePthPad().at(1.27, 3.81)
        self.p3 = SaleaeProbePthPad().at(-1.27, 1.27)
        self.p4 = SaleaeProbePthPad().at(1.27, 1.27)
        self.p5 = SaleaeProbePthPad().at(-1.27, -1.27)
        self.p6 = SaleaeProbePthPad().at(1.27, -1.27)
        self.p7 = SaleaeProbePthPad().at(-1.27, -3.81)
        self.p8 = SaleaeProbePthPad().at(1.27, -3.81)
        half_w = 2.54
        half_h = 5.08
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

from __future__ import annotations

from typing import Any

from jitx.component import Component
from jitx.feature import Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.primitive import Circle, Polyline
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class DSLabPthPad(Pad):
    shape = Circle(diameter=1.0)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=0.7))
        self.soldermask = Soldermask(Circle(diameter=0.9))


class SaleaeProbePthPad(Pad):
    shape = Circle(diameter=1.4)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        self.soldermask = Soldermask(Circle(diameter=1.5))


class SignalGroundHeader2x4(Component):
    # Shared semantic wrapper for the `GND + p0..p3` two-column headers used
    # by both the Saleae side and the DSLab side of the adapter.
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
    # Exact port of the archived `PIN_HDR_8` KiCad footprint used by the
    # Stanza Saleae adapter board.
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
    # Closest Python equivalent of the generic `pin-header(8, 2)` used by
    # `components/Saleae/saleae8`.
    def __init__(self):
        super().__init__(
            landpattern=SaleaeProbeHeaderLandpattern(),
            manufacturer="Generic",
            mpn="generic-2x4-2.54mm-th",
            description="Generic 2x4 2.54 mm Saleae-compatible probe header",
            value="8X2-pin-header",
        )


class DSLabFemaleHeaderLandpattern(Landpattern):
    # Direct port of the hand-written `pcb-landpattern lp` in
    # `jitx/saleae-dslab-adapter.stanza`.
    def __init__(self):
        self.p1 = DSLabPthPad().at(-1.905, 0.635)
        self.p2 = DSLabPthPad().at(-1.905, -0.635)
        self.p3 = DSLabPthPad().at(-0.635, 0.635)
        self.p4 = DSLabPthPad().at(-0.635, -0.635)
        self.p5 = DSLabPthPad().at(0.635, 0.635)
        self.p6 = DSLabPthPad().at(0.635, -0.635)
        self.p7 = DSLabPthPad().at(1.905, 0.635)
        self.p8 = DSLabPthPad().at(1.905, -0.635)
        case_width = 5.48
        case_height = 3.0
        self.outline = Silkscreen(
            Polyline(
                0.2,
                [
                    (-case_width / 2.0, -case_height / 2.0),
                    (-case_width / 2.0, case_height / 2.0),
                    (case_width / 2.0, case_height / 2.0),
                    (case_width / 2.0, -case_height / 2.0),
                    (-case_width / 2.0, -case_height / 2.0),
                ],
            )
        )


class DSLabFemaleHeader2x4(SignalGroundHeader2x4):
    # Direct port of `dslab-component` in `jitx/saleae-dslab-adapter.stanza`.
    def __init__(self):
        super().__init__(
            landpattern=DSLabFemaleHeaderLandpattern(),
            manufacturer="DEALON",
            mpn="DW127R-22-08-34",
            description=(
                "1.27mm 1.27mm Double Row 1A 8P Direct Insert 2x4P 3.4mm Top Square Hole Plugin"
            ),
            value="DW127R-22-08-34",
        )

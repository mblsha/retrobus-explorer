from __future__ import annotations

from jitx.feature import Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad
from jitx.shapes.primitive import Circle, Polyline
from retrobus_jitx_parts.saleae import SignalGroundHeader2x4


class DSLabPthPad(Pad):
    shape = Circle(diameter=1.0)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=0.7))
        self.soldermask = Soldermask(Circle(diameter=0.9))


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

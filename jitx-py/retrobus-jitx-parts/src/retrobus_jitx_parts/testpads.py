from __future__ import annotations

from jitx.component import Component
from jitx.feature import Cutout, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.primitive import Circle
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class ProbePthPad3mm(Pad):
    shape = Circle(diameter=3.0)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.5))
        self.soldermask = Soldermask(Circle(diameter=2.9))


class GndTestpads(Component):
    GND = Port()
    reference_designator_prefix = "TP"
    value = "~"

    def __init__(self, *, diameter: float, width: float, height: float):
        class _Landpattern(Landpattern):
            p1 = ProbePthPad3mm().at(width / 2.0 - diameter, height / 2.0 - diameter)
            p2 = ProbePthPad3mm().at(width / 2.0 - diameter, -height / 2.0 + diameter)
            p3 = ProbePthPad3mm().at(-width / 2.0 + diameter, height / 2.0 - diameter)
            p4 = ProbePthPad3mm().at(-width / 2.0 + diameter, -height / 2.0 + diameter)

        self.landpattern = _Landpattern()
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([self.GND]))], config=BoxConfig())
        self.pad_mapping = PadMapping(
            {
                self.GND: [
                    self.landpattern.p1,
                    self.landpattern.p2,
                    self.landpattern.p3,
                    self.landpattern.p4,
                ]
            }
        )


class TestPadPad(Pad):
    shape = Circle(diameter=3.0)

    def __init__(self):
        self.soldermask = Soldermask(Circle(diameter=2.9))


class SignalTestPad(Component):
    p = Port()
    reference_designator_prefix = "TP"
    value = "~"

    def __init__(self):
        class _Landpattern(Landpattern):
            pad = TestPadPad().at(0.0, 0.0)

        self.landpattern = _Landpattern()
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([self.p]))], config=BoxConfig())
        self.pad_mapping = PadMapping({self.p: self.landpattern.pad})

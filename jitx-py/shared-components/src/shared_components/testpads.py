from __future__ import annotations

from functools import cache

from jitx.component import Component
from jitx.feature import Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side
from jitx.net import Port
from jitx.shapes.primitive import Circle, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class ProbePthPad3mm(Pad):
    shape = Circle(diameter=3.0)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.5))
        self.soldermask = Soldermask(Circle(diameter=2.9))


DEFAULT_PTH_SOLDERMASK_EXPANSION = 0.05
DEFAULT_GND_MARKING_SIZE = 0.8


class GroundedPthPad(Pad):
    """Plated grounded hole with its complete annulus exposed on both faces."""

    def __init__(
        self,
        *,
        diameter: float,
        hole_diameter: float,
        soldermask_expansion: float = DEFAULT_PTH_SOLDERMASK_EXPANSION,
    ):
        mask_diameter = diameter + 2.0 * soldermask_expansion
        self.shape = Circle(diameter=diameter)
        self.cutout = Cutout(Circle(diameter=hole_diameter))
        self.soldermask_top = Soldermask(Circle(diameter=mask_diameter), side=Side.Top)
        self.soldermask_bottom = Soldermask(Circle(diameter=mask_diameter), side=Side.Bottom)


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


@cache
def gnd_testpads_class(
    *,
    diameter: float,
    width: float,
    height: float,
    hole_diameter: float = 1.5,
    soldermask_expansion: float = DEFAULT_PTH_SOLDERMASK_EXPANSION,
    mark_ground: bool = True,
) -> type[Component]:
    """Create grounded corner holes with exposed annuli on both PCB faces."""

    pad_x = width / 2.0 - diameter
    pad_y = height / 2.0 - diameter
    label_offset = diameter / 2.0 + DEFAULT_GND_MARKING_SIZE
    upper_label_y = pad_y - label_offset
    lower_label_y = -pad_y + label_offset

    class _Landpattern(Landpattern):
        p1 = GroundedPthPad(
            diameter=diameter,
            hole_diameter=hole_diameter,
            soldermask_expansion=soldermask_expansion,
        ).at(pad_x, pad_y)
        p2 = GroundedPthPad(
            diameter=diameter,
            hole_diameter=hole_diameter,
            soldermask_expansion=soldermask_expansion,
        ).at(pad_x, -pad_y)
        p3 = GroundedPthPad(
            diameter=diameter,
            hole_diameter=hole_diameter,
            soldermask_expansion=soldermask_expansion,
        ).at(-pad_x, pad_y)
        p4 = GroundedPthPad(
            diameter=diameter,
            hole_diameter=hole_diameter,
            soldermask_expansion=soldermask_expansion,
        ).at(-pad_x, -pad_y)

        if mark_ground:
            gnd_label_top_1 = Silkscreen(Text("GND", DEFAULT_GND_MARKING_SIZE).at(pad_x, upper_label_y), side=Side.Top)
            gnd_label_bottom_1 = Silkscreen(
                Text("GND", DEFAULT_GND_MARKING_SIZE).at(pad_x, upper_label_y), side=Side.Bottom
            )
            gnd_label_top_2 = Silkscreen(Text("GND", DEFAULT_GND_MARKING_SIZE).at(pad_x, lower_label_y), side=Side.Top)
            gnd_label_bottom_2 = Silkscreen(
                Text("GND", DEFAULT_GND_MARKING_SIZE).at(pad_x, lower_label_y), side=Side.Bottom
            )
            gnd_label_top_3 = Silkscreen(Text("GND", DEFAULT_GND_MARKING_SIZE).at(-pad_x, upper_label_y), side=Side.Top)
            gnd_label_bottom_3 = Silkscreen(
                Text("GND", DEFAULT_GND_MARKING_SIZE).at(-pad_x, upper_label_y), side=Side.Bottom
            )
            gnd_label_top_4 = Silkscreen(Text("GND", DEFAULT_GND_MARKING_SIZE).at(-pad_x, lower_label_y), side=Side.Top)
            gnd_label_bottom_4 = Silkscreen(
                Text("GND", DEFAULT_GND_MARKING_SIZE).at(-pad_x, lower_label_y), side=Side.Bottom
            )

    class _GndTestpads(Component):
        GND = Port()
        reference_designator_prefix = "TP"
        value = "GND MOUNT"
        description = "Grounded plated mounting holes with exposed annuli and two-sided GND markings"

        def __init__(self):
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

    _GndTestpads.__name__ = f"GndTestpads_{width:g}x{height:g}_{diameter:g}mm_{hole_diameter:g}mmHole".replace(".", "p")
    return _GndTestpads


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

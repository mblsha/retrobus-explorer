from __future__ import annotations

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

from src.geometry import (
    ULN_BOARD_BOUNDS,
    ULN_COMPONENT_CUTOUT_BOUNDS,
    ULN_COMPONENT_CUTOUT_RADIUS,
    ULN_H_POSITIONS,
    ULN_HOLE_DIAMETER,
    ULN_PAD_DIAMETER,
    ULN_V_POSITIONS,
)


class UlnInterfacePad(Pad):
    shape = Circle(diameter=ULN_PAD_DIAMETER)

    def __init__(self):
        mask_diameter = ULN_PAD_DIAMETER + 0.20
        self.cutout = Cutout(Circle(diameter=ULN_HOLE_DIAMETER))
        self.soldermask_top = Soldermask(Circle(diameter=mask_diameter), side=Side.Top)
        self.soldermask_bottom = Soldermask(Circle(diameter=mask_diameter), side=Side.Bottom)


class Uln2003DriverInterfaceLandpattern(Landpattern):
    def __init__(self):
        self.h1 = UlnInterfacePad().at(*ULN_H_POSITIONS[0])
        self.h2 = UlnInterfacePad().at(*ULN_H_POSITIONS[1])
        self.h3 = UlnInterfacePad().at(*ULN_H_POSITIONS[2])
        self.h4 = UlnInterfacePad().at(*ULN_H_POSITIONS[3])
        self.v1 = UlnInterfacePad().at(*ULN_V_POSITIONS[0])
        self.v2 = UlnInterfacePad().at(*ULN_V_POSITIONS[1])
        self.v3 = UlnInterfacePad().at(*ULN_V_POSITIONS[2])
        self.v4 = UlnInterfacePad().at(*ULN_V_POSITIONS[3])

        cutout_left, cutout_bottom, cutout_right, cutout_top = ULN_COMPONENT_CUTOUT_BOUNDS
        self.component_clearance_cutout = Cutout(
            rectangle(
                cutout_right - cutout_left,
                cutout_top - cutout_bottom,
                radius=ULN_COMPONENT_CUTOUT_RADIUS,
            ).at(
                (cutout_left + cutout_right) / 2.0,
                (cutout_bottom + cutout_top) / 2.0,
            )
        )

        left, bottom, right, top = ULN_BOARD_BOUNDS
        outline_points = [(left, bottom), (left, top), (right, top), (right, bottom), (left, bottom)]
        self.module_outline = Silkscreen(Polyline(0.20, outline_points))
        for name, label, position in zip(
            ("h1_label", "h2_label", "v5_label", "gnd_label"),
            ("H1", "H2", "5V", "GND"),
            ULN_H_POSITIONS,
            strict=True,
        ):
            setattr(self, name, Silkscreen(Text(label, 1.0).at(position[0], position[1] - 1.8)))
        for index, position in enumerate(ULN_V_POSITIONS, start=1):
            setattr(
                self,
                f"in{index}_label",
                Silkscreen(Text(f"IN{index}", 1.0).at(position[0] - 2.5, position[1])),
            )
        self.courtyard = Courtyard(rectangle(right - left, top - bottom).at((left + right) / 2.0, (bottom + top) / 2.0))


class Uln2003DriverInterface(Component):
    IN = [Port() for _ in range(4)]
    H1 = Port()
    H2 = Port()
    V5 = Port()
    GND = Port()

    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "ULN2003-module-L-interface"
    description = "Measured L-shaped 8-pin interface and component clearance for a ULN2003 driver module"
    value = "ULN2003 DRIVER MODULE"

    def __init__(self):
        self.landpattern = Uln2003DriverInterfaceLandpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.IN[index]])) for index in range(4)]
            + [
                Row(left=PinGroup([self.H1]), right=PinGroup([self.H2])),
                Row(left=PinGroup([self.V5]), right=PinGroup([self.GND])),
            ],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping(
            {
                self.H1: self.landpattern.h1,
                self.H2: self.landpattern.h2,
                self.V5: self.landpattern.h3,
                self.GND: self.landpattern.h4,
                self.IN[0]: self.landpattern.v1,
                self.IN[1]: self.landpattern.v2,
                self.IN[2]: self.landpattern.v3,
                self.IN[3]: self.landpattern.v4,
            }
        )

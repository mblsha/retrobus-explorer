from __future__ import annotations

from typing import cast

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


def pad_attr(obj: object, name: str) -> Pad:
    return cast(Pad, getattr(obj, name))


class HeaderPthPad(Pad):
    shape = Circle(diameter=1.4)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        self.soldermask_top = Soldermask(Circle(diameter=1.5), side=Side.Top)
        self.soldermask_bottom = Soldermask(Circle(diameter=1.5), side=Side.Bottom)


class PinHeader2x3Landpattern(Landpattern):
    # Direct port of the archived `PIN_HDR_6` KiCad footprint.
    # Python JITX exports this bottom-side through-hole header mirrored in Y,
    # so the source pad rows are intentionally flipped to preserve KiCad parity.
    def __init__(self):
        self.p1 = HeaderPthPad().at(-1.27, 2.54)
        self.p2 = HeaderPthPad().at(1.27, 2.54)
        self.p3 = HeaderPthPad().at(-1.27, 0.0)
        self.p4 = HeaderPthPad().at(1.27, 0.0)
        self.p5 = HeaderPthPad().at(-1.27, -2.54)
        self.p6 = HeaderPthPad().at(1.27, -2.54)
        self.outline = Silkscreen(
            Polyline(
                0.153,
                [(-2.54, -3.81), (-2.54, 3.81), (2.54, 3.81), (2.54, -3.81), (-2.54, -3.81)],
            )
        )
        self.courtyard = Courtyard(rectangle(5.08, 7.62))


class PinHeader2x3(Component):
    p = [Port() for _ in range(6)]
    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "generic-6x2-2.54mm-th"
    description = "Generic 2x3 2.54 mm through-hole header"
    value = "6X2-pin-header"

    def __init__(self):
        self.landpattern = PinHeader2x3Landpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]])),
                Row(left=PinGroup([self.p[2]]), right=PinGroup([self.p[3]])),
                Row(left=PinGroup([self.p[4]]), right=PinGroup([self.p[5]])),
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping(
            {
                self.p[0]: self.landpattern.p1,
                self.p[1]: self.landpattern.p2,
                self.p[2]: self.landpattern.p3,
                self.p[3]: self.landpattern.p4,
                self.p[4]: self.landpattern.p5,
                self.p[5]: self.landpattern.p6,
            }
        )


class Cap0402Pad(Pad):
    shape = rectangle(0.6, 0.280277563773199)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.7, 0.380277563773199))
        self.paste = Paste(rectangle(0.6, 0.280277563773199))


class Cap0402Landpattern(Landpattern):
    # Direct port of the archived `Pkg0402` footprint.
    def __init__(self):
        self.p1 = Cap0402Pad().at(0.0, -0.4098612181134)
        self.p2 = Cap0402Pad().at(0.0, 0.4098612181134)
        self.ref_text = Silkscreen(Text(">REF", 0.6).at(0.75, 0.0, rotate=90))
        self.courtyard = Courtyard(rectangle(0.9, 1.4))


class Cap0402(Component):
    p = [Port() for _ in range(2)]
    reference_designator_prefix = "C"
    manufacturer = "Generic"
    mpn = "generic-0402-cap"
    description = "Generic 0402 capacitor"
    value = "10uF"

    def __init__(self):
        self.landpattern = Cap0402Landpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]]))],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping({self.p[0]: self.landpattern.p1, self.p[1]: self.landpattern.p2})


class Txb0108PwrPad(Pad):
    shape = rectangle(0.364, 1.742)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.466, 1.844))
        self.paste = Paste(rectangle(0.466, 1.844))


class Txb0108PwrLandpattern(Landpattern):
    # Direct footprint port of `components/TXB0108PWR.stanza` / archived `LP_2`.
    # Python JITX exports this custom-pad footprint mirrored in Y, so the source
    # rows and pin-1 marker are intentionally flipped to preserve KiCad parity.
    def __init__(self):
        for index in range(10):
            x = -2.925 + 0.65 * index
            pad = Txb0108PwrPad().at(x, -2.87)
            setattr(self, f"p{index + 1}", pad)
        for index in range(10):
            x = 2.925 - 0.65 * index
            pad = Txb0108PwrPad().at(x, 2.87)
            setattr(self, f"p{index + 11}", pad)

        self.ref_text = Silkscreen(Text(">REF", 0.5).at(-0.75, 5.498))
        self.outline = Silkscreen(
            Polyline(0.152, [(-3.326, -1.771), (-3.326, 1.772), (3.326, 1.772), (3.326, -1.771), (-3.326, -1.771)])
        )
        self.pin1 = Silkscreen(Circle(diameter=0.3).at(-3.559, -2.87))
        self.courtyard = Courtyard(rectangle(6.804, 7.585))


class Txb0108Pwr(Component):
    # Direct component port of `components/TXB0108PWR.stanza`.
    A1 = Port()
    VCCA = Port()
    A2 = Port()
    A3 = Port()
    A4 = Port()
    A5 = Port()
    A6 = Port()
    A7 = Port()
    A8 = Port()
    OE = Port()
    GND = Port()
    B8 = Port()
    B7 = Port()
    B6 = Port()
    B5 = Port()
    B4 = Port()
    B3 = Port()
    B2 = Port()
    VCCB = Port()
    B1 = Port()

    manufacturer = "Texas Instruments"
    mpn = "TXB0108PWR"
    datasheet = "https://www.lcsc.com/datasheet/lcsc_datasheet_1810151720_Texas-Instruments-TXB0108PWR_C53406.pdf"
    description = "8-bit dual-supply auto-direction translating transceiver"
    reference_designator_prefix = "U"
    value = "TXB0108PWR"

    def __init__(self):
        self.landpattern = Txb0108PwrLandpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.A1]), right=PinGroup([self.B1])),
                Row(left=PinGroup([self.VCCA]), right=PinGroup([self.VCCB])),
                Row(left=PinGroup([self.A2]), right=PinGroup([self.B2])),
                Row(left=PinGroup([self.A3]), right=PinGroup([self.B3])),
                Row(left=PinGroup([self.A4]), right=PinGroup([self.B4])),
                Row(left=PinGroup([self.A5]), right=PinGroup([self.B5])),
                Row(left=PinGroup([self.A6]), right=PinGroup([self.B6])),
                Row(left=PinGroup([self.A7]), right=PinGroup([self.B7])),
                Row(left=PinGroup([self.A8]), right=PinGroup([self.B8])),
                Row(left=PinGroup([self.OE]), right=PinGroup([self.GND])),
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping(
            {
                self.A1: pad_attr(self.landpattern, "p1"),
                self.VCCA: pad_attr(self.landpattern, "p2"),
                self.A2: pad_attr(self.landpattern, "p3"),
                self.A3: pad_attr(self.landpattern, "p4"),
                self.A4: pad_attr(self.landpattern, "p5"),
                self.A5: pad_attr(self.landpattern, "p6"),
                self.A6: pad_attr(self.landpattern, "p7"),
                self.A7: pad_attr(self.landpattern, "p8"),
                self.A8: pad_attr(self.landpattern, "p9"),
                self.OE: pad_attr(self.landpattern, "p10"),
                self.GND: pad_attr(self.landpattern, "p11"),
                self.B8: pad_attr(self.landpattern, "p12"),
                self.B7: pad_attr(self.landpattern, "p13"),
                self.B6: pad_attr(self.landpattern, "p14"),
                self.B5: pad_attr(self.landpattern, "p15"),
                self.B4: pad_attr(self.landpattern, "p16"),
                self.B3: pad_attr(self.landpattern, "p17"),
                self.B2: pad_attr(self.landpattern, "p18"),
                self.VCCB: pad_attr(self.landpattern, "p19"),
                self.B1: pad_attr(self.landpattern, "p20"),
            }
        )



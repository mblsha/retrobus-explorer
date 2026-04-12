from __future__ import annotations

from typing import Any

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
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
    # Exact port of the archived `PIN_HDR_8` KiCad footprint used by the
    # Stanza Saleae-based boards.
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


class HeaderPthPad(Pad):
    shape = Circle(diameter=1.4)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        self.soldermask = Soldermask(Circle(diameter=1.5))


class PinHeader2x10Landpattern(Landpattern):
    def __init__(self):
        pad_positions = [
            (-1.27, 11.43), (1.27, 11.43),
            (-1.27, 8.89), (1.27, 8.89),
            (-1.27, 6.35), (1.27, 6.35),
            (-1.27, 3.81), (1.27, 3.81),
            (-1.27, 1.27), (1.27, 1.27),
            (-1.27, -1.27), (1.27, -1.27),
            (-1.27, -3.81), (1.27, -3.81),
            (-1.27, -6.35), (1.27, -6.35),
            (-1.27, -8.89), (1.27, -8.89),
            (-1.27, -11.43), (1.27, -11.43),
        ]
        for index, (x, y) in enumerate(pad_positions, start=1):
            setattr(self, f'p{index}', HeaderPthPad().at(x, y))
        self.outline = Silkscreen(
            Polyline(
                0.153,
                [(-2.54, -12.7), (-2.54, 12.7), (2.54, 12.7), (2.54, -12.7), (-2.54, -12.7)],
            )
        )
        self.courtyard = Courtyard(rectangle(5.08, 25.4))


class PinHeader2x10(Component):
    # Python analogue of the generic `pin-header(20, 2)` used by
    # `jitx/espi-debug-breakout.stanza`.
    p = [Port() for _ in range(20)]
    reference_designator_prefix = 'J'
    manufacturer = 'Generic'
    mpn = 'generic-20x2-2.54mm-th'
    value = '20X2-pin-header'

    def __init__(self):
        self.landpattern = PinHeader2x10Landpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.p[2 * row]]), right=PinGroup([self.p[2 * row + 1]]))
                for row in range(10)
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping({
            self.p[index]: getattr(self.landpattern, f'p{index + 1}')
            for index in range(20)
        })


class JushuoSignalPad(Pad):
    shape = rectangle(0.3, 1.25)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.402, 1.352))
        self.paste = Paste(rectangle(0.402, 1.352))


class JushuoHoldPad(Pad):
    shape = rectangle(1.8, 2.2)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.902, 2.302))
        self.paste = Paste(rectangle(1.902, 2.302))


class JushuoAfa01S10Fca00Landpattern(Landpattern):
    # Direct footprint port of `components/JUSHUO/AFA01-S10FCA-00.stanza`.
    def __init__(self):
        signal_positions = [
            (-4.498, -2.613),
            (-3.498, -2.613),
            (-2.498, -2.613),
            (-1.498, -2.613),
            (-0.498, -2.613),
            (0.502, -2.613),
            (1.502, -2.613),
            (2.502, -2.613),
            (3.502, -2.611),
            (4.502, -2.611),
        ]
        for index, (x, y) in enumerate(signal_positions, start=1):
            setattr(self, f'p{index}', JushuoSignalPad().at(x, y))
        self.p11 = JushuoHoldPad().at(-6.901, -0.061, rotate=180)
        self.p12 = JushuoHoldPad().at(6.899, -0.061, rotate=180)
        self.outline_top = Silkscreen(Polyline(0.254, [(-8.0, 3.163), (8.0, 3.163)]))
        self.outline_left = Silkscreen(Polyline(0.254, [(-8.0, 3.163), (-8.0, 1.156)]))
        self.outline_left_lower = Silkscreen(Polyline(0.254, [(-8.0, -1.277), (-8.0, -2.111), (-4.88, -2.111)]))
        self.outline_right_lower = Silkscreen(Polyline(0.254, [(4.883, -2.111), (8.0, -2.111), (8.0, -1.273)]))
        self.outline_right = Silkscreen(Polyline(0.254, [(8.0, 1.151), (8.0, 3.163)]))
        self.courtyard = Courtyard(rectangle(16.253, 6.579))


class JushuoAfa01S10Fca00(Component):
    # Direct raw connector component port of
    # `components/JUSHUO/AFA01-S10FCA-00.stanza`.
    p = [Port() for _ in range(12)]
    manufacturer = 'JUSHUO'
    mpn = 'AFA01-S10FCA-00'
    description = 'Clamshell 10P Bottom Contact Surface Mount 1mm FFC/FPC connector'
    datasheet = 'https://www.lcsc.com/datasheet/lcsc_datasheet_2304140030_JUSHUO-AFA01-S10FCA-00_C262756.pdf'
    reference_designator_prefix = 'J'
    value = 'AFA01-S10FCA-00'

    def __init__(self):
        self.landpattern = JushuoAfa01S10Fca00Landpattern()
        rows = [Row(left=PinGroup([port])) for port in self.p[:10]]
        rows.append(Row(left=PinGroup([self.p[10]]), right=PinGroup([self.p[11]])))
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=1))
        self.pad_mapping = PadMapping({
            self.p[index]: getattr(self.landpattern, f'p{index + 1}')
            for index in range(12)
        })

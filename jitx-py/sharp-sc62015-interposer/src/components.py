from __future__ import annotations

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polygon, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class SmallRectSmdPad(Pad):
    shape = rectangle(0.3, 1.25)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.4, 1.35))
        self.paste = Paste(rectangle(0.4, 1.35))


class LargeRectSmdPad(Pad):
    shape = rectangle(2.0, 2.5)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(2.1, 2.6))
        self.paste = Paste(rectangle(2.1, 2.6))


class HDGC60PinFfcLandpattern(Landpattern):
    # Footprint-level port of `components/_0_5K-1_2X-60PWB.stanza`.
    def __init__(self):
        self.signal_pads = [SmallRectSmdPad().at(14.75 - 0.5 * index, -2.096, rotate=180) for index in range(60)]
        self.mount_pad_left = LargeRectSmdPad().at(-16.43, 0.527, rotate=180)
        self.mount_pad_right = LargeRectSmdPad().at(16.43, 0.527, rotate=180)

        self.ref_text = Silkscreen(Text('>REF', 0.5).at(-0.75, 4.477))
        self.top_outline = Silkscreen(Polyline(0.254, [(-18.041, 2.644), (18.041, 2.644), (18.041, 1.247)]))
        self.left_outline = Silkscreen(Polyline(0.254, [(-18.041, 2.644), (-18.041, 1.247), (-17.661, 1.247)]))
        self.right_outline = Silkscreen(Polyline(0.254, [(17.661, 1.247), (18.041, 1.247)]))
        self.lower_left = Silkscreen(Polyline(0.254, [(-17.406, -0.954), (-17.406, -1.547), (-15.131, -1.547)]))
        self.lower_right = Silkscreen(Polyline(0.254, [(15.131, -1.547), (17.406, -1.547), (17.406, -0.954)]))
        self.courtyard = Courtyard(rectangle(36.336, 5.543))


class HDGC60PinFfc(Component):
    # Raw connector component port of `components/_0_5K-1_2X-60PWB.stanza`.
    p = [Port() for _ in range(62)]

    manufacturer = 'HDGC'
    mpn = '0.5K-1.2X-60PWB'
    datasheet = 'https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2111151930_HDGC-0-5K-1-2X-60PWB_C2919552.pdf'
    description = '60-pin 0.5 mm bottom-contact FFC/FPC connector'
    reference_designator_prefix = 'J'
    value = '0.5K-1.2X-60PWB'

    def __init__(self):
        self.landpattern = HDGC60PinFfcLandpattern()
        rows = [Row(left=PinGroup([port])) for port in self.p[:60]]
        rows.append(Row(left=PinGroup([self.p[60]]), right=PinGroup([self.p[61]])))
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=1))

        mapping = {self.p[i]: self.landpattern.signal_pads[i] for i in range(60)}
        mapping[self.p[60]] = self.landpattern.mount_pad_left
        mapping[self.p[61]] = self.landpattern.mount_pad_right
        self.pad_mapping = PadMapping(mapping)


class TestPadPad(Pad):
    shape = Circle(diameter=3.0)

    def __init__(self):
        self.soldermask = Soldermask(Circle(diameter=2.9))


class SignalTestPad(Component):
    # Direct port of the `gen-testpad(3.0)` usage in the Stanza board.
    p = Port()
    reference_designator_prefix = 'TP'
    value = '~'

    def __init__(self):
        class _Landpattern(Landpattern):
            pad = TestPadPad().at(0.0, 0.0)

        self.landpattern = _Landpattern()
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([self.p]))], config=BoxConfig())
        self.pad_mapping = PadMapping({self.p: self.landpattern.pad})


class Sc62015LeadPad(Pad):
    shape = rectangle(1.2, 0.22)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.3, 0.32))
        self.paste = Paste(rectangle(1.2, 0.22))


class Sc62015InterposerLandpattern(Landpattern):
    # Direct footprint port of `components/SC62015B02.stanza` and archived
    # `QFN65P1400X2000X200_100N.kicad_mod`.
    # The current Python JITX KiCad export mirrors custom-pad Y coordinates, so
    # this footprint is defined with Y inverted to land on the archived KiCad
    # geometry after export.
    def __init__(self):
        self.pads = [
            *[Sc62015LeadPad().at(-8.7, 9.425 - 0.65 * index) for index in range(30)],
            *[Sc62015LeadPad().at(-6.175 + 0.65 * index, -11.7, rotate=90) for index in range(20)],
            *[Sc62015LeadPad().at(8.7, -9.425 + 0.65 * index, rotate=180) for index in range(30)],
            *[Sc62015LeadPad().at(6.175 - 0.65 * index, 11.7, rotate=270) for index in range(20)],
        ]

        self.outline_top = Silkscreen(Polyline(0.2, [(-6.5, -10.9), (6.5, -10.9)]))
        self.outline_left = Silkscreen(Polyline(0.2, [(-6.5, -10.9), (-8.1, -9.75), (-8.1, 9.75), (-6.5, 10.9)]))
        self.outline_right = Silkscreen(Polyline(0.2, [(6.5, -10.9), (8.1, -9.75), (8.1, 9.75), (6.5, 10.9)]))
        self.outline_bottom = Silkscreen(Polyline(0.2, [(-6.5, 10.9), (6.5, 10.9)]))
        self.pin1_marker = Silkscreen(Circle(diameter=0.4).at(-9.9, 9.425))
        self.body_cutout = Cutout(
            Polygon([
                (-8.15, -9.75),
                (-6.5, -11.1),
                (6.5, -11.1),
                (8.15, -9.75),
                (8.15, 9.75),
                (6.5, 11.1),
                (-6.5, 11.1),
                (-8.15, 9.75),
            ])
        )
        self.courtyard = Courtyard(rectangle(20.2, 23.8))


class Sc62015Interposer(Component):
    # Direct port of `components/SC62015B02.stanza` `pcb-component interposer`.
    A = [Port() for _ in range(19)]
    D = [Port() for _ in range(8)]
    CE = [Port() for _ in range(8)]
    DCLK = Port()
    OUT = Port()
    ACLK = Port()
    DIS = Port()
    RD = Port()
    RXD = Port()
    TXD = Port()
    RESET = Port()
    TEST = Port()
    ON = Port()
    WR = Port()
    MRQ = Port()
    GND = Port()
    VCC = Port()

    manufacturer = 'Hitachi?'
    mpn = 'SC62015B02'
    description = 'SC62015 CPU interposer footprint'
    reference_designator_prefix = 'U'
    value = '~'

    def __init__(self):
        self.landpattern = Sc62015InterposerLandpattern()

        symbol_ports = [
            self.RESET,
            self.GND,
            self.TEST,
            self.ON,
            self.WR,
            self.MRQ,
            *self.D,
            *self.A,
            self.DCLK,
            self.OUT,
            self.CE[7],
            self.CE[6],
            self.CE[5],
            self.CE[4],
            self.CE[3],
            self.CE[2],
            self.CE[1],
            self.CE[0],
            self.ACLK,
            self.DIS,
            self.RD,
            self.RXD,
            self.TXD,
            self.VCC,
        ]
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([port])) for port in symbol_ports], config=BoxConfig())

        mapping = {
            self.VCC: self.landpattern.pads[5],
            self.RESET: self.landpattern.pads[6],
            self.GND: self.landpattern.pads[7],
            self.TEST: self.landpattern.pads[8],
            self.ON: self.landpattern.pads[11],
            self.WR: self.landpattern.pads[12],
            self.MRQ: self.landpattern.pads[13],
            self.D[0]: self.landpattern.pads[22],
            self.D[1]: self.landpattern.pads[23],
            self.D[2]: self.landpattern.pads[24],
            self.D[3]: self.landpattern.pads[25],
            self.D[4]: self.landpattern.pads[26],
            self.D[5]: self.landpattern.pads[27],
            self.D[6]: self.landpattern.pads[28],
            self.D[7]: self.landpattern.pads[29],
            self.A[0]: self.landpattern.pads[30],
            self.A[1]: self.landpattern.pads[31],
            self.A[2]: self.landpattern.pads[32],
            self.A[3]: self.landpattern.pads[33],
            self.A[4]: self.landpattern.pads[34],
            self.A[5]: self.landpattern.pads[35],
            self.A[6]: self.landpattern.pads[36],
            self.A[7]: self.landpattern.pads[37],
            self.A[8]: self.landpattern.pads[38],
            self.A[9]: self.landpattern.pads[39],
            self.A[10]: self.landpattern.pads[40],
            self.A[11]: self.landpattern.pads[41],
            self.A[12]: self.landpattern.pads[42],
            self.A[13]: self.landpattern.pads[43],
            self.A[14]: self.landpattern.pads[44],
            self.A[15]: self.landpattern.pads[45],
            self.A[16]: self.landpattern.pads[46],
            self.A[17]: self.landpattern.pads[47],
            self.A[18]: self.landpattern.pads[48],
            self.DCLK: self.landpattern.pads[51],
            self.OUT: self.landpattern.pads[59],
            self.CE[7]: self.landpattern.pads[60],
            self.CE[6]: self.landpattern.pads[61],
            self.CE[5]: self.landpattern.pads[62],
            self.CE[4]: self.landpattern.pads[63],
            self.CE[3]: self.landpattern.pads[64],
            self.CE[2]: self.landpattern.pads[65],
            self.CE[1]: self.landpattern.pads[66],
            self.CE[0]: self.landpattern.pads[67],
            self.ACLK: self.landpattern.pads[68],
            self.DIS: self.landpattern.pads[69],
            self.RD: self.landpattern.pads[71],
            self.RXD: self.landpattern.pads[82],
            self.TXD: self.landpattern.pads[83],
        }
        self.pad_mapping = PadMapping(mapping)

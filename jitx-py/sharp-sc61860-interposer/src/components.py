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


class Sc61860LeadPad(Pad):
    shape = rectangle(1.2, 0.42)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.3, 0.52))
        self.paste = Paste(rectangle(1.2, 0.42))


class Sc61860InterposerLandpattern(Landpattern):
    # Direct footprint port of `components/SC61860D4x.stanza` and archived
    # `QFN80P1400X2000X200_80N.kicad_mod`.
    # The current Python JITX KiCad export mirrors custom-pad Y coordinates, so
    # this footprint is defined with Y inverted to land on the archived KiCad
    # geometry after export.
    def __init__(self):
        self.pads = [
            *[Sc61860LeadPad().at(-8.8, 9.2 - 0.8 * index) for index in range(24)],
            *[Sc61860LeadPad().at(-6.0 + 0.8 * index, -11.8, rotate=90) for index in range(16)],
            *[Sc61860LeadPad().at(8.8, -9.2 + 0.8 * index) for index in range(24)],
            *[Sc61860LeadPad().at(6.0 - 0.8 * index, 11.8, rotate=90) for index in range(16)],
        ]

        self.outline_top = Silkscreen(Polyline(0.2, [(-7.1, 10.1), (7.1, 10.1)]))
        self.outline_left = Silkscreen(Polyline(0.2, [(-7.1, 10.1), (-7.1, -10.1)]))
        self.outline_right = Silkscreen(Polyline(0.2, [(7.1, 10.1), (7.1, -10.1)]))
        self.outline_bottom = Silkscreen(Polyline(0.2, [(-7.1, -10.1), (7.1, -10.1)]))
        self.pin1_marker = Silkscreen(Circle(diameter=0.4).at(-9.85, 9.2))
        self.body_cutout = Cutout(
            Polygon([
                (-6.4, 11.2),
                (6.4, 11.2),
                (8.2, 9.6),
                (8.2, -9.6),
                (6.4, -11.2),
                (-6.4, -11.2),
                (-8.2, -9.6),
                (-8.2, 9.6),
            ])
        )
        self.courtyard = Courtyard(rectangle(20.5, 23.5))


class Sc61860Interposer(Component):
    # Direct port of `components/SC61860D4x.stanza` `pcb-component interposer`.
    A = [Port() for _ in range(16)]
    IA = [Port() for _ in range(8)]
    D = [Port() for _ in range(8)]
    FO = [Port() for _ in range(5)]
    RW = Port()
    AL = Port()
    TEST = Port()
    OSC_I = Port()
    OSC_O = Port()
    RESET = Port()
    XIN = Port()
    KON = Port()
    XOUT = Port()
    DIS = Port()
    GND = Port()
    VCC = Port()
    VGG = Port()

    manufacturer = 'Sharp'
    mpn = 'SC61860D4x'
    description = 'SC61860 CPU interposer footprint'
    reference_designator_prefix = 'U'
    value = '~'

    def __init__(self):
        self.landpattern = Sc61860InterposerLandpattern()

        symbol_ports = [
            self.A[0],
            self.RW,
            self.AL,
            self.TEST,
            self.OSC_I,
            self.OSC_O,
            self.RESET,
            self.XIN,
            self.KON,
            self.XOUT,
            self.DIS,
            *[self.IA[index] for index in range(7, -1, -1)],
            self.GND,
            self.VCC,
            self.VGG,
            *[self.D[index] for index in range(7, -1, -1)],
            *[self.FO[index] for index in range(4, -1, -1)],
            *[self.A[index] for index in range(15, 0, -1)],
        ]
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([port])) for port in symbol_ports], config=BoxConfig())

        mapping = {
            self.A[0]: self.landpattern.pads[0],
            self.RW: self.landpattern.pads[1],
            self.AL: self.landpattern.pads[2],
            self.TEST: self.landpattern.pads[3],
            self.OSC_I: self.landpattern.pads[4],
            self.OSC_O: self.landpattern.pads[5],
            self.RESET: self.landpattern.pads[6],
            self.XIN: self.landpattern.pads[7],
            self.KON: self.landpattern.pads[8],
            self.XOUT: self.landpattern.pads[9],
            self.DIS: self.landpattern.pads[10],
            self.IA[7]: self.landpattern.pads[12],
            self.IA[6]: self.landpattern.pads[13],
            self.IA[5]: self.landpattern.pads[14],
            self.IA[4]: self.landpattern.pads[15],
            self.IA[3]: self.landpattern.pads[16],
            self.IA[2]: self.landpattern.pads[17],
            self.IA[1]: self.landpattern.pads[18],
            self.IA[0]: self.landpattern.pads[19],
            self.GND: self.landpattern.pads[30],
            self.VCC: self.landpattern.pads[49],
            self.VGG: self.landpattern.pads[51],
            self.D[7]: self.landpattern.pads[52],
            self.D[6]: self.landpattern.pads[53],
            self.D[5]: self.landpattern.pads[54],
            self.D[4]: self.landpattern.pads[55],
            self.D[3]: self.landpattern.pads[56],
            self.D[2]: self.landpattern.pads[57],
            self.D[1]: self.landpattern.pads[58],
            self.D[0]: self.landpattern.pads[59],
            self.FO[4]: self.landpattern.pads[60],
            self.FO[3]: self.landpattern.pads[61],
            self.FO[2]: self.landpattern.pads[62],
            self.FO[1]: self.landpattern.pads[63],
            self.FO[0]: self.landpattern.pads[64],
            self.A[15]: self.landpattern.pads[65],
            self.A[14]: self.landpattern.pads[66],
            self.A[13]: self.landpattern.pads[67],
            self.A[12]: self.landpattern.pads[68],
            self.A[11]: self.landpattern.pads[69],
            self.A[10]: self.landpattern.pads[70],
            self.A[9]: self.landpattern.pads[71],
            self.A[8]: self.landpattern.pads[72],
            self.A[7]: self.landpattern.pads[73],
            self.A[6]: self.landpattern.pads[74],
            self.A[5]: self.landpattern.pads[75],
            self.A[4]: self.landpattern.pads[76],
            self.A[3]: self.landpattern.pads[77],
            self.A[2]: self.landpattern.pads[78],
            self.A[1]: self.landpattern.pads[79],
        }
        self.pad_mapping = PadMapping(mapping)

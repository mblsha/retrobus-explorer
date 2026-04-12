from __future__ import annotations

from jitx.component import Component
from jitx.feature import Courtyard, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Polyline, Text
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

        self.ref_text = Silkscreen(Text(">REF", 0.5).at(-0.75, 4.477))
        self.top_outline = Silkscreen(Polyline(0.254, [(-18.041, 2.644), (18.041, 2.644), (18.041, 1.247)]))
        self.left_outline = Silkscreen(Polyline(0.254, [(-18.041, 2.644), (-18.041, 1.247), (-17.661, 1.247)]))
        self.right_outline = Silkscreen(Polyline(0.254, [(17.661, 1.247), (18.041, 1.247)]))
        self.lower_left = Silkscreen(Polyline(0.254, [(-17.406, -0.954), (-17.406, -1.547), (-15.131, -1.547)]))
        self.lower_right = Silkscreen(Polyline(0.254, [(15.131, -1.547), (17.406, -1.547), (17.406, -0.954)]))
        self.courtyard = Courtyard(rectangle(36.336, 5.543))


class HDGC60PinFfc(Component):
    # Raw connector component port of `components/_0_5K-1_2X-60PWB.stanza`.
    p = [Port() for _ in range(62)]

    manufacturer = "HDGC"
    mpn = "0.5K-1.2X-60PWB"
    datasheet = "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2111151930_HDGC-0-5K-1-2X-60PWB_C2919552.pdf"
    description = "60-pin 0.5 mm bottom-contact FFC/FPC connector"
    reference_designator_prefix = "J"
    value = "0.5K-1.2X-60PWB"

    def __init__(self):
        self.landpattern = HDGC60PinFfcLandpattern()
        rows = [Row(left=PinGroup([port])) for port in self.p[:60]]
        rows.append(Row(left=PinGroup([self.p[60]]), right=PinGroup([self.p[61]])))
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=1))

        mapping = {self.p[i]: self.landpattern.signal_pads[i] for i in range(60)}
        mapping[self.p[60]] = self.landpattern.mount_pad_left
        mapping[self.p[61]] = self.landpattern.mount_pad_right
        self.pad_mapping = PadMapping(mapping)


class BigRamCardPad(Pad):
    shape = rectangle(1.9, 9.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(2.0, 10.0))
        self.paste = Paste(rectangle(2.0, 10.0))


class SmallRamCardPad(Pad):
    shape = rectangle(0.7, 9.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.8, 10.0))
        self.paste = Paste(rectangle(0.8, 10.0))


class SharpPcE500RamCardLandpattern(Landpattern):
    # Direct footprint port of `jitx/sharp-pc-e500-ram-card.stanza` and the archived `LP.kicad_mod`.
    def __init__(self):
        self.pad1 = BigRamCardPad().at(-22.3, 0.0)
        self.pad2 = BigRamCardPad().at(22.4, 0.0)
        self.small_pads = [SmallRamCardPad().at(-20.26 + 1.27 * index, 0.0) for index in range(33)]


class SharpPcE500RamCard(Component):
    # Direct port of `jitx/sharp-pc-e500-ram-card.stanza` `pcb-component ramcard`.
    VCC = Port()
    GND = Port()
    RW = Port()
    A0 = Port()
    A1 = Port()
    A2 = Port()
    A3 = Port()
    A4 = Port()
    A5 = Port()
    A6 = Port()
    A7 = Port()
    A8 = Port()
    A9 = Port()
    A10 = Port()
    A11 = Port()
    A12 = Port()
    A13 = Port()
    A14 = Port()
    A15 = Port()
    A16 = Port()
    A17 = Port()
    VCC2 = Port()
    D0 = Port()
    D1 = Port()
    D2 = Port()
    D3 = Port()
    D4 = Port()
    D5 = Port()
    D6 = Port()
    D7 = Port()
    CE1 = Port()
    CE6 = Port()
    NC = Port()
    OE = Port()

    manufacturer = "SHARP"
    mpn = "pc-e500-ram-card"
    description = "SHARP PC-E500 RAM card connector"
    reference_designator_prefix = "J"
    value = "~"

    def __init__(self):
        self.landpattern = SharpPcE500RamCardLandpattern()
        ordered_ports = [
            self.VCC,
            self.GND,
            self.RW,
            self.A0,
            self.A1,
            self.A2,
            self.A3,
            self.A4,
            self.A5,
            self.A6,
            self.A7,
            self.A8,
            self.A9,
            self.A10,
            self.A11,
            self.A12,
            self.A13,
            self.A14,
            self.A15,
            self.A16,
            self.A17,
            self.VCC2,
            self.D0,
            self.D1,
            self.D2,
            self.D3,
            self.D4,
            self.D5,
            self.D6,
            self.D7,
            self.CE1,
            self.CE6,
            self.NC,
            self.OE,
        ]
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([port])) for port in ordered_ports], config=BoxConfig())
        mapping = {
            self.VCC: [self.landpattern.pad1, self.landpattern.small_pads[0]],
            self.GND: self.landpattern.pad2,
            self.RW: self.landpattern.small_pads[1],
            self.A0: self.landpattern.small_pads[2],
            self.A1: self.landpattern.small_pads[3],
            self.A2: self.landpattern.small_pads[4],
            self.A3: self.landpattern.small_pads[5],
            self.A4: self.landpattern.small_pads[6],
            self.A5: self.landpattern.small_pads[7],
            self.A6: self.landpattern.small_pads[8],
            self.A7: self.landpattern.small_pads[9],
            self.A8: self.landpattern.small_pads[10],
            self.A9: self.landpattern.small_pads[11],
            self.A10: self.landpattern.small_pads[12],
            self.A11: self.landpattern.small_pads[13],
            self.A12: self.landpattern.small_pads[14],
            self.A13: self.landpattern.small_pads[15],
            self.A14: self.landpattern.small_pads[16],
            self.A15: self.landpattern.small_pads[17],
            self.A16: self.landpattern.small_pads[18],
            self.A17: self.landpattern.small_pads[19],
            self.VCC2: self.landpattern.small_pads[20],
            self.D0: self.landpattern.small_pads[21],
            self.D1: self.landpattern.small_pads[22],
            self.D2: self.landpattern.small_pads[23],
            self.D3: self.landpattern.small_pads[24],
            self.D4: self.landpattern.small_pads[25],
            self.D5: self.landpattern.small_pads[26],
            self.D6: self.landpattern.small_pads[27],
            self.D7: self.landpattern.small_pads[28],
            self.CE1: self.landpattern.small_pads[29],
            self.CE6: self.landpattern.small_pads[30],
            self.NC: self.landpattern.small_pads[31],
            self.OE: self.landpattern.small_pads[32],
        }
        self.pad_mapping = PadMapping(mapping)

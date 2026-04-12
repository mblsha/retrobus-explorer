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


class SharpOrganizerContactPad(Pad):
    shape = rectangle(0.4, 4.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.5, 5.0))
        self.paste = Paste(rectangle(0.5, 5.0))


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


class SharpOrganizerBusLandpattern(Landpattern):
    # Direct footprint port of `components/JC20-C45S-F1-A1.stanza`.
    def __init__(self):
        self.pads = [SharpOrganizerContactPad().at(-22.0 + index, 0.0) for index in range(45)]


class SharpOrganizerBus(Component):
    # Direct port of `components/JC20-C45S-F1-A1/sharp-organizer-component`.
    GND = Port()
    NC44 = Port()
    NC43 = Port()
    NC42 = Port()
    E2 = Port()
    CI = Port()
    A16 = Port()
    A17 = Port()
    A18 = Port()
    A19 = Port()
    OE = Port()
    RW = Port()
    EPROM = Port()
    SRAM2 = Port()
    SRAM1 = Port()
    MSKROM = Port()
    D7 = Port()
    D6 = Port()
    D5 = Port()
    D4 = Port()
    D3 = Port()
    D2 = Port()
    D1 = Port()
    D0 = Port()
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
    VPP = Port()
    VBATT = Port()
    STNBY = Port()
    NC02 = Port()
    VCC = Port()

    manufacturer = "JAE"
    mpn = "JC20-C45S-F1-A1"
    description = "Sharp organizer direct-insert card connector"
    reference_designator_prefix = "J"
    value = "~"

    def __init__(self):
        self.landpattern = SharpOrganizerBusLandpattern()
        ordered_ports = [
            self.GND,
            self.NC44,
            self.NC43,
            self.NC42,
            self.E2,
            self.CI,
            self.A16,
            self.A17,
            self.A18,
            self.A19,
            self.OE,
            self.RW,
            self.EPROM,
            self.SRAM2,
            self.SRAM1,
            self.MSKROM,
            self.D7,
            self.D6,
            self.D5,
            self.D4,
            self.D3,
            self.D2,
            self.D1,
            self.D0,
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
            self.VPP,
            self.VBATT,
            self.STNBY,
            self.NC02,
            self.VCC,
        ]
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([port])) for port in ordered_ports], config=BoxConfig())
        self.pad_mapping = PadMapping({port: pad for port, pad in zip(ordered_ports, self.landpattern.pads, strict=True)})

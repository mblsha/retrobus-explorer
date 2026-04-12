from __future__ import annotations

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
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


class ProbePthPad3mm(Pad):
    shape = Circle(diameter=3.0)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.5))
        self.soldermask = Soldermask(Circle(diameter=2.9))


class GndTestpads(Component):
    # Direct port of `components/GndTestpads.stanza`.
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
        self.pad_mapping = PadMapping({
            self.GND: [
                self.landpattern.p1,
                self.landpattern.p2,
                self.landpattern.p3,
                self.landpattern.p4,
            ]
        })


class HostContactPad(Pad):
    shape = rectangle(0.5, 2.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.6, 3.0))
        self.paste = Paste(rectangle(0.6, 3.0))


class HostMountPad(Pad):
    shape = rectangle(1.9, 1.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(2.0, 2.0))
        self.paste = Paste(rectangle(2.0, 2.0))


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


class SharpOrganizerHostLandpattern(Landpattern):
    # Direct footprint port of `components/SharpOrganizerHostDBZ.stanza`.
    def __init__(self):
        self.pads = [HostContactPad().at(-22.0 + index, 0.0) for index in range(45)]
        self.mount_right = HostMountPad().at(28.5, -8.0)
        self.mount_left = HostMountPad().at(-28.5, -8.0)
        self.hole_left = Cutout(Circle(diameter=1.1).at(-25.0, -4.3))
        self.hole_right = Cutout(Circle(diameter=1.1).at(25.0, -4.3))


class SharpOrganizerHost(Component):
    # Direct port of `components/SharpOrganizerHostDBZ/sharp-organizer-component`.
    VCC = Port()
    NC02 = Port()
    STNBY = Port()
    VBATT = Port()
    VPP = Port()
    A15 = Port()
    A14 = Port()
    A13 = Port()
    A12 = Port()
    A11 = Port()
    A10 = Port()
    A9 = Port()
    A8 = Port()
    A7 = Port()
    A6 = Port()
    A5 = Port()
    A4 = Port()
    A3 = Port()
    A2 = Port()
    A1 = Port()
    A0 = Port()
    D0 = Port()
    D1 = Port()
    D2 = Port()
    D3 = Port()
    D4 = Port()
    D5 = Port()
    D6 = Port()
    D7 = Port()
    MSKROM = Port()
    SRAM1 = Port()
    SRAM2 = Port()
    EPROM = Port()
    RW = Port()
    OE = Port()
    A19 = Port()
    A18 = Port()
    A17 = Port()
    A16 = Port()
    CI = Port()
    E2 = Port()
    NC42 = Port()
    NC43 = Port()
    NC44 = Port()
    GND = Port()

    manufacturer = "JAE?"
    mpn = "Sharp Organizer Host from DB-Z"
    description = "Sharp organizer host connector"
    reference_designator_prefix = "J"
    value = "~"

    def __init__(self):
        self.landpattern = SharpOrganizerHostLandpattern()
        ordered_ports = [
            self.VCC,
            self.NC02,
            self.STNBY,
            self.VBATT,
            self.VPP,
            self.A15,
            self.A14,
            self.A13,
            self.A12,
            self.A11,
            self.A10,
            self.A9,
            self.A8,
            self.A7,
            self.A6,
            self.A5,
            self.A4,
            self.A3,
            self.A2,
            self.A1,
            self.A0,
            self.D0,
            self.D1,
            self.D2,
            self.D3,
            self.D4,
            self.D5,
            self.D6,
            self.D7,
            self.MSKROM,
            self.SRAM1,
            self.SRAM2,
            self.EPROM,
            self.RW,
            self.OE,
            self.A19,
            self.A18,
            self.A17,
            self.A16,
            self.CI,
            self.E2,
            self.NC42,
            self.NC43,
            self.NC44,
            self.GND,
        ]
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([port])) for port in ordered_ports], config=BoxConfig())
        mapping = {port: pad for port, pad in zip(ordered_ports, self.landpattern.pads, strict=True)}
        self.pad_mapping = PadMapping(mapping)

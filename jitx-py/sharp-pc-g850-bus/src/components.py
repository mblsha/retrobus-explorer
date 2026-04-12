from __future__ import annotations

from jitx.component import Component
from jitx.feature import Cutout, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.primitive import Circle, Polyline
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class EdgePthPad(Pad):
    shape = Circle(diameter=1.5)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        self.soldermask = Soldermask(Circle(diameter=1.4))


class PCG850BusLandpattern(Landpattern):
    # Direct footprint port of `components/PCG850Bus.stanza`. JITX landpattern
    # Y coordinates export mirrored to KiCad, so this footprint is written with
    # the opposite sign to match the archived gold KiCad geometry.
    def __init__(self):
        col_pitch = 1.27
        row_pitch = 2.54 * 2.0
        x0 = -12.065
        y0 = 3.81

        self.pads = []
        for col in range(20):
            x = x0 + col * col_pitch
            column_offset = row_pitch / 2.0 if col % 2 == 1 else 0.0
            for row in range(2):
                y = y0 - row * row_pitch - column_offset
                self.pads.append(EdgePthPad().at(x, y))

        self.pin1_marker = Silkscreen(Circle(diameter=0.6).at(x0 - 1.0, y0 + 1.0))
        half_w = 31.50 / 2.0
        half_h = 8.88 / 2.0
        self.outline = Silkscreen(
            Polyline(
                0.2,
                [
                    (-half_w, -half_h),
                    (-half_w, half_h),
                    (half_w, half_h),
                    (half_w, -half_h),
                    (-half_w, -half_h),
                ],
            )
        )


class PCG850Bus(Component):
    # Direct port of `components/PCG850Bus.stanza`.
    VCC = Port()
    M1 = Port()
    MREQ = Port()
    IORQ = Port()
    IORESET = Port()
    WAIT = Port()
    INT1 = Port()
    WR = Port()
    RD = Port()
    BNK1 = Port()
    BNK0 = Port()
    CEROM2 = Port()
    CERAM2 = Port()
    D7 = Port()
    D6 = Port()
    D5 = Port()
    D4 = Port()
    D3 = Port()
    D2 = Port()
    D1 = Port()
    D0 = Port()
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
    GND = Port()

    manufacturer = "WingTAT"
    mpn = "PC-G850"
    datasheet = "https://www.lcsc.com/datasheet/lcsc_datasheet_2312301551_WingTAT-HED40LP03BK_C5448171.pdf"
    description = "1.27 mm edge-slot 40P direct insert connector"
    reference_designator_prefix = "U"
    value = "PC-G850"

    def __init__(self):
        self.landpattern = PCG850BusLandpattern()

        left_ports = [
            self.VCC,
            self.VCC,
            self.M1,
            self.MREQ,
            self.IORQ,
            self.IORESET,
            self.WAIT,
            self.INT1,
            self.WR,
            self.RD,
            self.BNK1,
            self.BNK0,
            self.CEROM2,
            self.CERAM2,
            self.D7,
            self.D6,
            self.D5,
            self.D4,
            self.D3,
            self.D2,
        ]
        right_ports = [
            self.D1,
            self.D0,
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
            self.GND,
            self.GND,
        ]
        rows = [
            Row(left=PinGroup([left]), right=PinGroup([right]))
            for left, right in zip(left_ports, right_ports, strict=True)
        ]
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=2))

        pad_ports = [
            self.VCC,
            self.VCC,
            self.M1,
            self.MREQ,
            self.IORQ,
            self.IORESET,
            self.WAIT,
            self.INT1,
            self.WR,
            self.RD,
            self.BNK1,
            self.BNK0,
            self.CEROM2,
            self.CERAM2,
            self.D7,
            self.D6,
            self.D5,
            self.D4,
            self.D3,
            self.D2,
            self.D1,
            self.D0,
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
            self.GND,
            self.GND,
        ]
        self.pad_mapping = PadMapping({
            port: [pad for mapped_port, pad in zip(pad_ports, self.landpattern.pads, strict=True) if mapped_port is port]
            for port in [
                self.VCC,
                self.M1,
                self.MREQ,
                self.IORQ,
                self.IORESET,
                self.WAIT,
                self.INT1,
                self.WR,
                self.RD,
                self.BNK1,
                self.BNK0,
                self.CEROM2,
                self.CERAM2,
                self.D7,
                self.D6,
                self.D5,
                self.D4,
                self.D3,
                self.D2,
                self.D1,
                self.D0,
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
                self.GND,
            ]
        })

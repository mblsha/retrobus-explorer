from __future__ import annotations

from jitx.component import Component
from jitx.feature import Cutout, Paste, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


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

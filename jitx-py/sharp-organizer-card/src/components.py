from __future__ import annotations

from jitx.component import Component
from jitx.feature import Paste, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class SharpOrganizerContactPad(Pad):
    shape = rectangle(0.4, 4.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.5, 5.0))
        self.paste = Paste(rectangle(0.5, 5.0))


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

from __future__ import annotations

from typing import cast

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polygon, Polyline
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row
from shared_components.fabrication import silkscreen_text

from src.pinmap import CPU_PIN_NAMES_BY_NUMBER


def pad_attr(obj: object, name: str) -> Pad:
    return cast(Pad, getattr(obj, name))


class Sc62015LeadPad(Pad):
    shape = rectangle(1.2, 0.22)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.3, 0.32))
        self.paste = Paste(rectangle(1.2, 0.22))


class Sc62015Landpattern(Landpattern):
    """100-lead SC62015 footprint ported from the existing interposer."""

    def __init__(self, *, include_body_cutout: bool = True):
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
        self.pin1_marker = Silkscreen(Circle(diameter=0.5).at(-9.9, 9.425))
        if include_body_cutout:
            self.body_cutout = Cutout(
                Polygon(
                    [
                        (-8.15, -9.75),
                        (-6.5, -11.1),
                        (6.5, -11.1),
                        (8.15, -9.75),
                        (8.15, 9.75),
                        (6.5, 11.1),
                        (-6.5, 11.1),
                        (-8.15, 9.75),
                    ]
                )
            )
        self.courtyard = Courtyard(rectangle(20.2, 23.8))


class Sc62015B02(Component):
    X = [Port() for _ in range(4)]
    VDD = Port()
    VCC = Port()
    RESET = Port()
    GND = Port()
    TEST = Port()
    CI = Port()
    CO = Port()
    ON = Port()
    WR = Port()
    MRQ = Port()
    K = [Port() for _ in range(8)]
    D = [Port() for _ in range(8)]
    A = [Port() for _ in range(19)]
    VDISP = Port()
    VA = Port()
    DCLK = Port()
    KO = [Port() for _ in range(16)]
    IRQ = Port()
    OUT = Port()
    CE = [Port() for _ in range(8)]
    ACLK = Port()
    DIS = Port()
    HA = Port()
    RD = Port()
    RXD = Port()
    TXD = Port()
    E = [Port() for _ in range(16)]

    manufacturer = "Sharp"
    mpn = "SC62015B02"
    description = "SHARP SC62015B02 100-lead CPU"
    reference_designator_prefix = "U"
    value = "SC62015B02"

    def __init__(self, *, include_body_cutout: bool = True):
        self.landpattern = Sc62015Landpattern(include_body_cutout=include_body_cutout)
        ports = {
            **{f"X{index + 1}": self.X[index] for index in range(4)},
            "VDD": self.VDD,
            "VCC": self.VCC,
            "RESET": self.RESET,
            "GND": self.GND,
            "TEST": self.TEST,
            "CI": self.CI,
            "CO": self.CO,
            "ON": self.ON,
            "WR": self.WR,
            "MRQ": self.MRQ,
            **{f"K{index + 10}": self.K[index] for index in range(8)},
            **{f"D{index}": self.D[index] for index in range(8)},
            **{f"A{index}": self.A[index] for index in range(19)},
            "VDISP": self.VDISP,
            "VA": self.VA,
            "DCLK": self.DCLK,
            **{f"KO{index}": self.KO[index] for index in range(16)},
            "IRQ": self.IRQ,
            "OUT": self.OUT,
            **{f"CE{index}": self.CE[index] for index in range(8)},
            "ACLK": self.ACLK,
            "DIS": self.DIS,
            "HA": self.HA,
            "RD": self.RD,
            "RXD": self.RXD,
            "TXD": self.TXD,
            **{f"E{index}": self.E[index] for index in range(16)},
        }
        ordered_ports = [ports[name] for name in CPU_PIN_NAMES_BY_NUMBER]
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([ordered_ports[index]]), right=PinGroup([ordered_ports[index + 50]]))
                for index in range(50)
            ],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping(
            {ports[name]: self.landpattern.pads[index] for index, name in enumerate(CPU_PIN_NAMES_BY_NUMBER)}
        )

    def port(self, name: str) -> Port:
        if name.startswith("KO"):
            return self.KO[int(name[2:])]
        if name.startswith("CE"):
            return self.CE[int(name[2:])]
        if name.startswith("X"):
            return self.X[int(name[1:]) - 1]
        if name.startswith("K"):
            return self.K[int(name[1:]) - 10]
        if name.startswith("D") and name[1:].isdigit():
            return self.D[int(name[1:])]
        if name.startswith("A") and name[1:].isdigit():
            return self.A[int(name[1:])]
        if name.startswith("E") and name[1:].isdigit():
            return self.E[int(name[1:])]
        return cast(Port, getattr(self, name))


class Tssop48Pad(Pad):
    shape = rectangle(1.5, 0.3)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.6, 0.4))
        self.paste = Paste(rectangle(1.5, 0.3))


class Tssop48DggLandpattern(Landpattern):
    """TI DGG0048A land pattern: 0.5-mm pitch, 1.5 x 0.3-mm lands."""

    def __init__(self):
        for index in range(24):
            # TI's top-view package drawing numbers counter-clockwise from
            # pin 1 at the upper-left corner.
            setattr(self, f"p{index + 1}", Tssop48Pad().at(-3.75, 5.75 - 0.5 * index))
            setattr(self, f"p{48 - index}", Tssop48Pad().at(3.75, 5.75 - 0.5 * index, rotate=180))
        self.outline = Silkscreen(
            Polyline(0.15, [(-3.05, -6.25), (-3.05, 6.25), (3.05, 6.25), (3.05, -6.25), (-3.05, -6.25)])
        )
        self.pin1 = Silkscreen(Circle(diameter=0.45).at(-4.9, 5.75))
        self.ref_text = Silkscreen(silkscreen_text(">REF").at(0.0, 7.0))
        self.courtyard = Courtyard(rectangle(8.5, 13.5))


class Sn74Lvc16T245(Component):
    A = [[Port() for _ in range(8)] for _ in range(2)]
    B = [[Port() for _ in range(8)] for _ in range(2)]
    DIR = [Port() for _ in range(2)]
    OE_N = [Port() for _ in range(2)]
    # Keep the two physical supply pins distinct. Collapsing them onto one
    # logical Port makes physical endpoint selection ambiguous and can
    # silently attach a decoupler to the wrong end of the package.
    VCCA = [Port() for _ in range(2)]
    VCCB = [Port() for _ in range(2)]
    GND = Port()

    manufacturer = "Texas Instruments"
    mpn = "SN74LVC16T245DGGR"
    datasheet = "https://www.ti.com/lit/ds/symlink/sn74lvc16t245.pdf"
    description = "16-bit dual-supply bus transceiver with two independently controlled 8-bit banks"
    reference_designator_prefix = "U"
    value = "SN74LVC16T245DGGR"

    def __init__(self):
        self.landpattern = Tssop48DggLandpattern()
        rows = [
            *(Row(left=PinGroup([self.A[0][index]]), right=PinGroup([self.B[0][index]])) for index in range(8)),
            Row(left=PinGroup([self.DIR[0]]), right=PinGroup([self.OE_N[0]])),
            *(Row(left=PinGroup([self.A[1][index]]), right=PinGroup([self.B[1][index]])) for index in range(8)),
            Row(left=PinGroup([self.DIR[1]]), right=PinGroup([self.OE_N[1]])),
            Row(left=PinGroup(self.VCCA), right=PinGroup(self.VCCB)),
            Row(left=PinGroup([self.GND])),
        ]
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=2))

        pin_by_port: dict[Port, int | tuple[int, ...]] = {
            self.DIR[0]: 1,
            self.OE_N[0]: 48,
            self.DIR[1]: 24,
            self.OE_N[1]: 25,
            self.VCCA[0]: 31,
            self.VCCA[1]: 42,
            self.VCCB[0]: 7,
            self.VCCB[1]: 18,
            self.GND: (4, 10, 15, 21, 28, 34, 39, 45),
        }
        a1_pins = (47, 46, 44, 43, 41, 40, 38, 37)
        b1_pins = (2, 3, 5, 6, 8, 9, 11, 12)
        a2_pins = (36, 35, 33, 32, 30, 29, 27, 26)
        b2_pins = (13, 14, 16, 17, 19, 20, 22, 23)
        for channel in range(8):
            pin_by_port[self.A[0][channel]] = a1_pins[channel]
            pin_by_port[self.B[0][channel]] = b1_pins[channel]
            pin_by_port[self.A[1][channel]] = a2_pins[channel]
            pin_by_port[self.B[1][channel]] = b2_pins[channel]

        mapping = {}
        for port, pin_numbers in pin_by_port.items():
            numbers = (pin_numbers,) if isinstance(pin_numbers, int) else pin_numbers
            pads = tuple(pad_attr(self.landpattern, f"p{number}") for number in numbers)
            mapping[port] = pads[0] if len(pads) == 1 else pads
        self.pad_mapping = PadMapping(mapping)

class Tssop20Pad(Pad):
    shape = rectangle(1.5, 0.4)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.6, 0.5))
        self.paste = Paste(rectangle(1.5, 0.4))


class Tssop20PwLandpattern(Landpattern):
    """TI PW0020A land pattern: 0.65-mm pitch TSSOP-20."""

    def __init__(self):
        for index in range(10):
            setattr(self, f"p{index + 1}", Tssop20Pad().at(-3.15, 2.925 - 0.65 * index))
            setattr(self, f"p{20 - index}", Tssop20Pad().at(3.15, 2.925 - 0.65 * index, rotate=180))
        self.outline = Silkscreen(
            Polyline(0.15, [(-2.2, -3.25), (-2.2, 3.25), (2.2, 3.25), (2.2, -3.25), (-2.2, -3.25)])
        )
        self.pin1 = Silkscreen(Circle(diameter=0.4).at(-4.25, 2.925))
        # The west-column translators are intentionally packed with only
        # 0.2-0.3 mm between courtyards.  Keep the reference on the open
        # outer side instead of between adjacent package outlines.
        self.ref_text = Silkscreen(silkscreen_text(">REF").at(-4.8, 0.0))
        self.courtyard = Courtyard(rectangle(8.2, 7.5))


class Txs0108e(Component):
    A = [Port() for _ in range(8)]
    B = [Port() for _ in range(8)]
    OE = Port()
    VCCA = Port()
    VCCB = Port()
    GND = Port()

    manufacturer = "Texas Instruments"
    mpn = "TXS0108EPWR"
    datasheet = "https://www.ti.com/lit/ds/symlink/txs0108e.pdf"
    description = "8-bit auto-bidirectional translator for open-drain and push-pull signals"
    reference_designator_prefix = "U"
    value = "TXS0108EPWR"

    def __init__(self):
        self.landpattern = Tssop20PwLandpattern()
        self.symbol = BoxSymbol(
            rows=[
                *(Row(left=PinGroup([self.A[index]]), right=PinGroup([self.B[index]])) for index in range(8)),
                Row(left=PinGroup([self.VCCA]), right=PinGroup([self.VCCB])),
                Row(left=PinGroup([self.OE]), right=PinGroup([self.GND])),
            ],
            config=BoxConfig(group_spacing=2),
        )
        a_pins = (1, 3, 4, 5, 6, 7, 8, 9)
        b_pins = (20, 18, 17, 16, 15, 14, 13, 12)
        mapping: dict[Port, Pad] = {
            self.VCCA: pad_attr(self.landpattern, "p2"),
            self.OE: pad_attr(self.landpattern, "p10"),
            self.GND: pad_attr(self.landpattern, "p11"),
            self.VCCB: pad_attr(self.landpattern, "p19"),
        }
        for channel in range(8):
            mapping[self.A[channel]] = pad_attr(self.landpattern, f"p{a_pins[channel]}")
            mapping[self.B[channel]] = pad_attr(self.landpattern, f"p{b_pins[channel]}")
        self.pad_mapping = PadMapping(mapping)

class Chip0402Pad(Pad):
    shape = rectangle(0.6, 0.55)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.7, 0.65))
        self.paste = Paste(rectangle(0.6, 0.55))


class Chip0402Landpattern(Landpattern):
    def __init__(self):
        self.p1 = Chip0402Pad().at(-0.5, 0.0)
        self.p2 = Chip0402Pad().at(0.5, 0.0, rotate=180)
        self.courtyard = Courtyard(rectangle(1.7, 1.2))


class Chip0201Pad(Pad):
    shape = rectangle(0.3, 0.3)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.4, 0.4))
        self.paste = Paste(rectangle(0.3, 0.3))


class Chip0201Landpattern(Landpattern):
    def __init__(self):
        self.p1 = Chip0201Pad().at(-0.25, 0.0)
        self.p2 = Chip0201Pad().at(0.25, 0.0, rotate=180)
        self.courtyard = Courtyard(rectangle(1.0, 0.65))


class Resistor0402(Component):
    p = [Port() for _ in range(2)]
    reference_designator_prefix = "R"
    manufacturer = "Generic"
    mpn = "0402-resistor"
    description = "0402 resistor"

    def __init__(self, value: str):
        self.value = value
        self.landpattern = Chip0402Landpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]]))],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping({self.p[0]: self.landpattern.p1, self.p[1]: self.landpattern.p2})


class Chip0603Pad(Pad):
    shape = rectangle(0.9, 0.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.0, 1.0))
        self.paste = Paste(rectangle(0.9, 0.9))


class Chip0603Landpattern(Landpattern):
    def __init__(self):
        self.p1 = Chip0603Pad().at(-0.85, 0.0)
        self.p2 = Chip0603Pad().at(0.85, 0.0, rotate=180)
        self.courtyard = Courtyard(rectangle(2.5, 1.5))


class Capacitor0603(Component):
    p = [Port() for _ in range(2)]
    reference_designator_prefix = "C"
    manufacturer = "Generic"
    mpn = "0603-capacitor"
    description = "0603 ceramic capacitor"

    def __init__(self, value: str):
        self.value = value
        self.landpattern = Chip0603Landpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]]))],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping({self.p[0]: self.landpattern.p1, self.p[1]: self.landpattern.p2})


class Capacitor0201(Component):
    p = [Port() for _ in range(2)]
    reference_designator_prefix = "C"
    manufacturer = "Generic"
    mpn = "0201-capacitor"
    description = "0201 ceramic capacitor"

    def __init__(self, value: str):
        self.value = value
        self.landpattern = Chip0201Landpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]]))],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping({self.p[0]: self.landpattern.p1, self.p[1]: self.landpattern.p2})


class Capacitor0402(Component):
    p = [Port() for _ in range(2)]
    reference_designator_prefix = "C"
    manufacturer = "Generic"
    mpn = "0402-capacitor"
    description = "0402 ceramic capacitor"

    def __init__(self, value: str):
        self.value = value
        self.landpattern = Chip0402Landpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]]))],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping({self.p[0]: self.landpattern.p1, self.p[1]: self.landpattern.p2})


class Chip0805Pad(Pad):
    shape = rectangle(1.3, 1.4)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(1.4, 1.5))
        self.paste = Paste(rectangle(1.3, 1.4))


class Chip0805Landpattern(Landpattern):
    def __init__(self):
        self.p1 = Chip0805Pad().at(-1.0, 0.0)
        self.p2 = Chip0805Pad().at(1.0, 0.0, rotate=180)
        self.courtyard = Courtyard(rectangle(3.2, 2.1))


class Capacitor0805(Component):
    p = [Port() for _ in range(2)]
    reference_designator_prefix = "C"
    manufacturer = "Generic"
    mpn = "0805-capacitor"
    description = "0805 ceramic capacitor"

    def __init__(self, value: str):
        self.value = value
        self.landpattern = Chip0805Landpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]]))],
            config=BoxConfig(group_spacing=1),
        )
        self.pad_mapping = PadMapping({self.p[0]: self.landpattern.p1, self.p[1]: self.landpattern.p2})


class TestPadPad(Pad):
    shape = Circle(diameter=3.0)

    def __init__(self):
        self.soldermask = Soldermask(Circle(diameter=2.9))


class TestPadLandpattern(Landpattern):
    pad = TestPadPad().at(0.0, 0.0)


class TestPad(Component):
    p = Port()
    reference_designator_prefix = "TP"
    manufacturer = "Generic"
    mpn = "3mm-smd-testpad"
    description = "3-mm exposed signal test pad"
    value = "TEST"

    def __init__(self):
        self.landpattern = TestPadLandpattern()
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([self.p]))], config=BoxConfig())
        self.pad_mapping = PadMapping({self.p: self.landpattern.pad})

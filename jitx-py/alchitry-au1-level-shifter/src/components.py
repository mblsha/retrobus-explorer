from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


def pad_attr(obj: object, name: str) -> Pad:
    return cast(Pad, getattr(obj, name))


class HeaderPthPad(Pad):
    shape = Circle(diameter=1.4)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.0))
        self.soldermask = Soldermask(Circle(diameter=1.5))


class PinHeader2x3Landpattern(Landpattern):
    # Direct port of the archived `PIN_HDR_6` KiCad footprint.
    # Python JITX exports this bottom-side through-hole header mirrored in Y,
    # so the source pad rows are intentionally flipped to preserve KiCad parity.
    def __init__(self):
        self.p1 = HeaderPthPad().at(-1.27, 2.54)
        self.p2 = HeaderPthPad().at(1.27, 2.54)
        self.p3 = HeaderPthPad().at(-1.27, 0.0)
        self.p4 = HeaderPthPad().at(1.27, 0.0)
        self.p5 = HeaderPthPad().at(-1.27, -2.54)
        self.p6 = HeaderPthPad().at(1.27, -2.54)
        self.outline = Silkscreen(
            Polyline(
                0.153,
                [(-2.54, -3.81), (-2.54, 3.81), (2.54, 3.81), (2.54, -3.81), (-2.54, -3.81)],
            )
        )
        self.courtyard = Courtyard(rectangle(5.08, 7.62))


class PinHeader2x3(Component):
    p = [Port() for _ in range(6)]
    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "generic-6x2-2.54mm-th"
    description = "Generic 2x3 2.54 mm through-hole header"
    value = "6X2-pin-header"

    def __init__(self):
        self.landpattern = PinHeader2x3Landpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]])),
                Row(left=PinGroup([self.p[2]]), right=PinGroup([self.p[3]])),
                Row(left=PinGroup([self.p[4]]), right=PinGroup([self.p[5]])),
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping(
            {
                self.p[0]: self.landpattern.p1,
                self.p[1]: self.landpattern.p2,
                self.p[2]: self.landpattern.p3,
                self.p[3]: self.landpattern.p4,
                self.p[4]: self.landpattern.p5,
                self.p[5]: self.landpattern.p6,
            }
        )


class Cap0402Pad(Pad):
    shape = rectangle(0.6, 0.280277563773199)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.7, 0.380277563773199))
        self.paste = Paste(rectangle(0.6, 0.280277563773199))


class Cap0402Landpattern(Landpattern):
    # Direct port of the archived `Pkg0402` footprint.
    def __init__(self):
        self.p1 = Cap0402Pad().at(0.0, -0.4098612181134)
        self.p2 = Cap0402Pad().at(0.0, 0.4098612181134)
        self.ref_text = Silkscreen(Text(">REF", 0.6).at(0.75, 0.0, rotate=90))
        self.courtyard = Courtyard(rectangle(0.9, 1.4))


class Cap0402(Component):
    p = [Port() for _ in range(2)]
    reference_designator_prefix = "C"
    manufacturer = "Generic"
    mpn = "generic-0402-cap"
    description = "Generic 0402 capacitor"
    value = "10uF"

    def __init__(self):
        self.landpattern = Cap0402Landpattern()
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]]))],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping({self.p[0]: self.landpattern.p1, self.p[1]: self.landpattern.p2})


class Txb0108PwrPad(Pad):
    shape = rectangle(0.364, 1.742)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.466, 1.844))
        self.paste = Paste(rectangle(0.466, 1.844))


class Txb0108PwrLandpattern(Landpattern):
    # Direct footprint port of `components/TXB0108PWR.stanza` / archived `LP_2`.
    # Python JITX exports this custom-pad footprint mirrored in Y, so the source
    # rows and pin-1 marker are intentionally flipped to preserve KiCad parity.
    def __init__(self):
        for index in range(10):
            x = -2.925 + 0.65 * index
            pad = Txb0108PwrPad().at(x, -2.87)
            setattr(self, f"p{index + 1}", pad)
        for index in range(10):
            x = 2.925 - 0.65 * index
            pad = Txb0108PwrPad().at(x, 2.87)
            setattr(self, f"p{index + 11}", pad)

        self.ref_text = Silkscreen(Text(">REF", 0.5).at(-0.75, 5.498))
        self.outline = Silkscreen(
            Polyline(0.152, [(-3.326, -1.771), (-3.326, 1.772), (3.326, 1.772), (3.326, -1.771), (-3.326, -1.771)])
        )
        self.pin1 = Silkscreen(Circle(diameter=0.3).at(-3.559, -2.87))
        self.courtyard = Courtyard(rectangle(6.804, 7.585))


class Txb0108Pwr(Component):
    # Direct component port of `components/TXB0108PWR.stanza`.
    A1 = Port()
    VCCA = Port()
    A2 = Port()
    A3 = Port()
    A4 = Port()
    A5 = Port()
    A6 = Port()
    A7 = Port()
    A8 = Port()
    OE = Port()
    GND = Port()
    B8 = Port()
    B7 = Port()
    B6 = Port()
    B5 = Port()
    B4 = Port()
    B3 = Port()
    B2 = Port()
    VCCB = Port()
    B1 = Port()

    manufacturer = "Texas Instruments"
    mpn = "TXB0108PWR"
    datasheet = "https://www.lcsc.com/datasheet/lcsc_datasheet_1810151720_Texas-Instruments-TXB0108PWR_C53406.pdf"
    description = "8-bit dual-supply auto-direction translating transceiver"
    reference_designator_prefix = "U"
    value = "TXB0108PWR"

    def __init__(self):
        self.landpattern = Txb0108PwrLandpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.A1]), right=PinGroup([self.B1])),
                Row(left=PinGroup([self.VCCA]), right=PinGroup([self.VCCB])),
                Row(left=PinGroup([self.A2]), right=PinGroup([self.B2])),
                Row(left=PinGroup([self.A3]), right=PinGroup([self.B3])),
                Row(left=PinGroup([self.A4]), right=PinGroup([self.B4])),
                Row(left=PinGroup([self.A5]), right=PinGroup([self.B5])),
                Row(left=PinGroup([self.A6]), right=PinGroup([self.B6])),
                Row(left=PinGroup([self.A7]), right=PinGroup([self.B7])),
                Row(left=PinGroup([self.A8]), right=PinGroup([self.B8])),
                Row(left=PinGroup([self.OE]), right=PinGroup([self.GND])),
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping(
            {
                self.A1: pad_attr(self.landpattern, "p1"),
                self.VCCA: pad_attr(self.landpattern, "p2"),
                self.A2: pad_attr(self.landpattern, "p3"),
                self.A3: pad_attr(self.landpattern, "p4"),
                self.A4: pad_attr(self.landpattern, "p5"),
                self.A5: pad_attr(self.landpattern, "p6"),
                self.A6: pad_attr(self.landpattern, "p7"),
                self.A7: pad_attr(self.landpattern, "p8"),
                self.A8: pad_attr(self.landpattern, "p9"),
                self.OE: pad_attr(self.landpattern, "p10"),
                self.GND: pad_attr(self.landpattern, "p11"),
                self.B8: pad_attr(self.landpattern, "p12"),
                self.B7: pad_attr(self.landpattern, "p13"),
                self.B6: pad_attr(self.landpattern, "p14"),
                self.B5: pad_attr(self.landpattern, "p15"),
                self.B4: pad_attr(self.landpattern, "p16"),
                self.B3: pad_attr(self.landpattern, "p17"),
                self.B2: pad_attr(self.landpattern, "p18"),
                self.VCCB: pad_attr(self.landpattern, "p19"),
                self.B1: pad_attr(self.landpattern, "p20"),
            }
        )


class AlchitryAuPad(Pad):
    shape = rectangle(0.15, 1.9)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.25, 2.0))
        self.paste = Paste(rectangle(0.25, 2.0))


class AlchitryAuLandpattern(Landpattern):
    # Direct footprint port of `components/AlchitryAu.stanza` / archived `LP`.
    # Python JITX exports these custom pads mirrored in Y, so the source rows are
    # intentionally flipped to keep the generated KiCad footprint aligned with gold.
    def __init__(self):
        for index in range(25):
            x = -6.0 + 0.5 * index
            pad_number = 49 - index
            pad = AlchitryAuPad().at(x, -2.2)
            setattr(self, f"p{pad_number}", pad)
        for index in range(25):
            x = 6.0 - 0.5 * index
            pad_number = 24 - index
            pad = AlchitryAuPad().at(x, 2.2)
            setattr(self, f"p{pad_number}", pad)

        self.hole_right = Cutout(Circle(diameter=0.55).at(6.95, -1.25))
        self.hole_left = Cutout(Circle(diameter=0.55).at(-6.95, -1.25))
        self.outline = Silkscreen(
            Polyline(
                0.2,
                [
                    (-7.6, 2.0),
                    (-7.6, 0.5),
                    (-7.3, 0.5),
                    (-7.3, -0.5),
                    (-7.6, -0.5),
                    (-7.6, -2.0),
                    (7.6, -2.0),
                    (7.6, 2.0),
                    (-7.6, 2.0),
                ],
            )
        )
        self.courtyard = Courtyard(rectangle(15.2, 4.0))


PowerPadMap = {
    "VCC5V": (0, 49),
    "GND": (3, 9, 15, 21, 28, 34, 40, 46),
    "VCC3V3": (6, 12, 18, 24, 25, 31, 37, 43),
}


def _build_symbol_rows(
    self: Component, *, left_names: Sequence[str], right_names: Sequence[str], group_spacing: int = 2
) -> BoxSymbol:
    rows: list[Row] = []
    total_rows = max(len(left_names), len(right_names))
    for index in range(total_rows):
        row_kwargs = {}
        if index < len(left_names):
            row_kwargs["left"] = PinGroup([getattr(self, left_names[index])])
        if index < len(right_names):
            row_kwargs["right"] = PinGroup([getattr(self, right_names[index])])
        rows.append(Row(**row_kwargs))
    return BoxSymbol(rows=rows, config=BoxConfig(group_spacing=group_spacing))


def _make_alchitry_connector_class(
    class_name: str, signal_pins: Sequence[tuple[str, tuple[int, ...], str]]
) -> type[Component]:
    def __init__(self):
        self.landpattern = AlchitryAuLandpattern()
        left_names = ["VCC5V", "GND", "VCC3V3"] + [name for name, _, side in signal_pins if side == "left"]
        right_names = [name for name, _, side in signal_pins if side == "right"]
        self.symbol = _build_symbol_rows(self, left_names=left_names, right_names=right_names)

        mapping = {
            getattr(self, name): tuple(getattr(self.landpattern, f"p{pad}") for pad in pad_numbers)
            for name, pad_numbers in PowerPadMap.items()
        }
        for signal_name, pad_numbers, _ in signal_pins:
            mapping[getattr(self, signal_name)] = tuple(getattr(self.landpattern, f"p{pad}") for pad in pad_numbers)
        self.pad_mapping = PadMapping(mapping)

    attrs: dict[str, object] = {
        "__init__": __init__,
        "manufacturer": "4UCON",
        "mpn": "4UCON-19008-50",
        "description": "Alchitry Au element board-to-board connector slice",
        "reference_designator_prefix": "U",
        "value": "~",
        "VCC5V": Port(),
        "GND": Port(),
        "VCC3V3": Port(),
    }
    for signal_name, _, _ in signal_pins:
        attrs[signal_name] = Port()

    return type(class_name, (Component,), attrs)


AlchitryA = _make_alchitry_connector_class(
    "AlchitryA",
    [
        ("T8", (1,), "left"),
        ("T7", (2,), "left"),
        ("T5", (4,), "left"),
        ("R5", (5,), "left"),
        ("R8", (7,), "left"),
        ("P8", (8,), "left"),
        ("L2", (10,), "left"),
        ("L3", (11,), "left"),
        ("J1", (13,), "left"),
        ("K1", (14,), "left"),
        ("H1", (16,), "left"),
        ("H2", (17,), "left"),
        ("G1", (19,), "left"),
        ("G2", (20,), "left"),
        ("K5", (22,), "left"),
        ("E6", (23,), "left"),
        ("M6", (26,), "right"),
        ("N6", (27,), "right"),
        ("H5", (29,), "right"),
        ("H4", (30,), "right"),
        ("J3", (32,), "right"),
        ("H3", (33,), "right"),
        ("J5", (35,), "right"),
        ("J4", (36,), "right"),
        ("K3", (38,), "right"),
        ("K2", (39,), "right"),
        ("N9", (41,), "right"),
        ("P9", (42,), "right"),
        ("R7", (44,), "right"),
        ("R6", (45,), "right"),
        ("T9", (47,), "right"),
        ("T10", (48,), "right"),
    ],
)

AlchitryB = _make_alchitry_connector_class(
    "AlchitryB",
    [
        ("D1", (1,), "left"),
        ("E2", (2,), "left"),
        ("A2", (4,), "left"),
        ("B2", (5,), "left"),
        ("E1", (7,), "left"),
        ("F2", (8,), "left"),
        ("F3", (10,), "left"),
        ("F4", (11,), "left"),
        ("A3", (13,), "left"),
        ("B4", (14,), "left"),
        ("A4", (16,), "left"),
        ("A5", (17,), "left"),
        ("B5", (19,), "left"),
        ("B6", (20,), "left"),
        ("A7", (22,), "left"),
        ("B7", (23,), "left"),
        ("C7", (26,), "right"),
        ("C6", (27,), "right"),
        ("D6", (29,), "right"),
        ("D5", (30,), "right"),
        ("F5", (32,), "right"),
        ("E5", (33,), "right"),
        ("G5", (35,), "right"),
        ("G4", (36,), "right"),
        ("D4", (38,), "right"),
        ("C4", (39,), "right"),
        ("E3", (41,), "right"),
        ("D3", (42,), "right"),
        ("C3", (44,), "right"),
        ("C2", (45,), "right"),
        ("C1", (47,), "right"),
        ("B1", (48,), "right"),
    ],
)

AlchitryC = _make_alchitry_connector_class(
    "AlchitryC",
    [
        ("T13", (1,), "left"),
        ("R13", (2,), "left"),
        ("T12", (4,), "left"),
        ("R12", (5,), "left"),
        ("R11", (7,), "left"),
        ("R10", (8,), "left"),
        ("N2", (10,), "left"),
        ("N3", (11,), "left"),
        ("P3", (13,), "left"),
        ("P4", (14,), "left"),
        ("M4", (16,), "left"),
        ("L4", (17,), "left"),
        ("N4", (19,), "left"),
        ("M5", (20,), "left"),
        ("L5", (22,), "left"),
        ("P5", (23,), "left"),
        ("T4", (26,), "right"),
        ("T3", (27,), "right"),
        ("R3", (29,), "right"),
        ("T2", (30,), "right"),
        ("R2", (32,), "right"),
        ("R1", (33,), "right"),
        ("N1", (35,), "right"),
        ("P1", (36,), "right"),
        ("M2", (38,), "right"),
        ("M1", (39,), "right"),
        ("N13", (41,), "right"),
        ("P13", (42,), "right"),
        ("N11", (44,), "right"),
        ("N12", (45,), "right"),
        ("P10", (47,), "right"),
        ("P11", (48,), "right"),
    ],
)

AlchitryD = _make_alchitry_connector_class(
    "AlchitryD",
    [
        ("LED2", (1,), "left"),
        ("LED3", (2,), "left"),
        ("LED6", (4,), "left"),
        ("LED7", (5,), "left"),
        ("R16", (7,), "left"),
        ("R15", (8,), "left"),
        ("P14", (10,), "left"),
        ("M15", (11,), "left"),
        ("USB_RX", (13,), "left"),
        ("USB_TX", (14,), "left"),
        ("A1V8", (16, 17), "left"),
        ("VBSEL", (19,), "left"),
        ("VCC1V8", (20,), "left"),
        ("N7_TDI", (22,), "left"),
        ("N8_TDO", (23,), "left"),
        ("L7_TCK", (26,), "right"),
        ("M7_TMS", (27,), "right"),
        ("AVN", (29,), "right"),
        ("AVP", (30,), "right"),
        ("AGND", (32,), "right"),
        ("AVREF", (33,), "right"),
        ("PROGRAM_B", (35,), "right"),
        ("DONE", (36,), "right"),
        ("RESET", (38,), "right"),
        ("F100MHZ", (39,), "right"),
        ("T14", (41,), "right"),
        ("T15", (42,), "right"),
        ("LED5", (44,), "right"),
        ("LED4", (45,), "right"),
        ("LED1", (47,), "right"),
        ("LED0", (48,), "right"),
    ],
)

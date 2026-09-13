from __future__ import annotations

from collections.abc import Sequence

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


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
        left = PinGroup([getattr(self, left_names[index])]) if index < len(left_names) else ()
        right = PinGroup([getattr(self, right_names[index])]) if index < len(right_names) else ()
        rows.append(Row(left=left, right=right))
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

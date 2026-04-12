from __future__ import annotations

import keyword
import re
from collections import OrderedDict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
SYMBOL_FILE = VENDOR_DIR / "Alchitry V2 Elements.kicad_sym"
FOOTPRINT_DIR = VENDOR_DIR / "Alchitry V2 Elements.pretty"

SPECIAL_SIGNAL_NAMES = {
    "3.3V": "V3V3",
    "~{PROG}": "PROG_N",
}

FOOTPRINT_UNITS = {
    "V2_TOP": ("V2_TOP_1_0", "V2_TOP_2_0", "V2_TOP_3_0"),
    "V2_BOTTOM": ("V2_BOTTOM_1_0", "V2_BOTTOM_3_0", "V2_BOTTOM_2_0"),
    "V2_BOTH": ("V2_BOTH_1_0", "V2_BOTH_2_0", "V2_BOTH_3_0", "V2_BOTH_4_0", "V2_BOTH_5_0", "V2_BOTH_6_0"),
}

PRIMARY_SIGNAL_ORDER = [
    "GND",
    "VCC",
    "V3V3",
    "A1V8",
    "MP1",
    "MP2",
    "MP3",
    "MP4",
    "RESET",
    "DONE",
    "PROG_N",
    "VBSEL_A",
    "VBSEL_B",
    "AV_P",
    "AV_N",
    "AVREF_P",
    "AVREF_N",
]


@dataclass(frozen=True)
class PadSpec:
    name: str
    x: float
    y: float
    rotate: float
    width: float
    height: float
    side: Side


class RectSmdPad(Pad):
    def __init__(self, width: float, height: float, *, mask_margin: float = 0.1016):
        self.shape = rectangle(width, height)
        self.soldermask = Soldermask(rectangle(width + 2 * mask_margin, height + 2 * mask_margin))
        self.paste = Paste(rectangle(width, height))



def _signal_attr_name(signal_name: str) -> str:
    mapped = SPECIAL_SIGNAL_NAMES.get(signal_name, signal_name)
    mapped = mapped.replace("/", "_").replace("-", "_")
    mapped = mapped.replace("~{", "").replace("}", "_N").replace("~", "N_")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mapped):
        mapped = re.sub(r"[^A-Za-z0-9_]", "_", mapped)
        if not mapped or mapped[0].isdigit():
            mapped = f"P_{mapped}"
    mapped = re.sub(r"_+", "_", mapped).strip("_")
    if keyword.iskeyword(mapped):
        mapped = f"{mapped}_"
    return mapped


@cache
def _unit_pin_pairs(target_name: str) -> tuple[tuple[str, str], ...]:
    text = SYMBOL_FILE.read_text().splitlines()
    start = next(index for index, line in enumerate(text) if line.strip() == f'(symbol "{target_name}"')
    depth = 0
    lines: list[str] = []
    for line in text[start:]:
        depth += line.count("(") - line.count(")")
        lines.append(line)
        if depth == 0:
            break

    pairs: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        if lines[index].strip().startswith("(pin "):
            depth = 0
            chunk: list[str] = []
            while index < len(lines):
                depth += lines[index].count("(") - lines[index].count(")")
                chunk.append(lines[index])
                index += 1
                if depth == 0:
                    break
            signal_name = None
            pin_name = None
            for line in chunk:
                stripped = line.strip()
                if stripped.startswith('(name "'):
                    signal_name = stripped.split('"')[1]
                elif stripped.startswith('(number "'):
                    pin_name = stripped.split('"')[1]
            if signal_name is None or pin_name is None:
                raise ValueError(f"Failed to extract pin pair from {target_name}")
            pairs.append((signal_name, pin_name))
        else:
            index += 1
    return tuple(pairs)


@cache
def _footprint_pad_specs(footprint_name: str) -> tuple[PadSpec, ...]:
    footprint_path = FOOTPRINT_DIR / f"{footprint_name}.kicad_mod"
    text = footprint_path.read_text()
    pattern = re.compile(
        r'\(pad "([A-Za-z]+\d+)" smd rect\s*\n'
        r'\s*\(at ([^ ]+) ([^ )]+) ([^ )]+)\)\s*\n'
        r'\s*\(size ([^ ]+) ([^ )]+)\)\s*\n'
        r'\s*\(layers ([^)]+)\)'
    )
    specs: list[PadSpec] = []
    for match in pattern.finditer(text):
        name, x, y, rotate, width, height, layers = match.groups()
        side = Side.Bottom if '"B.Cu"' in layers else Side.Top
        specs.append(
            PadSpec(
                name=name,
                x=float(x),
                y=float(y),
                rotate=float(rotate),
                width=float(width),
                height=float(height),
                side=side,
            )
        )
    return tuple(specs)


@cache
def _footprint_holes(footprint_name: str) -> tuple[tuple[float, float, float], ...]:
    footprint_path = FOOTPRINT_DIR / f"{footprint_name}.kicad_mod"
    text = footprint_path.read_text()
    pattern = re.compile(
        r'\(pad "" np_thru_hole circle\s*\n'
        r'\s*\(at ([^ ]+) ([^ )]+)\)\s*\n'
        r'\s*\(size ([^ ]+) ([^ )]+)\)\s*\n'
        r'\s*\(drill ([^ )]+)\)'
    )
    return tuple((float(x), float(y), float(drill)) for x, y, _sx, _sy, drill in pattern.findall(text))



def _signal_to_pad_names(unit_names: tuple[str, ...]) -> OrderedDict[str, tuple[str, ...]]:
    mapping: OrderedDict[str, list[str]] = OrderedDict()
    for unit_name in unit_names:
        for signal_name, pad_name in _unit_pin_pairs(unit_name):
            mapping.setdefault(signal_name, []).append(pad_name)
    return OrderedDict((signal_name, tuple(pad_names)) for signal_name, pad_names in mapping.items())



def _signal_sort_key(attr_name: str) -> tuple[int, int | str]:
    if attr_name in PRIMARY_SIGNAL_ORDER:
        return (0, PRIMARY_SIGNAL_ORDER.index(attr_name))
    if re.fullmatch(r"A\d+", attr_name):
        return (1, int(attr_name[1:]))
    if re.fullmatch(r"B\d+", attr_name):
        return (2, int(attr_name[1:]))
    if re.fullmatch(r"C\d+", attr_name):
        return (3, int(attr_name[1:]))
    if re.fullmatch(r"L\d+", attr_name):
        return (4, int(attr_name[1:]))
    return (5, attr_name)



def _build_symbol(self: Component, attr_names: tuple[str, ...]) -> BoxSymbol:
    ordered = sorted(attr_names, key=_signal_sort_key)
    midpoint = (len(ordered) + 1) // 2
    left_names = ordered[:midpoint]
    right_names = ordered[midpoint:]

    rows: list[Row] = []
    total_rows = max(len(left_names), len(right_names))
    for index in range(total_rows):
        row_kwargs = {}
        if index < len(left_names):
            row_kwargs["left"] = PinGroup([cast(Port, getattr(self, left_names[index]))])
        if index < len(right_names):
            row_kwargs["right"] = PinGroup([cast(Port, getattr(self, right_names[index]))])
        rows.append(Row(**row_kwargs))
    return BoxSymbol(rows=rows, config=BoxConfig(group_spacing=2))



def _make_landpattern_class(class_name: str, footprint_name: str) -> type[Landpattern]:
    pad_specs = _footprint_pad_specs(footprint_name)
    holes = _footprint_holes(footprint_name)

    class _Landpattern(Landpattern):
        def __init__(self):
            for spec in pad_specs:
                pad = RectSmdPad(spec.width, spec.height).at(spec.x, spec.y, on=spec.side, rotate=spec.rotate)
                setattr(self, f"pad_{spec.name}", pad)

            for index, (x, y, diameter) in enumerate(holes, start=1):
                setattr(self, f"hole_{index}", Cutout(Circle(diameter=diameter).at(x, y)))

            self.ref_text = Silkscreen(Text(">REF", 1.0).at(27.5, 2.5))
            self.outline = Silkscreen(
                Polyline(
                    0.1524,
                    [(0.0, -43.5), (1.5, -45.0), (53.5, -45.0), (55.0, -43.5), (55.0, -1.5), (53.5, 0.0), (1.5, 0.0), (0.0, -1.5), (0.0, -43.5)],
                )
            )
            self.courtyard = Courtyard(rectangle(55.0, 45.0).at(27.5, -22.5))

    _Landpattern.__name__ = class_name
    return _Landpattern



def _make_component_class(class_name: str, footprint_name: str, description: str) -> type[Component]:
    unit_names = FOOTPRINT_UNITS[footprint_name]
    signal_map = _signal_to_pad_names(unit_names)
    signal_attr_map = OrderedDict((signal_name, _signal_attr_name(signal_name)) for signal_name in signal_map)
    attr_names = tuple(OrderedDict.fromkeys(signal_attr_map.values()))
    landpattern_class = _make_landpattern_class(f"{class_name}Landpattern", footprint_name)

    def __init__(self):
        self.landpattern = landpattern_class()
        self.symbol = _build_symbol(self, attr_names)
        self.signal_to_attr = dict(signal_attr_map)
        self.attr_to_signal = {attr_name: signal_name for signal_name, attr_name in signal_attr_map.items()}
        mapping = {}
        for signal_name, pad_names in signal_map.items():
            attr_name = signal_attr_map[signal_name]
            port = cast(Port, getattr(self, attr_name))
            pads = tuple(getattr(self.landpattern, f"pad_{pad_name}") for pad_name in pad_names)
            mapping[port] = pads if len(pads) > 1 else pads[0]
        self.pad_mapping = PadMapping(mapping)

    def port(self, signal_name: str) -> Port:
        return cast(Port, getattr(self, self.signal_to_attr[signal_name]))

    attrs: dict[str, object] = {
        "__init__": __init__,
        "port": port,
        "manufacturer": "Alchitry",
        "mpn": footprint_name,
        "description": description,
        "reference_designator_prefix": "J",
        "value": footprint_name,
        "source_footprint": footprint_name,
        "source_units": unit_names,
        "source_signal_names": tuple(signal_map.keys()),
    }
    for attr_name in attr_names:
        attrs[attr_name] = Port()

    return type(class_name, (Component,), attrs)


AlchitryV2TopElement = _make_component_class(
    "AlchitryV2TopElement",
    "V2_TOP",
    "Python JITX import of the Alchitry V2 top-side element footprint and pinout",
)
AlchitryV2BottomElement = _make_component_class(
    "AlchitryV2BottomElement",
    "V2_BOTTOM",
    "Python JITX import of the Alchitry V2 bottom-side element footprint and pinout",
)
AlchitryV2BothElement = _make_component_class(
    "AlchitryV2BothElement",
    "V2_BOTH",
    "Python JITX import of the Alchitry V2 combined top and bottom element footprint and pinout",
)

__all__ = [
    "AlchitryV2TopElement",
    "AlchitryV2BottomElement",
    "AlchitryV2BothElement",
]

from __future__ import annotations

# Alchitry V2 composite element footprints built from shared DF40 connectors.
#
# Provenance:
# - Connector naming, role, and orientation come from Alchitry's primary
#   reference: https://alchitry.com/tutorials/references/pinouts-and-custom-elements/
# - Exact signal names come from the published KiCad element library converted
#   into src.generated_data.
# - The reusable DF40 pad geometry comes from shared_components.hirose_df40,
#   which is fitted against the published Alchitry KiCad footprints rather than
#   relying on a checked-in vendor snapshot at runtime.
import keyword
import re
from collections import OrderedDict
from typing import cast

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Silkscreen
from jitx.landpattern import Landpattern, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row
from shared_components.hirose_df40 import (
    DF40_50_BOTTOM_SPECS,
    DF40_50_TOP_SPECS,
    DF40_80_BOTTOM_SPECS,
    DF40_80_TOP_SPECS,
    Df40PadSpec,
    place_df40_pad_specs,
)

from src.generated_data import V2_BOTH_SIGNAL_MAP, V2_BOTTOM_SIGNAL_MAP, V2_TOP_SIGNAL_MAP

SPECIAL_SIGNAL_NAMES = {
    "3.3V": "V3V3",
    "~{PROG}": "PROG_N",
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

ELEMENT_HOLES = (
    (2.5, -42.5, 2.2),
    (2.5, -2.5, 2.2),
    (52.5, -42.5, 2.2),
    (52.5, -2.5, 2.2),
)
ELEMENT_OUTLINE = [
    (0.0, -43.5),
    (1.5, -45.0),
    (53.5, -45.0),
    (55.0, -43.5),
    (55.0, -1.5),
    (53.5, 0.0),
    (1.5, 0.0),
    (0.0, -1.5),
    (0.0, -43.5),
]
# The composite placements below match the published V2 element library: control
# connector on the left, Bank A above, and Bank B below.
ELEMENT_LAYOUTS = {
    "V2_TOP": (
        (DF40_50_TOP_SPECS, 16.5, -41.0, "C", None),
        (DF40_80_TOP_SPECS, 38.0, -41.0, "A", None),
        (DF40_80_TOP_SPECS, 38.0, -4.0, "B", None),
    ),
    "V2_BOTTOM": (
        (DF40_50_BOTTOM_SPECS, 16.5, -41.0, "C", "CM"),
        (DF40_80_BOTTOM_SPECS, 38.0, -41.0, "A", "AM"),
        (DF40_80_BOTTOM_SPECS, 38.0, -4.0, "B", "BM"),
    ),
    "V2_BOTH": (
        (DF40_50_TOP_SPECS, 16.5, -41.0, "C", None),
        (DF40_80_TOP_SPECS, 38.0, -41.0, "A", None),
        (DF40_80_TOP_SPECS, 38.0, -4.0, "B", None),
        (DF40_50_BOTTOM_SPECS, 16.5, -41.0, "CB", "CM"),
        (DF40_80_BOTTOM_SPECS, 38.0, -41.0, "AB", "AM"),
        (DF40_80_BOTTOM_SPECS, 38.0, -4.0, "BB", "BM"),
    ),
}


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


def _rename_specs(
    specs: tuple[Df40PadSpec, ...],
    *,
    signal_prefix: str,
    mount_prefix: str | None,
) -> tuple[Df40PadSpec, ...]:
    renamed: list[Df40PadSpec] = []
    for spec in specs:
        if spec.name.startswith("M"):
            if mount_prefix is None:
                continue
            new_name = f"{mount_prefix}{spec.name[1:]}"
        else:
            new_name = f"{signal_prefix}{spec.name}"
        renamed.append(
            Df40PadSpec(
                name=new_name,
                x=spec.x,
                y=spec.y,
                rotate=spec.rotate,
                width=spec.width,
                height=spec.height,
                side=spec.side,
            )
        )
    return tuple(renamed)


def _make_landpattern_class(class_name: str, footprint_name: str) -> type[Landpattern]:
    layout = ELEMENT_LAYOUTS[footprint_name]

    class _Landpattern(Landpattern):
        def __init__(self):
            for specs, center_x, center_y, signal_prefix, mount_prefix in layout:
                renamed_specs = _rename_specs(specs, signal_prefix=signal_prefix, mount_prefix=mount_prefix)
                place_df40_pad_specs(self, renamed_specs, x_offset=center_x, y_offset=center_y)

            for index, (x, y, diameter) in enumerate(ELEMENT_HOLES, start=1):
                setattr(self, f"hole_{index}", Cutout(Circle(diameter=diameter).at(x, y)))

            self.ref_text = Silkscreen(Text(">REF", 1.0).at(27.5, 2.5))
            self.outline = Silkscreen(Polyline(0.1524, ELEMENT_OUTLINE))
            self.courtyard = Courtyard(rectangle(55.0, 45.0).at(27.5, -22.5))

    _Landpattern.__name__ = class_name
    return _Landpattern


def _make_component_class(
    class_name: str,
    footprint_name: str,
    signal_map: tuple[tuple[str, tuple[str, ...]], ...],
    description: str,
) -> type[Component]:
    signal_attr_map = OrderedDict((signal_name, _signal_attr_name(signal_name)) for signal_name, _ in signal_map)
    attr_names = tuple(OrderedDict.fromkeys(signal_attr_map.values()))
    landpattern_class = _make_landpattern_class(f"{class_name}Landpattern", footprint_name)

    def __init__(self):
        self.landpattern = landpattern_class()
        self.symbol = _build_symbol(self, attr_names)
        self.signal_to_attr = dict(signal_attr_map)
        self.attr_to_signal = {attr_name: signal_name for signal_name, attr_name in signal_attr_map.items()}
        mapping = {}
        for signal_name, pad_names in signal_map:
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
        "source_signal_names": tuple(signal_name for signal_name, _ in signal_map),
    }
    for attr_name in attr_names:
        attrs[attr_name] = Port()

    return type(class_name, (Component,), attrs)


AlchitryV2TopElement = _make_component_class(
    "AlchitryV2TopElement",
    "V2_TOP",
    V2_TOP_SIGNAL_MAP,
    "Alchitry V2 top-side element footprint composed from shared Hirose DF40 connector models",
)
AlchitryV2BottomElement = _make_component_class(
    "AlchitryV2BottomElement",
    "V2_BOTTOM",
    V2_BOTTOM_SIGNAL_MAP,
    "Alchitry V2 bottom-side element footprint composed from shared Hirose DF40 connector models",
)
AlchitryV2BothElement = _make_component_class(
    "AlchitryV2BothElement",
    "V2_BOTH",
    V2_BOTH_SIGNAL_MAP,
    "Alchitry V2 combined element footprint composed from shared Hirose DF40 connector models",
)

__all__ = [
    "AlchitryV2TopElement",
    "AlchitryV2BottomElement",
    "AlchitryV2BothElement",
]

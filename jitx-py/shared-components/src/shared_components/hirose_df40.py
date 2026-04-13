from __future__ import annotations

# Reusable Hirose DF40 connector geometry used by the Alchitry V2 element import.
#
# Primary sources:
# - Alchitry reference: https://alchitry.com/tutorials/references/pinouts-and-custom-elements/
#   This page states that each V2 side uses one 50-pin Control header and two
#   80-pin bank headers, with pin 1 at the bottom-left in the published diagram.
#   It also names the exact connector variants used by Alchitry:
#   - Top control: DF40HC(4.0)-50DS-0.4V(51)
#   - Top banks:   DF40HC(4.0)-80DS-0.4V(51)
#   - Bottom mate: DF40C-50DP-0.4V(51) and DF40C-80DP-0.4V(51)
# - Published KiCad library: https://cdn.alchitry.com/elements/Alchitry%20V2%20Elements%20KiCAD.zip
#   The numeric pad geometry below was fit to the published Alchitry KiCad
#   footprints so the shared model reproduces the shipped V2 element library.
# - Hirose DF40 family page: https://www.hirose.com/en/product/series/DF40/
#
# These helpers model the connector land patterns used by the Alchitry V2
# element libraries. They are intentionally parameterized in terms of pin count
# and side, rather than hard-coding only the composite Alchitry footprints.
from dataclasses import dataclass

from jitx.component import Component
from jitx.feature import Courtyard, Paste, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

SIGNAL_PITCH_MM = 0.4
TOP_SIGNAL_ROW_OFFSET_MM = 1.54
BOTTOM_SIGNAL_ROW_OFFSET_MM = 1.355
TOP_SIGNAL_PAD_SIZE_MM = (0.7, 0.2)
BOTTOM_SIGNAL_PAD_SIZE_MM = (0.66, 0.23)
BOTTOM_MOUNT_PAD_SIZE_MM = (0.66, 0.35)
MOUNT_PAD_EDGE_DELTA_MM = 0.475


@dataclass(frozen=True)
class Df40PadSpec:
    name: str
    x: float
    y: float
    rotate: float
    width: float
    height: float
    side: Side


class RectSmdPad(Pad):
    def __init__(self, width: float, height: float, *, mask_margin: float = 0.05):
        self.shape = rectangle(width, height)
        self.soldermask = Soldermask(rectangle(width + 2 * mask_margin, height + 2 * mask_margin))
        self.paste = Paste(rectangle(width, height))


def _row_x_positions(pin_count: int) -> tuple[float, ...]:
    per_row = pin_count // 2
    return tuple(SIGNAL_PITCH_MM * (index - (per_row - 1) / 2.0) for index in range(per_row))


def make_df40_pad_specs(
    pin_count: int,
    *,
    top: bool,
    signal_prefix: str = "",
    mount_prefix: str | None = None,
) -> tuple[Df40PadSpec, ...]:
    x_positions = _row_x_positions(pin_count)
    row_offset = TOP_SIGNAL_ROW_OFFSET_MM if top else BOTTOM_SIGNAL_ROW_OFFSET_MM
    signal_width, signal_height = TOP_SIGNAL_PAD_SIZE_MM if top else BOTTOM_SIGNAL_PAD_SIZE_MM
    rotate = 90.0 if top else 270.0
    side = Side.Top if top else Side.Bottom

    specs: list[Df40PadSpec] = []
    for index, x in enumerate(x_positions):
        odd_pin = 2 * index + 1
        even_pin = odd_pin + 1
        specs.append(
            Df40PadSpec(
                name=f"{signal_prefix}{odd_pin}",
                x=x,
                y=row_offset,
                rotate=rotate,
                width=signal_width,
                height=signal_height,
                side=side,
            )
        )
        specs.append(
            Df40PadSpec(
                name=f"{signal_prefix}{even_pin}",
                x=x,
                y=-row_offset,
                rotate=rotate,
                width=signal_width,
                height=signal_height,
                side=side,
            )
        )

    if mount_prefix is not None and not top:
        left_x = x_positions[0] - MOUNT_PAD_EDGE_DELTA_MM
        right_x = x_positions[-1] + MOUNT_PAD_EDGE_DELTA_MM
        mount_width, mount_height = BOTTOM_MOUNT_PAD_SIZE_MM
        specs.extend(
            [
                Df40PadSpec(
                    name=f"{mount_prefix}1",
                    x=left_x,
                    y=row_offset,
                    rotate=270.0,
                    width=mount_width,
                    height=mount_height,
                    side=Side.Bottom,
                ),
                Df40PadSpec(
                    name=f"{mount_prefix}2",
                    x=left_x,
                    y=-row_offset,
                    rotate=270.0,
                    width=mount_width,
                    height=mount_height,
                    side=Side.Bottom,
                ),
                Df40PadSpec(
                    name=f"{mount_prefix}3",
                    x=right_x,
                    y=row_offset,
                    rotate=270.0,
                    width=mount_width,
                    height=mount_height,
                    side=Side.Bottom,
                ),
                Df40PadSpec(
                    name=f"{mount_prefix}4",
                    x=right_x,
                    y=-row_offset,
                    rotate=270.0,
                    width=mount_width,
                    height=mount_height,
                    side=Side.Bottom,
                ),
            ]
        )

    return tuple(specs)


DF40_50_TOP_SPECS = make_df40_pad_specs(50, top=True)
DF40_50_BOTTOM_SPECS = make_df40_pad_specs(50, top=False, mount_prefix="M")
DF40_80_TOP_SPECS = make_df40_pad_specs(80, top=True)
DF40_80_BOTTOM_SPECS = make_df40_pad_specs(80, top=False, mount_prefix="M")


def place_df40_pad_specs(
    landpattern: Landpattern,
    specs: tuple[Df40PadSpec, ...],
    *,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
) -> None:
    for spec in specs:
        pad = RectSmdPad(spec.width, spec.height).at(
            spec.x + x_offset,
            spec.y + y_offset,
            on=spec.side,
            rotate=spec.rotate,
        )
        setattr(landpattern, f"pad_{spec.name}", pad)


def _make_landpattern_class(class_name: str, specs: tuple[Df40PadSpec, ...]) -> type[Landpattern]:
    x_values = [spec.x for spec in specs]
    y_values = [spec.y for spec in specs]
    width = max(x_values) - min(x_values) + 2.0
    height = max(y_values) - min(y_values) + 2.0

    class _Landpattern(Landpattern):
        def __init__(self):
            place_df40_pad_specs(self, specs)
            self.courtyard = Courtyard(rectangle(width, height))

    _Landpattern.__name__ = class_name
    return _Landpattern


def _make_component_class(
    class_name: str,
    *,
    specs: tuple[Df40PadSpec, ...],
    pin_count: int,
    mpn: str,
    description: str,
) -> type[Component]:
    landpattern_class = _make_landpattern_class(f"{class_name}Landpattern", specs)
    mount_names = tuple(spec.name for spec in specs if spec.name.startswith("M"))

    def __init__(self):
        self.landpattern = landpattern_class()
        rows = [Row(left=PinGroup([getattr(self, f"p{pin}")])) for pin in range(1, pin_count + 1)]
        rows.extend(Row(right=PinGroup([getattr(self, name.lower())])) for name in mount_names)
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=1))

        mapping = {getattr(self, f"p{pin}"): getattr(self.landpattern, f"pad_{pin}") for pin in range(1, pin_count + 1)}
        for name in mount_names:
            mapping[getattr(self, name.lower())] = getattr(self.landpattern, f"pad_{name}")
        self.pad_mapping = PadMapping(mapping)

    attrs: dict[str, object] = {
        "__init__": __init__,
        "manufacturer": "Hirose",
        "mpn": mpn,
        "description": description,
        "reference_designator_prefix": "J",
        "value": mpn,
    }
    for pin in range(1, pin_count + 1):
        attrs[f"p{pin}"] = Port()
    for name in mount_names:
        attrs[name.lower()] = Port()
    return type(class_name, (Component,), attrs)


HiroseDf40ControlTop = _make_component_class(
    "HiroseDf40ControlTop",
    specs=DF40_50_TOP_SPECS,
    pin_count=50,
    mpn="DF40 series 50-pin",
    description="Hirose DF40-series 50-pin Alchitry V2 element connector footprint, top mount",
)
HiroseDf40ControlBottom = _make_component_class(
    "HiroseDf40ControlBottom",
    specs=DF40_50_BOTTOM_SPECS,
    pin_count=50,
    mpn="DF40 series 50-pin",
    description="Hirose DF40-series 50-pin Alchitry V2 element connector footprint, bottom mount",
)
HiroseDf40BankTop = _make_component_class(
    "HiroseDf40BankTop",
    specs=DF40_80_TOP_SPECS,
    pin_count=80,
    mpn="DF40 series 80-pin",
    description="Hirose DF40-series 80-pin Alchitry V2 element connector footprint, top mount",
)
HiroseDf40BankBottom = _make_component_class(
    "HiroseDf40BankBottom",
    specs=DF40_80_BOTTOM_SPECS,
    pin_count=80,
    mpn="DF40 series 80-pin",
    description="Hirose DF40-series 80-pin Alchitry V2 element connector footprint, bottom mount",
)

__all__ = [
    "Df40PadSpec",
    "DF40_50_TOP_SPECS",
    "DF40_50_BOTTOM_SPECS",
    "DF40_80_TOP_SPECS",
    "DF40_80_BOTTOM_SPECS",
    "HiroseDf40ControlTop",
    "HiroseDf40ControlBottom",
    "HiroseDf40BankTop",
    "HiroseDf40BankBottom",
    "place_df40_pad_specs",
]

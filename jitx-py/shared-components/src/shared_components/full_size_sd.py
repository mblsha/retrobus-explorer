from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from jitx.component import Component
from jitx.feature import Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Arc
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


@dataclass(frozen=True)
class SdCardContact:
    number: int
    name: str
    spi_role: str | None = None

    @property
    def label(self) -> str:
        role = f" / {self.spi_role}" if self.spi_role is not None else ""
        return f"{self.number} {self.name}{role}"


SD_CARD_CONTACTS = (
    SdCardContact(1, "DAT3", "CS"),
    SdCardContact(2, "CMD", "MOSI"),
    SdCardContact(3, "GND", "VSS1"),
    SdCardContact(4, "3V3", "VDD"),
    SdCardContact(5, "CLK", "SCK"),
    SdCardContact(6, "GND", "VSS2"),
    SdCardContact(7, "DAT0", "MISO"),
    SdCardContact(8, "DAT1"),
    SdCardContact(9, "DAT2"),
)
SD_CARD_PINOUT = {contact.number: contact for contact in SD_CARD_CONTACTS}
SD_CARD_PIN_NUMBER_BY_PORT = {
    "DAT3": 1,
    "CMD": 2,
    "VSS1": 3,
    "VDD": 4,
    "CLK": 5,
    "VSS2": 6,
    "DAT0": 7,
    "DAT1": 8,
    "DAT2": 9,
}

# Exact local pad geometry from SparkFun's SD_Sniffer Eagle
# `SparkFun-Boards:SD-MMC-CARD` package. JITX's bottom-side KiCad export mirrors
# the local Y coordinate once more than Eagle's MR270 transform, so the
# landpattern instantiation below negates Y while retaining these source values.
# Values are (x, y, size_x, size_y), in millimetres.
SD_EDGE_PAD_SPECS: dict[int, tuple[float, float, float, float]] = {
    1: (-6.7446, 14.7134, 1.75, 6.0),
    2: (-4.1950, 14.7030, 1.75, 6.0),
    3: (-1.6000, 14.7030, 1.75, 6.0),
    4: (0.9300, 14.7030, 1.75, 6.0),
    5: (3.4650, 14.7030, 1.75, 6.0),
    6: (6.0300, 14.7030, 1.75, 6.0),
    7: (8.4300, 14.7030, 1.65, 6.0),
    8: (10.4300, 14.7030, 1.25, 6.0),
    9: (-9.5300, 12.0300, 2.00, 5.0),
}

# Reusable placement which reproduces the reference card-edge geometry. The
# pad-center map is expressed in the same board coordinate system as the open
# outline below, so breakout designs can route without duplicating transforms.
SD_EDGE_ORIGIN = (17.78, 16.51)
SD_EDGE_ROTATION = 270.0
SD_CARD_PAD_CENTERS_BY_NUMBER = {
    number: (SD_EDGE_ORIGIN[0] - y, SD_EDGE_ORIGIN[1] - x)
    for number, (x, y, _width, _length) in SD_EDGE_PAD_SPECS.items()
}
SD_CARD_PAD_CENTERS = {
    name: SD_CARD_PAD_CENTERS_BY_NUMBER[number]
    for name, number in SD_CARD_PIN_NUMBER_BY_PORT.items()
}

# The full-size SD section is open at the shoulder so each breakout can append
# its own connector tail. These coordinates are taken from SparkFun's SD
# Sniffer outline. The leading sequence runs from the lower insertion edge to
# the upper shoulder; the trailing sequence closes the lower shoulder.
SD_CARD_FRONT_X = 0.0
SD_CARD_SHOULDER_X = 34.29
SD_CARD_OUTLINE_LEADING: tuple[tuple[float, float], ...] = (
    (SD_CARD_FRONT_X, 3.81),
    (SD_CARD_FRONT_X, 24.13),
    (3.81, 27.94),
    (SD_CARD_SHOULDER_X, 27.94),
    (SD_CARD_SHOULDER_X, 29.21),
)
SD_CARD_OUTLINE_TRAILING: tuple[tuple[float, float], ...] = (
    (SD_CARD_SHOULDER_X, 2.54),
    (SD_CARD_SHOULDER_X, 3.81),
)

SdOutlineElement = tuple[float, float] | Arc


def full_size_sd_card_outline(tail: Sequence[SdOutlineElement]) -> list[SdOutlineElement]:
    """Return the SparkFun-compatible card section closed by ``tail``."""

    return [*SD_CARD_OUTLINE_LEADING, *tail, *SD_CARD_OUTLINE_TRAILING]


class SdCardFingerPad(Pad):
    def __init__(self, *, width: float, length: float):
        self.shape = rectangle(width, length)
        # The mask opening is intentionally a little larger than the copper.
        # No Paste feature is present: these are connector fingers, not SMT pads.
        self.soldermask = Soldermask(rectangle(width + 0.1, length + 0.1))


class FullSizeSdCardEdgeLandpattern(Landpattern):
    def __init__(self):
        for number, (x, y, width, length) in SD_EDGE_PAD_SPECS.items():
            setattr(self, f"p{number}", SdCardFingerPad(width=width, length=length).at(-x, -y, rotate=180))


class FullSizeSdCardEdge(Component):
    DAT3 = Port()
    CMD = Port()
    VSS1 = Port()
    VDD = Port()
    CLK = Port()
    VSS2 = Port()
    DAT0 = Port()
    DAT1 = Port()
    DAT2 = Port()

    manufacturer = "PCB"
    mpn = "FULL-SIZE-SD-CARD-EDGE"
    description = "Full-size SD card PCB edge fingers"
    reference_designator_prefix = "J"
    value = "SD-CARD-EDGE"

    def __init__(self):
        self.landpattern = FullSizeSdCardEdgeLandpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.DAT3]), right=PinGroup([self.DAT2])),
                Row(left=PinGroup([self.CMD]), right=PinGroup([self.DAT1])),
                Row(left=PinGroup([self.VSS1]), right=PinGroup([self.DAT0])),
                Row(left=PinGroup([self.VDD]), right=PinGroup([self.VSS2])),
                Row(left=PinGroup([self.CLK])),
            ],
            config=BoxConfig(group_spacing=1),
        )
        ports = (
            self.DAT3,
            self.CMD,
            self.VSS1,
            self.VDD,
            self.CLK,
            self.VSS2,
            self.DAT0,
            self.DAT1,
            self.DAT2,
        )
        self.pad_mapping = PadMapping(
            {port: getattr(self.landpattern, f"p{number}") for number, port in enumerate(ports, start=1)}
        )

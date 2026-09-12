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

SPARKFUN_MICRO_SD_SNIFFER_SOURCE = (
    "https://github.com/sparkfun/MicroSD_Sniffer/blob/master/Hardware/SparkFun_MicroSD_Sniffer.brd"
)


@dataclass(frozen=True)
class MicroSdContact:
    number: int
    name: str
    spi_role: str | None = None

    @property
    def label(self) -> str:
        role = f" / {self.spi_role}" if self.spi_role is not None else ""
        return f"{self.number} {self.name}{role}"


MICRO_SD_CONTACTS = (
    MicroSdContact(1, "DAT2"),
    MicroSdContact(2, "DAT3", "CS"),
    MicroSdContact(3, "CMD", "MOSI"),
    MicroSdContact(4, "VDD", "3V3"),
    MicroSdContact(5, "CLK", "SCK"),
    MicroSdContact(6, "VSS", "GND"),
    MicroSdContact(7, "DAT0", "MISO"),
    MicroSdContact(8, "DAT1"),
)
MICRO_SD_PINOUT = {contact.number: contact for contact in MICRO_SD_CONTACTS}
MICRO_SD_PIN_NUMBER_BY_PORT = {contact.name: contact.number for contact in MICRO_SD_CONTACTS}
MICRO_SD_DATA_PORTS = ("DAT2", "DAT3", "CMD", "CLK", "DAT0", "DAT1")

# Proven microSD-card edge geometry from SparkFun's open-source MicroSD
# Sniffer. The source board explicitly requires a PCB no thicker than 0.75 mm;
# the nearest broadly available JLCPCB finished thickness is 0.8 mm. Values are
# local (x across the card, y from the insertion edge, width, length), in mm.
MICRO_SD_EDGE_PAD_SPECS: dict[int, tuple[float, float, float, float]] = {
    1: (1.46, 2.30, 0.85, 3.25),
    2: (2.56, 2.30, 0.85, 3.25),
    3: (3.66, 2.30, 0.85, 3.25),
    4: (4.76, 2.10, 0.85, 3.75),
    5: (5.86, 2.30, 0.85, 3.25),
    6: (6.96, 2.10, 0.85, 3.75),
    7: (8.06, 2.30, 0.85, 3.25),
    8: (9.16, 2.30, 0.85, 3.25),
}

# Place the card edge bottom-side at R270. These constants yield a card-aligned
# board coordinate system with the insertion edge at x=0, shoulder at x=15,
# and y spanning 0..11 mm.
MICRO_SD_EDGE_ORIGIN = (0.0, 10.16)
MICRO_SD_EDGE_ROTATION = 270.0
MICRO_SD_EDGE_PAD_CENTERS_BY_NUMBER = {
    number: (round(y, 2), round(MICRO_SD_EDGE_ORIGIN[1] - x, 2))
    for number, (x, y, _width, _length) in MICRO_SD_EDGE_PAD_SPECS.items()
}
MICRO_SD_EDGE_PAD_CENTERS = {
    name: MICRO_SD_EDGE_PAD_CENTERS_BY_NUMBER[number] for name, number in MICRO_SD_PIN_NUMBER_BY_PORT.items()
}

# Card outline transformed into the same card-aligned board coordinates. The
# shoulder remains open so an emulator board can append a connector tail.
MICRO_SD_CARD_FRONT_X = 0.0
MICRO_SD_CARD_SHOULDER_X = 15.0
MICRO_SD_CARD_OUTLINE_LEADING: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (MICRO_SD_CARD_SHOULDER_X, 0.0),
)
MICRO_SD_CARD_OUTLINE_TRAILING: tuple[tuple[float, float], ...] = (
    (MICRO_SD_CARD_SHOULDER_X, 11.0),
    (9.6, 11.0),
    (9.2, 10.6),
    (7.4, 10.6),
    (7.0, 11.0),
    (6.0, 11.0),
    (5.0, 10.0),
    (0.0, 10.0),
)

MicroSdOutlineElement = tuple[float, float] | Arc


def micro_sd_card_outline(tail: Sequence[MicroSdOutlineElement]) -> list[MicroSdOutlineElement]:
    """Return the microSD insertion section closed by an emulator tail."""

    return [*MICRO_SD_CARD_OUTLINE_LEADING, *tail, *MICRO_SD_CARD_OUTLINE_TRAILING]


class MicroSdFingerPad(Pad):
    """Exposed connector finger without solder paste."""

    def __init__(self, *, width: float, length: float):
        self.shape = rectangle(width, length)
        self.soldermask = Soldermask(rectangle(width + 0.10, length + 0.10))


class MicroSdCardEdgeLandpattern(Landpattern):
    def __init__(self):
        for number, (x, y, width, length) in MICRO_SD_EDGE_PAD_SPECS.items():
            # Bottom-side R270 placement reflects local X before rotation. The
            # -x/y coordinates reproduce the SparkFun card-aligned centers.
            setattr(
                self,
                f"p{number}",
                MicroSdFingerPad(width=width, length=length).at(-x, y),
            )


class MicroSdCardEdge(Component):
    """Eight-contact microSD card emulator edge fingers."""

    DAT2 = Port()
    DAT3 = Port()
    CMD = Port()
    VDD = Port()
    CLK = Port()
    VSS = Port()
    DAT0 = Port()
    DAT1 = Port()

    manufacturer = "PCB"
    mpn = "MICRO-SD-CARD-EDGE"
    datasheet = SPARKFUN_MICRO_SD_SNIFFER_SOURCE
    description = "microSD card emulator PCB edge fingers"
    reference_designator_prefix = "J"
    value = "microSD-CARD-EDGE"

    def __init__(self):
        self.landpattern = MicroSdCardEdgeLandpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.DAT2]), right=PinGroup([self.DAT1])),
                Row(left=PinGroup([self.DAT3]), right=PinGroup([self.DAT0])),
                Row(left=PinGroup([self.CMD]), right=PinGroup([self.VSS])),
                Row(left=PinGroup([self.VDD]), right=PinGroup([self.CLK])),
            ],
            config=BoxConfig(group_spacing=1),
        )
        ports = (
            self.DAT2,
            self.DAT3,
            self.CMD,
            self.VDD,
            self.CLK,
            self.VSS,
            self.DAT0,
            self.DAT1,
        )
        self.pad_mapping = PadMapping(
            {port: getattr(self.landpattern, f"p{number}") for number, port in enumerate(ports, start=1)}
        )

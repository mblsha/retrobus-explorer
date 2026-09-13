from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from jitx.component import Component
from jitx.feature import Courtyard, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Arc, Circle, Polyline
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


MOLEX_104031_0811_DATASHEET = (
    "https://www.molex.com/content/dam/molex/molex-dot-com/products/"
    "automated/en-us/salesdrawingpdf/104/104031/1040310811_sd.pdf"
)


# Exact recommended copper geometry from the Molex 104031-0811 sales drawing,
# cross-checked against KiCad 9's official microSD_HC_Molex_104031-0811
# footprint. Values are local (x, y, width, height) in millimetres.
MOLEX_104031_0811_SIGNAL_PAD_SPECS: dict[int, tuple[float, float, float, float]] = {
    1: (-3.105, -5.45, 0.85, 1.10),
    2: (-2.005, -5.45, 0.85, 1.10),
    3: (-0.905, -5.45, 0.85, 1.10),
    4: (0.195, -5.45, 0.85, 1.10),
    5: (1.295, -5.45, 0.85, 1.10),
    6: (2.395, -5.45, 0.85, 1.10),
    7: (3.495, -5.45, 0.85, 1.10),
    8: (4.545, -5.45, 0.75, 1.10),
}
MOLEX_104031_0811_DETECT_PAD_SPECS: dict[int, tuple[float, float, float, float]] = {
    9: (-5.74, 0.70, 1.20, 1.00),
    10: (-5.74, 4.40, 1.20, 1.00),
}
MOLEX_104031_0811_SHIELD_PAD_SPECS: tuple[tuple[float, float, float, float], ...] = (
    (-5.565, -5.325, 1.55, 1.35),
    (-2.240, 5.375, 1.90, 1.35),
    (3.730, 5.375, 1.90, 1.35),
    (5.755, -5.100, 1.17, 1.80),
)
MOLEX_104031_0811_BODY_SIZE = (11.95, 11.40)
MOLEX_104031_0811_COURTYARD_SIZE = (13.68, 13.05)


class MicroSdSmtPad(Pad):
    def __init__(self, *, width: float, height: float):
        self.shape = rectangle(width, height)
        self.soldermask = Soldermask(rectangle(width + 0.10, height + 0.10))
        self.paste = Paste(rectangle(width, height))



class Molex1040310811Landpattern(Landpattern):
    def __init__(self):
        for number, (x, y, width, height) in MOLEX_104031_0811_SIGNAL_PAD_SPECS.items():
            setattr(self, f"p{number}", MicroSdSmtPad(width=width, height=height).at(x, y))
        for number, (x, y, width, height) in MOLEX_104031_0811_DETECT_PAD_SPECS.items():
            setattr(self, f"p{number}", MicroSdSmtPad(width=width, height=height).at(x, y))
        for index, (x, y, width, height) in enumerate(MOLEX_104031_0811_SHIELD_PAD_SPECS, start=1):
            setattr(self, f"shield{index}", MicroSdSmtPad(width=width, height=height).at(x, y))

        half_width = MOLEX_104031_0811_BODY_SIZE[0] / 2.0
        half_height = MOLEX_104031_0811_BODY_SIZE[1] / 2.0
        self.outline = Silkscreen(
            Polyline(
                0.12,
                [
                    (-half_width, -half_height),
                    (-half_width, half_height),
                    (half_width, half_height),
                    (half_width, -half_height),
                ],
            )
        )
        self.pin_one = Silkscreen(Circle(diameter=0.35).at(-3.105, -6.05))
        self.courtyard = Courtyard(rectangle(*MOLEX_104031_0811_COURTYARD_SIZE))


class Molex1040310811MicroSdSocket(Component):
    """Molex push-pull micro-SD socket with card-detect and four shell tabs."""

    DAT2 = Port()
    DAT3 = Port()
    CMD = Port()
    VDD = Port()
    CLK = Port()
    VSS = Port()
    DAT0 = Port()
    DAT1 = Port()
    DETECT_A = Port()
    DETECT_B = Port()
    SHIELD = [Port() for _ in range(4)]

    manufacturer = "Molex"
    mpn = "104031-0811"
    datasheet = MOLEX_104031_0811_DATASHEET
    description = "1.10 mm pitch push-pull micro-SD socket, 1.42 mm high, with detect switch"
    reference_designator_prefix = "J"
    value = "microSD"

    def __init__(self):
        self.landpattern = Molex1040310811Landpattern()
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.DAT2]), right=PinGroup([self.DAT1])),
                Row(left=PinGroup([self.DAT3]), right=PinGroup([self.DAT0])),
                Row(left=PinGroup([self.CMD]), right=PinGroup([self.VSS])),
                Row(left=PinGroup([self.VDD]), right=PinGroup([self.CLK])),
                Row(left=PinGroup([self.DETECT_A]), right=PinGroup([self.DETECT_B])),
                Row(left=PinGroup(self.SHIELD)),
            ],
            config=BoxConfig(group_spacing=1),
        )
        signal_ports = (
            self.DAT2,
            self.DAT3,
            self.CMD,
            self.VDD,
            self.CLK,
            self.VSS,
            self.DAT0,
            self.DAT1,
        )
        mapping = {
            port: getattr(self.landpattern, f"p{number}")
            for number, port in enumerate(signal_ports, start=1)
        }
        mapping[self.DETECT_A] = self.landpattern.p9
        mapping[self.DETECT_B] = self.landpattern.p10
        mapping.update(
            {
                port: getattr(self.landpattern, f"shield{index}")
                for index, port in enumerate(self.SHIELD, start=1)
            }
        )
        self.pad_mapping = PadMapping(mapping)

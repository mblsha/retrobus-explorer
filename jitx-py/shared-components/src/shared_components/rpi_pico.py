from __future__ import annotations

from jitx.circuit import Circuit
from jitx.component import Component
from jitx.landpattern import PadMapping
from jitx.net import Port
from jitx.placement import Placement, Side
from jitx.toleranced import Toleranced
from jitxlib.landpatterns.generators.header import Header
from jitxlib.landpatterns.leads import THLead
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

PICO_PIN_COUNT = 40
PICO_PINS_PER_ROW = 20
PICO_PIN_PITCH = 2.54
PICO_ROW_SPACING = 17.78
PICO_BOARD_LENGTH = 51.0
PICO_BOARD_WIDTH = 21.0


def pico_physical_pin_index(physical_number: int) -> int:
    if not 1 <= physical_number <= PICO_PIN_COUNT:
        raise ValueError(f"Pico physical pin must be 1..{PICO_PIN_COUNT}, got {physical_number}")
    return physical_number - 1


class PinHeader1x20(Component):
    """One half of the standard Raspberry Pi Pico 40-pin footprint."""

    p = [Port() for _ in range(PICO_PINS_PER_ROW)]
    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "generic-20x1-2.54mm-th"
    value = "20X1-pin-header"

    def __init__(self):
        self.landpattern = Header(
            num_leads=PICO_PINS_PER_ROW,
            num_rows=1,
            lead=THLead(
                length=Toleranced.exact(3.0),
                width=Toleranced.exact(0.64),
            ),
            pitch=PICO_PIN_PITCH,
        )
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[index]])) for index in range(PICO_PINS_PER_ROW)],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping(
            {self.p[index]: self.landpattern.p[index + 1] for index in range(PICO_PINS_PER_ROW)}
        )


class Pico40PinHeaders(Circuit):
    """Standard Pico footprint with each numbered physical pin exposed.

    Physical pins 1-20 run along the left row. Pins 21-40 run in the
    opposite direction along the right row, matching the Raspberry Pi Pico and
    footprint-compatible boards such as the Pimoroni Pico Plus 2.
    """

    physical = [Port() for _ in range(PICO_PIN_COUNT)]

    def __init__(self):
        super().__init__()
        self.left_header = PinHeader1x20()
        self.right_header = PinHeader1x20()

        self.nets = [self.physical[index] + self.left_header.p[index] for index in range(PICO_PINS_PER_ROW)]
        self.nets.extend(
            self.physical[PICO_PINS_PER_ROW + index] + self.right_header.p[index] for index in range(PICO_PINS_PER_ROW)
        )

        half_spacing = PICO_ROW_SPACING / 2.0
        self.place(self.left_header, Placement((-half_spacing, 0.0), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.right_header, Placement((half_spacing, 0.0), 270, on=Side.Top))  # ty: ignore[no-matching-overload]

    def pin(self, physical_number: int) -> Port:
        return self.physical[pico_physical_pin_index(physical_number)]

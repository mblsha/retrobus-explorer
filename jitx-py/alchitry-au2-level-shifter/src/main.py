from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal, Protocol, cast

from alchitry_v2_elements import AlchitryFtV2BottomElement
from jitx.board import Board
from jitx.circuit import Circuit
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.net import Port
from jitx.placement import Placement, Side
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Text
from jitx.substrate import Substrate
from jitx.via import Via, ViaType
from shared_components.alchitry_v2 import FT_PROFILE
from shared_components.connectivity import connect_ports
from shared_components.fabrication import jlcpcb_fab_constraints, jlcpcb_stackup
from shared_components.ffc import RetroBus60FfcConnector
from shared_components.level_shifter import Cap0402, PinHeader2x3, Txb0108Pwr
from shared_components.saleae import SaleaeProbeHeader2x4
from shared_components.testpads import gnd_testpads_class

from src.pinmap import DATA_CONNECTIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

REFERENCE_BOARD_WIDTH = 55.0
REFERENCE_BOARD_HEIGHT = 45.0
BOARD_EXTENSION = 4.5
BOARD_WIDTH = REFERENCE_BOARD_WIDTH + BOARD_EXTENSION
BOARD_HEIGHT = REFERENCE_BOARD_HEIGHT
BOARD_SHAPE = rectangle(BOARD_WIDTH, BOARD_HEIGHT, radius=3.0)
SIGNAL_AREA = rectangle(BOARD_WIDTH - 1.0, BOARD_HEIGHT - 1.0, radius=2.5)
# Align the official Au2 outline with the adapter's negative-X, top, and bottom
# edges. The additional 4.5 mm is therefore positive X in JITX and appears on
# the left in the mirrored bottom view used for assembly review.
AU2_CENTER_X = (REFERENCE_BOARD_WIDTH - BOARD_WIDTH) / 2.0
V2_BOTTOM_ELEMENT_ORIGIN = (-BOARD_WIDTH / 2.0, BOARD_HEIGHT / 2.0)
AU2_CONNECTOR_ELEMENT = AlchitryFtV2BottomElement
GROUND_PAD_DIAMETER = 3.0
GROUND_HOLE_DIAMETER = 2.2
REFERENCE_MOUNTING_HOLE_X = 25.0
REFERENCE_MOUNTING_HOLE_Y = 20.0
GROUND_PAD_ARRAY_WIDTH = 2.0 * (REFERENCE_MOUNTING_HOLE_X + GROUND_PAD_DIAMETER)
GROUND_PAD_ARRAY_HEIGHT = 2.0 * (REFERENCE_MOUNTING_HOLE_Y + GROUND_PAD_DIAMETER)
AU2_GROUNDED_CORNERS = gnd_testpads_class(
    diameter=GROUND_PAD_DIAMETER,
    hole_diameter=GROUND_HOLE_DIAMETER,
    width=GROUND_PAD_ARRAY_WIDTH,
    height=GROUND_PAD_ARRAY_HEIGHT,
)
GROUNDED_CORNERS_ORIGIN = (AU2_CENTER_X, 0.0)


def _unclaimed_signal_pins(connector: Literal["A", "B"]) -> tuple[int, ...]:
    profile = FT_PROFILE.connector_profile(connector)
    claimed = set(profile.claims_by_pin())
    return tuple(pin for pin in range(1, profile.pin_count + 1) if pin not in claimed)


BANK_A_SIGNAL_PINS = _unclaimed_signal_pins("A")
BANK_B_SIGNAL_PINS = _unclaimed_signal_pins("B")
SAFE_PIN_NAMES = tuple(f"A{pin}" for pin in BANK_A_SIGNAL_PINS) + tuple(f"B{pin}" for pin in BANK_B_SIGNAL_PINS)
SAFE_PIN_INDEX = {name: index for index, name in enumerate(SAFE_PIN_NAMES)}

# One explicit route owns both halves of every data path.  Keeping the FFC to
# shifter channel permutation together with its Au2 target prevents the two
# halves from silently diverging, as the previous split constants did.
DATA_PIN_NAMES = tuple(route.fpga_pin for route in DATA_CONNECTIONS)
SALEAE_PIN_NAMES = ("B15", "B21", "B27", "B39", "B3", "B5", "B9", "B11")
UPPER_GPIO_LABELS = (7, 6, 5, 4)
LOWER_GPIO_LABELS = (3, 2, 1, 0)
SUPPLY_SELECT_LABELS = ("NC", "VDD", "3V3")
SUPPLY_BUS_LABEL = "VBus"

SHIFTER_PARENT_PLACEMENTS = (
    ((-2.736, 9.468), 90.0),
    ((6.492, 9.468), 90.0),
    ((11.257, -9.468), 270.0),
    ((20.259, -9.468), 270.0),
    ((2.249, -9.468), 270.0),
    ((15.543, 9.468), 90.0),
)
FFC_PARENT_PLACEMENTS = (((8.468, -8.25), 180.0), ((8.468, 8.25), 180.0))
SALEAE_PARENT_PLACEMENT = ((-15.25, -10.0), 0.0)
SUPPLY_SELECT_PARENT_PLACEMENT = ((-23.25, 13.5), 180.0)



def port_attr(obj: object, name: str) -> Port:
    return cast(Port, getattr(obj, name))


class AlchitryV2BottomInterface(Protocol):
    GND: Port
    V3V3: Port
    VCC: Port

    def port(self, signal_name: str) -> Port: ...


class AlchitryAu2LevelShifterSubstrate(Substrate):
    stackup = jlcpcb_stackup(4)
    constraints = jlcpcb_fab_constraints(4)

    class StandardVia(Via):
        start_layer = 0
        stop_layer = 3
        diameter = 0.45
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class Saleae8(Circuit):
    gnd = Port()
    data = [Port() for _ in range(8)]

    def __init__(self, *, text_angle: float = 0.0):
        super().__init__()
        self.upper = SaleaeProbeHeader2x4()
        self.lower = SaleaeProbeHeader2x4()
        self.nets = [
            connect_ports(None, self.gnd, self.upper.GND, self.lower.GND),
            *(
                connect_ports(
                    f"SALEAE{index}",
                    self.data[index],
                    port_attr(self.lower if index < 4 else self.upper, f"p{index % 4}"),
                )
                for index in range(8)
            ),
        ]
        self.place(self.upper, Placement((0.0, 6.731), on=Side.Top))
        self.place(self.lower, Placement((0.0, -6.731), on=Side.Top))

        for index, (upper_label, lower_label) in enumerate(zip(UPPER_GPIO_LABELS, LOWER_GPIO_LABELS, strict=True)):
            offset = 2.54 * index
            self += Silkscreen(
                Text(str(upper_label), 1.5).at(3.5, 6.731 + 3.8 - offset, rotate=text_angle),
                side=FeatureSide.Top,
            )
            self += Silkscreen(
                Text(str(lower_label), 1.5).at(3.5, -6.731 + 3.8 - offset, rotate=text_angle),
                side=FeatureSide.Top,
            )


class SupplySelectHeader(Circuit):
    bus = Port()
    au2_vdd = Port()
    au2_3v3 = Port()

    def __init__(self, *, text_angle: float = 0.0):
        super().__init__()
        self.header = PinHeader2x3()
        self.nets = [
            connect_ports(None, self.bus, self.header.p[0], self.header.p[2], self.header.p[4]),
            connect_ports(None, self.au2_3v3, self.header.p[1]),
            connect_ports(None, self.au2_vdd, self.header.p[3]),
        ]
        self.place(self.header, Placement((0.0, 0.0), on=Side.Top))

        for index, name in enumerate(SUPPLY_SELECT_LABELS):
            offset = 2.54 * index - 2.54
            self += Silkscreen(Text(name, 1.5).at(4.1, offset, rotate=text_angle), side=FeatureSide.Top)
            self += Silkscreen(
                Text(SUPPLY_BUS_LABEL, 1.5).at(-4.5, offset, rotate=text_angle),
                side=FeatureSide.Top,
            )


class LevelShifter(Circuit):
    vcclo = Port()
    vcchi = Port()
    gnd = Port()
    oe = Port()
    lo = [Port() for _ in range(8)]
    hi = [Port() for _ in range(8)]

    def __init__(self):
        super().__init__()
        self.shifter = Txb0108Pwr()
        self.cap_lo = Cap0402()
        self.cap_hi = Cap0402()
        self.nets = [
            connect_ports(None, self.gnd, self.shifter.GND, self.cap_lo.p[1], self.cap_hi.p[1]),
            connect_ports(None, self.vcclo, self.shifter.VCCA, self.cap_lo.p[0]),
            connect_ports(None, self.vcchi, self.shifter.VCCB, self.cap_hi.p[0]),
            connect_ports(None, self.oe, self.shifter.OE),
            *(connect_ports(None, self.lo[index], port_attr(self.shifter, f"A{index + 1}")) for index in range(8)),
            *(connect_ports(None, self.hi[index], port_attr(self.shifter, f"B{index + 1}")) for index in range(8)),
        ]
        self.place(self.shifter, Placement((0.0, 0.0), 270, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.cap_lo, Placement((-2.0, 3.9), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.cap_hi, Placement((2.0, 3.9), 270, on=Side.Top))  # ty: ignore[no-matching-overload]


class AlchitryAu2FtSafeInterface(Circuit):
    data = [Port() for _ in SAFE_PIN_NAMES]
    data_a = [Port() for _ in BANK_A_SIGNAL_PINS]
    data_b = [Port() for _ in BANK_B_SIGNAL_PINS]
    V3V3 = Port()
    VDD = Port()
    GND = Port()

    def __init__(self):
        super().__init__()
        self.element = AU2_CONNECTOR_ELEMENT(include_holes=False)  # ty: ignore[unknown-argument]
        element = cast(AlchitryV2BottomInterface, self.element)
        self.nets = [
            connect_ports(None, self.GND, element.GND),
            connect_ports(None, self.V3V3, element.V3V3),
            connect_ports(None, self.VDD, element.VCC),
        ]

        for index, pin in enumerate(BANK_A_SIGNAL_PINS):
            self.nets.append(connect_ports(None, self.data[index], self.data_a[index], element.port(f"A{pin}")))
        bank_b_offset = len(BANK_A_SIGNAL_PINS)
        for index, pin in enumerate(BANK_B_SIGNAL_PINS):
            self.nets.append(
                connect_ports(
                    None,
                    self.data[bank_b_offset + index],
                    self.data_b[index],
                    element.port(f"B{pin}"),
                )
            )

        # Place the canonical reference-derived V2_BOTTOM element as one unit.
        # Its footprint owns connector positions, pad identities, mounting pads,
        # and the upstream C30/GND quirk. The reference NPTH mounting holes are
        # omitted here and replaced with GND-connected plated holes below.
        self.place(self.element, Placement(V2_BOTTOM_ELEMENT_ORIGIN, on=Side.Top))


class AlchitryAu2LevelShifterCircuit(Circuit):
    gnd = Port()
    v3v3 = Port()
    vdd = Port()
    vbus = Port()

    def __init__(self):
        super().__init__()
        self.fpga = AlchitryAu2FtSafeInterface()
        self.ffc1 = RetroBus60FfcConnector(flip_pins=False)
        self.ffc2 = RetroBus60FfcConnector(flip_pins=False)
        self.saleae = Saleae8(text_angle=90.0)
        self.supply_select = SupplySelectHeader(text_angle=180.0)
        self.shift = [LevelShifter() for _ in range(6)]
        self.tp_gnd = AU2_GROUNDED_CORNERS()

        gnd_net = connect_ports(
            "GND",
            self.gnd,
            self.fpga.GND,
            self.ffc1.GND,
            self.ffc2.GND,
            self.saleae.gnd,
            port_attr(self.tp_gnd, "GND"),
        )
        v3v3_net = connect_ports("V3V3", self.v3v3, self.fpga.V3V3, self.supply_select.au2_3v3)
        vdd_net = connect_ports("VDD", self.vdd, self.fpga.VDD, self.supply_select.au2_vdd)
        vbus_net = connect_ports("VBUS", self.vbus, self.ffc1.VCC5V, self.ffc2.VCC5V, self.supply_select.bus)
        for shifter in self.shift:
            gnd_net = gnd_net + shifter.gnd
            v3v3_net = v3v3_net + shifter.vcclo + shifter.oe
            vbus_net = vbus_net + shifter.vcchi
        self.nets = [gnd_net, v3v3_net, vdd_net, vbus_net]

        for index, pin_name in enumerate(SALEAE_PIN_NAMES):
            self.nets.append(
                connect_ports(f"SALEAE{index}", self.saleae.data[index], self.fpga.data[SAFE_PIN_INDEX[pin_name]])
            )

        for data_index, route in enumerate(DATA_CONNECTIONS):
            shifter = self.shift[route.shifter_index]
            self.nets.append(
                connect_ports(
                    f"DATA{data_index}",
                    self.ffc1.data[data_index],
                    self.ffc2.data[data_index],
                    shifter.hi[route.shifter_pin],
                )
            )
            self.nets.append(
                connect_ports(
                    f"loDATA{data_index}",
                    self.fpga.data[SAFE_PIN_INDEX[route.fpga_pin]],
                    shifter.lo[route.shifter_pin],
                )
            )

        # The Au2 connector and level shifters mate underneath this element;
        # the FFC, Saleae, and supply-select connectors remain accessible from
        # the top. Positions and angles are mirrored in X when assemblies move
        # sides so each physical face retains the intended layout.
        self.place(self.fpga, Placement((0.0, 0.0), on=Side.Top))
        for shifter, (position, rotation) in zip(self.shift, SHIFTER_PARENT_PLACEMENTS, strict=True):
            self.place(shifter, Placement(position, rotation, on=Side.Bottom))  # ty: ignore[no-matching-overload]
        self.place(self.tp_gnd, Placement(GROUNDED_CORNERS_ORIGIN, on=Side.Bottom))

        for ffc, (position, rotation) in zip(
            (self.ffc1, self.ffc2),
            FFC_PARENT_PLACEMENTS,
            strict=True,
        ):
            self.place(ffc, Placement(position, rotation, on=Side.Top))  # ty: ignore[no-matching-overload]
        saleae_position, saleae_rotation = SALEAE_PARENT_PLACEMENT
        self.place(self.saleae, Placement(saleae_position, saleae_rotation, on=Side.Top))  # ty: ignore[no-matching-overload]
        supply_position, supply_rotation = SUPPLY_SELECT_PARENT_PLACEMENT
        self.place(self.supply_select, Placement(supply_position, supply_rotation, on=Side.Top))  # ty: ignore[no-matching-overload]

        self += Silkscreen(Text("Level Shifter Element (Au2)", 1.4).at(3.0, 1.0), side=FeatureSide.Top)
        self += Silkscreen(Text(f"(c) mblsha {BOARD_DATE}", 1.2).at(3.0, -1.0), side=FeatureSide.Top)
        self += Silkscreen(Text("VDD <= 5.5V", 1.0).at(0.0, 18.0), side=FeatureSide.Top)


class AlchitryAu2LevelShifterBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class AlchitryAu2LevelShifterDesign(Design):
    substrate = AlchitryAu2LevelShifterSubstrate()
    board = AlchitryAu2LevelShifterBoard()
    circuit = AlchitryAu2LevelShifterCircuit()

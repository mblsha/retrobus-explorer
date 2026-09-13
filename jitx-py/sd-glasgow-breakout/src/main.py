from __future__ import annotations

import subprocess
from math import sqrt
from pathlib import Path

from jitx.board import Board
from jitx.circuit import Circuit
from jitx.copper import Copper, Pour
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.net import Net, Port
from jitx.placement import Placement, Side
from jitx.shapes import Shape
from jitx.shapes.primitive import Anchor, Arc, ArcPolygon, Polyline, Text
from jitx.substrate import Substrate
from jitx.transform import Transform
from jitx.via import Via, ViaType
from shared_components.fabrication import jlcpcb_fab_constraints, jlcpcb_stackup
from shared_components.full_size_sd import (
    SD_CARD_OUTLINE_LEADING,
    SD_CARD_OUTLINE_TRAILING,
    SD_CARD_PAD_CENTERS,
    SD_CARD_PIN_NUMBER_BY_PORT,
    SD_CARD_PINOUT,
    SD_CARD_SHOULDER_X,
    SD_EDGE_ORIGIN,
    SD_EDGE_ROTATION,
    FullSizeSdCardEdge,
    full_size_sd_card_outline,
)
from shared_components.glasgow import (
    HCTL_PM254_OPPOSITE_SIDE_MATING_PIN,
    HCTL_PM254_PAD_CENTERS,
    HCTL_PM254_PITCH,
    GlasgowPortConnector,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

TAIL_START_X = 37.0
BOARD_REAR_X = 47.0
SD_CARD_BOTTOM_Y = SD_CARD_OUTLINE_LEADING[0][1]
SD_CARD_TOP_Y = SD_CARD_OUTLINE_LEADING[2][1]
SD_CARD_CENTER_Y = (SD_CARD_BOTTOM_Y + SD_CARD_TOP_Y) / 2.0
BOARD_CENTER_Y = SD_CARD_CENTER_Y
BOARD_HALF_HEIGHT = 15.0
BOARD_TOP_Y = BOARD_CENTER_Y + BOARD_HALF_HEIGHT
BOARD_BOTTOM_Y = BOARD_CENTER_Y - BOARD_HALF_HEIGHT
BOARD_REAR_CORNER_RADIUS = 2.0
BOARD_REAR_CORNER_X = BOARD_REAR_X - BOARD_REAR_CORNER_RADIUS
BOARD_REAR_TOP_CORNER_Y = BOARD_TOP_Y - BOARD_REAR_CORNER_RADIUS
BOARD_REAR_BOTTOM_CORNER_Y = BOARD_BOTTOM_Y + BOARD_REAR_CORNER_RADIUS
TAIL_CHAMFER_SIZE = BOARD_TOP_Y - SD_CARD_OUTLINE_LEADING[-1][1]
TAIL_CHAMFER_X = SD_CARD_SHOULDER_X + TAIL_CHAMFER_SIZE

BOARD_OUTLINE = full_size_sd_card_outline(
    [
        (TAIL_CHAMFER_X, BOARD_TOP_Y),
        (TAIL_START_X, BOARD_TOP_Y),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_TOP_CORNER_Y), BOARD_REAR_CORNER_RADIUS, 90.0, -90.0),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_BOTTOM_CORNER_Y), BOARD_REAR_CORNER_RADIUS, 0.0, -90.0),
        (TAIL_START_X, BOARD_BOTTOM_Y),
        (TAIL_CHAMFER_X, BOARD_BOTTOM_Y),
    ]
)
BOARD_SHAPE = ArcPolygon(BOARD_OUTLINE)

POUR_EDGE_CLEARANCE = 0.5
POUR_REAR_CORNER_RADIUS = BOARD_REAR_CORNER_RADIUS - POUR_EDGE_CLEARANCE
POUR_CHAMFER_OFFSET = POUR_EDGE_CLEARANCE * (sqrt(2.0) - 1.0)
POUR_SHOULDER_X = SD_CARD_SHOULDER_X + POUR_EDGE_CLEARANCE
POUR_CHAMFER_X = TAIL_CHAMFER_X + POUR_CHAMFER_OFFSET
POUR_TOP_Y = BOARD_TOP_Y - POUR_EDGE_CLEARANCE
POUR_BOTTOM_Y = BOARD_BOTTOM_Y + POUR_EDGE_CLEARANCE
POUR_TOP_SHOULDER_Y = SD_CARD_OUTLINE_LEADING[-1][1] - POUR_CHAMFER_OFFSET
POUR_BOTTOM_SHOULDER_Y = SD_CARD_OUTLINE_TRAILING[0][1] + POUR_CHAMFER_OFFSET
SIGNAL_AREA = ArcPolygon(
    [
        (0.5, 4.31),
        (0.5, 23.92),
        (4.02, 27.44),
        (POUR_SHOULDER_X, 27.44),
        (POUR_SHOULDER_X, POUR_TOP_SHOULDER_Y),
        (POUR_CHAMFER_X, POUR_TOP_Y),
        (37.2, POUR_TOP_Y),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_TOP_CORNER_Y), POUR_REAR_CORNER_RADIUS, 90.0, -90.0),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_BOTTOM_CORNER_Y), POUR_REAR_CORNER_RADIUS, 0.0, -90.0),
        (37.2, POUR_BOTTOM_Y),
        (POUR_CHAMFER_X, POUR_BOTTOM_Y),
        (POUR_SHOULDER_X, POUR_BOTTOM_SHOULDER_Y),
        (POUR_SHOULDER_X, 4.31),
    ]
)
TOP_GROUND_POUR_AREA = SIGNAL_AREA
BOTTOM_GROUND_POUR_AREA = SIGNAL_AREA

GLASGOW_ORIGIN = (BOARD_REAR_X - 4.0, SD_CARD_CENTER_Y)
GLASGOW_ROTATION = 180.0
GLASGOW_SIDE = Side.Bottom
GLASGOW_SWAP_ROWS_FOR_MATING = True

# The socket is mounted on the SD card's bottom and mates with the top of the
# Glasgow. Swap each pin pair so the ground row faces the SD card while the
# connector's end-to-end orientation and Glasgow pinout stay unchanged.
# DAT2 is fixed to IO7. The remaining assignment is the minimum total direct
# pad-to-pad distance over distinct IO0..IO6 choices, leaving the two rows in
# the SD power/ground gap unused. The physical Y ordering remains crossing-free.
SD_TO_GLASGOW_IO = {
    "DAT1": 0,
    "DAT0": 1,
    "CLK": 2,
    "CMD": 5,
    "DAT3": 6,
    "DAT2": 7,
}
GLASGOW_UNUSED_IO = (3, 4)
SD_VDD_GLASGOW_PIN = 1
GLASGOW_VIO_CONNECTED = False
GLASGOW_PIN_LABEL_SIZE = 1.0
GLASGOW_PIN_LABEL_RIGHT_X = GLASGOW_ORIGIN[0] - 2.4

SD_CONTACT_LABEL_X = 15.0
SD_CONTACT_LABEL_SIZE = 1.0
SD_CONTACT_LABELS = tuple(
    (number, SD_CARD_PINOUT[number].label, SD_CARD_PAD_CENTERS[port_name][1])
    for port_name, number in sorted(SD_CARD_PIN_NUMBER_BY_PORT.items(), key=lambda item: item[1])
)

SD_GROUND_VIA_X = 8.0
SD_GROUND_VIA_CENTERS = (
    (SD_GROUND_VIA_X, SD_CARD_PAD_CENTERS["VSS1"][1]),
    (SD_GROUND_VIA_X, SD_CARD_PAD_CENTERS["VSS2"][1]),
)
SIGNAL_TRACE_WIDTH = 0.2
POWER_TRACE_WIDTH = 0.3


def glasgow_pad_center(pin: int) -> tuple[float, float]:
    """Global center for a physical bottom-side Glasgow connector pad."""

    x, y = HCTL_PM254_PAD_CENTERS[pin]
    return (GLASGOW_ORIGIN[0] + x, GLASGOW_ORIGIN[1] - y)


def glasgow_logical_pad_center(pin: int) -> tuple[float, float]:
    """Physical pad center that mates with one logical Glasgow pin."""

    physical_pin = (
        HCTL_PM254_OPPOSITE_SIDE_MATING_PIN[pin] if GLASGOW_SWAP_ROWS_FOR_MATING else pin
    )
    return glasgow_pad_center(physical_pin)


SENSE_CENTER = glasgow_logical_pad_center(SD_VDD_GLASGOW_PIN)
SENSE_ROUTE_LAYER = 1
SENSE_ROUTE_BEHIND_X = BOARD_REAR_X - 1.4
SENSE_ROUTE_ENTRY_Y = GLASGOW_ORIGIN[1]
SENSE_ROUTE_AROUND_Y = SENSE_CENTER[1] - HCTL_PM254_PITCH / 2.0
SENSE_ROUTE_POINTS = [
    SD_CARD_PAD_CENTERS["VDD"],
    (SD_CARD_PAD_CENTERS["VDD"][0], SENSE_ROUTE_ENTRY_Y),
    (SENSE_ROUTE_BEHIND_X, SENSE_ROUTE_ENTRY_Y),
    (SENSE_ROUTE_BEHIND_X, SENSE_ROUTE_AROUND_Y),
    (SENSE_CENTER[0], SENSE_ROUTE_AROUND_Y),
    SENSE_CENTER,
]


# Exact bottom-layer polylines produced by JITX's live autorouter with 0.20 mm
# trace width and clearance. Capturing them in source makes subsequent builds
# reproduce the autorouted physical design without relying on session state.
AUTOROUTED_SIGNAL_PATHS = {
    "DAT1": [
        SD_CARD_PAD_CENTERS["DAT1"],
        (41.724450, 5.885014),
        (42.206378, 5.993504),
        glasgow_logical_pad_center(3),
    ],
    "DAT0": [
        SD_CARD_PAD_CENTERS["DAT0"],
        (41.739816, 8.425044),
        (42.206378, 8.533504),
        glasgow_logical_pad_center(5),
    ],
    "CLK": [
        SD_CARD_PAD_CENTERS["CLK"],
        (41.726585, 13.164995),
        (42.206378, 13.056496),
        glasgow_logical_pad_center(7),
    ],
    "CMD": [
        SD_CARD_PAD_CENTERS["CMD"],
        (41.727723, 20.784998),
        (42.206378, 20.676496),
        glasgow_logical_pad_center(13),
    ],
    "DAT3": [
        SD_CARD_PAD_CENTERS["DAT3"],
        (41.727997, 23.324998),
        (42.206378, 23.216496),
        glasgow_logical_pad_center(15),
    ],
    "DAT2": [
        SD_CARD_PAD_CENTERS["DAT2"],
        (41.735350, 25.864987),
        (42.206378, 25.756496),
        glasgow_logical_pad_center(17),
    ],
}


GLASGOW_IO_TO_SD = {io_index: name for name, io_index in SD_TO_GLASGOW_IO.items()}
GLASGOW_ROW_LABELS = (
    ((1, 2), "VDD VS", GLASGOW_PIN_LABEL_RIGHT_X, glasgow_logical_pad_center(1)[1] + 0.3),
    *(
        (
            (3 + 2 * io_index, 4 + 2 * io_index),
            f"{GLASGOW_IO_TO_SD[io_index]} G{io_index}"
            if io_index in GLASGOW_IO_TO_SD
            else f"G{io_index}",
            GLASGOW_PIN_LABEL_RIGHT_X,
            glasgow_logical_pad_center(3 + 2 * io_index)[1],
        )
        for io_index in range(8)
    ),
    ((19, 20), "··", GLASGOW_PIN_LABEL_RIGHT_X, glasgow_logical_pad_center(19)[1] - 0.8),
)


def trace(width: float, points: list[tuple[float, float]], *, layer: int) -> Copper:
    return Copper(Polyline(width, points), layer=layer)


def bottom_text(string: str, size: float, x: float, y: float) -> Shape[Text]:
    return Text(string, size).at(Transform((x, y), scale=(-1.0, 1.0)))


def connect_ports(name: str, *ports: Port) -> Net:
    net = Net(name=name)
    for port in ports:
        net = net + port
    return net


class SdGlasgowBreakoutSubstrate(Substrate):
    stackup = jlcpcb_stackup(2)
    constraints = jlcpcb_fab_constraints(2)

    class StandardVia(Via):
        start_layer = 0
        stop_layer = 1
        diameter = 0.7
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class SdGlasgowBreakoutCircuit(Circuit):
    gnd = Port()
    sd_vdd = Port()

    def __init__(self):
        super().__init__()
        self.card = FullSizeSdCardEdge()
        self.glasgow = GlasgowPortConnector(
            swap_rows_for_mating=GLASGOW_SWAP_ROWS_FOR_MATING
        )

        self.ground_vias = [
            SdGlasgowBreakoutSubstrate.StandardVia().at(position) for position in SD_GROUND_VIA_CENTERS
        ]
        ground_net = connect_ports(
            "GND",
            self.gnd,
            self.card.VSS1,
            self.card.VSS2,
            *self.glasgow.GND,
        )
        for via in self.ground_vias:
            ground_net = ground_net + via
        ground_net = (
            ground_net
            + trace(POWER_TRACE_WIDTH, [SD_CARD_PAD_CENTERS["VSS1"], SD_GROUND_VIA_CENTERS[0]], layer=1)
            + trace(POWER_TRACE_WIDTH, [SD_CARD_PAD_CENTERS["VSS2"], SD_GROUND_VIA_CENTERS[1]], layer=1)
            + Pour(TOP_GROUND_POUR_AREA, layer=0, isolate=0.2, orphans=False)
            + Pour(BOTTOM_GROUND_POUR_AREA, layer=1, isolate=0.2, orphans=False)
        )

        vdd_net = (
            connect_ports("SD_VDD_SENSE", self.sd_vdd, self.card.VDD, self.glasgow.SENSE)
            + trace(POWER_TRACE_WIDTH, SENSE_ROUTE_POINTS, layer=SENSE_ROUTE_LAYER)
        )

        signal_ports = {
            "DAT3": self.card.DAT3,
            "CMD": self.card.CMD,
            "CLK": self.card.CLK,
            "DAT0": self.card.DAT0,
            "DAT1": self.card.DAT1,
            "DAT2": self.card.DAT2,
        }
        signal_nets: list[Net] = []
        for name, io_index in SD_TO_GLASGOW_IO.items():
            signal_nets.append(
                connect_ports(f"SD_{name}", signal_ports[name], self.glasgow.IO[io_index])
                + trace(SIGNAL_TRACE_WIDTH, AUTOROUTED_SIGNAL_PATHS[name], layer=1)
            )

        self.nets = [ground_net, vdd_net, *signal_nets]

        self.place(self.card, Placement(SD_EDGE_ORIGIN, SD_EDGE_ROTATION, on=Side.Bottom))
        self.place(self.glasgow, Placement(GLASGOW_ORIGIN, GLASGOW_ROTATION, on=GLASGOW_SIDE))

        self += Silkscreen(
            Text("Full-size SD -> Glasgow", 1.2).at(17.0, 20.5),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            Text("SENSE = SD 3V3; VIO isolated", 1.0).at(17.0, 17.5),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            Text("A0/1/2: DAT1 DAT0 CLK", 1.0).at(17.0, 13.5),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            Text("A5/6/7: CMD DAT3 DAT2", 1.0).at(17.0, 11.5),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            Text(f"(c) mblsha {BOARD_DATE}", 1.0).at(17.0, 9.0),
            side=FeatureSide.Top,
        )
        for _pins, label, x, y in GLASGOW_ROW_LABELS:
            self += Silkscreen(
                Text(label, GLASGOW_PIN_LABEL_SIZE, Anchor.E).at(x, y),
                side=FeatureSide.Top,
            )
        for _pin, label, y in SD_CONTACT_LABELS:
            self += Silkscreen(
                bottom_text(label, SD_CONTACT_LABEL_SIZE, SD_CONTACT_LABEL_X, y),
                side=FeatureSide.Bottom,
            )


class SdGlasgowBreakoutBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class SdGlasgowBreakoutDesign(Design):
    substrate = SdGlasgowBreakoutSubstrate()
    board = SdGlasgowBreakoutBoard()
    circuit = SdGlasgowBreakoutCircuit()

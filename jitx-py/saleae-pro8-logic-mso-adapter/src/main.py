from __future__ import annotations

import subprocess
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
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Polyline, Text
from jitx.substrate import Substrate
from jitx.transform import Transform
from jitx.via import Via, ViaType
from shared_components.fabrication import jlcpcb_fab_constraints, jlcpcb_stackup
from shared_components.saleae import (
    SALEAE8_HEADER_CENTER_SPACING,
    LogicMsoDigitalHeader2x5,
    Saleae8,
    SaleaeMaleHeader2x4,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_WIDTH = 47.0
BOARD_HEIGHT = 22.0
BOARD_SHAPE = rectangle(BOARD_WIDTH, BOARD_HEIGHT, radius=1.5)
SIGNAL_AREA = rectangle(BOARD_WIDTH - 1.0, BOARD_HEIGHT - 1.0, radius=1.0)
BANK_CENTER_SPACING = SALEAE8_HEADER_CENTER_SPACING
PRO8_ASSEMBLY_CENTER = (0.0, 3.3)
PRO8_ROTATION = 270.0
PRO8_HEADER_COMPONENT = Saleae8
PRO8_HEADER_CENTERS = (
    (-BANK_CENTER_SPACING / 2.0, PRO8_ASSEMBLY_CENTER[1]),
    (BANK_CENTER_SPACING / 2.0, PRO8_ASSEMBLY_CENTER[1]),
)
LOGIC_MSO_CENTER_SPACING = 22.0
LOGIC_MSO_BANK_Y = -4.5
CHANNEL_GROUPS = ((0, 1, 2, 3), (4, 5, 6, 7))
SIGNAL_TRACE_WIDTH = 0.10
SIGNAL_ROUTE_LAYER = 1
GROUND_TRACE_WIDTH = 0.5
GROUND_ROUTE_LAYER = 0
GROUND_POUR_LAYERS = (0, 1)
GROUND_POUR_CLEARANCE = 0.2
GROUND_STITCH_VIA_CENTERS = (
    *((x, 9.5) for x in (-20.0, -16.0, -12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0, 16.0, 20.0)),
    *((x, -9.8) for x in (-20.0, -16.0, -12.0, 12.0, 16.0, 20.0)),
    *((22.0, y) for y in (-8.0, -5.0, -2.0, 1.0, 4.0, 7.0)),
    *((-22.0, y) for y in (-8.0, 7.0)),
    (0.0, -4.5),
)
PRO8_PIN_LABEL_SIZE = 0.8
LOGIC_MSO_PIN_LABEL_SIZE = 1.0
MIN_SILKSCREEN_TEXT_HEIGHT = 0.8

PRO8_PIN_LABELS = (
    ("0", -10.541, 3.3),
    ("1", -8.001, 3.3),
    ("2", -5.461, 3.3),
    ("3", -2.921, 3.3),
    ("4", 2.4, 3.3),
    ("5", 5.461, 3.3),
    ("6", 8.001, 3.3),
    ("7", 10.541, 3.3),
    *(("G", x, 6.6) for x in (-10.541, -8.001, -5.461, -2.921, 2.921, 5.461, 8.001, 10.541)),
)
LOGIC_MSO_PIN_LABELS = (
    ("G", -16.08, -1.7),
    ("G", -13.54, -1.7),
    ("G", -11.0, -1.7),
    ("G", -8.46, -1.7),
    ("·", -5.92, -1.7),
    ("0", -16.08, -7.3),
    ("1", -13.54, -7.3),
    ("2", -11.0, -7.3),
    ("3", -8.46, -7.3),
    ("·", -5.92, -7.3),
    ("G", 5.92, -1.7),
    ("G", 8.46, -1.7),
    ("G", 11.0, -1.7),
    ("G", 13.54, -1.7),
    ("·", 16.08, -1.7),
    ("4", 5.92, -7.3),
    ("5", 8.46, -7.3),
    ("6", 11.0, -7.3),
    ("7", 13.54, -7.3),
    ("·", 16.08, -7.3),
)
PIN_LABELS = PRO8_PIN_LABELS + LOGIC_MSO_PIN_LABELS

# Bottom-layer route definitions after rotating the rigid Saleae8 assembly as
# a whole. Each channel bank is a parallel direct fan to the outer MSO row.
AUTOROUTED_SIGNAL_PATHS = {
    0: [(-10.541, 2.03), (-16.08, -5.77)],
    1: [(-8.001, 2.03), (-13.54, -5.77)],
    2: [(-5.461, 2.03), (-11.0, -5.77)],
    3: [(-2.921, 2.03), (-8.46, -5.77)],
    4: [(2.921, 2.03), (5.92, -5.77)],
    5: [(5.461, 2.03), (8.46, -5.77)],
    6: [(8.001, 2.03), (11.0, -5.77)],
    7: [(10.541, 2.03), (13.54, -5.77)],
}

GROUND_ROUTE_PATHS = (
    [
        (-8.46, -3.23),
        (-16.08, -3.23),
        (-18.0, -3.23),
        (-18.0, 4.57),
        (-10.541, 4.57),
        (10.541, 4.57),
    ],
    [
        (13.54, -3.23),
        (5.92, -3.23),
        (0.0, -3.23),
        (0.0, 4.57),
    ],
)


def signal_trace(points: list[tuple[float, float]]) -> Copper:
    return Copper(Polyline(SIGNAL_TRACE_WIDTH, points), layer=SIGNAL_ROUTE_LAYER)


def ground_trace(points: list[tuple[float, float]]) -> Copper:
    return Copper(Polyline(GROUND_TRACE_WIDTH, points), layer=GROUND_ROUTE_LAYER)


def bottom_text(
    string: str,
    size: float,
    x: float,
    y: float,
    *,
    rotate: float = 0.0,
) -> Shape[Text]:
    return Text(string, size).at(Transform((x, y), rotate=rotate, scale=(-1.0, 1.0)))


class SaleaePro8LogicMsoAdapterSubstrate(Substrate):
    stackup = jlcpcb_stackup(2)
    constraints = jlcpcb_fab_constraints(2)
    constraints.min_silkscreen_text_height = MIN_SILKSCREEN_TEXT_HEIGHT

    class StandardVia(Via):
        start_layer = 0
        stop_layer = 1
        diameter = 0.7
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class LogicMsoHeaderBank(Circuit):
    gnd = Port()
    data = [Port() for _ in range(8)]

    def __init__(self):
        super().__init__()
        self.lower = LogicMsoDigitalHeader2x5()
        self.upper = LogicMsoDigitalHeader2x5()

        self.nets = [
            Net(name="GND") + self.gnd + self.lower.GND + self.upper.GND,
            *[
                Net(name=f"CH{channel}") + self.data[channel] + self.lower.data[channel]
                for channel in CHANNEL_GROUPS[0]
            ],
            *[
                Net(name=f"CH{channel}") + self.data[channel] + self.upper.data[channel - 4]
                for channel in CHANNEL_GROUPS[1]
            ],
        ]

        self.place(
            self.lower,
            Placement((-LOGIC_MSO_CENTER_SPACING / 2.0, 0.0), on=Side.Top),
        )
        self.place(
            self.upper,
            Placement((LOGIC_MSO_CENTER_SPACING / 2.0, 0.0), on=Side.Top),
        )


class SaleaePro8LogicMsoAdapterCircuit(Circuit):
    gnd = Port()

    def __init__(self):
        super().__init__()
        self.pro8 = PRO8_HEADER_COMPONENT(
            header_factory=SaleaeMaleHeader2x4,
            show_labels=False,
        )
        self.logic_mso = LogicMsoHeaderBank()
        self.ground_stitch_vias = [
            SaleaePro8LogicMsoAdapterSubstrate.StandardVia().at(position) for position in GROUND_STITCH_VIA_CENTERS
        ]

        ground_net = Net(name="GND") + self.gnd + self.pro8.gnd + self.logic_mso.gnd
        for via in self.ground_stitch_vias:
            ground_net = ground_net + via
        for layer in GROUND_POUR_LAYERS:
            ground_net = ground_net + Pour(
                SIGNAL_AREA,
                layer=layer,
                isolate=GROUND_POUR_CLEARANCE,
                orphans=False,
            )
        for path in GROUND_ROUTE_PATHS:
            ground_net = ground_net + ground_trace(path)
        signal_nets = []
        for channel in range(8):
            signal_net = Net(name=f"CH{channel}") + self.pro8.data[channel] + self.logic_mso.data[channel]
            if channel in AUTOROUTED_SIGNAL_PATHS:
                signal_net = signal_net + signal_trace(AUTOROUTED_SIGNAL_PATHS[channel])
            signal_nets.append(signal_net)
        self.nets = [ground_net, *signal_nets]

        self.place(
            self.pro8,
            Placement(PRO8_ASSEMBLY_CENTER, PRO8_ROTATION, on=Side.Top),  # ty: ignore[no-matching-overload]
        )
        self.place(self.logic_mso, Placement((0.0, LOGIC_MSO_BANK_Y), on=Side.Top))

        self += Silkscreen(Text("PRO 8  →  LOGIC MSO", 1.0).at(0.0, -10.2), side=FeatureSide.Top)
        self += Silkscreen(
            bottom_text("PRO 8  →  LOGIC MSO", 1.0, 0.0, -10.2),
            side=FeatureSide.Bottom,
        )
        for label, x, y in PRO8_PIN_LABELS:
            self += Silkscreen(Text(label, PRO8_PIN_LABEL_SIZE).at(x, y), side=FeatureSide.Top)
            self += Silkscreen(
                bottom_text(label, PRO8_PIN_LABEL_SIZE, x, y),
                side=FeatureSide.Bottom,
            )
        for label, x, y in LOGIC_MSO_PIN_LABELS:
            self += Silkscreen(Text(label, LOGIC_MSO_PIN_LABEL_SIZE).at(x, y), side=FeatureSide.Top)
            self += Silkscreen(
                bottom_text(label, LOGIC_MSO_PIN_LABEL_SIZE, x, y),
                side=FeatureSide.Bottom,
            )
        self += Silkscreen(
            bottom_text(BOARD_DATE, 1.0, -22.7, 0.0, rotate=90.0),
            side=FeatureSide.Bottom,
        )


class SaleaePro8LogicMsoAdapterBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA
    label = Silkscreen(
        Text(BOARD_DATE, 1.0).at(-22.7, 0.0, rotate=90.0),
        side=FeatureSide.Top,
    )


class SaleaePro8LogicMsoAdapterDesign(Design):
    substrate = SaleaePro8LogicMsoAdapterSubstrate()
    board = SaleaePro8LogicMsoAdapterBoard()
    circuit = SaleaePro8LogicMsoAdapterCircuit()

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
from jitx.shapes.primitive import Arc, ArcPolygon, Circle, Polyline, Text
from jitx.substrate import Substrate
from jitx.transform import Transform
from jitx.via import Via, ViaType
from shared_components.connectivity import connect_ports
from shared_components.fabrication import jlcpcb_fab_constraints, jlcpcb_stackup
from shared_components.ffc import HDGC60PinFfc
from shared_components.full_size_sd import (
    SD_CARD_FRONT_X,
    SD_CARD_PAD_CENTERS,
    SD_CARD_PIN_NUMBER_BY_PORT,
    SD_CARD_PINOUT,
    SD_CARD_SHOULDER_X,
    SD_EDGE_ORIGIN,
    SD_EDGE_ROTATION,
    FullSizeSdCardEdge,
    full_size_sd_card_outline,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

# The inserted plug geometry through x=34.29 mm is taken directly from the
# SparkFun SD Sniffer board. Only the non-inserted tail is widened for the FFC.
CARD_FRONT_X = SD_CARD_FRONT_X
CARD_SHOULDER_X = SD_CARD_SHOULDER_X
TAIL_START_X = 39.0
REFERENCE_FFC_TAIL_DEPTH = 27.0
FFC_TAIL_DEPTH = REFERENCE_FFC_TAIL_DEPTH / 3.0
BOARD_REAR_X = TAIL_START_X + FFC_TAIL_DEPTH
BOARD_CENTER_Y = 16.129
BOARD_TOP_Y = 36.129
BOARD_BOTTOM_Y = -3.871
BOARD_REAR_CORNER_RADIUS = 3.0
BOARD_REAR_CORNER_X = BOARD_REAR_X - BOARD_REAR_CORNER_RADIUS
BOARD_REAR_TOP_CORNER_Y = BOARD_TOP_Y - BOARD_REAR_CORNER_RADIUS
BOARD_REAR_BOTTOM_CORNER_Y = BOARD_BOTTOM_Y + BOARD_REAR_CORNER_RADIUS

BOARD_OUTLINE = full_size_sd_card_outline(
    [
        (TAIL_START_X, BOARD_TOP_Y),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_TOP_CORNER_Y), BOARD_REAR_CORNER_RADIUS, 90.0, -90.0),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_BOTTOM_CORNER_Y), BOARD_REAR_CORNER_RADIUS, 0.0, -90.0),
        (TAIL_START_X, BOARD_BOTTOM_Y),
    ]
)

BOARD_SHAPE = ArcPolygon(BOARD_OUTLINE)
POUR_EDGE_CLEARANCE = 0.5
POUR_REAR_CORNER_RADIUS = BOARD_REAR_CORNER_RADIUS - POUR_EDGE_CLEARANCE
SIGNAL_AREA = ArcPolygon(
    [
        (0.5, 4.31),
        (0.5, 23.92),
        (4.02, 27.44),
        (33.79, 27.44),
        (33.79, 29.0),
        (39.3, 35.629),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_TOP_CORNER_Y), POUR_REAR_CORNER_RADIUS, 90.0, -90.0),
        Arc((BOARD_REAR_CORNER_X, BOARD_REAR_BOTTOM_CORNER_Y), POUR_REAR_CORNER_RADIUS, 0.0, -90.0),
        (39.3, -3.371),
        (33.79, 2.75),
        (33.79, 4.31),
    ]
)
TOP_GROUND_POUR_AREA = SIGNAL_AREA
BOTTOM_GROUND_POUR_AREA = SIGNAL_AREA

FFC_ORIGIN = (BOARD_REAR_X - 4.0, BOARD_CENTER_Y)
FFC_ROTATION = 270.0
FFC_SIDE = Side.Bottom

SD_VDD_FFC_PIN = 1
SD_TO_FFC_PIN = {
    "DAT2": 4,
    "DAT3": 14,
    "CMD": 24,
    "CLK": 36,
    "DAT0": 46,
    "DAT1": 56,
}
FFC_SIGNAL_PINS = frozenset(SD_TO_FFC_PIN.values())
FFC_GROUND_PINS = tuple(
    pin for pin in range(1, 61) if pin != SD_VDD_FFC_PIN and pin not in FFC_SIGNAL_PINS
)

CARD_PAD_CENTERS = SD_CARD_PAD_CENTERS

SD_CONTACT_LABEL_X = 15.0
SD_CONTACT_LABEL_SIZE = 1.0
SD_CONTACT_LABELS = tuple(
    (number, SD_CARD_PINOUT[number].label, CARD_PAD_CENTERS[port_name][1])
    for port_name, number in sorted(SD_CARD_PIN_NUMBER_BY_PORT.items(), key=lambda item: item[1])
)

SD_GROUND_VIA_X = 8.0
SD_GROUND_VIA_CENTERS = (
    (SD_GROUND_VIA_X, CARD_PAD_CENTERS["VSS1"][1]),
    (SD_GROUND_VIA_X, CARD_PAD_CENTERS["VSS2"][1]),
)

VDD_VIA_CENTERS = (
    (35.0, CARD_PAD_CENTERS["VDD"][1]),
    (TAIL_START_X - 0.5, 30.879),
)
VDD_ESCAPE_Y = 1.0

GROUND_BUS_X = BOARD_REAR_X - 1.0
FFC_MOUNT_PAD_CENTERS = ((FFC_ORIGIN[0] + 0.527, -0.301), (FFC_ORIGIN[0] + 0.527, 32.559))
FFC_GROUND_VIA_XS = (FFC_ORIGIN[0] + 1.0, FFC_ORIGIN[0] + 2.0)
FFC_MOUNT_GROUND_VIA_CENTERS = ((GROUND_BUS_X, -0.301), (GROUND_BUS_X, 32.559))
FFC_FANOUT_X = FFC_ORIGIN[0] - 4.0

SIGNAL_TRACE_WIDTH = 0.2
POWER_TRACE_WIDTH = 0.3


def ffc_pad_center(pin: int) -> tuple[float, float]:
    pad_index = pin - 1
    return (FFC_ORIGIN[0] - 2.096, FFC_ORIGIN[1] + 14.75 - 0.5 * pad_index)


FFC_GROUND_VIA_CENTERS = tuple(
    (FFC_GROUND_VIA_XS[index % len(FFC_GROUND_VIA_XS)], ffc_pad_center(pin)[1])
    for index, pin in enumerate(FFC_GROUND_PINS)
)
GROUND_VIA_CENTERS = SD_GROUND_VIA_CENTERS + FFC_GROUND_VIA_CENTERS + FFC_MOUNT_GROUND_VIA_CENTERS


def trace(width: float, points: list[tuple[float, float]], *, layer: int) -> Copper:
    return Copper(Polyline(width, points), layer=layer)


def bottom_text(string: str, size: float, x: float, y: float) -> Shape[Text]:
    return Text(string, size).at(Transform((x, y), scale=(-1.0, 1.0)))



class FullSizeSdFfcBreakoutSubstrate(Substrate):
    stackup = jlcpcb_stackup(2)
    constraints = jlcpcb_fab_constraints(2)

    class StandardVia(Via):
        start_layer = 0
        stop_layer = 1
        diameter = 0.7
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class FullSizeSdFfcBreakoutCircuit(Circuit):
    gnd = Port()
    sd_vdd = Port()

    def __init__(self):
        super().__init__()
        self.card = FullSizeSdCardEdge()
        self.ffc = HDGC60PinFfc()

        self.vdd_vias = [
            FullSizeSdFfcBreakoutSubstrate.StandardVia().at(position) for position in VDD_VIA_CENTERS
        ]
        self.ground_vias = [
            FullSizeSdFfcBreakoutSubstrate.StandardVia().at(position)
            for position in GROUND_VIA_CENTERS
        ]

        ground_ports = [self.ffc.p[pin - 1] for pin in FFC_GROUND_PINS]
        ground_net = connect_ports(
            "GND",
            self.gnd,
            self.card.VSS1,
            self.card.VSS2,
            *ground_ports,
            self.ffc.p[60],
            self.ffc.p[61],
        )
        for via in self.ground_vias:
            ground_net = ground_net + via
        ground_bus = trace(
            POWER_TRACE_WIDTH,
            [(GROUND_BUS_X, FFC_MOUNT_PAD_CENTERS[0][1]), (GROUND_BUS_X, FFC_MOUNT_PAD_CENTERS[1][1])],
            layer=1,
        )
        for pin in FFC_GROUND_PINS:
            pad_center = ffc_pad_center(pin)
            ground_bus += trace(
                POWER_TRACE_WIDTH,
                [(GROUND_BUS_X, pad_center[1]), pad_center],
                layer=1,
            )
        for pad_center in FFC_MOUNT_PAD_CENTERS:
            ground_bus += trace(
                POWER_TRACE_WIDTH,
                [(GROUND_BUS_X, pad_center[1]), pad_center],
                layer=1,
            )
        ground_net = (
            ground_net
            + ground_bus
            + trace(POWER_TRACE_WIDTH, [CARD_PAD_CENTERS["VSS1"], SD_GROUND_VIA_CENTERS[0]], layer=1)
            + trace(POWER_TRACE_WIDTH, [CARD_PAD_CENTERS["VSS2"], SD_GROUND_VIA_CENTERS[1]], layer=1)
            + Pour(TOP_GROUND_POUR_AREA, layer=0, isolate=0.2, orphans=False)
            + Pour(BOTTOM_GROUND_POUR_AREA, layer=1, isolate=0.2, orphans=False)
        )

        vdd_net = (
            connect_ports("SD_VDD", self.sd_vdd, self.card.VDD, self.ffc.p[SD_VDD_FFC_PIN - 1])
            + self.vdd_vias[0]
            + self.vdd_vias[1]
            + trace(
                POWER_TRACE_WIDTH,
                [
                    CARD_PAD_CENTERS["VDD"],
                    VDD_VIA_CENTERS[0],
                ],
                layer=1,
            )
            + trace(
                POWER_TRACE_WIDTH,
                [VDD_VIA_CENTERS[0], (TAIL_START_X - 0.5, VDD_ESCAPE_Y), VDD_VIA_CENTERS[1]],
                layer=0,
            )
            + trace(POWER_TRACE_WIDTH, [VDD_VIA_CENTERS[1], ffc_pad_center(SD_VDD_FFC_PIN)], layer=1)
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
        for name in ("DAT2", "DAT3", "CMD", "CLK", "DAT0", "DAT1"):
            ffc_pin = SD_TO_FFC_PIN[name]
            ffc_center = ffc_pad_center(ffc_pin)
            signal_nets.append(
                connect_ports(f"SD_{name}", signal_ports[name], self.ffc.p[ffc_pin - 1])
                + trace(
                    SIGNAL_TRACE_WIDTH,
                    [
                        CARD_PAD_CENTERS[name],
                        (35.5, CARD_PAD_CENTERS[name][1]),
                        (FFC_FANOUT_X, ffc_center[1]),
                        ffc_center,
                    ],
                    layer=1,
                )
            )

        self.nets = [ground_net, vdd_net, *signal_nets]

        # This reproduces SparkFun's bottom-side MR270 card-finger transform.
        self.place(self.card, Placement(SD_EDGE_ORIGIN, SD_EDGE_ROTATION, on=Side.Bottom))
        self.place(self.ffc, Placement(FFC_ORIGIN, FFC_ROTATION, on=FFC_SIDE))

        self += Silkscreen(
            Text("Full-size SD -> RetroBus 60P FFC", 1.2).at(17.0, 20.0),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            Text("SD 3V3 -> FFC VCC5V", 1.2).at(17.0, 16.0),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            Text(f"(c) mblsha {BOARD_DATE}", 1.0).at(17.0, 12.0),
            side=FeatureSide.Top,
        )
        # Pin 1 is at the high-Y end after the bottom-side 270-degree placement.
        self += Silkscreen(Circle(diameter=1.0).at(FFC_ORIGIN[0] - 4.5, 32.8), side=FeatureSide.Bottom)
        for _pin, label, y in SD_CONTACT_LABELS:
            self += Silkscreen(
                bottom_text(label, SD_CONTACT_LABEL_SIZE, SD_CONTACT_LABEL_X, y),
                side=FeatureSide.Bottom,
            )


class FullSizeSdFfcBreakoutBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class FullSizeSdFfcBreakoutDesign(Design):
    substrate = FullSizeSdFfcBreakoutSubstrate()
    board = FullSizeSdFfcBreakoutBoard()
    circuit = FullSizeSdFfcBreakoutCircuit()

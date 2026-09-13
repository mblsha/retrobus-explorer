from __future__ import annotations

import subprocess
from datetime import date
from math import sqrt
from pathlib import Path

from jitx.board import Board
from jitx.circuit import Circuit
from jitx.copper import Pour
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.net import Net, Port
from jitx.placement import Placement, Side
from jitx.shapes import Shape
from jitx.shapes.primitive import Anchor, Arc, ArcPolygon, Text
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
from shared_components.pmod import (
    PMOD_PAD_CENTERS,
    PMOD_PAD_DIAMETER,
    PMOD_PIN_NAMES,
    PMOD_ROW_SPACING,
    PmodHeader2x6,
)


def last_commit_date() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        return subprocess.check_output(
            ["git", "log", "-1", "--format=%cs"],
            text=True,
            cwd=repo_root,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return date.today().isoformat()


BOARD_DATE = last_commit_date()

TAIL_START_X = 37.0
PMOD_ORIGIN_X = 43.0
PMOD_OUTBOARD_PAD_CENTER_X = PMOD_ORIGIN_X + PMOD_ROW_SPACING / 2.0
PMOD_EDGE_COPPER_CLEARANCE = 0.6
BOARD_REAR_X = PMOD_OUTBOARD_PAD_CENTER_X + PMOD_PAD_DIAMETER / 2.0 + PMOD_EDGE_COPPER_CLEARANCE
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

PMOD_ORIGIN = (PMOD_ORIGIN_X, SD_CARD_CENTER_Y)
PMOD_ROTATION = 0.0
PMOD_SIDE = Side.Bottom
PMOD_UNUSED_PINS = (3, 4)
PMOD_CONNECTED_GROUND_PINS: tuple[int, ...] = ()
PMOD_CONNECTED_VCC_PINS: tuple[int, ...] = ()

# Rank 1 from jitx-tooling's exhaustive six-of-eight fungible PMOD data-pin
# optimizer. The supplied straight-segment model evaluated all 20,160 complete
# assignments and selected a zero-crossing, zero-via, zero-bend hypothesis.
PMOD_MAPPING_SHA256 = "28d19e5d15e0e4139128fb9cacba5f93e987345144f5b500e82ef2622f33248c"
SD_TO_PMOD_PIN = {
    "DAT3": 7,
    "CMD": 2,
    "CLK": 8,
    "DAT0": 9,
    "DAT1": 10,
    "DAT2": 1,
}
PMOD_PIN_TO_SD_SIGNAL = {pin: signal for signal, pin in SD_TO_PMOD_PIN.items()}

PMOD_PIN_LABEL_SIZE = 0.72
PMOD_SD_LABEL_SIZE = 0.62
PMOD_PIN_LABEL_OFFSET_Y = 0.38
PMOD_SD_LABEL_OFFSET_Y = -0.45
PMOD_OUTBOARD_ROW_LABEL_X = 33.5
PMOD_INBOARD_ROW_LABEL_X = 38.5

SD_CONTACT_LABEL_X = 15.0
SD_CONTACT_LABEL_SIZE = 1.0
SD_CONTACT_LABELS = tuple(
    (number, SD_CARD_PINOUT[number].label, SD_CARD_PAD_CENTERS[port_name][1])
    for port_name, number in sorted(SD_CARD_PIN_NUMBER_BY_PORT.items(), key=lambda item: item[1])
)


def pmod_pad_center(pin: int) -> tuple[float, float]:
    x, y = PMOD_PAD_CENTERS[pin]
    # A bottom-side, zero-degree placement mirrors the landpattern's local X.
    return (PMOD_ORIGIN[0] - x, PMOD_ORIGIN[1] + y)


def pmod_pin_labels(pin: int) -> tuple[str, ...]:
    labels = [f"{pin} {PMOD_PIN_NAMES[pin]}"]
    if sd_signal := PMOD_PIN_TO_SD_SIGNAL.get(pin):
        labels.append(f"SD {sd_signal}")
    return tuple(labels)


def pmod_pin_label_x(pin: int) -> float:
    # A right-angle header must mate beyond the outboard row, so both label
    # columns live on the inboard side of the connector body.
    return PMOD_OUTBOARD_ROW_LABEL_X if pin <= 6 else PMOD_INBOARD_ROW_LABEL_X


def bottom_text(string: str, size: float, x: float, y: float, anchor: Anchor = Anchor.C) -> Shape[Text]:
    return Text(string, size, anchor).at(Transform((x, y), scale=(-1.0, 1.0)))


def connect_ports(name: str, *ports: Port) -> Net:
    net = Net(name=name)
    for port in ports:
        net = net + port
    return net


class SdPmodBreakoutSubstrate(Substrate):
    stackup = jlcpcb_stackup(2)
    constraints = jlcpcb_fab_constraints(2)

    class StandardVia(Via):
        start_layer = 0
        stop_layer = 1
        diameter = 0.7
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class SdPmodBreakoutCircuit(Circuit):
    gnd = Port()

    def __init__(self):
        super().__init__()
        self.card = FullSizeSdCardEdge()
        self.pmod = PmodHeader2x6()

        ground_net = connect_ports(
            "GND",
            self.gnd,
            self.card.VSS1,
            self.card.VSS2,
            *(self.pmod.pin(pin) for pin in PMOD_CONNECTED_GROUND_PINS),
        )
        ground_net = (
            ground_net
            + Pour(SIGNAL_AREA, layer=0, isolate=0.2, orphans=False)
            + Pour(SIGNAL_AREA, layer=1, isolate=0.2, orphans=False)
        )

        card_signal_ports = {
            "DAT3": self.card.DAT3,
            "CMD": self.card.CMD,
            "CLK": self.card.CLK,
            "DAT0": self.card.DAT0,
            "DAT1": self.card.DAT1,
            "DAT2": self.card.DAT2,
        }
        signal_nets = [
            connect_ports(f"SD_{name}", card_signal_ports[name], self.pmod.pin(pin))
            for name, pin in SD_TO_PMOD_PIN.items()
        ]
        self.nets = [ground_net, *signal_nets]

        self.place(self.card, Placement(SD_EDGE_ORIGIN, SD_EDGE_ROTATION, on=Side.Bottom))  # ty: ignore[no-matching-overload]
        self.place(self.pmod, Placement(PMOD_ORIGIN, PMOD_ROTATION, on=PMOD_SIDE))  # ty: ignore[no-matching-overload]

        self += Silkscreen(Text("SD <-> PMOD GPIO", 1.2).at(17.0, 20.5), side=FeatureSide.Top)
        self += Silkscreen(Text("PMOD 5/6/11/12 NC", 1.0).at(17.0, 17.8), side=FeatureSide.Top)
        self += Silkscreen(Text("IO1 DAT2  IO2 CMD  IO5 DAT3", 0.9).at(17.0, 14.8), side=FeatureSide.Top)
        self += Silkscreen(Text("IO6 CLK  IO7 DAT0  IO8 DAT1", 0.9).at(17.0, 12.3), side=FeatureSide.Top)
        self += Silkscreen(Text(f"(c) mblsha {BOARD_DATE}", 1.0).at(17.0, 9.0), side=FeatureSide.Top)

        for pin in range(1, 13):
            _x, y = pmod_pad_center(pin)
            labels = pmod_pin_labels(pin)
            label_x = pmod_pin_label_x(pin)
            pmod_label_y = y + PMOD_PIN_LABEL_OFFSET_Y if len(labels) == 2 else y
            self += Silkscreen(
                Text(labels[0], PMOD_PIN_LABEL_SIZE, Anchor.C).at(label_x, pmod_label_y),
                side=FeatureSide.Top,
            )
            self += Silkscreen(
                bottom_text(labels[0], PMOD_PIN_LABEL_SIZE, label_x, pmod_label_y),
                side=FeatureSide.Bottom,
            )
            if len(labels) == 2:
                self += Silkscreen(
                    Text(labels[1], PMOD_SD_LABEL_SIZE, Anchor.C).at(
                        label_x,
                        y + PMOD_SD_LABEL_OFFSET_Y,
                    ),
                    side=FeatureSide.Top,
                )
                self += Silkscreen(
                    bottom_text(
                        labels[1],
                        PMOD_SD_LABEL_SIZE,
                        label_x,
                        y + PMOD_SD_LABEL_OFFSET_Y,
                    ),
                    side=FeatureSide.Bottom,
                )
        self += Silkscreen(bottom_text("PMOD 5/6/11/12 + SD VDD: NC", 0.9, 18.0, 2.2), side=FeatureSide.Bottom)
        for _pin, label, y in SD_CONTACT_LABELS:
            self += Silkscreen(
                bottom_text(label, SD_CONTACT_LABEL_SIZE, SD_CONTACT_LABEL_X, y),
                side=FeatureSide.Bottom,
            )


class SdPmodBreakoutBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class SdPmodBreakoutDesign(Design):
    substrate = SdPmodBreakoutSubstrate()
    board = SdPmodBreakoutBoard()
    circuit = SdPmodBreakoutCircuit()
